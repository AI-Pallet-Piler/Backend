"""Navigation API endpoints for warehouse map management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from typing import List, Optional
import shapely
import shapely.wkt

from app.db import get_db
from app.models.models import Corridor, Shelf, Connection, ConnectionPoint, Location, LocationType
from app.navigation.warehouse_generator import WarehouseGenerator
from app.navigation.postgis_exporter import PostGISExporter
from app.navigation.config import Config, DatabaseConfig, load_config

router = APIRouter(prefix="/navigation", tags=["navigation"])

@router.get("/map")
async def get_warehouse_map(
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the current warehouse map with all components."""
    try:
        # Get corridors
        result = await db.execute(select(Corridor))
        corridors = result.scalars().all()
        
        # Get shelves
        result = await db.execute(select(Shelf))
        shelves = result.scalars().all()
        
        # Get connections
        result = await db.execute(select(Connection))
        connections = result.scalars().all()
        
        # Get connection points
        result = await db.execute(select(ConnectionPoint))
        connection_points = result.scalars().all()
        
        # Convert to GeoJSON-like format
        return {
            "corridors": [
                {
                    "corridor_id": c.corridor_id,
                    "name": c.name,
                    "geometry": _get_geojson_geometry(c.coordinates)
                } for c in corridors
            ],
            "shelves": [
                {
                    "shelf_id": s.shelf_id,
                    "name": s.name,
                    "geometry": _get_geojson_geometry(s.coordinates)
                } for s in shelves
            ],
            "connections": [
                {
                    "connection_id": c.connection_id,
                    "shelf_id": c.shelf_id,
                    "corridor_id": c.corridor_id,
                    "geometry": _get_geojson_geometry(c.connection_coordinates)
                } for c in connections
            ],
            "connection_points": [
                {
                    "connection_point_id": cp.connection_point_id,
                    "corridor_id": cp.corridor_id,
                    "geometry": _get_geojson_geometry(cp.connection_point_coordinates)
                } for cp in connection_points
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/locations")
async def get_all_locations(
    db: AsyncSession = Depends(get_db)
):
    """Get all locations with their shelf associations."""
    try:
        from app.models.models import Location
        from sqlalchemy import select
        
        result = await db.execute(
            select(Location).order_by(Location.location_code)
        )
        locations = result.scalars().all()
        
        return {
            "locations": [
                {
                    "location_id": loc.location_id,
                    "location_code": loc.location_code,
                    "shelf_id": loc.shelf_id,
                    "x_coordinate": float(loc.x_coordinate) if loc.x_coordinate else None,
                    "y_coordinate": float(loc.y_coordinate) if loc.y_coordinate else None,
                    "location_type": loc.location_type.value if loc.location_type else None,
                    "is_active": loc.is_active
                }
                for loc in locations
            ],
            "total": len(locations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @router.get("/shelves/{shelf_id}/locations")
# async def get_shelf_locations(
#     shelf_id: int,
#     db: AsyncSession = Depends(get_db)
# ):
#     """Get all locations associated with a specific shelf."""
#     try:
#         result = await db.execute(
#             select(Location).where(Location.shelf_id == shelf_id)
#         )
#         locations = result.scalars().all()
#
#         return [
#             {
#                 "location_id": l.location_id,
#                 "location_code": l.location_code,
#                 "aisle": l.aisle,
#                 "rack": l.rack,
#                 "level": l.level,
#                 "bin": l.bin,
#                 "x_coordinate": float(l.x_coordinate) if l.x_coordinate else None,
#                 "y_coordinate": float(l.y_coordinate) if l.y_coordinate else None,
#                 "z_coordinate": float(l.z_coordinate) if l.z_coordinate else None,
#                 "location_type": l.location_type.value if l.location_type else None,
#                 "is_active": l.is_active
#             }
#             for l in locations
#         ]
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


def _get_geojson_geometry(wkt_string: Optional[str]) -> Optional[dict]:
    """Convert WKT string to GeoJSON geometry."""
    if not wkt_string:
        return None
    
    try:
        geom = shapely.wkt.loads(wkt_string)
        return geom.__geo_interface__
    except Exception:
        return None


def _get_wkt(wkt_string: Optional[str]) -> Optional[str]:
    """Convert WKT string (already in WKT format, just return it)."""
    return wkt_string


@router.post("/generate-and-sync")
async def generate_and_sync(
    config: Optional[dict] = None,
    generate_paths: bool = True,  # New parameter to optionally generate paths
    db: AsyncSession = Depends(get_db)
):
    """Generate warehouse map and sync locations with shelves in one step.
    
    This endpoint:
    1. Generates the warehouse map (corridors, shelves, connections)
    2. Saves it to the database
    3. Creates Location records for each Shelf (if none exist)
    4. Links Location records to their corresponding Shelves
    5. Generates and saves all shelf-to-shelf paths (optional)
    """
    try:
        # Step 1: Create config
        if config:
            cfg = Config.from_dict(config)
        else:
            cfg = load_config()
        
        # Step 2: Generate warehouse map
        generator = WarehouseGenerator(cfg)
        warehouse_map = generator.generate()
        
        # Step 3: Export to database
        exporter = PostGISExporter(db)
        await exporter.clear_all()  # Clear old data first
        await exporter.export(warehouse_map)
        
        # Step 4: Create locations from shelves (if needed)
        result = await db.execute(select(Location))
        existing_locations = result.scalars().all()
        
        if not existing_locations:
            # Get all shelves
            result = await db.execute(select(Shelf))
            shelves = result.scalars().all()
            
            for shelf in shelves:
                if shelf.coordinates is None:
                    continue
                
                shelf_geom = shapely.wkt.loads(shelf.coordinates)
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
                db.add(location)
            
            await db.commit()
            message = "Warehouse map generated and locations created from shelves"
        else:
            # Sync existing locations with shelves
            synced_count = await _sync_locations_with_shelves(db)
            message = f"Warehouse map generated and {synced_count} locations synced with shelves"
        
        # Step 5: Generate all paths (if enabled)
        path_count = 0
        if generate_paths:
            # Get all data needed for path generation
            result = await db.execute(select(Shelf))
            shelves = result.scalars().all()
            
            result = await db.execute(select(Connection))
            connections = result.scalars().all()
            
            result = await db.execute(select(ConnectionPoint))
            connection_points = result.scalars().all()
            
            if shelves and connections and connection_points:
                from app.navigation.routing import generate_all_paths
                
                # Generate all paths
                paths = generate_all_paths(shelves, connections, connection_points)
                
                # Clear existing paths (delete shelves first to avoid FK issues)
                await db.execute(text("DELETE FROM shelf_paths;"))
                
                # Save paths to database
                from app.models.models import ShelfPath
                for path_data in paths:
                    shelf_path = ShelfPath(
                        from_shelf_id=path_data["from_shelf_id"],
                        to_shelf_id=path_data["to_shelf_id"],
                        total_distance=path_data["total_distance"],
                        path_coordinates=path_data["path_coordinates"],
                        num_segments=path_data["num_segments"]
                    )
                    db.add(shelf_path)
                
                await db.commit()
                path_count = len(paths)
                message += f", and {path_count} paths generated"
        
        stats = generator.get_statistics(warehouse_map)
        stats["paths_generated"] = path_count
        
        return {
            "status": "success",
            "message": message,
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _sync_locations_with_shelves(db: AsyncSession) -> int:
    """Sync existing locations with shelves based on coordinates."""
    # Get all shelves with coordinates
    result = await db.execute(select(Shelf))
    shelves = result.scalars().all()
    
    # Get all locations with coordinates
    result = await db.execute(
        select(Location).where(
            Location.x_coordinate.isnot(None), 
            Location.y_coordinate.isnot(None)
        )
    )
    locations = result.scalars().all()
    
    updated_count = 0
    
    for location in locations:
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
            
            shelf_geom = shapely.wkt.loads(shelf.coordinates)
            distance = loc_point.distance(shelf_geom)
            
            if distance < best_distance:
                best_distance = distance
                best_shelf_id = shelf.shelf_id
        
        # Link location to shelf if within threshold
        if best_shelf_id is not None and best_distance < 50.0:
            location.shelf_id = best_shelf_id
            updated_count += 1
    
    await db.commit()
    return updated_count


@router.get("/path/{from_shelf_id}/{to_shelf_id}")
async def get_path(
    from_shelf_id: int,
    to_shelf_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get path between two shelves. If not in DB, creates it on-demand."""
    try:
        from app.models.models import ShelfPath, Shelf, Connection, ConnectionPoint
        from app.navigation.routing import RoutingService
        from sqlalchemy import select
        import shapely.wkb
        
        # First try to find the path in database
        result = await db.execute(
            select(ShelfPath).where(
                ShelfPath.from_shelf_id == from_shelf_id,
                ShelfPath.to_shelf_id == to_shelf_id
            )
        )
        path = result.scalar_one_or_none()
        
        # If path exists, return it
        if path:
            geometry = _get_geojson_geometry(path.path_coordinates)
            wkt = _get_wkt(path.path_coordinates)
            return {
                "from_shelf_id": path.from_shelf_id,
                "to_shelf_id": path.to_shelf_id,
                "total_distance": path.total_distance,
                "num_segments": path.num_segments,
                "geometry": geometry,
                "wkt": wkt,
                "cached": True
            }
        
        # Path not found - calculate on-demand
        result = await db.execute(select(Shelf))
        shelves = result.scalars().all()
        
        result = await db.execute(select(Connection))
        connections = result.scalars().all()
        
        result = await db.execute(select(ConnectionPoint))
        connection_points = result.scalars().all()
        
        # Calculate path
        routing_service = RoutingService()
        path_result = routing_service.find_path_between_shelves(
            from_shelf_id, to_shelf_id, shelves, connections, connection_points
        )
        
        if not path_result:
            raise HTTPException(
                status_code=404,
                detail=f"No path found from shelf {from_shelf_id} to {to_shelf_id}"
            )
        
        # Save to database (upsert)
        from sqlalchemy.dialects.postgresql import insert
        from app.models.models import ShelfPath
        
        stmt = insert(ShelfPath).values(
            from_shelf_id=from_shelf_id,
            to_shelf_id=to_shelf_id,
            total_distance=path_result["total_distance"],
            path_coordinates=path_result["path_coordinates"],
            num_segments=path_result["num_segments"]
        )
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["from_shelf_id", "to_shelf_id"],
            set_={
                "total_distance": path_result["total_distance"],
                "path_coordinates": path_result["path_coordinates"],
                "num_segments": path_result["num_segments"],
                "created_at": text("NOW()")
            }
        )
        
        await db.execute(stmt)
        await db.commit()
        
        geometry = _get_geojson_geometry(path_result["path_coordinates"])
        
        return {
            "from_shelf_id": from_shelf_id,
            "to_shelf_id": to_shelf_id,
            "total_distance": path_result["total_distance"],
            "num_segments": path_result["num_segments"],
            "geometry": geometry,
            "wkt": path_result.get("path_coordinates_wkt"),
            "cached": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/path/location/{from_location_id}/{to_location_id}")
async def get_path_between_locations(
    from_location_id: int,
    to_location_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get the path between two locations (by their location IDs)."""
    try:
        from app.models.models import ShelfPath, Shelf, Connection, ConnectionPoint, Location
        from app.navigation.routing import RoutingService
        from sqlalchemy import select
        import shapely.wkt
        import shapely.geometry
        
        # Look up both locations
        result = await db.execute(
            select(Location).where(Location.location_id == from_location_id)
        )
        from_location = result.scalar_one_or_none()
        
        result = await db.execute(
            select(Location).where(Location.location_id == to_location_id)
        )
        to_location = result.scalar_one_or_none()
        
        if not from_location:
            raise HTTPException(
                status_code=404,
                detail=f"From location {from_location_id} not found"
            )
        
        if not to_location:
            raise HTTPException(
                status_code=404,
                detail=f"To location {to_location_id} not found"
            )
        
        from_shelf_id = from_location.shelf_id
        to_shelf_id = to_location.shelf_id
        
        if not from_shelf_id or not to_shelf_id:
            raise HTTPException(
                status_code=400,
                detail=f"One or both locations don't have shelves assigned"
            )
        
        # Get the shelf-to-shelf path
        result = await db.execute(
            select(ShelfPath).where(
                ShelfPath.from_shelf_id == from_shelf_id,
                ShelfPath.to_shelf_id == to_shelf_id
            )
        )
        path = result.scalar_one_or_none()
        
        # Prepend from_location and append to_location coordinates
        from_coords = (float(from_location.x_coordinate), float(from_location.y_coordinate))
        to_coords = (float(to_location.x_coordinate), float(to_location.y_coordinate))
        
        # If path exists, return it with location info
        if path:
            geometry = _get_geojson_geometry(path.path_coordinates)
            
            # Build full path with locations - convert tuples to lists
            shelf_points = [list(coord) for coord in geometry["coordinates"]]
            from_coords_list = [float(from_location.x_coordinate), float(from_location.y_coordinate)]
            to_coords_list = [float(to_location.x_coordinate), float(to_location.y_coordinate)]
            full_path_geom = shapely.geometry.LineString([from_coords_list] + shelf_points + [to_coords_list])
            full_wkt = full_path_geom.wkt
            
            # Calculate additional distance
            from_to_shelf_dist = path.total_distance
            from_to_location_dist = shapely.geometry.Point(from_coords).distance(shapely.geometry.Point(shelf_points[0]))
            location_to_shelf_dist = shapely.geometry.Point(to_coords).distance(shapely.geometry.Point(shelf_points[-1]))
            total_distance = from_to_shelf_dist + from_to_location_dist + location_to_shelf_dist
            
            return {
                "from_location_id": from_location_id,
                "to_location_id": to_location_id,
                "from_shelf_id": from_shelf_id,
                "to_shelf_id": to_shelf_id,
                "total_distance": total_distance,
                "num_segments": path.num_segments + 2,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [from_coords_list] + shelf_points + [to_coords_list]
                },
                "wkt": full_wkt,
                "cached": True
            }
        
        # Path not found - calculate on-demand
        result = await db.execute(select(Shelf))
        shelves = result.scalars().all()
        
        result = await db.execute(select(Connection))
        connections = result.scalars().all()
        
        result = await db.execute(select(ConnectionPoint))
        connection_points = result.scalars().all()
        
        # Calculate shelf path
        routing_service = RoutingService()
        path_result = routing_service.find_path_between_shelves(
            from_shelf_id, to_shelf_id, shelves, connections, connection_points
        )
        
        if not path_result:
            raise HTTPException(
                status_code=404,
                detail=f"No path found from shelf {from_shelf_id} to {to_shelf_id}"
            )
        
        # Get shelf coordinates from path result
        shelf_coords = path_result.get("path_coordinates")
        if shelf_coords:
            # shelf_coords might be WKT string or already parsed
            if isinstance(shelf_coords, str):
                shelf_geom = shapely.wkt.loads(shelf_coords)
                shelf_points = [list(coord) for coord in shelf_geom.coords]
            else:
                shelf_points = [list(coord) for coord in shelf_coords]
        else:
            # Use geometry coordinates - convert tuples to lists
            shelf_points = [list(coord) for coord in path_result.get("geometry", {}).get("coordinates", [])]
        
        # Build full path with locations - convert to lists
        from_coords_list = [float(from_location.x_coordinate), float(from_location.y_coordinate)]
        to_coords_list = [float(to_location.x_coordinate), float(to_location.y_coordinate)]
        full_path_geom = shapely.geometry.LineString([from_coords_list] + shelf_points + [to_coords_list])
        full_wkt = full_path_geom.wkt
        
        # Calculate additional distance
        from_to_shelf_dist = path_result["total_distance"]
        from_to_location_dist = shapely.geometry.Point(from_coords).distance(shapely.geometry.Point(shelf_points[0]))
        location_to_shelf_dist = shapely.geometry.Point(to_coords).distance(shapely.geometry.Point(shelf_points[-1]))
        total_distance = from_to_shelf_dist + from_to_location_dist + location_to_shelf_dist
        
        # Save shelf path to database
        from sqlalchemy.dialects.postgresql import insert
        from app.models.models import ShelfPath
        
        stmt = insert(ShelfPath).values(
            from_shelf_id=from_shelf_id,
            to_shelf_id=to_shelf_id,
            total_distance=path_result["total_distance"],
            path_coordinates=path_result["path_coordinates"],
            num_segments=path_result["num_segments"]
        )
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["from_shelf_id", "to_shelf_id"],
            set_={
                "total_distance": path_result["total_distance"],
                "path_coordinates": path_result["path_coordinates"],
                "num_segments": path_result["num_segments"],
                "created_at": text("NOW()")
            }
        )
        
        await db.execute(stmt)
        await db.commit()
        
        return {
            "from_location_id": from_location_id,
            "to_location_id": to_location_id,
            "from_shelf_id": from_shelf_id,
            "to_shelf_id": to_shelf_id,
            "total_distance": total_distance,
            "num_segments": path_result["num_segments"] + 2,
            "geometry": {
                "type": "LineString",
                "coordinates": [from_coords_list] + shelf_points + [to_coords_list]
            },
            "wkt": full_wkt,
            "cached": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/path/code/{from_location_code}/{to_location_code}")
async def get_path_between_location_codes(
    from_location_code: str,
    to_location_code: str,
    db: AsyncSession = Depends(get_db)
):
    """Get the path between two locations (by their location codes, e.g., 'LOC-001')."""
    try:
        from app.models.models import ShelfPath, Shelf, Connection, ConnectionPoint, Location
        from app.navigation.routing import RoutingService
        from sqlalchemy import select
        import shapely.wkt
        import shapely.geometry
        
        # Look up both locations by code
        result = await db.execute(
            select(Location).where(Location.location_code == from_location_code)
        )
        from_location = result.scalar_one_or_none()
        
        result = await db.execute(
            select(Location).where(Location.location_code == to_location_code)
        )
        to_location = result.scalar_one_or_none()
        
        if not from_location:
            raise HTTPException(
                status_code=404,
                detail=f"From location '{from_location_code}' not found"
            )
        
        if not to_location:
            raise HTTPException(
                status_code=404,
                detail=f"To location '{to_location_code}' not found"
            )
        
        from_shelf_id = from_location.shelf_id
        to_shelf_id = to_location.shelf_id
        
        if not from_shelf_id or not to_shelf_id:
            raise HTTPException(
                status_code=400,
                detail=f"One or both locations don't have shelves assigned"
            )
        
        # Get the shelf-to-shelf path
        result = await db.execute(
            select(ShelfPath).where(
                ShelfPath.from_shelf_id == from_shelf_id,
                ShelfPath.to_shelf_id == to_shelf_id
            )
        )
        path = result.scalar_one_or_none()
        
        # Prepend from_location and append to_location coordinates
        from_coords = (float(from_location.x_coordinate), float(from_location.y_coordinate))
        to_coords = (float(to_location.x_coordinate), float(to_location.y_coordinate))
        
        # If path exists, return it with location info
        if path:
            geometry = _get_geojson_geometry(path.path_coordinates)
            
            # Build full path with locations - convert tuples to lists
            shelf_points = [list(coord) for coord in geometry["coordinates"]]
            from_coords_list = [float(from_location.x_coordinate), float(from_location.y_coordinate)]
            to_coords_list = [float(to_location.x_coordinate), float(to_location.y_coordinate)]
            full_path_geom = shapely.geometry.LineString([from_coords_list] + shelf_points + [to_coords_list])
            full_wkt = full_path_geom.wkt
            
            # Calculate additional distance
            from_to_shelf_dist = path.total_distance
            from_to_location_dist = shapely.geometry.Point(from_coords).distance(shapely.geometry.Point(shelf_points[0]))
            location_to_shelf_dist = shapely.geometry.Point(to_coords).distance(shapely.geometry.Point(shelf_points[-1]))
            total_distance = from_to_shelf_dist + from_to_location_dist + location_to_shelf_dist
            
            return {
                "from_location_code": from_location_code,
                "to_location_code": to_location_code,
                "from_location_id": from_location.location_id,
                "to_location_id": to_location.location_id,
                "from_shelf_id": from_shelf_id,
                "to_shelf_id": to_shelf_id,
                "total_distance": total_distance,
                "num_segments": path.num_segments + 2,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [from_coords_list] + shelf_points + [to_coords_list]
                },
                "wkt": full_wkt,
                "cached": True
            }
        
        # Path not found - calculate on-demand
        result = await db.execute(select(Shelf))
        shelves = result.scalars().all()
        
        result = await db.execute(select(Connection))
        connections = result.scalars().all()
        
        result = await db.execute(select(ConnectionPoint))
        connection_points = result.scalars().all()
        
        # Calculate shelf path
        routing_service = RoutingService()
        path_result = routing_service.find_path_between_shelves(
            from_shelf_id, to_shelf_id, shelves, connections, connection_points
        )
        
        if not path_result:
            raise HTTPException(
                status_code=404,
                detail=f"No path found from shelf {from_shelf_id} to {to_shelf_id}"
            )
        
        # Get shelf coordinates from path result
        shelf_coords = path_result.get("path_coordinates")
        if shelf_coords:
            # shelf_coords might be WKT string or already parsed
            if isinstance(shelf_coords, str):
                shelf_geom = shapely.wkt.loads(shelf_coords)
                shelf_points = [list(coord) for coord in shelf_geom.coords]
            else:
                shelf_points = [list(coord) for coord in shelf_coords]
        else:
            # Use geometry coordinates - convert tuples to lists
            shelf_points = [list(coord) for coord in path_result.get("geometry", {}).get("coordinates", [])]
        
        # Build full path with locations - convert to lists
        from_coords_list = [float(from_location.x_coordinate), float(from_location.y_coordinate)]
        to_coords_list = [float(to_location.x_coordinate), float(to_location.y_coordinate)]
        full_path_geom = shapely.geometry.LineString([from_coords_list] + shelf_points + [to_coords_list])
        full_wkt = full_path_geom.wkt
        
        # Calculate additional distance
        from_to_shelf_dist = path_result["total_distance"]
        from_to_location_dist = shapely.geometry.Point(from_coords).distance(shapely.geometry.Point(shelf_points[0]))
        location_to_shelf_dist = shapely.geometry.Point(to_coords).distance(shapely.geometry.Point(shelf_points[-1]))
        total_distance = from_to_shelf_dist + from_to_location_dist + location_to_shelf_dist
        
        # Save shelf path to database
        from sqlalchemy.dialects.postgresql import insert
        from app.models.models import ShelfPath
        
        stmt = insert(ShelfPath).values(
            from_shelf_id=from_shelf_id,
            to_shelf_id=to_shelf_id,
            total_distance=path_result["total_distance"],
            path_coordinates=path_result["path_coordinates"],
            num_segments=path_result["num_segments"]
        )
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["from_shelf_id", "to_shelf_id"],
            set_={
                "total_distance": path_result["total_distance"],
                "path_coordinates": path_result["path_coordinates"],
                "num_segments": path_result["num_segments"],
                "created_at": text("NOW()")
            }
        )
        
        await db.execute(stmt)
        await db.commit()
        
        return {
            "from_location_code": from_location_code,
            "to_location_code": to_location_code,
            "from_location_id": from_location.location_id,
            "to_location_id": to_location.location_id,
            "from_shelf_id": from_shelf_id,
            "to_shelf_id": to_shelf_id,
            "total_distance": total_distance,
            "num_segments": path_result["num_segments"] + 2,
            "geometry": {
                "type": "LineString",
                "coordinates": [from_coords_list] + shelf_points + [to_coords_list]
            },
            "wkt": full_wkt,
            "cached": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
