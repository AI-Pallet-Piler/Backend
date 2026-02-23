from datetime import datetime, timezone
from typing import List, Optional
import json
from pathlib import Path as PathLib

from fastapi import APIRouter, Depends, HTTPException, Query, status, Path
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, SQLModel

from app.db import get_db
from app.models.models import Order, OrderLine, OrderStatus, Product


# Request/Response schemas
class OrderLineCreate(SQLModel):
    """Schema for creating order lines."""
    product_id: int
    quantity_ordered: int


class OrderLineResponse(SQLModel):
    """Enhanced order line response with product details."""
    order_line_id: int
    order_id: int
    product_id: int
    quantity_ordered: int
    quantity_picked: int
    
    # Product details
    product_name: Optional[str] = None
    product_sku: Optional[str] = None


class OrderCreate(SQLModel):
    """Schema for creating new orders."""
    order_number: str
    customer_name: Optional[str] = None
    priority: int = 1
    promised_ship_date: Optional[datetime] = None
    order_lines: Optional[List[OrderLineCreate]] = []


class OrderUpdate(SQLModel):
    """Schema for updating orders."""
    customer_name: Optional[str] = None
    status: Optional[OrderStatus] = None
    priority: Optional[int] = None
    promised_ship_date: Optional[datetime] = None


class OrderStatusUpdate(SQLModel):
    """Schema for updating only order status."""
    status: OrderStatus


class OrderLinePickedUpdate(SQLModel):
    """Schema for updating the picked quantity of an order line."""
    quantity_picked: int


class OrderResponse(SQLModel):
    """Enhanced order response with order lines."""
    order_id: int
    order_number: str
    customer_name: Optional[str] = None
    status: OrderStatus
    priority: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    promised_ship_date: Optional[datetime] = None
    
    # Order lines
    order_lines: Optional[List[OrderLineResponse]] = []


def _naive_utc_now() -> datetime:
    """Naive UTC datetime for TIMESTAMP columns (asyncpg compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


router = APIRouter(prefix="/orders", tags=["orders"])


@router.get(
    "",
    response_model=List[OrderResponse],
    summary="List orders",
)
@router.get(
    "/",
    response_model=List[OrderResponse],
    summary="List orders",
)
async def list_orders(
    *,
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query(
        default=None,
        description="Filter by order status (new, picking, packing, shipped, cancelled)",
    ),
    priority: Optional[int] = Query(
        default=None,
        ge=1,
        le=5,
        description="Filter by priority level",
    ),
    customer_name: Optional[str] = Query(
        default=None,
        description="Filter by customer name (case-insensitive contains)",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> List[OrderResponse]:
    """
    List orders with optional filtering and pagination.
    
    Returns orders with their associated order lines and product details.
    """
    # Build base query
    stmt = select(Order)
    
    # Apply filters
    if status_filter:
        try:
            status_enum = OrderStatus(status_filter.lower())
            stmt = stmt.where(Order.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Valid values: new, ready, picking, packing, cancelled",
            )
    
    if priority is not None:
        stmt = stmt.where(Order.priority == priority)
    
    if customer_name:
        pattern = f"%{customer_name.lower()}%"
        stmt = stmt.where(Order.customer_name.ilike(pattern))
    
    # Order by created_at descending (newest first)
    stmt = stmt.order_by(Order.created_at.desc())
    
    # Pagination
    stmt = stmt.offset(skip).limit(limit)
    
    result = await db.execute(stmt)
    orders = result.scalars().all()
    
    # Fetch order lines for each order
    order_responses = []
    for order in orders:
        # Get order lines with product details
        lines_stmt = (
            select(
                OrderLine.order_line_id,
                OrderLine.order_id,
                OrderLine.product_id,
                OrderLine.quantity_ordered,
                OrderLine.quantity_picked,
                Product.name.label("product_name"),
                Product.sku.label("product_sku"),
            )
            .join(Product, OrderLine.product_id == Product.product_id)
            .where(OrderLine.order_id == order.order_id)
        )
        
        lines_result = await db.execute(lines_stmt)
        lines_data = lines_result.all()
        
        order_lines = [
            OrderLineResponse(
                order_line_id=row.order_line_id,
                order_id=row.order_id,
                product_id=row.product_id,
                quantity_ordered=row.quantity_ordered,
                quantity_picked=row.quantity_picked,
                product_name=row.product_name,
                product_sku=row.product_sku,
            )
            for row in lines_data
        ]
        
        order_responses.append(
            OrderResponse(
                order_id=order.order_id,
                order_number=order.order_number,
                customer_name=order.customer_name,
                status=order.status,
                priority=order.priority,
                created_at=order.created_at,
                completed_at=order.completed_at,
                promised_ship_date=order.promised_ship_date,
                order_lines=order_lines,
            )
        )
    
    return order_responses


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get a single order by ID",
)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """
    Get a single order by its ID with all order lines and product details.
    """
    stmt = select(Order).where(Order.order_id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    
    # Get order lines with product details
    lines_stmt = (
        select(
            OrderLine.order_line_id,
            OrderLine.order_id,
            OrderLine.product_id,
            OrderLine.quantity_ordered,
            OrderLine.quantity_picked,
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
        )
        .join(Product, OrderLine.product_id == Product.product_id)
        .where(OrderLine.order_id == order.order_id)
    )
    
    lines_result = await db.execute(lines_stmt)
    lines_data = lines_result.all()
    
    order_lines = [
        OrderLineResponse(
            order_line_id=row.order_line_id,
            order_id=row.order_id,
            product_id=row.product_id,
            quantity_ordered=row.quantity_ordered,
            quantity_picked=row.quantity_picked,
            product_name=row.product_name,
            product_sku=row.product_sku,
        )
        for row in lines_data
    ]
    
    return OrderResponse(
        order_id=order.order_id,
        order_number=order.order_number,
        customer_name=order.customer_name,
        status=order.status,
        priority=order.priority,
        created_at=order.created_at,
        completed_at=order.completed_at,
        promised_ship_date=order.promised_ship_date,
        order_lines=order_lines,
    )


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new order",
)
@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new order",
)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """
    Create a new order with optional order lines.
    """
    now = _naive_utc_now()
    
    # Check if order number already exists
    existing_order = await db.execute(
        select(Order).where(Order.order_number == payload.order_number)
    )
    if existing_order.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order number {payload.order_number} already exists",
        )
    
    # Create order
    order = Order(
        order_number=payload.order_number,
        customer_name=payload.customer_name,
        status=OrderStatus.NEW,
        priority=payload.priority,
        created_at=now,
        promised_ship_date=payload.promised_ship_date,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    # Create order lines if provided
    order_lines_response = []
    if payload.order_lines:
        for line_data in payload.order_lines:
            # Verify product exists
            product_result = await db.execute(
                select(Product).where(Product.product_id == line_data.product_id)
            )
            product = product_result.scalar_one_or_none()
            
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Product with ID {line_data.product_id} not found",
                )
            
            # Create order line
            order_line = OrderLine(
                order_id=order.order_id,
                product_id=line_data.product_id,
                quantity_ordered=line_data.quantity_ordered,
                quantity_picked=0,
            )
            db.add(order_line)
            await db.commit()
            await db.refresh(order_line)
            
            order_lines_response.append(
                OrderLineResponse(
                    order_line_id=order_line.order_line_id,
                    order_id=order_line.order_id,
                    product_id=order_line.product_id,
                    quantity_ordered=order_line.quantity_ordered,
                    quantity_picked=order_line.quantity_picked,
                    product_name=product.name,
                    product_sku=product.sku,
                )
            )
    
    return OrderResponse(
        order_id=order.order_id,
        order_number=order.order_number,
        customer_name=order.customer_name,
        status=order.status,
        priority=order.priority,
        created_at=order.created_at,
        completed_at=order.completed_at,
        promised_ship_date=order.promised_ship_date,
        order_lines=order_lines_response,
    )


@router.put(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Update an order",
)
async def update_order(
    order_id: int,
    payload: OrderUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """
    Update an existing order.
    """
    stmt = select(Order).where(Order.order_id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    
    # Update fields if provided
    if payload.customer_name is not None:
        order.customer_name = payload.customer_name
    if payload.status is not None:
        order.status = payload.status
    if payload.priority is not None:
        order.priority = payload.priority
    if payload.promised_ship_date is not None:
        order.promised_ship_date = payload.promised_ship_date
    
    await db.commit()
    await db.refresh(order)
    
    # Get order lines with product details
    lines_stmt = (
        select(
            OrderLine.order_line_id,
            OrderLine.order_id,
            OrderLine.product_id,
            OrderLine.quantity_ordered,
            OrderLine.quantity_picked,
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
        )
        .join(Product, OrderLine.product_id == Product.product_id)
        .where(OrderLine.order_id == order.order_id)
    )
    
    lines_result = await db.execute(lines_stmt)
    lines_data = lines_result.all()
    
    order_lines = [
        OrderLineResponse(
            order_line_id=row.order_line_id,
            order_id=row.order_id,
            product_id=row.product_id,
            quantity_ordered=row.quantity_ordered,
            quantity_picked=row.quantity_picked,
            product_name=row.product_name,
            product_sku=row.product_sku,
        )
        for row in lines_data
    ]
    
    return OrderResponse(
        order_id=order.order_id,
        order_number=order.order_number,
        customer_name=order.customer_name,
        status=order.status,
        priority=order.priority,
        created_at=order.created_at,
        completed_at=order.completed_at,
        promised_ship_date=order.promised_ship_date,
        order_lines=order_lines,
    )


@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
    summary="Update order status",
)
async def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    """
    Update only the status of an order.
    """
    stmt = select(Order).where(Order.order_id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    
    order.status = payload.status
    if payload.status == OrderStatus.PACKING and order.completed_at is None:
        order.completed_at = _naive_utc_now()
    
    await db.commit()
    await db.refresh(order)
    
    # Get order lines with product details
    lines_stmt = (
        select(
            OrderLine.order_line_id,
            OrderLine.order_id,
            OrderLine.product_id,
            OrderLine.quantity_ordered,
            OrderLine.quantity_picked,
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
        )
        .join(Product, OrderLine.product_id == Product.product_id)
        .where(OrderLine.order_id == order.order_id)
    )
    
    lines_result = await db.execute(lines_stmt)
    lines_data = lines_result.all()
    
    order_lines = [
        OrderLineResponse(
            order_line_id=row.order_line_id,
            order_id=row.order_id,
            product_id=row.product_id,
            quantity_ordered=row.quantity_ordered,
            quantity_picked=row.quantity_picked,
            product_name=row.product_name,
            product_sku=row.product_sku,
        )
        for row in lines_data
    ]
    
    return OrderResponse(
        order_id=order.order_id,
        order_number=order.order_number,
        customer_name=order.customer_name,
        status=order.status,
        priority=order.priority,
        created_at=order.created_at,
        completed_at=order.completed_at,
        promised_ship_date=order.promised_ship_date,
        order_lines=order_lines,
    )


@router.delete(
    "/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an order",
)
async def delete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete an order and its associated order lines.
    """
    stmt = select(Order).where(Order.order_id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    
    # Delete order lines first (due to foreign key constraint)
    await db.execute(
        select(OrderLine).where(OrderLine.order_id == order_id)
    )
    lines_result = await db.execute(
        select(OrderLine).where(OrderLine.order_id == order_id)
    )
    lines = lines_result.scalars().all()
    for line in lines:
        await db.delete(line)
    
    # Delete the order
    await db.delete(order)
    await db.commit()


@router.get(
    "/{order_id}/lines",
    response_model=List[OrderLineResponse],
    summary="Get order lines",
)
async def get_order_lines(
    order_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[OrderLineResponse]:
    """
    Get all order lines for a specific order.
    """
    # Verify order exists
    order_stmt = select(Order).where(Order.order_id == order_id)
    order_result = await db.execute(order_stmt)
    order = order_result.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    
    # Get order lines with product details
    lines_stmt = (
        select(
            OrderLine.order_line_id,
            OrderLine.order_id,
            OrderLine.product_id,
            OrderLine.quantity_ordered,
            OrderLine.quantity_picked,
            Product.name.label("product_name"),
            Product.sku.label("product_sku"),
        )
        .join(Product, OrderLine.product_id == Product.product_id)
        .where(OrderLine.order_id == order_id)
    )
    
    lines_result = await db.execute(lines_stmt)
    lines_data = lines_result.all()
    
    return [
        OrderLineResponse(
            order_line_id=row.order_line_id,
            order_id=row.order_id,
            product_id=row.product_id,
            quantity_ordered=row.quantity_ordered,
            quantity_picked=row.quantity_picked,
            product_name=row.product_name,
            product_sku=row.product_sku,
        )
        for row in lines_data
    ]


@router.patch(
    "/{order_id}/lines/{order_line_id}",
    response_model=OrderLineResponse,
    summary="Update order line picked quantity",
)
async def update_order_line_picked(
    order_id: int,
    order_line_id: int,
    payload: OrderLinePickedUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrderLineResponse:
    """
    Update the quantity_picked for a specific order line.
    Called by the picking app when a warehouse worker confirms picking an item.
    """
    # Verify order exists
    order_stmt = select(Order).where(Order.order_id == order_id)
    order_result = await db.execute(order_stmt)
    order = order_result.scalar_one_or_none()

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    # Get the order line (must belong to this order)
    line_stmt = (
        select(OrderLine)
        .where(OrderLine.order_line_id == order_line_id)
        .where(OrderLine.order_id == order_id)
    )
    line_result = await db.execute(line_stmt)
    order_line = line_result.scalar_one_or_none()

    if order_line is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order line not found",
        )

    order_line.quantity_picked = payload.quantity_picked
    await db.commit()
    await db.refresh(order_line)

    # Fetch product details for the response
    product_stmt = select(Product).where(Product.product_id == order_line.product_id)
    product_result = await db.execute(product_stmt)
    product = product_result.scalar_one_or_none()

    return OrderLineResponse(
        order_line_id=order_line.order_line_id,
        order_id=order_line.order_id,
        product_id=order_line.product_id,
        quantity_ordered=order_line.quantity_ordered,
        quantity_picked=order_line.quantity_picked,
        product_name=product.name if product else None,
        product_sku=product.sku if product else None,
    )


@router.get(
    "/{order_id}/pallet-instructions",
    summary="Get pallet instructions for an order",
    response_class=JSONResponse,
)
async def get_pallet_instructions(
    order_id: int = Path(..., description="The ID of the order"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Retrieve the generated pallet instructions JSON for a specific order.
    
    Returns the most recent pallet instructions file generated by the algorithm
    for the given order. The file contains pallet configuration data for 3D visualization.
    
    Args:
        order_id: The unique identifier of the order
        db: Database session
    
    Returns:
        JSON response containing pallet instructions with structure:
        [
            {
                "pallet_id": int,
                "items": [
                    {
                        "id": str,
                        "name": str,
                        "x": int,
                        "y": int,
                        "z": int,
                        "w": int,
                        "h": int,
                        "d": int,
                        "weight": float,
                        "tipped": bool
                    },
                    ...
                ]
            },
            ...
        ]
    
    Raises:
        HTTPException 404: If order not found or pallet instructions not generated
    """
    # First, verify the order exists and get order number
    stmt = select(Order).where(Order.order_id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found",
        )
    
    # Find the pallet instructions JSON file
    # Files are stored in app/algorithms/PalletPiler/Pallets_Json/
    # with format: pallet_instructions_{order_number}_{timestamp}.json
    
    # Get the directory containing pallet JSON files
    base_dir = PathLib(__file__).parent.parent.parent.parent  # Go up to app/
    pallet_json_dir = base_dir / "algorithms" / "PalletPiler" / "Pallets_Json"
    
    if not pallet_json_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pallet instructions not generated for order {order.order_number}. Please run the packing algorithm first.",
        )
    
    # Find all JSON files for this order number (sorted by timestamp, newest first)
    pattern = f"pallet_instructions_{order.order_number}_*.json"
    matching_files = sorted(
        pallet_json_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    if not matching_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pallet instructions not generated for order {order.order_number}. Please run the packing algorithm first.",
        )
    
    # Get the most recent file
    latest_file = matching_files[0]
    
    try:
        with open(latest_file, 'r') as f:
            pallet_data = json.load(f)
        
        return JSONResponse(content=pallet_data)
    
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse pallet instructions file",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading pallet instructions: {str(e)}",
        )


@router.post(
    "/{order_id}/trigger-packing",
    summary="Manually trigger packing algorithm for an order",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_packing(
    order_id: int = Path(..., description="The ID of the order"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Manually trigger the packing algorithm for a specific order.
    
    This endpoint queues the order for processing. The packing algorithm
    will run asynchronously in the background. Use the pallet-instructions
    endpoint to check if the results are ready.
    
    Args:
        order_id: The unique identifier of the order
        db: Database session
    
    Returns:
        JSON response confirming the order was queued
    
    Raises:
        HTTPException 404: If order not found
        HTTPException 400: If order is not in NEW status
    """
    from app.services.packing_service import queue_order_for_packing
    
    # Verify the order exists and is in NEW status
    stmt = select(Order).where(Order.order_id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found",
        )
    
    if order.status != OrderStatus.NEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order {order.order_number} is not in NEW status (current: {order.status}). Cannot process.",
        )
    
    # Queue the order for packing
    await queue_order_for_packing(order_id)
    
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": "Order queued for packing",
            "order_id": order_id,
            "order_number": order.order_number,
            "status": "queued"
        }
    )
