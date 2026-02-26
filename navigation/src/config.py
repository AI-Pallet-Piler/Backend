"""Configuration management for warehouse map generation."""

from pathlib import Path
from typing import Optional, Union, List
from pydantic import BaseModel, Field
import yaml


class WarehouseConfig(BaseModel):
    """Warehouse dimension configuration."""
    name: str = "Sample Warehouse"
    width: float = 100.0
    height: float = 80.0


class CorridorConfig(BaseModel):
    """Corridor layout configuration."""
    width: float = 2.0
    horizontal_count: int = 3
    vertical_count: int = 4
    spacing: float = 20.0
    offset_x: float = 10.0
    offset_y: float = 10.0
    # NEW: Disable shelves on specific corridor directions
    disable_horizontal_shelves: bool = False  # No shelves on ANY horizontal corridor
    disable_vertical_shelves: bool = False     # No shelves on ANY vertical corridor
    # NEW: Variable spacing for non-grid layouts (rectangular cells)
    # Can be a single float (same spacing for all) or list (different per corridor)
    horizontal_spacing: Union[float, List[float]] = 0.0  # 0.0 means use default spacing
    vertical_spacing: Union[float, List[float]] = 0.0    # 0.0 means use default spacing


class ShelfConfig(BaseModel):
    """Shelf placement configuration."""
    width: float = 1.5
    height: float = 0.8
    count_per_segment: int = 4
    spacing: float = 3.0


class VisualizationConfig(BaseModel):
    """Visual styling configuration."""
    corridor_color: str = "#000000"  # Black
    shelf_color: str = "#0000FF"     # Blue
    connection_color: str = "#808080"  # Grey
    connection_point_color: str = "#FF0000"  # Red
    show_labels: bool = True


class DatabaseConfig(BaseModel):
    """PostGIS database connection configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "interior_map"
    user: str = "postgres"
    password: str = "postgres"


class Config(BaseModel):
    """Main configuration container."""
    warehouse: WarehouseConfig = Field(default_factory=WarehouseConfig)
    corridors: CorridorConfig = Field(default_factory=CorridorConfig)
    shelves: ShelfConfig = Field(default_factory=ShelfConfig)
    visualization: VisualizationConfig = Field(default_factory=VisualizationConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Create Config from dictionary."""
        return cls(
            warehouse=WarehouseConfig(**data.get("warehouse", {})),
            corridors=CorridorConfig(**data.get("corridors", {})),
            shelves=ShelfConfig(**data.get("shelves", {})),
            visualization=VisualizationConfig(**data.get("visualization", {})),
            database=DatabaseConfig(**data.get("database", {})),
        )
    
    @classmethod
    def from_yaml(cls, path: Union[Path, str]) -> "Config":
        """Load configuration from YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        
        return cls.from_dict(data)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "warehouse": {
                "name": self.warehouse.name,
                "width": self.warehouse.width,
                "height": self.warehouse.height,
            },
            "corridors": {
                "width": self.corridors.width,
                "horizontal_count": self.corridors.horizontal_count,
                "vertical_count": self.corridors.vertical_count,
                "spacing": self.corridors.spacing,
                "offset_x": self.corridors.offset_x,
                "offset_y": self.corridors.offset_y,
                "disable_horizontal_shelves": self.corridors.disable_horizontal_shelves,
                "disable_vertical_shelves": self.corridors.disable_vertical_shelves,
                "horizontal_spacing": self.corridors.horizontal_spacing,
                "vertical_spacing": self.corridors.vertical_spacing,
            },
            "shelves": {
                "width": self.shelves.width,
                "height": self.shelves.height,
                "count_per_segment": self.shelves.count_per_segment,
                "spacing": self.shelves.spacing,
            },
            "visualization": {
                "corridor_color": self.visualization.corridor_color,
                "shelf_color": self.visualization.shelf_color,
                "connection_color": self.visualization.connection_color,
                "connection_point_color": self.visualization.connection_point_color,
                "show_labels": self.visualization.show_labels,
            },
            "database": {
                "host": self.database.host,
                "port": self.database.port,
                "database": self.database.database,
                "user": self.database.user,
                "password": self.database.password,
            },
        }


def load_config(path: Optional[Union[Path, str]] = None) -> Config:
    """Load configuration from file or return defaults."""
    if path is None:
        # Try default locations
        default_paths = [
            Path("data/warehouse_config.yaml"),
            Path("config/warehouse_config.yaml"),
            Path("warehouse_config.yaml"),
        ]
        for default_path in default_paths:
            if default_path.exists():
                return Config.from_yaml(default_path)
        return Config()
    
    return Config.from_yaml(path)


# Default configuration instance
DEFAULT_CONFIG = Config()
