from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db import get_db
from app.models import Product
from app.models.models import Inventory, Location
from sqlmodel import SQLModel


# Request body schema: no product_id, created_at, updated_at (set server-side)
class ProductCreate(SQLModel):
    sku: str
    name: str
    description: Optional[str] = None
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal
    weight_kg: Decimal
    is_fragile: bool = False
    is_liquid: bool = False
    requires_upright: bool = False
    max_stack_layers: int = 10
    pick_frequency: int = 0
    popularity_score: Decimal = Decimal("0")
    initial_quantity: int = 0  # New field for initial inventory quantity
    location_code: Optional[str] = None  # Optional location code for inventory


# Full update body: same as create (no product_id, created_at, updated_at)
ProductUpdate = ProductCreate


def _naive_utc_now() -> datetime:
    """Naive UTC datetime for TIMESTAMP columns (asyncpg compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


router = APIRouter(prefix="/products", tags=["products"])


@router.get(
    "",
    response_model=List[Product],
    summary="List products",
)
@router.get(
    "/",
    response_model=List[Product],
    summary="List products",
)
async def list_products(
    *,
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = Query(
        default=None,
        description="Filter by SKU (exact match) or name (case-insensitive contains).",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    sort_by_pick_frequency: bool = Query(
        False,
        description="If true, order by pick_frequency descending.",
    ),
) -> List[Product]:
    """
    List products with optional filtering and basic pagination.
    """
    stmt = select(Product)

    if search:
        # Simple search: match SKU exactly or name case-insensitive contains
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            (Product.sku == search) | (Product.name.ilike(pattern))
        )

    if sort_by_pick_frequency:
        stmt = stmt.order_by(Product.pick_frequency.desc())
    else:
        stmt = stmt.order_by(Product.product_id)

    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get(
    "/{product_id}",
    response_model=Product,
    summary="Get a single product by ID",
)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
) -> Product:
    stmt = select(Product).where(Product.product_id == product_id)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product


@router.post(
    "",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product",
)
@router.post(
    "/",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product",
)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
) -> Product:
    now = _naive_utc_now()

    # Extract inventory-related fields before building product
    initial_quantity = payload.initial_quantity
    location_code = payload.location_code

    # Validate location BEFORE touching the DB when inventory is requested
    location = None
    if initial_quantity > 0:
        if location_code:
            location_result = await db.execute(
                select(Location).where(Location.location_code == location_code)
            )
            location = location_result.scalar_one_or_none()
            if not location:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Location '{location_code}' not found. Generate the warehouse map first.",
                )
            if not location.shelf_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Location '{location_code}' is not linked to a shelf. Generate the warehouse map first.",
                )
        else:
            location_result = await db.execute(
                select(Location).where(Location.shelf_id.isnot(None)).limit(1)
            )
            location = location_result.scalar_one_or_none()
            if not location:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No shelf-based locations found. Generate the warehouse map first.",
                )

    # Build product object (do not commit yet)
    product_data = payload.model_dump(exclude={"initial_quantity", "location_code"})
    product = Product(**product_data, created_at=now, updated_at=now)
    db.add(product)

    # Flush to get product_id without committing (lets us catch duplicate SKU cleanly)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A product with SKU '{payload.sku}' already exists.",
        )

    # Add inventory record in the same transaction
    if initial_quantity > 0 and location is not None:
        inventory = Inventory(
            product_id=product.product_id,
            location_id=location.location_id,
            quantity=initial_quantity,
        )
        db.add(inventory)

    # Single commit for product + inventory together
    try:
        await db.commit()
        await db.refresh(product)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A product with SKU '{payload.sku}' already exists.",
        )

    return product


@router.put(
    "/{product_id}",
    response_model=Product,
    summary="Fully update a product",
)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
) -> Product:
    stmt = select(Product).where(Product.product_id == product_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    for field in [
        "sku",
        "name",
        "description",
        "length_cm",
        "width_cm",
        "height_cm",
        "weight_kg",
        "is_fragile",
        "is_liquid",
        "requires_upright",
        "max_stack_layers",
        "pick_frequency",
        "popularity_score",
    ]:
        setattr(existing, field, getattr(payload, field))
    existing.updated_at = _naive_utc_now()

    await db.commit()
    await db.refresh(existing)
    return existing


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product",
)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(Product).where(Product.product_id == product_id)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Delete related inventory records first
    inventory_stmt = select(Inventory).where(Inventory.product_id == product_id)
    inventory_result = await db.execute(inventory_stmt)
    inventory_records = inventory_result.scalars().all()
    
    for inventory in inventory_records:
        await db.delete(inventory)
    
    # Now delete the product
    await db.delete(product)
    await db.commit()
    return None