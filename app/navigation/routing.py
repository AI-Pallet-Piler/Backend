"""Routing service for finding shortest paths between shelves."""

from typing import Optional, Tuple, List, Dict
from collections import defaultdict
import heapq
import shapely
from shapely.geometry import Point, LineString

from app.models.models import Shelf, Connection, ConnectionPoint


class RoutingService:
    """Service for finding shortest paths between shelves using corridor network."""
    
    def __init__(self):
        """Initialize routing service."""
        self.graph = None
    
    def build_graph(self, shelves: list, connections: list, connection_points: list) -> Dict[Tuple[float, float], List[Tuple[float, float, float]]]:
        """Build a graph from corridor network for routing.
        
        Returns:
            Dictionary mapping node coordinates to list of (neighbor_x, neighbor_y, distance)
        """
        if self.graph is not None:
            return self.graph
        
        graph = defaultdict(list)
        
        # Create a mapping of connection points
        cp_by_id = {}
        for cp in connection_points:
            if cp.connection_point_coordinates:
                geom = shapely.wkb.loads(cp.connection_point_coordinates)
                cp_by_id[cp.connection_point_id] = (geom.x, geom.y)
        
        # Get all connection point coordinates that are on corridors
        corridor_nodes = set(cp_by_id.values())
        
        # Add intermediate points along corridors for more granular routing
        # We'll use the connection points as nodes and interpolate between them
        
        # Build graph edges from connection points
        # Each connection point connects to its shelf
        
        # First, add shelf centroids as nodes
        shelf_centroids = {}
        for shelf in shelves:
            if shelf.coordinates:
                geom = shapely.wkb.loads(shelf.coordinates)
                centroid = geom.centroid
                shelf_centroids[shelf.shelf_id] = (centroid.x, centroid.y)
        
        # Add edges from shelves to their connection points
        for conn in connections:
            if conn.shelf_id in shelf_centroids and conn.connection_point_id in cp_by_id:
                shelf_coord = shelf_centroids[conn.shelf_id]
                cp_coord = cp_by_id[conn.connection_point_id]
                
                # Add edge from shelf to connection point
                dist = ((shelf_coord[0] - cp_coord[0])**2 + (shelf_coord[1] - cp_coord[1])**2)**0.5
                graph[shelf_coord].append((cp_coord[0], cp_coord[1], dist))
                graph[cp_coord].append((shelf_coord[0], shelf_coord[1], dist))
        
        # Now we need to add edges between connection points via corridors
        # This is a simplified version - in a real app we'd analyze corridor geometry
        # For now, we'll create a mesh between connection points on the same corridor
        
        # Group connection points by corridor
        cp_by_corridor = defaultdict(list)
        for cp in connection_points:
            if cp.corridor_id and cp.connection_point_coordinates:
                geom = shapely.wkb.loads(cp.connection_point_coordinates)
                cp_by_corridor[cp.corridor_id].append((geom.x, geom.y))
        
        # Add edges between consecutive connection points on same corridor
        for corridor_id, coords in cp_by_corridor.items():
            # Sort by x then y to get order along corridor
            coords.sort()
            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]
                dist = ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
                
                # Add bidirectional edge
                graph[p1].append((p2[0], p2[1], dist))
                graph[p2].append((p1[0], p1[1], dist))
        
        self.graph = graph
        return graph
    
    def find_nearest_node(self, x: float, y: float) -> Tuple[float, float]:
        """Find the nearest node in the graph to the given coordinates."""
        if self.graph is None:
            return None
        
        min_dist = float('inf')
        nearest_node = None
        
        for node in self.graph:
            dist = ((node[0] - x)**2 + (node[1] - y)**2)**0.5
            if dist < min_dist:
                min_dist = dist
                nearest_node = node
        
        return nearest_node
    
    def dijkstra(self, start: Tuple[float, float], end: Tuple[float, float]) -> List[Tuple[float, float]]:
        """Find shortest path using Dijkstra's algorithm."""
        if self.graph is None:
            return []
        
        # Priority queue: (distance, current_node, path)
        pq = [(0, start, [start])]
        visited = set()
        
        while pq:
            dist, current, path = heapq.heappop(pq)
            
            if current in visited:
                continue
            
            visited.add(current)
            
            # Check if we reached the destination
            if ((current[0] - end[0])**2 + (current[1] - end[1])**2)**0.5 < 0.1:
                return path
            
            # Explore neighbors
            if current in self.graph:
                for neighbor_x, neighbor_y, edge_dist in self.graph[current]:
                    if (neighbor_x, neighbor_y) not in visited:
                        new_dist = dist + edge_dist
                        heapq.heappush(pq, (new_dist, (neighbor_x, neighbor_y), path + [(neighbor_x, neighbor_y)]))
        
        return []  # No path found
    
    def find_path_between_shelves(
        self,
        from_shelf_id: int,
        to_shelf_id: int,
        shelves: list,
        connections: list,
        connection_points: list
    ) -> Optional[Dict]:
        """Find the shortest path between two shelves.
        
        Args:
            from_shelf_id: Starting shelf ID
            to_shelf_id: Ending shelf ID
            shelves: List of Shelf objects
            connections: List of Connection objects
            connection_points: List of ConnectionPoint objects
            
        Returns:
            Dictionary with path info or None if no path found
        """
        # Build graph
        self.graph = None
        self.build_graph(shelves, connections, connection_points)
        
        # Get shelf centroids
        shelf_centroids = {}
        for shelf in shelves:
            if shelf.coordinates:
                geom = shapely.wkb.loads(shelf.coordinates)
                centroid = geom.centroid
                shelf_centroids[shelf.shelf_id] = (centroid.x, centroid.y)
        
        # Check if both shelves exist
        if from_shelf_id not in shelf_centroids:
            return None
        if to_shelf_id not in shelf_centroids:
            return None
        
        start_coord = shelf_centroids[from_shelf_id]
        end_coord = shelf_centroids[to_shelf_id]
        
        # Find path
        path_coords = self.dijkstra(start_coord, end_coord)
        
        if not path_coords:
            return None
        
        # Calculate total distance
        total_distance = 0
        for i in range(len(path_coords) - 1):
            p1 = path_coords[i]
            p2 = path_coords[i + 1]
            total_distance += ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
        
        # Create path geometry as LineString (needs at least 2 points)
        if len(path_coords) < 2:
            return None  # No valid path
        
        path_geom = LineString(path_coords)
        
        return {
            "from_shelf_id": from_shelf_id,
            "to_shelf_id": to_shelf_id,
            "total_distance": total_distance,
            "path_coordinates": path_geom.wkb,  # Store as WKB
            "num_segments": len(path_coords) - 1,
            "path_geometry": path_coords  # For JSON response
        }


def generate_all_paths(
    shelves: list,
    connections: list,
    connection_points: list
) -> List[Dict]:
    """Generate paths for all shelf-to-shelf combinations.
    
    Args:
        shelves: List of Shelf objects
        connections: List of Connection objects
        connection_points: List of ConnectionPoint objects
        
    Returns:
        List of path dictionaries
    """
    routing_service = RoutingService()
    paths = []
    
    # Build graph once
    routing_service.build_graph(shelves, connections, connection_points)
    
    # Get shelf centroids
    shelf_ids = []
    for shelf in shelves:
        if shelf.coordinates:
            shelf_ids.append(shelf.shelf_id)
    
    # Generate paths for all combinations (ALL ordered pairs, excluding self-to-self)
    for from_id in shelf_ids:
        for to_id in shelf_ids:
            if from_id == to_id:
                continue  # Skip self-to-self
            
            path = routing_service.find_path_between_shelves(
                from_id, to_id, shelves, connections, connection_points
            )
            if path:
                paths.append(path)
    
    return paths
