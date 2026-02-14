import asyncio
import json
from sqlmodel import Session, select
from . import piler
from app.models.models import OrderLine, Product, Order, OrderStatus
from app.db import engine
from datetime import datetime
from pathlib import Path

async def main():
    async with engine.begin() as conn:
        def process_orders(sync_conn):
            with Session(bind=sync_conn) as session:
                
                # Get ALL orders with NEW status, not just one
                statement = select(Order).where(Order.status == OrderStatus.NEW)
                orders = session.exec(statement).all()
                
                print(f"Found {len(orders)} orders to process\n")
                
                if not orders:
                    print("No orders found with NEW status")
                    return
                
                # Process each order
                for order in orders:
                    print(f"Processing Order #{order.order_number}")
                    
                    # Get order lines
                    order_lines = session.exec(
                        select(OrderLine).where(OrderLine.order_id == order.order_id)
                    ).all()
                    
                    print(f"  Items in order: {len(order_lines)}")
                    
                    all_items = []
                    for line in order_lines:
                        product = session.exec(
                            select(Product).where(Product.product_id == line.product_id)
                        ).first()
                        
                        # Create piler items for each quantity
                        for i in range(line.quantity_ordered):
                            item = piler.Item(
                                id=f"{product.sku}-{i}",
                                name=product.name,
                                w=int(product.width_cm),
                                d=int(product.length_cm),
                                h=int(product.height_cm),
                                weight=float(product.weight_kg),
                                allow_tipping=not product.requires_upright
                            )
                            all_items.append(item)
                        
                        print(f"   - Found {line.quantity_ordered}x {product.name}")
                    
                    total_items = len(all_items)
                    print(f"  Total items to pack: {total_items}")
                    
                    # Run packing algorithm
                    pallet_H = 150  # Max height
                    pallet_W = 120  # Max width
                    pallet_D = 100  # Max depth
                    
                    print(f"  Starting job with {total_items} items...")
                    pallet_instruction_json = piler.solve_multiple_pallets(all_items, pallet_W, pallet_D, pallet_H)
                    
                    # Save results to file
                    script_dir = Path(__file__).parent
                    output_dir = script_dir / "Pallets_Json"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    filename = output_dir / f"pallet_instructions_{order.order_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(filename, 'w') as f:
                        json.dump(pallet_instruction_json, f, indent=2)
                    
                    print(f"Saved: {filename.name}\n")

        await conn.run_sync(process_orders)

if __name__ == "__main__":
    asyncio.run(main())