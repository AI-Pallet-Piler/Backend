"""PostGIS database exporter for warehouse maps - async version."""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import shapely
import shapely.wkb

from app.models.models import Corridor, Shelf, Connection, ConnectionPoint
from app.navigation.config import DatabaseConfig


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
        """Clear all data from tables."""
        # Delete shelf_paths first to avoid FK issues with shelves
        await self.session.execute(text("DELETE FROM shelf_paths;"))
        await self.session.commit()
        
        await self.session.execute(text("DELETE FROM connection_points;"))
        await self.session.execute(text("DELETE FROM connections;"))
        await self.session.execute(text("DELETE FROM shelves;"))
        await self.session.execute(text("DELETE FROM corridors;"))
        await self.session.commit()
    
    async def _export_corridors(self, corridors: list) -> None:
        """Export corridors to database."""
        for corridor in corridors:
            coordinates = corridor.get("coordinates")
            wkb = coordinates.wkb if coordinates else None
            
            corridor_obj = Corridor(
                corridor_id=corridor.get("corridor_id"),
                name=corridor.get("name", ""),
                coordinates=wkb
            )
            self.session.add(corridor_obj)
        
        await self.session.commit()
    
    async def _export_shelves(self, shelves: list) -> None:
        """Export shelves to database."""
        for shelf in shelves:
            coordinates = shelf.get("coordinates")
            wkb = coordinates.wkb if coordinates else None
            
            shelf_obj = Shelf(
                shelf_id=shelf.get("shelf_id"),
                name=shelf.get("name", ""),
                coordinates=wkb
            )
            self.session.add(shelf_obj)
        
        await self.session.commit()
    
    async def _export_connections(self, connections: list) -> None:
        """Export connections to database."""
        for connection in connections:
            coords = connection.get("coordinates")
            wkb = coords.wkb if coords else None
            
            connection_obj = Connection(
                connection_id=connection.get("connection_id"),
                shelf_id=connection.get("shelf_id"),
                corridor_id=connection.get("corridor_id"),
                connection_point_id=connection.get("connection_point_id"),
                connection_coordinates=wkb
            )
            self.session.add(connection_obj)
        
        await self.session.commit()
    
    async def _export_connection_points(self, connection_points: list) -> None:
        """Export connection points to database."""
        for cp in connection_points:
            coords = cp.get("coordinates")
            wkb = coords.wkb if coords else None
            
            cp_obj = ConnectionPoint(
                point_id=cp.get("point_id"),
                connection_point_id=cp.get("connection_point_id", cp.get("point_id")),
                corridor_id=cp.get("corridor_id"),
                connection_point_coordinates=wkb
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
