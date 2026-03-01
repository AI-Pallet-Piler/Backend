"""Warehouse map generator with grid-based layout algorithm."""

from typing import Optional, List
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import nearest_points, unary_union

from app.navigation.config import Config, CorridorConfig, ShelfConfig
from app.models.models import Corridor, Shelf, Connection, ConnectionPoint


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
    
    def generate(self) -> dict:
        """Generate complete warehouse map.
        
        Returns:
            Dictionary with corridors, shelves, connections, and connection_points
        """
        warehouse_map = {
            "corridors": [],
            "shelves": [],
            "connections": [],
            "connection_points": []
        }
        
        # Generate corridors
        warehouse_map["corridors"] = self._generate_corridors()
        
        # Generate shelves along corridors
        warehouse_map["shelves"] = self._place_shelves(warehouse_map["corridors"])
        
        # Generate connections from shelves to corridors
        connections_data = self._create_connections(
            warehouse_map["shelves"], 
            warehouse_map["corridors"]
        )
        warehouse_map["connections"] = connections_data["connections"]
        warehouse_map["connection_points"] = connections_data["connection_points"]
        
        return warehouse_map
    
    def _generate_corridors(self) -> List[dict]:
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
            corridor = {
                "corridor_id": corridor_id,
                "name": f"Horizontal Corridor {corridor_id}",
                "coordinates": line
            }
            corridors.append(corridor)
            corridor_id += 1
        
        # Generate vertical corridors
        for x in v_positions:
            coords = [
                (x, 0),
                (x, self.config.warehouse.height)
            ]
            line = LineString(coords)
            corridor = {
                "corridor_id": corridor_id,
                "name": f"Vertical Corridor {corridor_id}",
                "coordinates": line
            }
            corridors.append(corridor)
            corridor_id += 1
        
        return corridors
    
    def _get_horizontal_positions(self) -> List[float]:
        """Calculate Y positions for horizontal corridors."""
        config = self.corridor_config
        positions = []
        start_y = config.offset_y
        
        use_custom_spacing = (
            isinstance(config.horizontal_spacing, list) and len(config.horizontal_spacing) > 0
        ) or (
            isinstance(config.horizontal_spacing, (int, float)) and config.horizontal_spacing > 0
        )
        
        if use_custom_spacing:
            if isinstance(config.horizontal_spacing, (int, float)):
                spacing = config.horizontal_spacing
                for i in range(config.horizontal_count):
                    y = start_y + (i * spacing)
                    if y <= self.config.warehouse.height:
                        positions.append(y)
            else:
                for i, spacing in enumerate(config.horizontal_spacing):
                    if i < config.horizontal_count:
                        y = start_y + (i * spacing) if i == 0 else positions[-1] + spacing
                        if y <= self.config.warehouse.height:
                            positions.append(y)
                for i in range(len(positions), config.horizontal_count):
                    y = positions[-1] + config.spacing
                    if y <= self.config.warehouse.height:
                        positions.append(y)
        else:
            for i in range(config.horizontal_count):
                y = start_y + (i * config.spacing)
                if y <= self.config.warehouse.height:
                    positions.append(y)
        
        return positions
    
    def _get_vertical_positions(self) -> List[float]:
        """Calculate X positions for vertical corridors."""
        config = self.corridor_config
        positions = []
        start_x = config.offset_x
        
        use_custom_spacing = (
            isinstance(config.vertical_spacing, list) and len(config.vertical_spacing) > 0
        ) or (
            isinstance(config.vertical_spacing, (int, float)) and config.vertical_spacing > 0
        )
        
        if use_custom_spacing:
            if isinstance(config.vertical_spacing, (int, float)):
                spacing = config.vertical_spacing
                for i in range(config.vertical_count):
                    x = start_x + (i * spacing)
                    if x <= self.config.warehouse.width:
                        positions.append(x)
            else:
                for i, spacing in enumerate(config.vertical_spacing):
                    if i < config.vertical_count:
                        x = start_x + (i * spacing) if i == 0 else positions[-1] + spacing
                        if x <= self.config.warehouse.width:
                            positions.append(x)
                for i in range(len(positions), config.vertical_count):
                    x = positions[-1] + config.spacing
                    if x <= self.config.warehouse.width:
                        positions.append(x)
        else:
            for i in range(config.vertical_count):
                x = start_x + (i * config.spacing)
                if x <= self.config.warehouse.width:
                    positions.append(x)
        
        return positions
    
    def _place_shelves(self, corridors: List[dict]) -> List[dict]:
        """Place shelves along corridor segments."""
        shelves = []
        shelf_id = 1
        config = self.shelf_config
        
        # Pre-build buffered corridor polygons for collision detection
        corridor_buffer = self.corridor_config.width / 2
        buffered_corridors = []
        for corridor in corridors:
            buffered = corridor["coordinates"].buffer(corridor_buffer)
            buffered_corridors.append(buffered)
        combined_corridors = unary_union(buffered_corridors)
        
        for corridor in corridors:
            is_horizontal = corridor["coordinates"].xy[1][0] == corridor["coordinates"].xy[1][1]
            
            if is_horizontal and self.corridor_config.disable_horizontal_shelves:
                continue
            elif not is_horizontal and self.corridor_config.disable_vertical_shelves:
                continue
            
            if is_horizontal:
                shelves.extend(
                    self._place_shelves_on_horizontal_corridor(
                        corridor, shelf_id, config, combined_corridors, shelves
                    )
                )
                shelf_id = len(shelves) + 1
            else:
                shelves.extend(
                    self._place_shelves_on_vertical_corridor(
                        corridor, shelf_id, config, combined_corridors, shelves
                    )
                )
                shelf_id = len(shelves) + 1
        
        return shelves
    
    def _place_shelves_on_horizontal_corridor(
        self, 
        corridor: dict, 
        start_id: int,
        config: ShelfConfig,
        combined_corridors,
        existing_shelves: list
    ) -> List[dict]:
        """Place shelves along a horizontal corridor."""
        shelves = []
        shelf_id = start_id
        
        y = corridor["coordinates"].xy[1][0]
        x_min, x_max = 0, self.config.warehouse.width
        spacing = config.spacing
        
        for side in [-1, 1]:
            shelf_y = y + (side * (spacing / 2 + config.height / 2 + 0.5))  # Add half height + gap to prevent overlap
            
            x = spacing
            while x < x_max - config.width:
                polygon = _create_polygon_from_center(
                    x, shelf_y, config.width, config.height
                )
                
                if polygon.intersects(combined_corridors):
                    pass
                elif (0 <= polygon.bounds[0] and polygon.bounds[2] <= self.config.warehouse.width and 
                      0 <= polygon.bounds[1] and polygon.bounds[3] <= self.config.warehouse.height):
                    
                    # Check for overlap with existing shelves
                    overlaps = False
                    for existing in existing_shelves:
                        if polygon.intersects(existing["coordinates"]):
                            overlaps = True
                            break
                    
                    if not overlaps:
                        shelf = {
                            "shelf_id": shelf_id,
                            "name": f"Shelf {shelf_id}",
                            "coordinates": polygon
                        }
                        shelves.append(shelf)
                        shelf_id += 1
                
                x += spacing
        
        return shelves
    
    def _place_shelves_on_vertical_corridor(
        self, 
        corridor: dict, 
        start_id: int,
        config: ShelfConfig,
        combined_corridors,
        existing_shelves: list
    ) -> List[dict]:
        """Place shelves along a vertical corridor."""
        shelves = []
        shelf_id = start_id
        
        x = corridor["coordinates"].xy[0][0]
        y_min, y_max = 0, self.config.warehouse.height
        spacing = config.spacing
        
        for side in [-1, 1]:
            shelf_x = x + (side * (spacing / 2 + config.width / 2 + 0.5))  # Add half width + gap to prevent overlap
            
            y = spacing
            while y < y_max - config.height:
                polygon = _create_polygon_from_center(
                    shelf_x, y, config.width, config.height
                )
                
                if polygon.intersects(combined_corridors):
                    pass
                elif (0 <= polygon.bounds[0] and polygon.bounds[2] <= self.config.warehouse.width and 
                      0 <= polygon.bounds[1] and polygon.bounds[3] <= self.config.warehouse.height):
                    
                    # Check for overlap with existing shelves
                    overlaps = False
                    for existing in existing_shelves:
                        if polygon.intersects(existing["coordinates"]):
                            overlaps = True
                            break
                    
                    if not overlaps:
                        shelf = {
                            "shelf_id": shelf_id,
                            "name": f"Shelf {shelf_id}",
                            "coordinates": polygon
                        }
                        shelves.append(shelf)
                        shelf_id += 1
                
                y += spacing
        
        return shelves
    
    def _create_connections(
        self, 
        shelves: List[dict],
        corridors: List[dict]
    ) -> dict:
        """Create connections from shelves to nearest corridor points.
        
        Also creates intersection connection points to ensure all corridors are connected.
        """
        connections = []
        connection_points = []
        connection_id = 1
        point_id = 1
        
        # Build a single geometry from all corridors for nearest point calculation
        corridor_geometries = [c["coordinates"] for c in corridors]
        combined_corridors = unary_union(corridor_geometries)
        
        # First, add corridor intersection points to connect horizontal and vertical corridors
        intersection_points = self._create_corridor_intersections(corridors, point_id)
        connection_points.extend(intersection_points)
        point_id += len(intersection_points)
        
        for shelf in shelves:
            shelf_geom = shelf["coordinates"]
            if hasattr(shelf_geom, 'centroid'):
                shelf_point = shelf_geom.centroid
            else:
                shelf_point = shelf_geom
            
            nearest = nearest_points(shelf_point, combined_corridors)
            connection_point_geom = nearest[1]
            
            connection_point = {
                "point_id": point_id,
                "connection_point_id": point_id,
                "coordinates": connection_point_geom,
                "corridor_id": self._find_nearest_corridor_id(corridors, connection_point_geom)
            }
            connection_points.append(connection_point)
            
            connection_coords = LineString([
                (shelf_point.x, shelf_point.y),
                (connection_point_geom.x, connection_point_geom.y)
            ])
            
            connection = {
                "connection_id": connection_id,
                "shelf_id": shelf["shelf_id"],
                "corridor_id": connection_point["corridor_id"],
                "connection_point_id": point_id,
                "coordinates": connection_coords
            }
            connections.append(connection)
            
            connection_id += 1
            point_id += 1
        
        return {
            "connections": connections,
            "connection_points": connection_points
        }
    
    def _create_corridor_intersections(
        self, 
        corridors: List[dict],
        start_point_id: int
    ) -> List[dict]:
        """Create connection points at corridor intersections to ensure connectivity.
        
        This adds points where horizontal and vertical corridors cross,
        allowing paths to traverse between different corridor types.
        """
        intersection_points = []
        
        # Separate horizontal and vertical corridors
        horizontal_corridors = []
        vertical_corridors = []
        
        for corridor in corridors:
            coords = corridor["coordinates"]
            if hasattr(coords, 'coords'):
                x_coords = [c[0] for c in coords.coords]
                y_coords = [c[1] for c in coords.coords]
                # If x coordinates are the same, it's vertical; if y coordinates are same, it's horizontal
                if len(set(x_coords)) == 1:
                    vertical_corridors.append(corridor)
                elif len(set(y_coords)) == 1:
                    horizontal_corridors.append(corridor)
        
        # Find intersections between horizontal and vertical corridors
        point_id = start_point_id
        for h_corr in horizontal_corridors:
            for v_corr in vertical_corridors:
                # Get the line coordinates
                h_coords = list(h_corr["coordinates"].coords)
                v_coords = list(v_corr["coordinates"].coords)
                
                # Find intersection point (where vertical x meets horizontal y)
                v_x = v_coords[0][0]  # X coordinate of vertical corridor
                h_y = h_coords[0][1]  # Y coordinate of horizontal corridor
                
                # Check if this intersection is within corridor bounds
                h_min_x = min(c[0] for c in h_coords)
                h_max_x = max(c[0] for c in h_coords)
                v_min_y = min(c[1] for c in v_coords)
                v_max_y = max(c[1] for c in v_coords)
                
                if h_min_x <= v_x <= h_max_x and v_min_y <= h_y <= v_max_y:
                    intersection_point = Point(v_x, h_y)
                    
                    # Check if this intersection already exists (within small tolerance)
                    exists = False
                    for existing in intersection_points:
                        if existing["coordinates"].distance(intersection_point) < 0.1:
                            # Add this corridor to the intersection's connected corridors
                            if "connected_corridor_ids" not in existing:
                                existing["connected_corridor_ids"] = []
                            if v_corr["corridor_id"] not in existing["connected_corridor_ids"]:
                                existing["connected_corridor_ids"].append(v_corr["corridor_id"])
                            if h_corr["corridor_id"] not in existing["connected_corridor_ids"]:
                                existing["connected_corridor_ids"].append(h_corr["corridor_id"])
                            exists = True
                            break
                    
                    if not exists:
                        # Mark intersection as connected to BOTH horizontal and vertical corridors
                        intersection_points.append({
                            "point_id": point_id,
                            "connection_point_id": point_id,
                            "coordinates": intersection_point,
                            "corridor_id": h_corr["corridor_id"],  # Primary corridor
                            "connected_corridor_ids": [h_corr["corridor_id"], v_corr["corridor_id"]],
                            "is_intersection": True
                        })
                        point_id += 1
        
        return intersection_points
    
    def _find_nearest_corridor_id(self, corridors: List[dict], point: Point) -> int:
        """Find the nearest corridor to a given point."""
        min_distance = float('inf')
        nearest_id = 1
        
        for corridor in corridors:
            dist = point.distance(corridor["coordinates"])
            if dist < min_distance:
                min_distance = dist
                nearest_id = corridor["corridor_id"]
        
        return nearest_id
    
    def get_statistics(self, warehouse_map: dict) -> dict:
        """Get statistics about the warehouse map."""
        return {
            "num_corridors": len(warehouse_map["corridors"]),
            "num_shelves": len(warehouse_map["shelves"]),
            "num_connections": len(warehouse_map["connections"]),
            "num_connection_points": len(warehouse_map["connection_points"]),
        }
