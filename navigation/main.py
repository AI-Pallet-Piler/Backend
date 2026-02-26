"""Main entry point for warehouse map generation.

This script demonstrates the complete workflow:
1. Load configuration from YAML
2. Generate warehouse map with corridors and shelves
3. Visualize the map
4. Export to PostGIS database (optional)
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.config import load_config, Config
from src.warehouse_generator import WarehouseGenerator
from src.visualization import visualize_warehouse, visualize_warehouse_simple, export_to_geojson
from src.postgis_exporter import export_to_postgis


def main():
    """Main function to run the warehouse map generation."""
    print("=" * 60)
    print("Warehouse Map Generation")
    print("=" * 60)
    
    # Load configuration
    config_path = Path("data/warehouse_config.yaml")
    print(f"\nLoading configuration from: {config_path}")
    config = load_config(config_path)
    
    print(f"\nWarehouse: {config.warehouse.name}")
    print(f"Dimensions: {config.warehouse.width} x {config.warehouse.height}")
    print(f"Corridors: {config.corridors.horizontal_count} horizontal, {config.corridors.vertical_count} vertical")
    
    # Generate warehouse map
    print("\nGenerating warehouse map...")
    generator = WarehouseGenerator(config)
    warehouse_map = generator.generate()
    
    # Print summary
    print(warehouse_map.summary())
    
    # Export to GeoJSON
    print("\nExporting to GeoJSON...")
    output_dir = Path("output")
    export_to_geojson(warehouse_map, output_dir)
    
    # Visualize (text-based for terminal)
    visualize_warehouse_simple(warehouse_map, config)
    
    # Export to PostGIS
    print("\nExporting to PostGIS...")
    try:
        exporter = export_to_postgis(warehouse_map, config.database)
        print("Successfully exported to PostGIS!")
    except Exception as e:
        print(f"PostGIS export failed: {e}")
        print("Make sure PostGIS is running (docker-compose up -d postgis)")
    
    # Visualize with matplotlib (set show_plot=True to display)
    print("\nGenerating visualization...")
    visualize_warehouse(
        warehouse_map, 
        config, 
        output_path="output/warehouse_map.png",
        show_plot=False  # Set to True to display interactive plot
    )
    
    print("\n" + "=" * 60)
    print("Generation complete!")
    print("=" * 60)
    print(f"\nOutput files:")
    print(f"  - GeoJSON: output/streets.geojson")
    print(f"  - GeoJSON: output/houses.geojson")
    print(f"  - GeoJSON: output/connections.geojson")
    print(f"  - GeoJSON: output/connection_points.geojson")
    print(f"  - Image: output/warehouse_map.png")


if __name__ == "__main__":
    main()
