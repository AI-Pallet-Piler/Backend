"""Warehouse map generator with grid-based layout algorithm."""

from typing import Optional
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import nearest_points

from src.models import Corridor, Shelf, Connection, ConnectionPoint, WarehouseMap
from src.config import Config, CorridorConfig, ShelfConfig


def _create_polygon_from_center(center_x: float, center_y: float, width: float, height: float) -> Polygon:
    """Create a polygon rectangle from center point and dimensions."""
    min_x = center_x - width / 2
    max_x = center_x + width / 2
    min_y = center_y - height / 2
    max_y = center_y + height / 2
    
    return Polygon([
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
        (min_x, min_y)
    ])


class WarehouseGenerator:
    """Generates warehouse maps with configurable grid-based layouts."""
    
    def __init__(self, config: Optional[Config] = None):
        """Initialize generator with configuration."""
        self.config = config or Config()
        self.corridor_config: CorridorConfig = self.config.corridors
        self.shelf_config: ShelfConfig = self.config.shelves
    
    def generate(self) -> WarehouseMap:
        """Generate complete warehouse map."""
        warehouse_map = WarehouseMap()
        
        # Generate corridors
        warehouse_map.corridors = self._generate_corridors()
        
        # Generate shelves along corridors
        warehouse_map.shelves = self._place_shelves(warehouse_map.corridors)
        
        # Generate connections from shelves to corridors
        connections_data = self._create_connections(
            warehouse_map.shelves, 
            warehouse_map.corridors
        )
        warehouse_map.connections = connections_data["connections"]
        warehouse_map.connection_points = connections_data["connection_points"]
        
        return warehouse_map
    
    def _generate_corridors(self) -> list[Corridor]:
        """Generate corridor paths based on grid layout."""
        corridors = []
        corridor_id = 1
        
        # Get corridor positions
        h_positions = self._get_horizontal_positions()
        v_positions = self._get_vertical_positions()
        
        # Generate horizontal corridors
        for y in h_positions:
            coords = [
                (0, y),
                (self.config.warehouse.width, y)
            ]
            line = LineString(coords)
            corridor = Corridor(
                corridor_id=corridor_id,
                name=f"Horizontal Corridor {corridor_id}",
                coordinates=line
            )
            corridors.append(corridor)
            corridor_id += 1
        
        # Generate vertical corridors
        for x in v_positions:
            coords = [
                (x, 0),
                (x, self.config.warehouse.height)
            ]
            line = LineString(coords)
            corridor = Corridor(
                corridor_id=corridor_id,
                name=f"Vertical Corridor {corridor_id}",
                coordinates=line
            )
            corridors.append(corridor)
            corridor_id += 1
        
        return corridors
    
    def _get_horizontal_positions(self) -> list[float]:
        """Calculate Y positions for horizontal corridors."""
        config = self.corridor_config
        positions = []
        
        # Calculate starting position
        start_y = config.offset_y
        
        # Check if variable spacing is configured
        use_custom_spacing = (
            isinstance(config.horizontal_spacing, list) and len(config.horizontal_spacing) > 0
        ) or (
            isinstance(config.horizontal_spacing, (int, float)) and config.horizontal_spacing > 0
        )
        
        if use_custom_spacing:
            # Use custom spacing from configuration
            if isinstance(config.horizontal_spacing, (int, float)):
                # Single float - use same spacing for all
                spacing = config.horizontal_spacing
                for i in range(config.horizontal_count):
                    y = start_y + (i * spacing)
                    if y <= self.config.warehouse.height:
                        positions.append(y)
            else:
                # List - use per-row spacing
                for i, spacing in enumerate(config.horizontal_spacing):
                    if i < config.horizontal_count:
                        y = start_y + (i * spacing) if i == 0 else positions[-1] + spacing
                        if y <= self.config.warehouse.height:
                            positions.append(y)
                # Fill remaining positions with default spacing if needed
                for i in range(len(positions), config.horizontal_count):
                    y = positions[-1] + config.spacing
                    if y <= self.config.warehouse.height:
                        positions.append(y)
        else:
            # Use uniform spacing (default behavior)
            for i in range(config.horizontal_count):
                y = start_y + (i * config.spacing)
                if y <= self.config.warehouse.height:
                    positions.append(y)
        
        return positions
    
    def _get_vertical_positions(self) -> list[float]:
        """Calculate X positions for vertical corridors."""
        config = self.corridor_config
        positions = []
        
        # Calculate starting position
        start_x = config.offset_x
        
        # Check if variable spacing is configured
        use_custom_spacing = (
            isinstance(config.vertical_spacing, list) and len(config.vertical_spacing) > 0
        ) or (
            isinstance(config.vertical_spacing, (int, float)) and config.vertical_spacing > 0
        )
        
        if use_custom_spacing:
            # Use custom spacing from configuration
            if isinstance(config.vertical_spacing, (int, float)):
                # Single float - use same spacing for all
                spacing = config.vertical_spacing
                for i in range(config.vertical_count):
                    x = start_x + (i * spacing)
                    if x <= self.config.warehouse.width:
                        positions.append(x)
            else:
                # List - use per-column spacing
                for i, spacing in enumerate(config.vertical_spacing):
                    if i < config.vertical_count:
                        x = start_x + (i * spacing) if i == 0 else positions[-1] + spacing
                        if x <= self.config.warehouse.width:
                            positions.append(x)
                # Fill remaining positions with default spacing if needed
                for i in range(len(positions), config.vertical_count):
                    x = positions[-1] + config.spacing
                    if x <= self.config.warehouse.width:
                        positions.append(x)
        else:
            # Use uniform spacing (default behavior)
            for i in range(config.vertical_count):
                x = start_x + (i * config.spacing)
                if x <= self.config.warehouse.width:
                    positions.append(x)
        
        return positions
    
    def _place_shelves(self, corridors: list[Corridor]) -> list[Shelf]:
        """Place shelves along corridor segments."""
        shelves = []
        shelf_id = 1
        config = self.shelf_config
        
        # Pre-build buffered corridor polygons for collision detection
        from shapely.ops import unary_union
        corridor_buffer = self.corridor_config.width / 2
        buffered_corridors = []
        for corridor in corridors:
            buffered = corridor.coordinates.buffer(corridor_buffer)
            buffered_corridors.append(buffered)
        combined_corridors = unary_union(buffered_corridors)
        
        for corridor in corridors:
            # Determine if horizontal or vertical corridor by checking Y coordinates
            # Horizontal corridor: y1 == y2 (same Y at both ends)
            # Vertical corridor: x1 == x2 (same X at both ends)
            is_horizontal = corridor.coordinates.xy[1][0] == corridor.coordinates.xy[1][1]
            
            # Check if shelves should be disabled for this corridor direction
            if is_horizontal and self.corridor_config.disable_horizontal_shelves:
                # Skip placing shelves on horizontal corridors
                continue
            elif not is_horizontal and self.corridor_config.disable_vertical_shelves:
                # Skip placing shelves on vertical corridors
                continue
            
            if is_horizontal:
                # Horizontal corridor - place shelves above and below
                shelves.extend(
                    self._place_shelves_on_horizontal_corridor(
                        corridor, shelf_id, config, combined_corridors
                    )
                )
                shelf_id = len(shelves) + 1
            else:
                # Vertical corridor - place shelves to left and right
                shelves.extend(
                    self._place_shelves_on_vertical_corridor(
                        corridor, shelf_id, config, combined_corridors
                    )
                )
                shelf_id = len(shelves) + 1
        
        return shelves
    
    def _place_shelves_on_horizontal_corridor(
        self, 
        corridor: Corridor, 
        start_id: int,
        config: ShelfConfig,
        combined_corridors
    ) -> list[Shelf]:
        """Place shelves along a horizontal corridor."""
        shelves = []
        shelf_id = start_id
        
        y = corridor.coordinates.xy[1][0]  # Get Y coordinate
        x_min, x_max = 0, self.config.warehouse.width
        
        # Calculate shelf spacing along the corridor
        available_length = x_max - x_min
        spacing = config.spacing
        
        # Place shelves on both sides of the corridor
        # Offset by spacing/2 from corridor center
        for side in [-1, 1]:  # Above and below
            shelf_y = y + (side * spacing / 2)
            
            x = spacing
            while x < x_max - config.width:
                # Create shelf polygon at this position
                polygon = _create_polygon_from_center(
                    x, shelf_y, config.width, config.height
                )
                
                # Check if shelf intersects with any corridor (collision detection)
                if polygon.intersects(combined_corridors):
                    # Skip this shelf position - don't increment ID
                    pass
                elif (0 <= polygon.bounds[0] and polygon.bounds[2] <= self.config.warehouse.width and 
                      0 <= polygon.bounds[1] and polygon.bounds[3] <= self.config.warehouse.height):
                    
                    shelf = Shelf(
                        shelf_id=shelf_id,
                        name=f"Shelf {shelf_id}",
                        coordinates=polygon
                    )
                    shelves.append(shelf)
                    shelf_id += 1
                
                x += spacing
        
        return shelves
    
    def _place_shelves_on_vertical_corridor(
        self, 
        corridor: Corridor, 
        start_id: int,
        config: ShelfConfig,
        combined_corridors
    ) -> list[Shelf]:
        """Place shelves along a vertical corridor."""
        shelves = []
        shelf_id = start_id
        
        x = corridor.coordinates.xy[0][0]  # Get X coordinate
        y_min, y_max = 0, self.config.warehouse.height
        
        # Calculate shelf spacing along the corridor
        spacing = config.spacing
        
        # Place shelves on both sides of the corridor
        # Offset by spacing/2 from corridor center
        for side in [-1, 1]:  # Left and right
            shelf_x = x + (side * spacing / 2)
            
            y = spacing
            while y < y_max - config.height:
                # Create shelf polygon at this position
                polygon = _create_polygon_from_center(
                    shelf_x, y, config.width, config.height
                )
                
                # Check if shelf intersects with any corridor (collision detection)
                if polygon.intersects(combined_corridors):
                    # Skip this shelf position - don't increment ID
                    pass
                elif (0 <= polygon.bounds[0] and polygon.bounds[2] <= self.config.warehouse.width and 
                      0 <= polygon.bounds[1] and polygon.bounds[3] <= self.config.warehouse.height):
                    
                    shelf = Shelf(
                        shelf_id=shelf_id,
                        name=f"Shelf {shelf_id}",
                        coordinates=polygon
                    )
                    shelves.append(shelf)
                    shelf_id += 1
                
                y += spacing
        
        return shelves
    
    def _create_connections(
        self, 
        shelves: list[Shelf],
        corridors: list[Corridor]
    ) -> dict:
        """Create connections from shelves to nearest corridor points."""
        connections = []
        connection_points = []
        connection_id = 1
        point_id = 1
        
        # Build a single geometry from all corridors for nearest point calculation
        from shapely.ops import unary_union
        corridor_geometries = [c.coordinates for c in corridors]
        combined_corridors = unary_union(corridor_geometries)
        
        for shelf in shelves:
            # Find nearest point on the corridor network
            # Use centroid for polygon-based shelves
            shelf_geom = shelf.coordinates
            if hasattr(shelf_geom, 'centroid'):
                shelf_point = shelf_geom.centroid
            else:
                shelf_point = shelf_geom
            
            # Find nearest point on the combined corridor geometry
            nearest = nearest_points(shelf_point, combined_corridors)
            connection_point_geom = nearest[1]
            
            # Create connection point
            connection_point = ConnectionPoint(
                point_id=point_id,
                coordinates=connection_point_geom,
                corridor_id=self._find_nearest_corridor_id(corridors, connection_point_geom)
            )
            connection_points.append(connection_point)
            
            # Create connection line from shelf to connection point
            connection_coords = LineString([
                (shelf_point.x, shelf_point.y),
                (connection_point_geom.x, connection_point_geom.y)
            ])
            
            connection = Connection(
                connection_id=connection_id,
                shelf_id=shelf.shelf_id,
                corridor_id=connection_point.corridor_id,
                connection_point_id=point_id,
                coordinates=connection_coords
            )
            connections.append(connection)
            
            connection_id += 1
            point_id += 1
        
        return {
            "connections": connections,
            "connection_points": connection_points
        }
    
    def _find_nearest_corridor_id(self, corridors: list[Corridor], point: Point) -> int:
        """Find the nearest corridor to a given point."""
        min_distance = float('inf')
        nearest_id = 1
        
        for corridor in corridors:
            dist = point.distance(corridor.coordinates)
            if dist < min_distance:
                min_distance = dist
                nearest_id = corridor.corridor_id
        
        return nearest_id
