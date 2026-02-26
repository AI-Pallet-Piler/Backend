"""Data models for warehouse map components."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from shapely.geometry import Point, LineString, Polygon
from geopandas import GeoDataFrame


class Corridor(BaseModel):
    """Represents a corridor in the warehouse (Black in visualization)."""
    model_config = {"arbitrary_types_allowed": True}
    
    corridor_id: int
    name: str
    coordinates: LineString
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GeoDataFrame."""
        return {
            "corridor_id": self.corridor_id,
            "name": self.name,
            "geometry": self.coordinates,
            "type": "corridor"
        }
    
    @property
    def geometry(self) -> LineString:
        return self.coordinates


class Shelf(BaseModel):
    """Represents a shelf in the warehouse (Blue in visualization)."""
    model_config = {"arbitrary_types_allowed": True}
    
    shelf_id: int
    name: str
    coordinates: Polygon
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GeoDataFrame."""
        return {
            "shelf_id": self.shelf_id,
            "name": self.name,
            "geometry": self.coordinates,
            "type": "shelf"
        }
    
    @property
    def geometry(self) -> Polygon:
        return self.coordinates


class ConnectionPoint(BaseModel):
    """Represents the connection point where shelf meets corridor (Red in visualization)."""
    model_config = {"arbitrary_types_allowed": True}
    
    point_id: int
    coordinates: Point
    corridor_id: int
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GeoDataFrame."""
        return {
            "point_id": self.point_id,
            "corridor_id": self.corridor_id,
            "geometry": self.coordinates,
            "type": "connection_point"
        }
    
    @property
    def geometry(self) -> Point:
        return self.coordinates


class Connection(BaseModel):
    """Represents the connection from shelf to corridor (Grey in visualization)."""
    model_config = {"arbitrary_types_allowed": True}
    
    connection_id: int
    shelf_id: int
    corridor_id: int
    connection_point_id: int
    coordinates: LineString
    
    def to_dict(self) -> dict:
        """Convert to dictionary for GeoDataFrame."""
        return {
            "connection_id": self.connection_id,
            "shelf_id": self.shelf_id,
            "corridor_id": self.corridor_id,
            "connection_point_id": self.connection_point_id,
            "geometry": self.coordinates,
            "type": "connection"
        }
    
    @property
    def geometry(self) -> LineString:
        return self.coordinates


class WarehouseMap(BaseModel):
    """Container for all warehouse map components."""
    model_config = {"arbitrary_types_allowed": True}
    
    corridors: List[Corridor] = Field(default_factory=list)
    shelves: List[Shelf] = Field(default_factory=list)
    connections: List[Connection] = Field(default_factory=list)
    connection_points: List[ConnectionPoint] = Field(default_factory=list)
    
    def to_geo_dataframes(self) -> Dict[str, GeoDataFrame]:
        """Convert all components to GeoDataFrames."""
        geo_df = {}
        
        if self.corridors:
            geo_df["corridors"] = GeoDataFrame(
                [s.to_dict() for s in self.corridors],
                crs="EPSG:4326"
            )
        
        if self.shelves:
            geo_df["shelves"] = GeoDataFrame(
                [h.to_dict() for h in self.shelves],
                crs="EPSG:4326"
            )
        
        if self.connections:
            geo_df["connections"] = GeoDataFrame(
                [c.to_dict() for c in self.connections],
                crs="EPSG:4326"
            )
        
        if self.connection_points:
            geo_df["connection_points"] = GeoDataFrame(
                [cp.to_dict() for cp in self.connection_points],
                crs="EPSG:4326"
            )
        
        return geo_df
    
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
