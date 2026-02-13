import asyncio
from sqlmodel import Session, select
from decimal import Decimal
import os

# --- IMPORTS ---
from app.models.models import Order, OrderLine, Product, OrderStatus
from app.db import engine

# --- CONFIG ---
# Use DATABASE_URL from environment, fallback to SQLite for local dev
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./warehouse.db")

async def create_test_data():
    async with engine.begin() as conn:
        def add_data(sync_conn):
            with Session(bind=sync_conn) as session:
                print("🗑️  Cleaning up old test data (ORD-TEST-001)...")
                existing_order = session.exec(select(Order).where(Order.order_number == "ORD-TEST-001")).first()
                if existing_order:
                    lines = session.exec(select(OrderLine).where(OrderLine.order_id == existing_order.order_id)).all()
                    for line in lines: 
                        session.delete(line)
                    session.delete(existing_order)
                    session.commit()

                print("📦 Creating Products (Physics Test Set)...")
                
                products_data = [
                    ("HEAVY-01", "Heavy Base",     45, 45, 20, 100.0, False),
                    ("TALL-01",  "Tall Pillar",    10, 10, 60, 15.0,  True),
                    ("FLAT-01",  "Steel Plate",    60, 60, 5,  20.0,  False),
                    ("BOX-S",    "Small Cube",     15, 15, 15, 5.0,   False),
                    ("BOX-M",    "Medium Box",     25, 25, 25, 12.0,  False),
                    ("BOX-L",    "Large Light",    50, 40, 30, 8.0,   False)
                ]

                db_products = []
                for sku, name, l, w, h, wt, upright in products_data:
                    product = session.exec(select(Product).where(Product.sku == sku)).first()
                    
                    if not product:
                        product = Product(
                            sku=sku,
                            name=name,
                            length_cm=Decimal(l),
                            width_cm=Decimal(w),
                            height_cm=Decimal(h),
                            weight_kg=Decimal(wt),
                            requires_upright=upright
                        )
                        session.add(product)
                        print(f"   + Created Product: {name}")
                    else:
                        product.length_cm = Decimal(l)
                        product.width_cm = Decimal(w)
                        product.height_cm = Decimal(h)
                        product.weight_kg = Decimal(wt)
                        product.requires_upright = upright
                        session.add(product)
                    
                    db_products.append(product)
                
                session.flush()

                print("📝 Creating Order...")
                order = Order(
                    order_number="ORD-TEST-001",
                    customer_name="Physics Test Corp",
                    status=OrderStatus.NEW,
                    priority=1
                )
                session.add(order)
                session.flush()

                print("🔗 Linking Items to Order...")
                quantities = {
                    "HEAVY-01": 4, 
                    "TALL-01":  2, 
                    "FLAT-01":  1, 
                    "BOX-S":    5, 
                    "BOX-M":    3, 
                    "BOX-L":    2  
                }

                for product in db_products:
                    qty = quantities.get(product.sku, 1)
                    line = OrderLine(
                        order_id=order.order_id,
                        product_id=product.product_id,
                        quantity_ordered=qty,
                        quantity_picked=0
                    )
                    session.add(line)

                session.commit()
                print(f"✅ Success! Created Order #{order.order_number} with {len(db_products)} product types.")
        
        await conn.run_sync(add_data)

if __name__ == "__main__":
    asyncio.run(create_test_data())