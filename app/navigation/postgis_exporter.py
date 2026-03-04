"""PostGIS database exporter for warehouse maps - async version."""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import shapely
import shapely.wkb

from app.models.models import Corridor, Shelf, Connection, ConnectionPoint
from app.navigation.config import DatabaseConfig


def wkb_to_wkt(wkb_bytes: Optional[bytes]) -> Optional[str]:
    """Convert WKB (Well-Known Binary) to WKT (Well-Known Text).
    
    Args:
        wkb_bytes: WKB bytes from PostGIS geometry column
    
    Returns:
        WKT string representation or None if input is None
    """
    if wkb_bytes is None:
        return None
    geometry = shapely.wkb.loads(wkb_bytes)
    return geometry.wkt


def wkt_to_wkb(wkt_string: str) -> bytes:
    """Convert WKT (Well-Known Text) to WKB (Well-Known Binary).
    
    Args:
        wkt_string: WKT string representation
    
    Returns:
        WKB bytes for PostGIS geometry column
    """
    geometry = shapely.wkt.loads(wkt_string)
    return geometry.wkb


def wkt_to_geometry(wkt_string: Optional[str]):
    """Convert WKT string to Shapely geometry.
    
    Args:
        wkt_string: WKT string representation
    
    Returns:
        Shapely geometry object or None if input is None
    """
    if wkt_string is None:
        return None
    return shapely.wkt.loads(wkt_string)


class PostGISExporter:
    """Async exporter for saving warehouse maps to PostGIS database."""
    
    def __init__(self, session: AsyncSession):
        """Initialize exporter with database session."""
        self.session = session
    
    async def export(self, warehouse_map: dict) -> None:
        """Export warehouse map to database.
        
        Args:
            warehouse_map: Dictionary with corridors, shelves, connections, connection_points
        """
        # Clear existing data
        await self.clear_all()
        
        # Export corridors
        await self._export_corridors(warehouse_map.get("corridors", []))
        
        # Export shelves
        await self._export_shelves(warehouse_map.get("shelves", []))
        
        # Export connections
        await self._export_connections(warehouse_map.get("connections", []))
        
        # Export connection_points
        await self._export_connection_points(warehouse_map.get("connection_points", []))
        
        await self.session.commit()
    
    async def clear_all(self) -> None:
        """Clear all data from tables using TRUNCATE for a clean reset."""
        # Use TRUNCATE for clean reset - CASCADE will handle dependent tables
        try:
            # Try TRUNCATE first (faster, cleaner)
            await self.session.execute(text("TRUNCATE TABLE shelf_paths CASCADE;"))
            await self.session.execute(text("TRUNCATE TABLE connection_points CASCADE;"))
            await self.session.execute(text("TRUNCATE TABLE connections CASCADE;"))
            await self.session.execute(text("TRUNCATE TABLE shelves CASCADE;"))
            await self.session.execute(text("TRUNCATE TABLE corridors CASCADE;"))
        except Exception:
            # If TRUNCATE fails (e.g., FK constraints), use DELETE
            await self.session.execute(text("DELETE FROM shelf_paths;"))
            await self.session.execute(text("DELETE FROM connection_points;"))
            await self.session.execute(text("DELETE FROM connections;"))
            await self.session.execute(text("DELETE FROM shelves;"))
            await self.session.execute(text("DELETE FROM corridors;"))
        
        await self.session.commit()
    
    async def _export_corridors(self, corridors: list) -> None:
        """Export corridors to database."""
        for corridor in corridors:
            coordinates = corridor.get("coordinates")
            wkt = coordinates.wkt if coordinates else None
            
            corridor_obj = Corridor(
                corridor_id=corridor.get("corridor_id"),
                name=corridor.get("name", ""),
                coordinates=wkt
            )
            self.session.add(corridor_obj)
        
        await self.session.commit()
    
    async def _export_shelves(self, shelves: list) -> None:
        """Export shelves to database."""
        for shelf in shelves:
            coordinates = shelf.get("coordinates")
            wkt = coordinates.wkt if coordinates else None
            
            shelf_obj = Shelf(
                shelf_id=shelf.get("shelf_id"),
                name=shelf.get("name", ""),
                coordinates=wkt
            )
            self.session.add(shelf_obj)
        
        await self.session.commit()
    
    async def _export_connections(self, connections: list) -> None:
        """Export connections to database."""
        for connection in connections:
            coords = connection.get("coordinates")
            wkt = coords.wkt if coords else None
            
            connection_obj = Connection(
                connection_id=connection.get("connection_id"),
                shelf_id=connection.get("shelf_id"),
                corridor_id=connection.get("corridor_id"),
                connection_point_id=connection.get("connection_point_id"),
                connection_coordinates=wkt
            )
            self.session.add(connection_obj)
        
        await self.session.commit()
    
    async def _export_connection_points(self, connection_points: list) -> None:
        """Export connection points to database."""
        for cp in connection_points:
            coords = cp.get("coordinates")
            wkt = coords.wkt if coords else None
            
            cp_obj = ConnectionPoint(
                point_id=cp.get("point_id"),
                connection_point_id=cp.get("connection_point_id", cp.get("point_id")),
                corridor_id=cp.get("corridor_id"),
                connection_point_coordinates=wkt
            )
            self.session.add(cp_obj)
        
        await self.session.commit()
    
    async def get_corridors(self) -> list:
        """Retrieve all corridors from database."""
        result = await self.session.execute(text("SELECT * FROM corridors;"))
        return result.fetchall()
    
    async def get_shelves(self) -> list:
        """Retrieve all shelves from database."""
        result = await self.session.execute(text("SELECT * FROM shelves;"))
        return result.fetchall()
    
    async def get_corridors_wkt(self) -> list:
        """Retrieve all corridors from database with coordinates as WKT."""
        result = await self.session.execute(
            text("SELECT corridor_id, name, ST_AsText(coordinates) as coordinates_wkt FROM corridors;")
        )
        return result.fetchall()
    
    async def get_shelves_wkt(self) -> list:
        """Retrieve all shelves from database with coordinates as WKT."""
        result = await self.session.execute(
            text("SELECT shelf_id, name, ST_AsText(coordinates) as coordinates_wkt FROM shelves;")
        )
        return result.fetchall()
    
    async def get_connection_points_wkt(self) -> list:
        """Retrieve all connection points from database with coordinates as WKT."""
        result = await self.session.execute(
            text("SELECT point_id, connection_point_id, corridor_id, ST_AsText(connection_point_coordinates) as coordinates_wkt FROM connection_points;")
        )
        return result.fetchall()
    
    async def get_connections_wkt(self) -> list:
        """Retrieve all connections from database with coordinates as WKT."""
        result = await self.session.execute(
            text("SELECT connection_id, shelf_id, corridor_id, connection_point_id, ST_AsText(connection_coordinates) as coordinates_wkt FROM connections;")
        )
        return result.fetchall()


async def generate_and_export(session: AsyncSession, config=None) -> dict:
    """Convenience function to generate warehouse map and export to database.
    
    Args:
        session: Database session
        config: Optional configuration (will use default if not provided)
    
    Returns:
        Statistics about the generated warehouse map
    """
    from app.navigation.warehouse_generator import WarehouseGenerator
    
    if config is None:
        from app.navigation.config import Config
        config = Config()
    
    # Generate warehouse map
    generator = WarehouseGenerator(config)
    warehouse_map = generator.generate()
    
    # Export to database
    exporter = PostGISExporter(session)
    await exporter.export(warehouse_map)
    
    return generator.get_statistics(warehouse_map)
