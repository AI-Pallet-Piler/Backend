"""SQLModel-based data models for warehouse map components.

This module provides models that work with both PostGIS database and GeoJSON serialization.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship
from shapely.geometry import Point, LineString, Polygon
from geopandas import GeoDataFrame
import geojson


class Corridor(SQLModel, table=True):
    """Represents a corridor in the warehouse (Black in visualization)."""
    __tablename__ = "corridors"
    
    corridor_id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    coordinates: bytes = Field(default=None, sa_column_kwargs={"nullable": True})  # PostGIS geometry (WKB)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    connections: List["Connection"] = Relationship(back_populates="corridor_obj")
    connection_points: List["ConnectionPoint"] = Relationship(back_populates="corridor_obj")
    
    @property
    def geometry(self) -> LineString:
        """Return Shapely geometry from WKB."""
        if self.coordinates:
            import shapely
            return shapely.wkb.loads(self.coordinates)
        return None
    
    @geometry.setter
    def geometry(self, value: LineString):
        """Set geometry as WKB."""
        if value:
            self.coordinates = value.wkb
        else:
            self.coordinates = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GeoDataFrame."""
        return {
            "corridor_id": self.corridor_id,
            "name": self.name,
            "geometry": self.geometry,
            "type": "corridor"
        }
    
    def to_geojson(self) -> dict:
        """Convert to GeoJSON feature."""
        geom = self.geometry
        if geom:
            return geojson.Feature(
                properties={
                    "corridor_id": self.corridor_id,
                    "name": self.name,
                    "type": "corridor"
                },
                geometry=geojson.loads(geom.__geo_interface__) if geom else None,
                id=self.corridor_id
            )
        return None


class Shelf(SQLModel, table=True):
    """Represents a shelf in the warehouse (Blue in visualization)."""
    __tablename__ = "shelves"
    
    shelf_id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    coordinates: bytes = Field(default=None, sa_column_kwargs={"nullable": True})  # PostGIS geometry (WKB)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    connections: List["Connection"] = Relationship(back_populates="shelf_obj")
    
    @property
    def geometry(self) -> Polygon:
        """Return Shapely geometry from WKB."""
        if self.coordinates:
            import shapely
            return shapely.wkb.loads(self.coordinates)
        return None
    
    @geometry.setter
    def geometry(self, value: Polygon):
        """Set geometry as WKB."""
        if value:
            self.coordinates = value.wkb
        else:
            self.coordinates = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GeoDataFrame."""
        return {
            "shelf_id": self.shelf_id,
            "name": self.name,
            "geometry": self.geometry,
            "type": "shelf"
        }
    
    def to_geojson(self) -> dict:
        """Convert to GeoJSON feature."""
        geom = self.geometry
        if geom:
            return geojson.Feature(
                properties={
                    "shelf_id": self.shelf_id,
                    "name": self.name,
                    "type": "shelf"
                },
                geometry=geojson.loads(geom.__geo_interface__) if geom else None,
                id=self.shelf_id
            )
        return None


class ConnectionPoint(SQLModel, table=True):
    """Represents the connection point where shelf meets corridor (Red in visualization)."""
    __tablename__ = "connection_points"
    
    point_id: Optional[int] = Field(default=None, primary_key=True)
    connection_point_id: int
    corridor_id: Optional[int] = Field(default=None, foreign_key="corridors.corridor_id")
    connection_point_coordinates: bytes = Field(default=None, sa_column_kwargs={"nullable": True})  # PostGIS geometry (WKB)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    corridor_obj: "Corridor" = Relationship(back_populates="connection_points")
    
    @property
    def geometry(self) -> Point:
        """Return Shapely geometry from WKB."""
        if self.connection_point_coordinates:
            import shapely
            return shapely.wkb.loads(self.connection_point_coordinates)
        return None
    
    @geometry.setter
    def geometry(self, value: Point):
        """Set geometry as WKB."""
        if value:
            self.connection_point_coordinates = value.wkb
        else:
            self.connection_point_coordinates = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GeoDataFrame."""
        return {
            "point_id": self.point_id,
            "connection_point_id": self.connection_point_id,
            "corridor_id": self.corridor_id,
            "geometry": self.geometry,
            "type": "connection_point"
        }
    
    def to_geojson(self) -> dict:
        """Convert to GeoJSON feature."""
        geom = self.geometry
        if geom:
            return geojson.Feature(
                properties={
                    "point_id": self.point_id,
                    "connection_point_id": self.connection_point_id,
                    "corridor_id": self.corridor_id,
                    "type": "connection_point"
                },
                geometry=geojson.loads(geom.__geo_interface__) if geom else None,
                id=self.point_id
            )
        return None


class Connection(SQLModel, table=True):
    """Represents the connection from shelf to corridor (Grey in visualization)."""
    __tablename__ = "connections"
    
    connection_id: Optional[int] = Field(default=None, primary_key=True)
    shelf_id: Optional[int] = Field(default=None, foreign_key="shelves.shelf_id")
    corridor_id: Optional[int] = Field(default=None, foreign_key="corridors.corridor_id")
    connection_point_id: Optional[int] = Field(default=None)
    connection_coordinates: bytes = Field(default=None, sa_column_kwargs={"nullable": True})  # PostGIS geometry (WKB)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    shelf_obj: "Shelf" = Relationship(back_populates="connections")
    corridor_obj: "Corridor" = Relationship(back_populates="connections")
    
    @property
    def geometry(self) -> LineString:
        """Return Shapely geometry from WKB."""
        if self.connection_coordinates:
            import shapely
            return shapely.wkb.loads(self.connection_coordinates)
        return None
    
    @geometry.setter
    def geometry(self, value: LineString):
        """Set geometry as WKB."""
        if value:
            self.connection_coordinates = value.wkb
        else:
            self.connection_coordinates = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GeoDataFrame."""
        return {
            "connection_id": self.connection_id,
            "shelf_id": self.shelf_id,
            "corridor_id": self.corridor_id,
            "connection_point_id": self.connection_point_id,
            "geometry": self.geometry,
            "type": "connection"
        }
    
    def to_geojson(self) -> dict:
        """Convert to GeoJSON feature."""
        geom = self.geometry
        if geom:
            return geojson.Feature(
                properties={
                    "connection_id": self.connection_id,
                    "shelf_id": self.shelf_id,
                    "corridor_id": self.corridor_id,
                    "connection_point_id": self.connection_point_id,
                    "type": "connection"
                },
                geometry=geojson.loads(geom.__geo_interface__) if geom else None,
                id=self.connection_id
            )
        return None


class WarehouseMap:
    """Container for all warehouse map components (non-database, in-memory)."""
    
    def __init__(
        self,
        corridors: List[Corridor] = None,
        shelves: List[Shelf] = None,
        connections: List[Connection] = None,
        connection_points: List[ConnectionPoint] = None
    ):
        self.corridors = corridors or []
        self.shelves = shelves or []
        self.connections = connections or []
        self.connection_points = connection_points or []
    
    def to_geo_dataframes(self) -> Dict[str, GeoDataFrame]:
        """Convert all components to GeoDataFrames."""
        geo_df = {}
        
        if self.corridors:
            geo_df["corridors"] = GeoDataFrame(
                [s.to_dict() for s in self.corridors if s.to_dict()["geometry"]],
                crs="EPSG:4326"
            )
        
        if self.shelves:
            geo_df["shelves"] = GeoDataFrame(
                [h.to_dict() for h in self.shelves if h.to_dict()["geometry"]],
                crs="EPSG:4326"
            )
        
        if self.connections:
            geo_df["connections"] = GeoDataFrame(
                [c.to_dict() for c in self.connections if c.to_dict()["geometry"]],
                crs="EPSG:4326"
            )
        
        if self.connection_points:
            geo_df["connection_points"] = GeoDataFrame(
                [cp.to_dict() for cp in self.connection_points if cp.to_dict()["geometry"]],
                crs="EPSG:4326"
            )
        
        return geo_df
    
    def to_geojson(self) -> dict:
        """Convert entire warehouse map to GeoJSON FeatureCollection."""
        features = []
        
        for corridor in self.corridors:
            feat = corridor.to_geojson()
            if feat:
                features.append(feat)
        
        for shelf in self.shelves:
            feat = shelf.to_geojson()
            if feat:
                features.append(feat)
        
        for connection in self.connections:
            feat = connection.to_geojson()
            if feat:
                features.append(feat)
        
        for cp in self.connection_points:
            feat = cp.to_geojson()
            if feat:
                features.append(feat)
        
        return geojson.FeatureCollection(features)
    
    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about the warehouse map."""
        return {
            "num_corridors": len(self.corridors),
            "num_shelves": len(self.shelves),
            "num_connections": len(self.connections),
            "num_connection_points": len(self.connection_points),
        }
    
    def summary(self) -> str:
        """Get a summary string of the warehouse map."""
        stats = self.get_statistics()
        return (
            f"Warehouse Map Summary:\n"
            f"  - Corridors: {stats['num_corridors']}\n"
            f"  - Shelves: {stats['num_shelves']}\n"
            f"  - Connections: {stats['num_connections']}\n"
            f"  - Connection Points: {stats['num_connection_points']}"
        )
