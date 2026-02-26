"""Visualization module for warehouse maps."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from typing import Optional

import geopandas as gpd

from src.models import WarehouseMap
from src.config import Config


def visualize_warehouse(
    warehouse_map: WarehouseMap,
    config: Optional[Config] = None,
    output_path: Optional[Path | str] = None,
    show_plot: bool = True
) -> None:
    """Visualize the warehouse map with color-coded components.
    
    Args:
        warehouse_map: The warehouse map to visualize
        config: Configuration for visualization styling
        output_path: Optional path to save the figure
        show_plot: Whether to display the plot
    """
    config = config or Config()
    vis_config = config.visualization
    
    # Create figure and axis
    fig, ax = plt.subplots(figsize=(12, 10))
    
    # Set axis limits based on warehouse dimensions
    ax.set_xlim(-5, config.warehouse.width + 5)
    ax.set_ylim(-5, config.warehouse.height + 5)
    
    # Get GeoDataFrames
    gdfs = warehouse_map.to_geo_dataframes()
    
    # Plot corridors - Black
    if "corridors" in gdfs:
        gdfs["corridors"].plot(
            ax=ax,
            color=vis_config.corridor_color,
            linewidth=3,
            label="Corridors"
        )
    
    # Plot connections - Grey
    if "connections" in gdfs:
        gdfs["connections"].plot(
            ax=ax,
            color=vis_config.connection_color,
            linewidth=1.5,
            linestyle="-",
            label="Connections"
        )
    
    # Plot connection points - Red
    if "connection_points" in gdfs:
        gdfs["connection_points"].plot(
            ax=ax,
            color=vis_config.connection_point_color,
            markersize=50,
            marker="o",
            label="Connection Points"
        )
    
    # Plot shelves - Blue
    if "shelves" in gdfs:
        gdfs["shelves"].plot(
            ax=ax,
            color=vis_config.shelf_color,
            markersize=100,
            marker="s",
            label="Shelves"
        )
        
        # Add labels if enabled
        if vis_config.show_labels:
            for idx, row in gdfs["shelves"].iterrows():
                # Get centroid for polygon geometries
                geom = row.geometry
                if hasattr(geom, 'centroid'):
                    point = geom.centroid
                else:
                    point = geom
                ax.annotate(
                    row.get("name", f"{idx}"),
                    (point.x, point.y),
                    textcoords="offset points",
                    xytext=(5, 5),
                    fontsize=6,
                    color=vis_config.shelf_color
                )
    
    # Create legend
    legend_elements = [
        mpatches.Patch(color=vis_config.corridor_color, label="Corridors"),
        mpatches.Patch(color=vis_config.shelf_color, label="Shelves"),
        mpatches.Patch(color=vis_config.connection_color, label="Connections"),
        mpatches.Patch(color=vis_config.connection_point_color, label="Connection Points"),
    ]
    ax.legend(handles=legend_elements, loc="upper right")
    
    # Add title and labels
    ax.set_title(
        f"Warehouse Map: {config.warehouse.name}",
        fontsize=14,
        fontweight="bold"
    )
    ax.set_xlabel("X Coordinate")
    ax.set_ylabel("Y Coordinate")
    
    # Add grid
    ax.grid(True, linestyle="--", alpha=0.3)
    
    # Set aspect ratio
    ax.set_aspect("equal")
    
    # Adjust layout
    plt.tight_layout()
    
    # Save if output path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Map saved to: {output_path}")
    
    # Show if requested
    if show_plot:
        plt.show()
    else:
        plt.close()


def visualize_warehouse_simple(
    warehouse_map: WarehouseMap,
    config: Optional[Config] = None
) -> None:
    """Simple visualization without matplotlib display.
    
    This is useful for quick testing without GUI.
    """
    config = config or Config()
    
    print(f"\n{'='*50}")
    print(f"Warehouse Map Visualization")
    print(f"{'='*50}")
    print(f"Warehouse: {config.warehouse.name}")
    print(f"Dimensions: {config.warehouse.width} x {config.warehouse.height}")
    print()
    
    stats = warehouse_map.get_statistics()
    print(f"Statistics:")
    print(f"  - Corridors (Black): {stats['num_corridors']}")
    print(f"  - Shelves (Blue): {stats['num_shelves']}")
    print(f"  - Connections (Grey): {stats['num_connections']}")
    print(f"  - Connection Points (Red): {stats['num_connection_points']}")
    print()
    
    # Print sample data
    print("\nSample Corridors:")
    for corridor in warehouse_map.corridors[:3]:
        print(f"  - {corridor.name}: {corridor.coordinates}")
    
    print("\nSample Shelves:")
    for shelf in warehouse_map.shelves[:3]:
        # Handle both Point and Polygon geometries
        if hasattr(shelf.coordinates, 'centroid'):
            coords = f"centroid ({shelf.coordinates.centroid.x}, {shelf.coordinates.centroid.y})"
        else:
            coords = f"({shelf.coordinates.x}, {shelf.coordinates.y})"
        print(f"  - {shelf.name}: {coords}")


def export_to_geojson(
    warehouse_map: WarehouseMap,
    output_dir: Path | str,
    crs: str = "EPSG:4326"
) -> dict[str, Path]:
    """Export warehouse map components to GeoJSON files.
    
    Args:
        warehouse_map: The warehouse map to export
        output_dir: Directory to save GeoJSON files
        crs: Coordinate reference system
    
    Returns:
        Dictionary mapping component names to output file paths
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    gdfs = warehouse_map.to_geo_dataframes()
    output_paths = {}
    
    for name, gdf in gdfs.items():
        # Set CRS
        gdf = gdf.set_crs(crs, allow_override=True)
        
        # Save to file
        output_path = output_dir / f"{name}.geojson"
        gdf.to_file(output_path, driver="GeoJSON")
        output_paths[name] = output_path
        print(f"Exported {name} to: {output_path}")
    
    return output_paths
