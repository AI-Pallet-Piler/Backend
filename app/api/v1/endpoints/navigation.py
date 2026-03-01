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


def wkb_to_wkt(wkt_string: Optional[str]) -> Optional[str]:
    """Convert WKT string (already in WKT format, just return it)."""
    return wkt_string

@router.post("/generate")
async def generate_warehouse_map(
    config: Optional[dict] = None,
    db: AsyncSession = Depends(get_db)
):
    """Generate and save a new warehouse map to the database.
    
    Optionally provide custom configuration. If not provided, uses defaults.
    """
    try:
        # Create config from provided data or use defaults
        if config:
            cfg = Config.from_dict(config)
        else:
            cfg = load_config()
        
        # Generate warehouse map
        generator = WarehouseGenerator(cfg)
        warehouse_map = generator.generate()
        
        # Export to database
        exporter = PostGISExporter(db)
        await exporter.export(warehouse_map)
        
        stats = generator.get_statistics(warehouse_map)
        
        return {
            "status": "success",
            "message": "Warehouse map generated and saved",
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
                }
                for c in corridors
            ],
            "shelves": [
                {
                    "shelf_id": s.shelf_id,
                    "name": s.name,
                    "geometry": _get_geojson_geometry(s.coordinates)
                }
                for s in shelves
            ],
            "connections": [
                {
                    "connection_id": c.connection_id,
                    "shelf_id": c.shelf_id,
                    "corridor_id": c.corridor_id,
                    "connection_point_id": c.connection_point_id,
                    "geometry": _get_geojson_geometry(c.connection_coordinates)
                }
                for c in connections
            ],
            "connection_points": [
                {
                    "point_id": cp.point_id,
                    "connection_point_id": cp.connection_point_id,
                    "corridor_id": cp.corridor_id,
                    "geometry": _get_geojson_geometry(cp.connection_point_coordinates)
                }
                for cp in connection_points
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shelves")
async def get_shelves(
    db: AsyncSession = Depends(get_db)
):
    """Get all shelves with their locations."""
    try:
        result = await db.execute(
            select(Shelf).order_by(Shelf.shelf_id)
        )
        shelves = result.scalars().all()
        
        return [
            {
                "shelf_id": s.shelf_id,
                "name": s.name,
                "geometry": _get_geojson_geometry(s.coordinates)
            }
            for s in shelves
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/corridors")
async def get_corridors(
    db: AsyncSession = Depends(get_db)
):
    """Get all corridors."""
    try:
        result = await db.execute(
            select(Corridor).order_by(Corridor.corridor_id)
        )
        corridors = result.scalars().all()
        
        return [
            {
                "corridor_id": c.corridor_id,
                "name": c.name,
                "geometry": _get_geojson_geometry(c.coordinates)
            }
            for c in corridors
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shelves/{shelf_id}/locations")
async def get_shelf_locations(
    shelf_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get all locations associated with a specific shelf."""
    try:
        result = await db.execute(
            select(Location).where(Location.shelf_id == shelf_id)
        )
        locations = result.scalars().all()
        
        return [
            {
                "location_id": l.location_id,
                "location_code": l.location_code,
                "aisle": l.aisle,
                "rack": l.rack,
                "level": l.level,
                "bin": l.bin,
                "x_coordinate": float(l.x_coordinate) if l.x_coordinate else None,
                "y_coordinate": float(l.y_coordinate) if l.y_coordinate else None,
                "z_coordinate": float(l.z_coordinate) if l.z_coordinate else None,
                "location_type": l.location_type.value if l.location_type else None,
                "is_active": l.is_active
            }
            for l in locations
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/locations/{location_id}/shelf")
async def get_location_shelf(
    location_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get the shelf associated with a specific location."""
    try:
        result = await db.execute(
            select(Location).where(Location.location_id == location_id)
        )
        location = result.scalar_one_or_none()
        
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")
        
        if not location.shelf_id:
            return {
                "location_id": location.location_id,
                "shelf": None,
                "message": "Location is not linked to any shelf"
            }
        
        result = await db.execute(
            select(Shelf).where(Shelf.shelf_id == location.shelf_id)
        )
        shelf = result.scalar_one_or_none()
        
        return {
            "location_id": location.location_id,
            "location_code": location.location_code,
            "shelf": {
                "shelf_id": shelf.shelf_id,
                "name": shelf.name,
                "geometry": _get_geojson_geometry(shelf.coordinates)
            } if shelf else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        if best_shelf_id is not None and best_distance < 5.0:
            location.shelf_id = best_shelf_id
            updated_count += 1
    
    await db.commit()
    return updated_count


@router.post("/generate-paths")
async def generate_all_paths(
    db: AsyncSession = Depends(get_db)
):
    """Generate and save all shelf-to-shelf paths.
    
    Iterates through all n*(n-1) combinations and calculates each path on-demand,
    saving to DB using upsert (update if exists, insert if not).
    """
    try:
        # Get all shelves, connections, and connection points
        result = await db.execute(select(Shelf))
        shelves = result.scalars().all()
        
        result = await db.execute(select(Connection))
        connections = result.scalars().all()
        
        result = await db.execute(select(ConnectionPoint))
        connection_points = result.scalars().all()
        
        if not shelves or not connections or not connection_points:
            raise HTTPException(
                status_code=400,
                detail="Warehouse map not found. Generate map first using /generate-and-sync"
            )
        
        # Get shelf IDs
        shelf_ids = [s.shelf_id for s in shelves if s.coordinates]
        
        # Import routing service
        from app.navigation.routing import RoutingService
        from app.models.models import ShelfPath
        from sqlalchemy.dialects.postgresql import insert
        
        routing_service = RoutingService()
        paths_generated = 0
        paths_failed = 0
        
        # Iterate through all ordered combinations (n * (n-1))
        for from_id in shelf_ids:
            for to_id in shelf_ids:
                if from_id == to_id:
                    continue  # Skip self-to-self
                
                # Calculate path
                path_result = routing_service.find_path_between_shelves(
                    from_id, to_id, shelves, connections, connection_points
                )
                
                if not path_result:
                    paths_failed += 1
                    continue
                
                # Upsert path to database
                stmt = insert(ShelfPath).values(
                    from_shelf_id=from_id,
                    to_shelf_id=to_id,
                    total_distance=path_result["total_distance"],
                    path_coordinates=path_result["path_coordinates"],
                    num_segments=path_result["num_segments"]
                )
                
                # On conflict, update the existing record
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
                paths_generated += 1
        
        await db.commit()
        
        return {
            "status": "success",
            "message": f"Generated {paths_generated} paths ({paths_failed} failed)",
            "paths_generated": paths_generated,
            "paths_failed": paths_failed
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/path/{from_shelf_id}/{to_shelf_id}")
async def get_path(
    from_shelf_id: int,
    to_shelf_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get or create the path between two shelves.
    
    If path exists in database, returns it.
    If not, calculates on-demand, saves to DB (upsert), and returns it.
    
    Args:
        from_shelf_id: Starting shelf ID
        to_shelf_id: Ending shelf ID
        
    Returns:
        Path geometry and distance information
    """
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
        # Get shelves, connections, and connection points
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
        
        # Save to database (upsert - update if exists, insert if not)
        from sqlalchemy.dialects.postgresql import insert
        from app.models.models import ShelfPath
        
        stmt = insert(ShelfPath).values(
            from_shelf_id=from_shelf_id,
            to_shelf_id=to_shelf_id,
            total_distance=path_result["total_distance"],
            path_coordinates=path_result["path_coordinates"],
            num_segments=path_result["num_segments"]
        )
        
        # On conflict, update the existing record
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
        
        # Convert path coordinates to GeoJSON
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


@router.get("/path/from-location/{from_location_id}/{to_location_id}")
async def get_path_between_locations(
    from_location_id: int,
    to_location_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get the path between two locations (by their IDs).
    
    Args:
        from_location_id: Starting location ID
        to_location_id: Ending location ID
        
    Returns:
        Path geometry and distance information
    """
    try:
        from app.models.models import ShelfPath, Location
        
        # Get the locations
        result = await db.execute(
            select(Location).where(Location.location_id == from_location_id)
        )
        from_location = result.scalar_one_or_none()
        
        result = await db.execute(
            select(Location).where(Location.location_id == to_location_id)
        )
        to_location = result.scalar_one_or_none()
        
        if not from_location or not to_location:
            raise HTTPException(
                status_code=404,
                detail="One or both locations not found"
            )
        
        if not from_location.shelf_id or not to_location.shelf_id:
            raise HTTPException(
                status_code=400,
                detail="One or both locations are not linked to shelves"
            )
        
        # Get the path between the shelves
        result = await db.execute(
            select(ShelfPath).where(
                ShelfPath.from_shelf_id == from_location.shelf_id,
                ShelfPath.to_shelf_id == to_location.shelf_id
            )
        )
        path = result.scalar_one_or_none()
        
        if not path:
            raise HTTPException(
                status_code=404,
                detail=f"Path not found. Generate paths first using /generate-paths"
            )
        
        # Convert path coordinates to GeoJSON
        geometry = _get_geojson_geometry(path.path_coordinates)
        
        return {
            "from_location_id": from_location_id,
            "to_location_id": to_location_id,
            "from_shelf_id": path.from_shelf_id,
            "to_shelf_id": path.to_shelf_id,
            "total_distance": path.total_distance,
            "num_segments": path.num_segments,
            "geometry": geometry
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug-graph")
async def debug_graph(
    db: AsyncSession = Depends(get_db)
):
    """Debug endpoint to check graph connectivity."""
    try:
        from app.navigation.routing import RoutingService
        from sqlalchemy import select
        import shapely.wkt
        
        # Get all data
        result = await db.execute(select(Shelf))
        shelves = result.scalars().all()
        
        result = await db.execute(select(Connection))
        connections = result.scalars().all()
        
        result = await db.execute(select(ConnectionPoint))
        connection_points = result.scalars().all()
        
        # Build graph
        routing_service = RoutingService()
        graph = routing_service.build_graph(shelves, connections, connection_points)
        
        # Analyze corridors
        corridor_id_to_cps = {}
        for cp in connection_points:
            if cp.corridor_id and cp.connection_point_coordinates:
                geom = shapely.wkt.loads(cp.connection_point_coordinates)
                if cp.corridor_id not in corridor_id_to_cps:
                    corridor_id_to_cps[cp.corridor_id] = []
                corridor_id_to_cps[cp.corridor_id].append((geom.x, geom.y))
        
        horizontal = set()
        vertical = set()
        for corr_id, coords in corridor_id_to_cps.items():
            if len(coords) >= 2:
                x_vals = [c[0] for c in coords]
                y_vals = [c[1] for c in coords]
                if max(x_vals) - min(x_vals) < 1.0:
                    vertical.add(corr_id)
                elif max(y_vals) - min(y_vals) < 1.0:
                    horizontal.add(corr_id)
        
        # Get shelf centroids
        shelf_centroids = {}
        for shelf in shelves:
            if shelf.coordinates:
                geom = shapely.wkt.loads(shelf.coordinates)
                shelf_centroids[shelf.shelf_id] = (geom.centroid.x, geom.centroid.y)
        
        # Check if shelves 1 and 5 exist and their positions
        shelf_1_corr = None
        shelf_5_corr = None
        for conn in connections:
            if conn.shelf_id == 1 and conn.connection_point_id:
                for cp in connection_points:
                    if cp.connection_point_id == conn.connection_point_id:
                        shelf_1_corr = cp.corridor_id
                        break
            if conn.shelf_id == 5 and conn.connection_point_id:
                for cp in connection_points:
                    if cp.connection_point_id == conn.connection_point_id:
                        shelf_5_corr = cp.corridor_id
                        break
        
        # Get shelf coordinates
        shelf_1_coord = shelf_centroids.get(1)
        shelf_5_coord = shelf_centroids.get(5)
        
        # Check neighbors in graph
        shelf_1_neighbors = []
        shelf_5_neighbors = []
        if shelf_1_coord and shelf_1_coord in graph:
            shelf_1_neighbors = [(n[0], n[1], n[2]) for n in graph[shelf_1_coord]]
        if shelf_5_coord and shelf_5_coord in graph:
            shelf_5_neighbors = [(n[0], n[1], n[2]) for n in graph[shelf_5_coord]]
        
        # Test path finding
        test_path = routing_service.find_path_between_shelves(1, 5, shelves, connections, connection_points)
        
        return {
            "num_shelves": len(shelves),
            "num_connections": len(connections),
            "num_connection_points": len(connection_points),
            "num_graph_nodes": len(graph),
            "horizontal_corridors": list(horizontal),
            "vertical_corridors": list(vertical),
            "corridors_with_cps": list(corridor_id_to_cps.keys()),
            "shelf_1_corridor": shelf_1_corr,
            "shelf_5_corridor": shelf_5_corr,
            "shelf_1_centroid": shelf_1_coord,
            "shelf_5_centroid": shelf_5_coord,
            "shelf_1_neighbors": shelf_1_neighbors,
            "shelf_5_neighbors": shelf_5_neighbors,
            "path_found": test_path is not None,
            "path_distance": test_path["total_distance"] if test_path else None,
        }
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=str(e) + "\n" + traceback.format_exc())
