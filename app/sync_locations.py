"""Script to sync navigation shelves with location data.

This script links Location records to Shelf records based on 
matching coordinates or proximity.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import shapely
import shapely.wkb

from app.db import AsyncSessionLocal, create_tables
from app.models.models import Location, Shelf, LocationType


async def sync_locations_with_shelves():
    """Sync Location records with Shelf records based on coordinates."""
    async with AsyncSessionLocal() as session:
        # Get all shelves with coordinates
        result = await session.execute(select(Shelf))
        shelves = result.scalars().all()
        
        # Get all locations
        result = await session.execute(
            select(Location).where(Location.x_coordinate.isnot(None))
        )
        locations = result.scalars().all()
        
        updated_count = 0
        
        for location in locations:
            if location.x_coordinate is None or location.y_coordinate is None:
                continue
            
            loc_point = shapely.geometry.Point(
                float(location.x_coordinate), 
                float(location.y_coordinate)
            )
            
            # Find the nearest shelf
            best_shelf_id = None
            best_distance = float('inf')
            
            for shelf in shelves:
                if shelf.coordinates is None:
                    continue
                
                shelf_geom = shapely.wkb.loads(shelf.coordinates)
                
                # Check if location point is within or near shelf
                if shelf_geom.contains(loc_point):
                    distance = 0
                else:
                    distance = loc_point.distance(shelf_geom)
                
                if distance < best_distance:
                    best_distance = distance
                    best_shelf_id = shelf.shelf_id
            
            # Link location to shelf if within threshold
            if best_shelf_id is not None and best_distance < 5.0:
                location.shelf_id = best_shelf_id
                updated_count += 1
                print(f"Linked location {location.location_code} (ID: {location.location_id}) to shelf {best_shelf_id}")
        
        await session.commit()
        print(f"\nSynced {updated_count} locations with shelves")


async def create_sample_locations():
    """Create sample locations for existing shelves if none exist."""
    async with AsyncSessionLocal() as session:
        # Check if we have shelves
        result = await session.execute(select(Shelf))
        shelves = result.scalars().all()
        
        if not shelves:
            print("No shelves found. Please generate warehouse map first.")
            return
        
        # Check if we already have locations
        result = await session.execute(select(Location))
        locations = result.scalars().all()
        
        if locations:
            print(f"Already have {len(locations)} locations. Skipping creation.")
            return
        
        # Create locations from shelves
        location_count = 0
        for shelf in shelves:
            if shelf.coordinates is None:
                continue
            
            shelf_geom = shapely.wkb.loads(shelf.coordinates)
            centroid = shelf_geom.centroid
            
            location = Location(
                location_code=f"LOC-{shelf.shelf_id:03d}",
                shelf_id=shelf.shelf_id,
                x_coordinate=centroid.x,
                y_coordinate=centroid.y,
                z_coordinate=0,
                location_type=LocationType.PICKING,
                is_active=True
            )
            session.add(location)
            location_count += 1
        
        await session.commit()
        print(f"Created {location_count} locations from shelves")


async def main():
    """Main function to run the sync."""
    print("Creating database tables...")
    await create_tables()
    
    print("\nCreating sample locations from shelves...")
    await create_sample_locations()
    
    print("\nSyncing locations with shelves...")
    await sync_locations_with_shelves()
    
    print("\nDone!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
