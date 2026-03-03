"""Configuration management for warehouse map generation."""

from pathlib import Path
from typing import Optional, Union, List
from pydantic import BaseModel, Field
import yaml
import os


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
    disable_horizontal_shelves: bool = False
    disable_vertical_shelves: bool = False
    horizontal_spacing: Union[float, List[float]] = 0.0
    vertical_spacing: Union[float, List[float]] = 0.0


class ShelfConfig(BaseModel):
    """Shelf placement configuration."""
    width: float = 1.5
    height: float = 0.8
    count_per_segment: int = 4
    spacing: float = 3.0


class VisualizationConfig(BaseModel):
    """Visual styling configuration."""
    corridor_color: str = "#000000"
    shelf_color: str = "#0000FF"
    connection_color: str = "#808080"
    connection_point_color: str = "#FF0000"
    show_labels: bool = True


class DatabaseConfig(BaseModel):
    """PostGIS database connection configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "backend"
    user: str = "postgres"
    password: str = "postgres"
    
    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Create config from environment variables."""
        return cls(
            host=os.getenv("POSTGIS_HOST", "localhost"),
            port=int(os.getenv("POSTGIS_PORT", "5432")),
            database=os.getenv("POSTGIS_DATABASE", "backend"),
            user=os.getenv("POSTGIS_USER", "postgres"),
            password=os.getenv("POSTGIS_PASSWORD", "postgres"),
        )


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
    """Load configuration from file, environment, or return defaults."""
    if path is not None:
        return Config.from_yaml(path)
    
    # Try default locations
    default_paths = [
        Path("data/warehouse_config.yaml"),
        Path("config/warehouse_config.yaml"),
        Path("navigation/data/warehouse_config.yaml"),
        Path("app/navigation/data/warehouse_config.yaml"),
    ]
    for default_path in default_paths:
        if default_path.exists():
            return Config.from_yaml(default_path)
    
    # Try environment variables
    return Config(database=DatabaseConfig.from_env())


# Default configuration instance
DEFAULT_CONFIG = Config()
