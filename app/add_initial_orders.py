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
    
    Note: During container startup, use direct call instead of HTTP to avoid
    connection issues when the server isn't fully ready yet.
    """
    # Check if we should use direct call (for Docker startup) or HTTP API
    use_direct = os.getenv("USE_DIRECT_PACKING", "true").lower() == "true"
    
    if use_direct:
        # Direct import to avoid circular imports
        from app.algorithms.PalletPiler.piler_adapter import process_single_order
        from app.db import get_db
        
        async for db in get_db():
            for order_id in order_ids:
                try:
                    print(f"   🔄 Processing order ID {order_id} directly...")
                    result = await process_single_order(order_id, db)
                    if result:
                        print(f"   ✅ Order {order_id} packed successfully")
                    else:
                        print(f"   ⚠️  Order {order_id} packing failed")
                except Exception as e:
                    print(f"   ❌ Error processing order {order_id}: {str(e)}")
            break
        return
    
    # Use HTTP API call
    # Use API Gateway - use service name when inside Docker, localhost when running on host
    # Check if we're inside Docker by looking for Docker environment indicators
    api_url = os.getenv("API_URL", "http://api-gateway:8080" if os.path.exists("/.dockerenv") else "http://localhost:8080")
    
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
                        # Delete order lines first
                        lines = session.exec(select(OrderLine).where(OrderLine.order_id == existing_order.order_id)).all()
                        for line in lines: 
                            session.delete(line)
                        session.flush()  # Flush order line deletions before deleting order
                        # Now delete the order
                        session.delete(existing_order)
                session.commit()

                print("📦 Creating Products (Standard Box Sizes)...")
                
                products_data = [
                    # (SKU, Name, Length, Width, Height, Weight, Fragile, Liquid, Upright, MaxStackLayers)
                    # Standard box sizes in cm (L x W x H)
                    
                    # Small boxes - 30x20x15 cm
                    ("ELEC-001", "Wireless Keyboard",       30, 20, 15, 0.8,   False, False, False, 8),
                    ("ELEC-002", "Computer Mouse Set",      30, 20, 15, 0.5,   False, False, False, 8),
                    ("BOOK-001", "Novel Box Set",           30, 20, 15, 2.0,   False, False, False, 6),
                    
                    # Medium boxes - 40x30x20 cm
                    ("HOME-001", "Coffee Maker",            40, 30, 20, 3.5,   False, False, False, 5),
                    ("ELEC-003", "Tablet Electronics",      40, 30, 20, 1.5,   False, False, False, 6),
                    ("TOY-001",   "Board Game Collection",  40, 30, 20, 2.5,   False, False, False, 5),
                    ("CLOTH-001", "Clothing Bundle Small",  40, 30, 20, 2.0,   False, False, False, 6),
                    
                    # Large boxes - 50x40x30 cm
                    ("HOME-002", "Kitchen Appliance Set",   50, 40, 30, 5.0,   False, False, False, 4),
                    ("SPORT-001", "Sports Equipment",       50, 40, 30, 4.5,   False, False, False, 4),
                    ("TOY-002",   "Large Toy Set",          50, 40, 30, 3.0,   False, False, False, 5),
                    ("CLOTH-002", "Winter Clothing Bundle", 50, 40, 30, 3.5,   False, False, False, 5),
                    
                    # Extra Large boxes - 60x40x30 cm
                    ("KITC-001", "Cookware Set Deluxe",     60, 40, 30, 8.0,   True,  False, False, 3),
                    ("ELEC-004", "Monitor 27 inch",         60, 40, 30, 6.5,   True,  False, False, 3),
                    ("BEVER-001", "Beverage Case 24pk",     60, 40, 30, 12.0,  False, True,  False, 4),
                    
                    # Flat boxes - 50x40x10 cm (for flat items)
                    ("BOOK-002", "Coffee Table Books",      50, 40, 10, 3.0,   False, False, False, 8),
                    ("ELEC-005", "Laptop Box",              50, 40, 10, 2.5,   True,  False, False, 6),
                    
                    # Tall boxes - 40x30x50 cm (items that need to stay upright)
                    ("HOME-003", "Blender Pro",             40, 30, 50, 4.0,   False, False, True,  3),
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

                # Sort products by weight in descending order (heaviest first)
                db_products.sort(key=lambda p: float(p.weight_kg), reverse=True)
                print("📊 Products sorted by weight (heaviest first):")
                for p in db_products:
                    print(f"   {p.sku}: {p.weight_kg}kg - {p.name}")

                print("\n📍 Creating Storage Locations (one per product)...")
                
                db_locations = []
                for i, product in enumerate(db_products, start=1):
                    # Generate location code: A-01-01, A-02-01, A-03-01, etc.
                    rack_num = f"{i:02d}"  # Format as 01, 02, 03, etc.
                    location_code = f"A-{rack_num}-01"
                    
                    location = session.exec(select(Location).where(Location.location_code == location_code)).first()
                    
                    if not location:
                        # Calculate coordinates based on rack number for warehouse layout
                        x_coord = Decimal(str((i - 1) * 5))  # 5 units apart
                        y_coord = Decimal("0")
                        z_coord = Decimal("0")
                        
                        location = Location(
                            location_code=location_code,
                            aisle="A",
                            rack=rack_num,
                            level=1,
                            bin=1,
                            x_coordinate=x_coord,
                            y_coordinate=y_coord,
                            z_coordinate=z_coord,
                            max_weight_kg=Decimal("500"),
                            max_height_cm=Decimal("150"),
                            location_type=LocationType.PICKING,
                            is_active=True
                        )
                        session.add(location)
                        print(f"   ✓ {location_code} (PICKING) - {product.name}")
                    
                    db_locations.append(location)
                
                session.flush()

                print("\n📦 Creating Inventory Stock (each product in its own location)...")
                
                for i, product in enumerate(db_products):
                    location = db_locations[i]  # Each product gets its own location
                    
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
                        print(f"   ✓ {product.name} @ {location.location_code}: {qty} units")
                
                session.flush()
                print(f"   ✅ Stocked {len(db_products)} products, each in its own location")

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
                            "ELEC-002": 5,    # Computer Mouse Sets (Small boxes)
                            "ELEC-003": 4,    # Tablet Electronics (Medium boxes)
                            "ELEC-004": 2,    # Monitors (Extra Large boxes)
                        }
                    },
                    {
                        "order_number": "ORD-TEST-002",
                        "customer_name": "BookStore & Toys Online",
                        "status": OrderStatus.NEW,
                        "priority": 1,
                        "days_ahead": 1,
                        "items": {
                            "BOOK-001": 8,    # Novel Box Sets (Small boxes)
                            "BOOK-002": 6,    # Coffee Table Books (Flat boxes)
                            "TOY-001": 5,     # Board Games (Medium boxes)
                            "TOY-002": 3,     # Large Toy Sets
                        }
                    },
                    {
                        "order_number": "ORD-TEST-003",
                        "customer_name": "Home & Kitchen Retailers",
                        "status": OrderStatus.NEW,
                        "priority": 3,
                        "days_ahead": 3,
                        "items": {
                            "HOME-001": 4,    # Coffee Makers (Medium boxes)
                            "HOME-002": 3,    # Kitchen Appliances (Large boxes)
                            "HOME-003": 2,    # Blenders (Tall boxes - upright)
                            "KITC-001": 3,    # Cookware (Extra Large, fragile)
                        }
                    },
                    {
                        "order_number": "ORD-TEST-004",
                        "customer_name": "Sports & Fashion Co",
                        "status": OrderStatus.NEW,
                        "priority": 2,
                        "days_ahead": 4,
                        "items": {
                            "CLOTH-001": 8,   # Small Clothing Bundles (Medium boxes)
                            "CLOTH-002": 5,   # Winter Clothing (Large boxes)
                            "SPORT-001": 4,   # Sports Equipment (Large boxes)
                            "BEVER-001": 3,   # Beverage Cases (Extra Large, liquid)
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