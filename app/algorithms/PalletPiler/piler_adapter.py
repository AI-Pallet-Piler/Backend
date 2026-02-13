import asyncio
from sqlmodel import Session, select
from . import piler
import json
from app.models.models import OrderLine, Product, Order
from app.db import engine

async def main():
    # example items to test the algorithm. You can modify this list to test different scenarios. 
    # all_items = [
    #     # Heavy Bases
    #     piler.Item("Heavy1", "Heavy Base 1", 45, 45, 20, weight=98),
    #     piler.Item("Heavy2", "Heavy Base 2", 45, 45, 20, weight=99),
    #     piler.Item("Heavy3", "Heavy Base 3", 45, 45, 20, weight=101),
    #     piler.Item("Heavy4", "Heavy Base 4", 45, 45, 20, weight=97),

    #     # Light but Huge (Should stack on top)
    #     piler.Item("Flat", "Flat Item", 60, 60, 5, weight=20),
        
    #     # TALL ITEM: 10x10x60. Should tip over to become 60x10x10 or 10x60x10
    #     piler.Item("Tall", "Tall Item", 10, 10, 60, weight=15),
        
    #     # Fillers
    #     piler.Item("Anvil", "Heavy Anvil", 10, 10, 10, weight=50), 
    #     piler.Item("Med1", "Normal Box", 20, 20, 20, weight=10),
    # ]

    async with engine.begin() as conn:
        def get_products(sync_conn):
            with Session(bind=sync_conn) as session:
                # 1. Get the first NEW order
                # Note: Your model likely uses 'status' not 'OrderStatus' based on previous context
                order = session.exec(select(Order).where(Order.status == "new")).first()
                
                if not order:
                    print("No new orders found.")
                    return

                print(f"Processing Order #{order.order_number}")

                # 2. Get Lines AND Products in one shot using a JOIN
                # This says: "Get the Line and the matching Product for this order"
                query = (
                    select(OrderLine, Product)
                    .join(Product, OrderLine.product_id == Product.product_id)
                    .where(OrderLine.order_id == order.order_id)
                )
                
                results = session.exec(query).all()

                all_items = []

                # 3. Loop through the joined results
                for line, product in results:
                    print(f" - Found {line.quantity_ordered} x {product.name}")
                    
                    # Create one item for EACH unit (e.g. 5x Box -> 5 items)
                    # Use 'line.quantity_ordered' based on your models.py
                    for i in range(line.quantity_ordered):
                        item = piler.Item(
                            id=f"{product.sku}-{i}",  # Unique ID for tracking
                            name=product.name,
                            w=int(product.width_cm),
                            d=int(product.length_cm),
                            h=int(product.height_cm),
                            weight=float(product.weight_kg),
                            # Ensure attribute matches your model (requires_upright vs allow_tipping)
                            allow_tipping=not product.requires_upright 
                        )
                        all_items.append(item)

                print(f"Total items to pack: {len(all_items)}")

                # 4. Run the packing algorithm
                pallet_H = 150 # Max height of the pallet load
                pallet_W = 120 # Max width of the pallet load
                pallet_D = 100 # Max depth of the pallet load

                pallet_instruction_json = piler.solve_multiple_pallets(all_items, pallet_W, pallet_D, pallet_H)

                print(f"json for order: {order.order_number}")
                print(f"Order id: {order.order_id}")
                print("=" * 60)
                print(json.dumps(pallet_instruction_json, indent=2))
                

        await conn.run_sync(get_products)

if __name__ == "__main__":
    asyncio.run(main())