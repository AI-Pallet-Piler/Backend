"""PostGIS database exporter for warehouse maps."""

from typing import Optional
from pathlib import Path
import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.models import WarehouseMap
from src.config import DatabaseConfig


class PostGISExporter:
    """Exporter for saving warehouse maps to PostGIS database."""
    
    def __init__(self, config: DatabaseConfig):
        """Initialize exporter with database configuration."""
        self.config = config
        self.engine = self._create_engine()
        self.Session = sessionmaker(bind=self.engine)
    
    def _create_engine(self):
        """Create SQLAlchemy engine for PostGIS."""
        connection_string = (
            f"postgresql://{self.config.user}:{self.config.password}"
            f"@{self.config.host}:{self.config.port}/{self.config.database}"
        )
        return create_engine(connection_string)
    
    def create_tables(self) -> None:
        """Create database tables if they don't exist."""
        # Enable PostGIS and pgrouting extensions
        with self.engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgrouting;"))
            conn.commit()
        
        # Create corridors table
        corridors_sql = """
        CREATE TABLE IF NOT EXISTS corridors (
            corridor_id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            coordinates GEOMETRY(LINESTRING, 4326)
        );
        """
        
        # Create shelves table
        shelves_sql = """
        CREATE TABLE IF NOT EXISTS shelves (
            shelf_id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            coordinates GEOMETRY(POLYGON, 4326)
        );
        """
        
        # Create connections table
        connections_sql = """
        CREATE TABLE IF NOT EXISTS connections (
            connection_id SERIAL PRIMARY KEY,
            shelf_id INTEGER REFERENCES shelves(shelf_id),
            corridor_id INTEGER REFERENCES corridors(corridor_id),
            connection_point_id INTEGER,
            connection_coordinates GEOMETRY(LINESTRING, 4326)
        );
        """
        
        # Create connection_points table
        connection_points_sql = """
        CREATE TABLE IF NOT EXISTS connection_points (
            point_id SERIAL PRIMARY KEY,
            connection_point_id INTEGER NOT NULL,
            corridor_id INTEGER REFERENCES corridors(corridor_id),
            connection_point_coordinates GEOMETRY(POINT, 4326)
        );
        """
        
        # Create spatial index for better performance
        index_sql = """
        CREATE INDEX IF NOT EXISTS idx_corridors_geometry ON corridors USING GIST(coordinates);
        CREATE INDEX IF NOT EXISTS idx_shelves_geometry ON shelves USING GIST(coordinates);
        CREATE INDEX IF NOT EXISTS idx_connections_geometry ON connections USING GIST(connection_coordinates);
        CREATE INDEX IF NOT EXISTS idx_connection_points_geometry ON connection_points USING GIST(connection_point_coordinates);
        """
        
        with self.engine.connect() as conn:
            conn.execute(text(corridors_sql))
            conn.execute(text(shelves_sql))
            conn.execute(text(connections_sql))
            conn.execute(text(connection_points_sql))
            conn.execute(text(index_sql))
            conn.commit()
        
        print("Database tables created successfully")
    
    def export(self, warehouse_map: WarehouseMap) -> None:
        """Export warehouse map to database."""
        # Clear existing data
        self._clear_tables()
        
        # Export corridors
        self._export_corridors(warehouse_map.corridors)
        
        # Export shelves
        self._export_shelves(warehouse_map.shelves)
        
        # Export connections
        self._export_connections(warehouse_map.connections)
        
        # Export connection_points
        self._export_connection_points(warehouse_map.connection_points)
        
        print(f"Exported {len(warehouse_map.corridors)} corridors")
        print(f"Exported {len(warehouse_map.shelves)} shelves")
        print(f"Exported {len(warehouse_map.connections)} connections")
        print(f"Exported {len(warehouse_map.connection_points)} connection points")
    
    def _clear_tables(self) -> None:
        """Clear all data from tables."""
        with self.engine.connect() as conn:
            conn.execute(text("DELETE FROM connection_points;"))
            conn.execute(text("DELETE FROM connections;"))
            conn.execute(text("DELETE FROM shelves;"))
            conn.execute(text("DELETE FROM corridors;"))
            conn.commit()
    
    def _export_corridors(self, corridors: list) -> None:
        """Export corridors to database."""
        for corridor in corridors:
            # Convert shapely geometry to WKT
            wkt_coords = corridor.coordinates.wkt
            
            with self.engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO corridors (corridor_id, name, coordinates)
                        VALUES (:corridor_id, :name, ST_GeomFromText(:coords, 4326))
                    """),
                    {
                        "corridor_id": corridor.corridor_id,
                        "name": corridor.name,
                        "coords": wkt_coords
                    }
                )
                conn.commit()
    
    def _export_shelves(self, shelves: list) -> None:
        """Export shelves to database."""
        for shelf in shelves:
            wkt_coords = shelf.coordinates.wkt
            
            with self.engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO shelves (shelf_id, name, coordinates)
                        VALUES (:shelf_id, :name, ST_GeomFromText(:coords, 4326))
                    """),
                    {
                        "shelf_id": shelf.shelf_id,
                        "name": shelf.name,
                        "coords": wkt_coords
                    }
                )
                conn.commit()
    
    def _export_connections(self, connections: list) -> None:
        """Export connections to database."""
        for connection in connections:
            wkt_conn_coords = connection.coordinates.wkt
            
            with self.engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO connections 
                        (connection_id, shelf_id, corridor_id, connection_point_id,
                         connection_coordinates)
                        VALUES (:conn_id, :shelf_id, :corridor_id, :point_id,
                                ST_GeomFromText(:conn_coords, 4326))
                    """),
                    {
                        "conn_id": connection.connection_id,
                        "shelf_id": connection.shelf_id,
                        "corridor_id": connection.corridor_id,
                        "point_id": connection.connection_point_id,
                        "conn_coords": wkt_conn_coords
                    }
                )
                conn.commit()
    
    def _export_connection_points(self, connection_points: list) -> None:
        """Export connection points to database."""
        for cp in connection_points:
            wkt_coords = cp.coordinates.wkt
            
            with self.engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO connection_points
                        (connection_point_id, corridor_id, connection_point_coordinates)
                        VALUES (:point_id, :corridor_id, ST_GeomFromText(:coords, 4326))
                    """),
                    {
                        "point_id": cp.point_id,
                        "corridor_id": cp.corridor_id,
                        "coords": wkt_coords
                    }
                )
                conn.commit()
    
    def get_corridors(self) -> list:
        """Retrieve all corridors from database."""
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM corridors;"))
            return result.fetchall()
    
    def get_shelves(self) -> list:
        """Retrieve all shelves from database."""
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM shelves;"))
            return result.fetchall()
    
    def get_connections(self) -> list:
        """Retrieve all connections from database."""
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM connections;"))
            return result.fetchall()


def export_to_postgis(
    warehouse_map: WarehouseMap,
    config: DatabaseConfig,
    create_tables: bool = True
) -> PostGISExporter:
    """Convenience function to export warehouse map to PostGIS.
    
    Args:
        warehouse_map: The warehouse map to export
        config: Database configuration
        create_tables: Whether to create tables if they don't exist
    
    Returns:
        PostGISExporter instance
    """
    exporter = PostGISExporter(config)
    
    if create_tables:
        exporter.create_tables()
    
    exporter.export(warehouse_map)
    
    return exporter
