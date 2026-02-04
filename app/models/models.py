from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from enum import Enum as PyEnum

from sqlmodel import Field, SQLModel, Column, Index
from sqlalchemy import Enum, DECIMAL, TIMESTAMP, func


# Helper function for UTC timestamp default
def _naive_utc_now() -> datetime:
    return datetime.now().replace(tzinfo=None)

# Utility function for default UTC now (for Product, Order, Pallet, etc.)
def utc_now() -> datetime:
    return datetime.utcnow()


# Enums

# User roles enum
class UserRole(str, PyEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    PICKER = "picker"
    
class LocationType(str, PyEnum):
    PICKING = "picking"
    RESERVE = "reserve"
    BULK = "bulk"


class OrderStatus(str, PyEnum):
    NEW = "new"
    PICKING = "picking"
    PACKING = "packing"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class PalletStatus(str, PyEnum):
    BUILDING = "building"
    FINISHED = "finished"
    SHIPPED = "shipped"


class Rotation(str, PyEnum):
    ZERO = "0"
    NINETY = "90"


class PickTaskStatus(str, PyEnum):
    PENDING = "pending"
    PICKED = "picked"
    COMPLETED = "completed"


# Models
class User(SQLModel, table=True):
    __tablename__ = "users"

    user_id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=150)
    email: str = Field(max_length=255, unique=True, index=True)
    badge_number: str = Field(max_length=50, unique=True, index=True)
    hashed_password: str = Field(max_length=255)
    role: UserRole = Field(default=UserRole.PICKER, sa_column=Column(Enum(UserRole)))
    created_at: datetime = Field(default_factory=_naive_utc_now, sa_column=Column(TIMESTAMP))
    updated_at: datetime = Field(default_factory=_naive_utc_now, sa_column=Column(TIMESTAMP))
    last_login: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP))


class Product(SQLModel, table=True):
    __tablename__ = "products"
    
    product_id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(max_length=50, unique=True, index=True)
    name: str = Field(max_length=150)
    description: Optional[str] = None
    length_cm: Decimal = Field(sa_column=Column(DECIMAL(8, 2)))
    width_cm: Decimal = Field(sa_column=Column(DECIMAL(8, 2)))
    height_cm: Decimal = Field(sa_column=Column(DECIMAL(8, 2)))
    weight_kg: Decimal = Field(sa_column=Column(DECIMAL(8, 3)))
    is_fragile: bool = Field(default=False)
    is_liquid: bool = Field(default=False)
    requires_upright: bool = Field(default=False)
    max_stack_layers: int = Field(default=10)
    pick_frequency: int = Field(default=0, index=True)
    popularity_score: Decimal = Field(default=Decimal("0"), sa_column=Column(DECIMAL(5, 4), index=True))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(TIMESTAMP))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(TIMESTAMP))


class Location(SQLModel, table=True):
    __tablename__ = "locations"
    
    location_id: Optional[int] = Field(default=None, primary_key=True)
    location_code: str = Field(max_length=20, unique=True)
    aisle: Optional[str] = Field(default=None, max_length=10)
    rack: Optional[str] = Field(default=None, max_length=10)
    level: Optional[int] = None
    bin: Optional[int] = None
    x_coordinate: Optional[Decimal] = Field(default=None, sa_column=Column(DECIMAL(8, 2)))
    y_coordinate: Optional[Decimal] = Field(default=None, sa_column=Column(DECIMAL(8, 2)))
    z_coordinate: Optional[Decimal] = Field(default=None, sa_column=Column(DECIMAL(8, 2)))
    max_weight_kg: Decimal = Field(default=Decimal("1000"), sa_column=Column(DECIMAL(8, 2)))
    max_height_cm: Decimal = Field(default=Decimal("200"), sa_column=Column(DECIMAL(8, 2)))
    location_type: LocationType = Field(default=LocationType.PICKING, sa_column=Column(Enum(LocationType)))
    is_active: bool = Field(default=True)


class Inventory(SQLModel, table=True):
    __tablename__ = "inventory"
    
    inventory_id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="products.product_id")
    location_id: int = Field(foreign_key="locations.location_id")
    quantity: int = Field(default=0)
    
    __table_args__ = (
        Index("idx_inventory_product_location", "product_id", "location_id", unique=True),
    )


class Order(SQLModel, table=True):
    __tablename__ = "orders"
    
    order_id: Optional[int] = Field(default=None, primary_key=True)
    order_number: str = Field(max_length=50, unique=True)
    customer_name: Optional[str] = Field(default=None, max_length=100)
    status: OrderStatus = Field(default=OrderStatus.NEW, sa_column=Column(Enum(OrderStatus)))
    priority: int = Field(default=1)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(TIMESTAMP))
    promised_ship_date: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP))


class OrderLine(SQLModel, table=True):
    __tablename__ = "order_lines"
    
    order_line_id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.order_id")
    product_id: int = Field(foreign_key="products.product_id")
    quantity_ordered: int
    quantity_picked: int = Field(default=0)


class Pallet(SQLModel, table=True):
    __tablename__ = "pallets"
    
    pallet_id: Optional[int] = Field(default=None, primary_key=True)
    pallet_code: str = Field(max_length=30, unique=True)
    order_id: Optional[int] = Field(default=None, foreign_key="orders.order_id")
    pallet_type: str = Field(default="EURO", max_length=30)
    max_weight_kg: Decimal = Field(default=Decimal("1000"), sa_column=Column(DECIMAL(8, 2)))
    max_height_cm: Decimal = Field(default=Decimal("180"), sa_column=Column(DECIMAL(8, 2)))
    status: PalletStatus = Field(default=PalletStatus.BUILDING, sa_column=Column(Enum(PalletStatus)))
    stability_score: Optional[Decimal] = Field(default=None, sa_column=Column(DECIMAL(5, 4)))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(TIMESTAMP))


class PalletLayer(SQLModel, table=True):
    __tablename__ = "pallet_layers"
    
    layer_id: Optional[int] = Field(default=None, primary_key=True)
    pallet_id: int = Field(foreign_key="pallets.pallet_id")
    layer_number: int
    total_weight_kg: Optional[Decimal] = Field(default=None, sa_column=Column(DECIMAL(8, 3)))
    total_height_cm: Optional[Decimal] = Field(default=None, sa_column=Column(DECIMAL(8, 2)))
    
    __table_args__ = (
        Index("idx_pallet_layer", "pallet_id", "layer_number", unique=True),
    )


class PalletItem(SQLModel, table=True):
    __tablename__ = "pallet_items"
    
    pallet_item_id: Optional[int] = Field(default=None, primary_key=True)
    pallet_id: int = Field(foreign_key="pallets.pallet_id")
    layer_id: int = Field(foreign_key="pallet_layers.layer_id")
    product_id: int = Field(foreign_key="products.product_id")
    quantity: int
    position_x: Optional[Decimal] = Field(default=None, sa_column=Column(DECIMAL(6, 2)))
    position_y: Optional[Decimal] = Field(default=None, sa_column=Column(DECIMAL(6, 2)))
    rotation: Rotation = Field(default=Rotation.ZERO, sa_column=Column(Enum(Rotation)))


class StackingRule(SQLModel, table=True):
    __tablename__ = "stacking_rules"
    
    rule_id: Optional[int] = Field(default=None, primary_key=True)
    product_id_top: Optional[int] = Field(default=None, foreign_key="products.product_id")
    product_id_bottom: Optional[int] = Field(default=None, foreign_key="products.product_id")
    allowed: bool = Field(default=True)
    max_overhang_cm: Decimal = Field(default=Decimal("0"), sa_column=Column(DECIMAL(5, 2)))
    reason: Optional[str] = Field(default=None, max_length=255)


class PickTask(SQLModel, table=True):
    __tablename__ = "pick_tasks"
    
    task_id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.order_id")
    product_id: int = Field(foreign_key="products.product_id")
    location_id: int = Field(foreign_key="locations.location_id")
    quantity_to_pick: int
    sequence_number: int
    status: PickTaskStatus = Field(default=PickTaskStatus.PENDING, sa_column=Column(Enum(PickTaskStatus)))
    picked_at: Optional[datetime] = Field(default=None, sa_column=Column(TIMESTAMP))
    
    __table_args__ = (
        Index("idx_pick_task_order_sequence", "order_id", "sequence_number"),
    )
