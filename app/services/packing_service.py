"""
Packing Service - Handles automatic packing algorithm execution.

This service listens for new orders in the database and automatically
triggers the packing algorithm to generate pallet instructions.
"""

import asyncio
import logging
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db, engine
from app.models.models import Order, OrderStatus
from app.algorithms.PalletPiler.piler_adapter import process_single_order

logger = logging.getLogger(__name__)


# Queue to store orders that need processing
order_queue = asyncio.Queue()


async def process_order_queue():
    """
    Background task that processes orders from the queue.
    This runs continuously and processes one order at a time.
    """
    logger.info("Packing service queue processor started")
    
    while True:
        try:
            # Get next order from queue
            order_id = await order_queue.get()
            logger.info(f"Processing queued order ID: {order_id}")
            
            # Create a new database session for processing
            async for db in get_db():
                try:
                    result = await process_single_order(order_id, db)
                    if result:
                        logger.info(f"Successfully processed order {order_id}: {result}")
                    else:
                        logger.warning(f"Failed to process order {order_id}")
                except Exception as e:
                    logger.error(f"Error processing order {order_id}: {str(e)}", exc_info=True)
                finally:
                    break  # Exit the async generator loop
            
            # Mark task as done
            order_queue.task_done()
            
        except Exception as e:
            logger.error(f"Error in queue processor: {str(e)}", exc_info=True)
            await asyncio.sleep(5)  # Wait before continuing on error


def setup_order_event_listener():
    """
    Set up database event listener to detect new orders.
    This uses SQLAlchemy's after_insert event to trigger packing.
    """
    @event.listens_for(Order, 'after_insert')
    def order_created(mapper, connection, target):
        """
        Event handler for when a new order is inserted.
        Adds the order to the processing queue.
        """
        if target.status == OrderStatus.NEW:
            logger.info(f"New order detected: {target.order_number} (ID: {target.order_id})")
            # Add to queue (non-blocking)
            try:
                # We need to use asyncio to add to the queue
                # Since this is called from sync context, we'll schedule it
                asyncio.create_task(order_queue.put(target.order_id))
                logger.info(f"Order {target.order_id} added to processing queue")
            except Exception as e:
                logger.error(f"Failed to queue order {target.order_id}: {str(e)}")
    
    logger.info("Order event listener registered")


async def start_packing_service():
    """
    Start the packing service background task.
    Call this from the FastAPI lifespan/startup event.
    """
    logger.info("Starting packing service...")
    
    # Set up event listener
    setup_order_event_listener()
    
    # Start background queue processor
    asyncio.create_task(process_order_queue())
    
    logger.info("Packing service started successfully")


async def queue_order_for_packing(order_id: int):
    """
    Manually queue an order for packing.
    Useful for manual triggers or retry logic.
    
    Args:
        order_id: The ID of the order to process
    """
    await order_queue.put(order_id)
    logger.info(f"Order {order_id} manually queued for packing")
