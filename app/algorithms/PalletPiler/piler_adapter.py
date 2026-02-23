import asyncio
import json
import logging
from sqlmodel import Session, select
from sqlalchemy.ext.asyncio import AsyncSession
from . import piler
from app.models.models import OrderLine, Product, Order, OrderStatus, Inventory, Location
from app.db import engine
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

async def process_single_order(order_id: int, db: AsyncSession) -> Optional[str]:
    """
    Process a single order through the packing algorithm.
    """
    try:
        # Get the order
        stmt = select(Order).where(Order.order_id == order_id)
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()
        
        if not order:
            logger.error(f"Order {order_id} not found")
            return None
        
        if order.status != OrderStatus.NEW:
            logger.warning(f"Order {order.order_number} is not in NEW status (current: {order.status})")
            return None
        
        logger.info(f"Processing Order #{order.order_number} (ID: {order_id})")
        
        # Get order lines
        lines_stmt = select(OrderLine).where(OrderLine.order_id == order.order_id)
        lines_result = await db.execute(lines_stmt)
        order_lines = lines_result.scalars().all()
        
        logger.info(f"  Items in order: {len(order_lines)}")
        
        if not order_lines:
            logger.warning(f"Order {order.order_number} has no order lines")
            return None
        
        # Build items list for packing algorithm
        all_items = []
        for line in order_lines:
            product_stmt = select(Product).where(Product.product_id == line.product_id)
            product_result = await db.execute(product_stmt)
            product = product_result.scalar_one_or_none()
            
            if not product:
                logger.error(f"Product {line.product_id} not found")
                continue
            
            # Look up the warehouse location for this product
            inv_stmt = select(Inventory).where(Inventory.product_id == product.product_id)
            inv_result = await db.execute(inv_stmt)
            inventory = inv_result.scalar_one_or_none()
            
            location_code = ""
            if inventory:
                loc_stmt = select(Location).where(Location.location_id == inventory.location_id)
                loc_result = await db.execute(loc_stmt)
                loc = loc_result.scalar_one_or_none()
                if loc:
                    location_code = loc.location_code
            
            # Create piler items for each quantity
            for i in range(line.quantity_ordered):
                item = piler.Item(
                    id=f"{product.sku}-{i}",
                    name=product.name,
                    w=int(product.width_cm),
                    d=int(product.length_cm),
                    h=int(product.height_cm),
                    weight=float(product.weight_kg),
                    allow_tipping=not product.requires_upright,
                    is_fragile=product.is_fragile,
                    type_id=product.sku,
                    location=location_code
                )
                all_items.append(item)
            
            logger.info(f"   - Added {line.quantity_ordered}x {product.name}")
        
        if not all_items:
            logger.error(f"No items to pack for order {order.order_number}")
            return None
        
        # Assign picking_order based on warehouse location (A-01-01 = bottom, higher = top)
        unique_locations = sorted(set(item.location for item in all_items))
        location_to_order = {loc: idx + 1 for idx, loc in enumerate(unique_locations)}
        for item in all_items:
            item.picking_order = location_to_order.get(item.location, 1)
        
        total_items = len(all_items)
        logger.info(f"  Total items to pack: {total_items}")
        
        # Run packing algorithm
        pallet_H = 150  
        pallet_W = 80   
        pallet_D = 120  
        
        logger.info(f"  Starting packing algorithm with {total_items} items...")
        pallet_instruction_json = piler.solve_multiple_pallets(all_items, pallet_W, pallet_D, pallet_H)
        
        # Save results to file
        script_dir = Path(__file__).parent
        output_dir = script_dir / "Pallets_Json"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = output_dir / f"pallet_instructions_{order.order_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(pallet_instruction_json, f, indent=2)
        
        logger.info(f"Successfully saved pallet instructions: {filename.name}")
        
        # Update order status to READY (algorithm done, ready for picking)
        order.status = OrderStatus.READY
        db.add(order)
        await db.commit()
        logger.info(f"Order {order.order_number} status updated to READY (ready for picking)")
        
        return str(filename)
        
    except Exception as e:
        logger.error(f"Error processing order {order_id}: {str(e)}", exc_info=True)
        await db.rollback()
        return None

async def process_all_new_orders():
    """Process all orders with NEW status."""
    async with engine.begin() as conn:
        def process_orders(sync_conn):
            with Session(bind=sync_conn) as session:
                
                # Get ALL orders with NEW status
                statement = select(Order).where(Order.status == OrderStatus.NEW)
                orders = session.exec(statement).all()
                
                print(f"Found {len(orders)} orders to process\n")
                
                if not orders:
                    print("No orders found with NEW status")
                    return
                
                # Process each order
                for order in orders:
                    print(f"Processing Order #{order.order_number}")
                    
                    order_lines = session.exec(
                        select(OrderLine).where(OrderLine.order_id == order.order_id)
                    ).all()
                    
                    print(f"  Items in order: {len(order_lines)}")
                    
                    all_items = []
                    for line in order_lines:
                        product = session.exec(
                            select(Product).where(Product.product_id == line.product_id)
                        ).first()
                        
                        # Look up the warehouse location for this product
                        inventory = session.exec(
                            select(Inventory).where(Inventory.product_id == product.product_id)
                        ).first()
                        
                        location_code = ""
                        if inventory:
                            loc = session.exec(
                                select(Location).where(Location.location_id == inventory.location_id)
                            ).first()
                            if loc:
                                location_code = loc.location_code
                        
                        for i in range(line.quantity_ordered):
                            item = piler.Item(
                                id=f"{product.sku}-{i}",
                                name=product.name,
                                w=int(product.width_cm),
                                d=int(product.length_cm),
                                h=int(product.height_cm),
                                weight=float(product.weight_kg),
                                allow_tipping=not product.requires_upright,
                                is_fragile=product.is_fragile,
                                type_id=product.sku,
                                location=location_code
                            )
                            all_items.append(item)
                        
                        print(f"   - Found {line.quantity_ordered}x {product.name}")
                    
                    # Assign picking_order based on warehouse location
                    unique_locations = sorted(set(item.location for item in all_items))
                    location_to_order = {loc: idx + 1 for idx, loc in enumerate(unique_locations)}
                    for item in all_items:
                        item.picking_order = location_to_order.get(item.location, 1)
                    
                    total_items = len(all_items)
                    print(f"  Total items to pack: {total_items}")
                    
                    pallet_H = 150 
                    pallet_W = 80 
                    pallet_D = 120 
                    
                    print(f"  Starting job with {total_items} items...")
                    pallet_instruction_json = piler.solve_multiple_pallets(all_items, pallet_W, pallet_D, pallet_H)
                    
                    # Save results
                    script_dir = Path(__file__).parent
                    output_dir = script_dir / "Pallets_Json"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    filename = output_dir / f"pallet_instructions_{order.order_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(filename, 'w') as f:
                        json.dump(pallet_instruction_json, f, indent=2)
                    
                    print(f"Saved: {filename.name}")
                    
                    order.status = OrderStatus.READY
                    session.add(order)
                    session.commit()
                    print(f"Order {order.order_number} status updated to READY (ready for picking)\n")

        await conn.run_sync(process_orders)

if __name__ == "__main__":
    asyncio.run(process_all_new_orders())