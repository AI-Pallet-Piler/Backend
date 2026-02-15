import asyncio
import httpx
from sqlmodel import Session, select
from decimal import Decimal
import os
from datetime import datetime, timedelta
import time

# --- IMPORTS ---
from app.models.models import Order, OrderLine, Product, OrderStatus, Location, LocationType, Inventory
from app.db import engine


async def trigger_packing_for_orders(order_ids: list[int]):
    """
    Trigger the packing algorithm for a list of order IDs via the API.
    
    Args:
        order_ids: List of order IDs to process
    """
    api_url = os.getenv("API_URL", "http://localhost:8000")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for order_id in order_ids:
            try:
                print(f"   \u23f3 Triggering packing for order ID {order_id}...")
                response = await client.post(f"{api_url}/api/v1/orders/{order_id}/trigger-packing")
                
                if response.status_code == 202:
                    print(f"   \u2705 Order {order_id} queued for packing")
                else:
                    print(f"   \u26a0\ufe0f  Order {order_id} - Status {response.status_code}: {response.text}")
                    
                # Small delay between requests
                time.sleep(0.5)
                
            except Exception as e:
                print(f"   \u274c Error triggering packing for order {order_id}: {str(e)}")
    
    print("\\n\u2705 Packing triggers completed. Check backend logs for processing status.")


async def create_test_data():
    async with engine.begin() as conn:
        def add_data(sync_conn):
            with Session(bind=sync_conn) as session:
                print("🗑️  Cleaning up old test data...")
                for order_num in ["ORD-TEST-001", "ORD-TEST-002", "ORD-TEST-003", "ORD-TEST-004"]:
                    existing_order = session.exec(select(Order).where(Order.order_number == order_num)).first()
                    if existing_order:
                        lines = session.exec(select(OrderLine).where(OrderLine.order_id == existing_order.order_id)).all()
                        for line in lines: 
                            session.delete(line)
                        session.delete(existing_order)
                session.commit()

                print("📦 Creating Products (Realistic E-Commerce Set)...")
                
                products_data = [
                    # (SKU, Name, Length, Width, Height, Weight, Fragile, Liquid, Upright, MaxStackLayers)
                    ("ELEC-001", "65\" Smart TV",           150, 90, 10, 25.0,  True,  False, False, 2),
                    ("ELEC-002", "Desktop Monitor 27\"",    65, 20, 40, 8.5,   True,  False, False, 3),
                    ("ELEC-003", "Wireless Keyboard",       45, 15, 3,  0.5,   False, False, False, 10),
                    ("BOOK-001", "Encyclopedia Set (5 Vol)", 25, 20, 30, 12.0,  False, False, True,  4),
                    ("BOOK-002", "Novel - Fantasy Series",  20, 15, 5,  0.8,   False, False, False, 8),
                    ("HOME-001", "Coffee Maker Deluxe",     35, 25, 30, 3.2,   False, False, False, 4),
                    ("HOME-002", "Blender Pro",             20, 20, 40, 2.1,   False, False, True,  5),
                    ("KITC-001", "Ceramic Dish Set (48pc)", 40, 40, 20, 8.5,   True,  False, False, 3),
                    ("KITC-002", "Stainless Steel Pots",    35, 30, 25, 5.5,   False, False, False, 4),
                    ("CLOTH-001", "Winter Jacket XL",       50, 40, 15, 1.2,   False, False, False, 6),
                    ("CLOTH-002", "Jeans Bundle (10 pairs)", 40, 35, 20, 4.0,   False, False, False, 5),
                    ("SPORT-001", "Bicycle 26\" Mountain",  180, 80, 100, 15.0, True,  False, False, 1),
                    ("SPORT-002", "Yoga Mat Bundle",        183, 61, 8,  2.0,   False, False, False, 5),
                    ("BEVER-001", "Water Bottles (24 pack)", 30, 30, 30, 18.0,  False, True,  False, 2),
                    ("BEVER-002", "Coffee Beans 1kg",       20, 15, 25, 1.0,   False, False, True,  8),
                    ("TOY-001",   "LEGO Set Large",         40, 30, 25, 2.5,   False, False, False, 6),
                    ("TOY-002",   "Toy Car Collection",     35, 25, 15, 1.5,   False, False, False, 7),
                ]

                db_products = []
                for sku, name, l, w, h, wt, frag, liq, upright, stack in products_data:
                    product = session.exec(select(Product).where(Product.sku == sku)).first()
                    
                    if not product:
                        product = Product(
                            sku=sku,
                            name=name,
                            length_cm=Decimal(l),
                            width_cm=Decimal(w),
                            height_cm=Decimal(h),
                            weight_kg=Decimal(wt),
                            is_fragile=frag,
                            is_liquid=liq,
                            requires_upright=upright,
                            max_stack_layers=stack,
                            pick_frequency=0,
                            popularity_score=Decimal("0.5")
                        )
                        session.add(product)
                        print(f"   ✓ {name}")
                    
                    db_products.append(product)
                
                session.flush()

                print("\n📍 Creating Storage Locations...")
                
                locations_data = [
                    ("A-01-01", "A", "01", 1, 1, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("500"), Decimal("150"), LocationType.PICKING),
                    ("A-01-02", "A", "01", 1, 2, Decimal("0"), Decimal("2"), Decimal("0"), Decimal("500"), Decimal("150"), LocationType.PICKING),
                    ("A-02-01", "A", "02", 1, 1, Decimal("5"), Decimal("0"), Decimal("0"), Decimal("500"), Decimal("150"), LocationType.RESERVE),
                    ("B-01-01", "B", "01", 1, 1, Decimal("10"), Decimal("0"), Decimal("0"), Decimal("500"), Decimal("150"), LocationType.PICKING),
                    ("B-02-01", "B", "02", 1, 1, Decimal("15"), Decimal("0"), Decimal("0"), Decimal("500"), Decimal("150"), LocationType.BULK),
                ]

                db_locations = []
                for loc_code, aisle, rack, level, bin_num, x, y, z, max_w, max_h, loc_type in locations_data:
                    location = session.exec(select(Location).where(Location.location_code == loc_code)).first()
                    
                    if not location:
                        location = Location(
                            location_code=loc_code,
                            aisle=aisle,
                            rack=rack,
                            level=level,
                            bin=bin_num,
                            x_coordinate=x,
                            y_coordinate=y,
                            z_coordinate=z,
                            max_weight_kg=max_w,
                            max_height_cm=max_h,
                            location_type=loc_type,
                            is_active=True
                        )
                        session.add(location)
                        print(f"   ✓ {loc_code} ({loc_type.value})")
                    
                    db_locations.append(location)
                
                session.flush()

                print("\n📦 Creating Inventory Stock...")
                
                for i, product in enumerate(db_products):
                    for location in db_locations[:3]:  # Stock in first 3 locations
                        inventory = session.exec(
                            select(Inventory).where(
                                (Inventory.product_id == product.product_id) &
                                (Inventory.location_id == location.location_id)
                            )
                        ).first()
                        
                        if not inventory:
                            qty = (i + 1) * 5 + (i % 3) * 10  # Varied quantities
                            inventory = Inventory(
                                product_id=product.product_id,
                                location_id=location.location_id,
                                quantity=qty
                            )
                            session.add(inventory)
                
                session.flush()
                print(f"   ✓ Stocked {len(db_products)} products across {len(db_locations[:3])} locations")

                print("\n📝 Creating Multiple Test Orders...")
                
                # Order 1: Electronics Heavy Order
                orders_config = [
                    {
                        "order_number": "ORD-TEST-001",
                        "customer_name": "TechCorp Distribution Center",
                        "status": OrderStatus.NEW,
                        "priority": 2,
                        "days_ahead": 2,
                        "items": {
                            "ELEC-002": 3,    # Desktop Monitors
                            "ELEC-003": 10,   # Wireless Keyboards
                            "HOME-001": 2,    # Coffee Makers
                        }
                    },
                    {
                        "order_number": "ORD-TEST-002",
                        "customer_name": "BookStore Online",
                        "status": OrderStatus.NEW,
                        "priority": 1,
                        "days_ahead": 1,
                        "items": {
                            "BOOK-001": 5,    # Encyclopedia Sets
                            "BOOK-002": 20,   # Novels
                            "TOY-001": 8,     # LEGO Sets
                        }
                    },
                    {
                        "order_number": "ORD-TEST-003",
                        "customer_name": "Home & Kitchen Retailers",
                        "status": OrderStatus.NEW,
                        "priority": 3,
                        "days_ahead": 3,
                        "items": {
                            "KITC-001": 4,    # Ceramic Dish Sets
                            "KITC-002": 6,    # Stainless Steel Pots
                            "HOME-002": 3,    # Blender Pro
                            "BEVER-001": 2,   # Water Bottles
                        }
                    },
                    {
                        "order_number": "ORD-TEST-004",
                        "customer_name": "Sports & Fashion Co",
                        "status": OrderStatus.NEW,
                        "priority": 2,
                        "days_ahead": 4,
                        "items": {
                            "CLOTH-001": 15,  # Winter Jackets
                            "CLOTH-002": 10,  # Jeans Bundle
                            "SPORT-002": 5,   # Yoga Mat Bundle
                            "TOY-002": 6,     # Toy Car Collection
                        }
                    },
                ]

                for order_config in orders_config:
                    order = Order(
                        order_number=order_config["order_number"],
                        customer_name=order_config["customer_name"],
                        status=order_config["status"],
                        priority=order_config["priority"],
                        promised_ship_date=datetime.utcnow() + timedelta(days=order_config["days_ahead"])
                    )
                    session.add(order)
                    session.flush()

                    print(f"\n🔗 Order #{order_config['order_number']} - {order_config['customer_name']}")
                    
                    total_items = 0
                    for product in db_products:
                        if product.sku in order_config["items"]:
                            qty = order_config["items"][product.sku]
                            line = OrderLine(
                                order_id=order.order_id,
                                product_id=product.product_id,
                                quantity_ordered=qty,
                                quantity_picked=0
                            )
                            session.add(line)
                            total_items += qty
                            print(f"   + {qty}x {product.name}")

                    session.commit()
                    print(f"   ✅ Total items: {total_items} | Ship date: {order.promised_ship_date.strftime('%Y-%m-%d')}")

                print(f"\n✅ Success! Created 4 test orders with varying complexity and priorities")
                
                # Store order numbers to query after transaction commits
                return [cfg["order_number"] for cfg in orders_config]
        
        order_numbers = await conn.run_sync(add_data)
    
    # Transaction is now committed, query for order IDs
    print("\n🔍 Retrieving order IDs...")
    async with engine.connect() as conn:
        def get_order_ids(sync_conn):
            with Session(bind=sync_conn) as session:
                orders = session.exec(select(Order).where(
                    Order.order_number.in_(order_numbers)
                )).all()
                return [order.order_id for order in orders]
        
        order_ids = await conn.run_sync(get_order_ids)
    
    if order_ids:
        # Trigger packing algorithm for each order
        print(f"📦 Found {len(order_ids)} orders to process")
        print("\n🚀 Triggering packing algorithm for created orders...")
        await trigger_packing_for_orders(order_ids)
    else:
        print("⚠️  No orders found to trigger packing")

if __name__ == "__main__":
    asyncio.run(create_test_data())