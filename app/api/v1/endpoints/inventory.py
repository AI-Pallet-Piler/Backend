from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, SQLModel

from app.db import get_db
from app.models.models import Inventory, Product, Location


# Request/Response schemas
class InventoryCreate(SQLModel):
    """Schema for creating new inventory records."""
    product_id: int
    location_id: int
    quantity: int = 0


class InventoryUpdate(SQLModel):
    """Schema for updating inventory quantities."""
    quantity: int


class InventoryResponse(SQLModel):
    """Enhanced inventory response with product and location details."""
    inventory_id: int
    product_id: int
    location_id: int
    quantity: int
    
    # Product details
    sku: Optional[str] = None
    product_name: Optional[str] = None
    product_description: Optional[str] = None
    
    # Location details
    location_code: Optional[str] = None


router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get(
    "",
    response_model=List[InventoryResponse],
    summary="List inventory",
)
@router.get(
    "/",
    response_model=List[InventoryResponse],
    summary="List inventory",
)
async def list_inventory(
    *,
    db: AsyncSession = Depends(get_db),
    product_id: Optional[int] = Query(
        default=None,
        description="Filter by specific product ID",
    ),
    location_id: Optional[int] = Query(
        default=None,
        description="Filter by specific location ID",
    ),
    sku: Optional[str] = Query(
        default=None,
        description="Filter by product SKU",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> List[InventoryResponse]:
    """
    List inventory records with optional filtering.
    
    Returns inventory with joined product and location details for display.
    """
    # Build query with joins
    stmt = (
        select(
            Inventory.inventory_id,
            Inventory.product_id,
            Inventory.location_id,
            Inventory.quantity,
            Product.sku,
            Product.name.label("product_name"),
            Product.description.label("product_description"),
            Location.location_code,
        )
        .join(Product, Inventory.product_id == Product.product_id)
        .join(Location, Inventory.location_id == Location.location_id)
    )
    
    # Apply filters
    if product_id is not None:
        stmt = stmt.where(Inventory.product_id == product_id)
    
    if location_id is not None:
        stmt = stmt.where(Inventory.location_id == location_id)
    
    if sku is not None:
        stmt = stmt.where(Product.sku == sku)
    
    # Order by inventory_id and apply pagination
    stmt = stmt.order_by(Inventory.inventory_id).offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    rows = result.all()
    
    # Convert rows to response model
    inventory_list = [
        InventoryResponse(
            inventory_id=row.inventory_id,
            product_id=row.product_id,
            location_id=row.location_id,
            quantity=row.quantity,
            sku=row.sku,
            product_name=row.product_name,
            product_description=row.product_description,
            location_code=row.location_code,
        )
        for row in rows
    ]
    
    return inventory_list


@router.get(
    "/{inventory_id}",
    response_model=InventoryResponse,
    summary="Get inventory by ID",
)
async def get_inventory(
    inventory_id: int,
    db: AsyncSession = Depends(get_db),
) -> InventoryResponse:
    """Get a single inventory record by ID with product and location details."""
    stmt = (
        select(
            Inventory.inventory_id,
            Inventory.product_id,
            Inventory.location_id,
            Inventory.quantity,
            Product.sku,
            Product.name.label("product_name"),
            Product.description.label("product_description"),
            Location.location_code,
        )
        .join(Product, Inventory.product_id == Product.product_id)
        .join(Location, Inventory.location_id == Location.location_id)
        .where(Inventory.inventory_id == inventory_id)
    )
    
    result = await db.execute(stmt)
    row = result.one_or_none()
    
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found",
        )
    
    return InventoryResponse(
        inventory_id=row.inventory_id,
        product_id=row.product_id,
        location_id=row.location_id,
        quantity=row.quantity,
        sku=row.sku,
        product_name=row.product_name,
        product_description=row.product_description,
        location_code=row.location_code,
    )


@router.post(
    "",
    response_model=InventoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create inventory record",
)
@router.post(
    "/",
    response_model=InventoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create inventory record",
)
async def create_inventory(
    payload: InventoryCreate,
    db: AsyncSession = Depends(get_db),
) -> InventoryResponse:
    """
    Create a new inventory record.
    
    Validates that the product and location exist before creating.
    Prevents duplicate product-location combinations.
    """
    # Validate product exists
    product_result = await db.execute(
        select(Product).where(Product.product_id == payload.product_id)
    )
    product = product_result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product with ID {payload.product_id} not found",
        )
    
    # Validate location exists
    location_result = await db.execute(
        select(Location).where(Location.location_id == payload.location_id)
    )
    location = location_result.scalar_one_or_none()
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Location with ID {payload.location_id} not found",
        )
    
    # Check for existing inventory record (unique constraint)
    existing_result = await db.execute(
        select(Inventory).where(
            Inventory.product_id == payload.product_id,
            Inventory.location_id == payload.location_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inventory record already exists for product {payload.product_id} at location {payload.location_id}",
        )
    
    # Create inventory record
    inventory = Inventory(**payload.model_dump())
    db.add(inventory)
    await db.commit()
    await db.refresh(inventory)
    
    # Return with enriched data
    return InventoryResponse(
        inventory_id=inventory.inventory_id,
        product_id=inventory.product_id,
        location_id=inventory.location_id,
        quantity=inventory.quantity,
        sku=product.sku,
        product_name=product.name,
        product_description=product.description,
        location_code=location.location_code,
    )


@router.put(
    "/{inventory_id}",
    response_model=InventoryResponse,
    summary="Update inventory quantity",
)
async def update_inventory(
    inventory_id: int,
    payload: InventoryUpdate,
    db: AsyncSession = Depends(get_db),
) -> InventoryResponse:
    """
    Update inventory quantity.
    
    Note: This only updates the quantity field.
    To move inventory to a different location, delete and create new record.
    """
    # Get existing inventory with joins
    stmt = (
        select(Inventory, Product, Location)
        .join(Product, Inventory.product_id == Product.product_id)
        .join(Location, Inventory.location_id == Location.location_id)
        .where(Inventory.inventory_id == inventory_id)
    )
    
    result = await db.execute(stmt)
    row = result.one_or_none()
    
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found",
        )
    
    inventory, product, location = row
    
    # Validate quantity is non-negative
    if payload.quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quantity cannot be negative",
        )
    
    # Update quantity
    inventory.quantity = payload.quantity
    
    await db.commit()
    await db.refresh(inventory)
    
    return InventoryResponse(
        inventory_id=inventory.inventory_id,
        product_id=inventory.product_id,
        location_id=inventory.location_id,
        quantity=inventory.quantity,
        sku=product.sku,
        product_name=product.name,
        product_description=product.description,
        location_code=location.location_code,
    )


@router.delete(
    "/{inventory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete inventory record",
)
async def delete_inventory(
    inventory_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an inventory record."""
    stmt = select(Inventory).where(Inventory.inventory_id == inventory_id)
    result = await db.execute(stmt)
    inventory = result.scalar_one_or_none()
    
    if inventory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory record not found",
        )
    
    await db.delete(inventory)
    await db.commit()
    return None
