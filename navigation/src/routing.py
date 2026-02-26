"""Shortest path routing between shelves using PostGIS - GPS-style navigation."""

import json
import sys
from pathlib import Path
from collections import defaultdict
import heapq

# Add src directory to path based on this file's location
src_dir = Path(__file__).resolve().parent
project_root = src_dir.parent
sys.path.insert(0, str(project_root))

from typing import Optional, Tuple, List, Dict
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.config import DatabaseConfig


def _is_point_on_segment(p: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float], tolerance: float = 0.5) -> bool:
    """Check if point p is on the line segment p1-p2."""
    # Check if point is collinear with segment endpoints
    cross = (p2[1] - p1[1]) * (p[0] - p1[0]) - (p2[0] - p1[0]) * (p[1] - p1[1])
    if abs(cross) > tolerance:
        return False
    
    # Check if point is within the bounding box of the segment
    if min(p1[0], p2[0]) - tolerance <= p[0] <= max(p1[0], p2[0]) + tolerance and \
       min(p1[1], p2[1]) - tolerance <= p[1] <= max(p1[1], p2[1]) + tolerance:
        return True
    
    return False


class RoutingService:
    """Service for finding shortest paths between shelves using PostGIS."""
    
    def __init__(self, config: DatabaseConfig):
        """Initialize routing service with database configuration."""
        self.config = config
        self.engine = self._create_engine()
        self.Session = sessionmaker(bind=self.engine)
        self.graph = None  # Will build graph on first use
    
    def _create_engine(self):
        """Create SQLAlchemy engine for PostGIS."""
        connection_string = (
            f"postgresql://{self.config.user}:{self.config.password}"
            f"@{self.config.host}:{self.config.port}/{self.config.database}"
        )
        return create_engine(connection_string)
    
    def _build_graph(self) -> Dict[Tuple[float, float], List[Tuple[float, float, float]]]:
        """Build a graph from corridor network for routing.
        
        Returns:
            Dictionary mapping node coordinates to list of (neighbor_x, neighbor_y, distance)
        """
        if self.graph is not None:
            return self.graph
        
        print("Building corridor network graph...")
        graph = defaultdict(list)
        with self.engine.connect() as conn:
            # Get all connection points to add as nodes
            result = conn.execute(text("""
                SELECT 
                    connection_point_id,
                    ST_X(connection_point_coordinates) as x,
                    ST_Y(connection_point_coordinates) as y,
                    corridor_id
                FROM connection_points
            """))
            
            connection_points = {}
            for row in result:
                conn_coords = (float(row.x), float(row.y))
                connection_points[row.connection_point_id] = {
                    'coords': conn_coords,
                    'corridor_id': row.corridor_id
                }
            
            print(f"Found {len(connection_points)} connection points")
            
            # Get all corridors with their coordinates
            result = conn.execute(text("""
                SELECT 
                    corridor_id,
                    ST_AsGeoJSON(coordinates) as geometry
                FROM corridors
                WHERE coordinates IS NOT NULL
            """))
            
            corridors = []
            for row in result:
                corridor_geom = json.loads(row.geometry)
                if corridor_geom['type'] == 'LineString':
                    coords = [(float(c[0]), float(c[1])) for c in corridor_geom['coordinates']]
                    corridors.append({
                        'id': row.street_id,
                        'coords': coords
                    })
            
            # Add intermediate points along each street and connection points
            for street in streets:
                coords = street['coords']
                
                # Generate intermediate points along the street
                new_coords = []
                for i in range(len(coords) - 1):
                    p1 = coords[i]
                    p2 = coords[i + 1]
                    new_coords.append(p1)
                    
                    # Add intermediate points every 5 units
                    dist = ((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)**0.5
                    num_points = max(1, int(dist / 5))  # Point every 5 units
                    
                    for j in range(1, num_points):
                        t = j / num_points
                        interp_x = p1[0] + t * (p2[0] - p1[0])
                        interp_y = p1[1] + t * (p2[1] - p1[1])
                        new_coords.append((interp_x, interp_y))
                    
                    # Check if any connection points are on this segment
                    for cp_id, cp_data in connection_points.items():
                        cp_coords = cp_data['coords']
                        if cp_data['street_id'] == street['id']:
                            if _is_point_on_segment(cp_coords, p1, p2, tolerance=0.5):
                                if cp_coords not in new_coords:
                                    new_coords.append(cp_coords)
                
                new_coords.append(coords[-1])
                street['coords'] = new_coords
            
            # Build edges from the streets
            for street in streets:
                coords = street['coords']
                
                # Add edges between consecutive points
                for i in range(len(coords) - 1):
                    p1 = coords[i]
                    p2 = coords[i + 1]
                    
                    # Calculate distance
                    dist = ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
                    
                    # Add bidirectional edges
                    graph[p1].append((p2[0], p2[1], dist))
                    graph[p2].append((p1[0], p1[1], dist))
        
        print(f"Graph built with {len(graph)} nodes")
        self.graph = graph
        return graph
    
    def _find_nearest_node(self, x: float, y: float) -> Tuple[float, float]:
        """Find the nearest node in the graph to the given coordinates."""
        graph = self._build_graph()
        
        min_dist = float('inf')
        nearest_node = None
        
        for node in graph:
            dist = ((node[0] - x)**2 + (node[1] - y)**2)**0.5
            if dist < min_dist:
                min_dist = dist
                nearest_node = node
        
        return nearest_node
    
    def _dijkstra(self, start: Tuple[float, float], end: Tuple[float, float]) -> List[Tuple[float, float]]:
        """Find shortest path using Dijkstra's algorithm.
        
        Args:
            start: Starting coordinates (x, y)
            end: Ending coordinates (x, y)
            
        Returns:
            List of coordinates representing the path
        """
        graph = self._build_graph()
        
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
            for neighbor_x, neighbor_y, edge_dist in graph[current]:
                if (neighbor_x, neighbor_y) not in visited:
                    new_dist = dist + edge_dist
                    heapq.heappush(pq, (new_dist, (neighbor_x, neighbor_y), path + [(neighbor_x, neighbor_y)]))
        
        return []  # No path found
    
    def find_shortest_path(
        self, 
        from_house_id: int, 
        to_house_id: int
    ) -> Optional[dict]:
        """Find the shortest path between two houses using the corridor network.
        
        Args:
            from_house_id: Starting house ID
            to_house_id: Ending house ID
            
        Returns:
            Dictionary with path geometry and total cost, or None if no path found
        """
        # Reset graph to rebuild with intersection detection
        self.graph = None
        
        with self.engine.connect() as conn:
            # First, check if both houses exist in the database
            check_result = conn.execute(text("""
                SELECT house_id FROM houses 
                WHERE house_id IN (:from_id, :to_id)
            """), {"from_id": from_house_id, "to_id": to_house_id})
            
            found_houses = {row[0] for row in check_result.fetchall()}
            
            if from_house_id not in found_houses:
                # Get available house IDs to show the user
                avail_result = conn.execute(text("SELECT house_id FROM houses LIMIT 10"))
                available_ids = [row[0] for row in avail_result.fetchall()]
                print(f"Error: House with ID {from_house_id} not found in database.")
                print(f"Available house IDs (first 10): {available_ids}")
                return None
            
            if to_house_id not in found_houses:
                # Get available house IDs to show the user
                avail_result = conn.execute(text("SELECT house_id FROM houses LIMIT 10"))
                available_ids = [row[0] for row in avail_result.fetchall()]
                print(f"Error: House with ID {to_house_id} not found in database.")
                print(f"Available house IDs (first 10): {available_ids}")
                return None
            
            # Get the connection points for both houses
            result = conn.execute(text("""
                SELECT 
                    h.house_id,
                    c.connection_point_id,
                    ST_X(ST_EndPoint(c.connection_coordinates)) as conn_x,
                    ST_Y(ST_EndPoint(c.connection_coordinates)) as conn_y,
                    c.street_id
                FROM houses h
                JOIN connections c ON h.house_id = c.house_id
                WHERE h.house_id IN (:from_id, :to_id)
                ORDER BY h.house_id
            """), {"from_id": from_house_id, "to_id": to_house_id})
            
            rows = result.fetchall()
            if len(rows) != 2:
                # Get available house IDs from connections
                avail_result = conn.execute(text("""
                    SELECT DISTINCT h.house_id FROM houses h
                    JOIN connections c ON h.house_id = c.house_id
                    LIMIT 10
                """))
                available_ids = [row[0] for row in avail_result.fetchall()]
                print(f"Error: Could not find connection points for houses {from_house_id} and {to_house_id}")
                print(f"Houses with connections (first 10): {available_ids}")
                return None
            
            from_conn = rows[0]
            to_conn = rows[1]
            
            from_x, from_y = from_conn.conn_x, from_conn.conn_y
            to_x, to_y = to_conn.conn_x, to_conn.conn_y
            
            print(f"Finding path from ({from_x}, {from_y}) to ({to_x}, {to_y})...")
            
            # Build the graph (now includes connection points and intermediate points)
            graph = self._build_graph()
            
            # Use connection points directly as start/end nodes (they're now in the graph)
            start_node = (from_x, from_y)
            end_node = (to_x, to_y)
            
            print(f"Start node (connection point): {start_node}")
            print(f"End node (connection point): {end_node}")
            
            # Verify nodes exist in graph
            if start_node not in graph:
                print(f"Warning: Start node {start_node} not in graph, finding nearest...")
                start_node = self._find_nearest_node(from_x, from_y)
            if end_node not in graph:
                print(f"Warning: End node {end_node} not in graph, finding nearest...")
                end_node = self._find_nearest_node(to_x, to_y)
            
            # Find shortest path using Dijkstra
            path_coords = self._dijkstra(start_node, end_node)
            
            if not path_coords:
                print(f"No path found between houses {from_house_id} and {to_house_id}")
                return None
            
            # Build full path - already includes connection points since they're in the graph now
            full_path = path_coords
            
            # Calculate total distance
            total_cost = 0
            for i in range(len(full_path) - 1):
                p1 = full_path[i]
                p2 = full_path[i + 1]
                total_cost += ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
            
            # Create GeoJSON
            path_geojson = json.dumps({
                "type": "LineString",
                "coordinates": full_path
            })
            
            return {
                "from_house_id": from_house_id,
                "to_house_id": to_house_id,
                "total_cost": total_cost,
                "path_geometry": path_geojson,
                "num_segments": len(full_path) - 1
            }
    
    def save_route_to_postgis(self, path: dict) -> bool:
        """Save a route path to PostGIS database."""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS routes (
                    route_id SERIAL PRIMARY KEY,
                    from_house_id INTEGER NOT NULL,
                    to_house_id INTEGER NOT NULL,
                    total_cost FLOAT NOT NULL,
                    num_segments INTEGER NOT NULL,
                    geometry GEOMETRY(LINESTRING, 4326) NOT NULL
                )
            """))
            conn.commit()
            
            conn.execute(text("""
                INSERT INTO routes (from_house_id, to_house_id, total_cost, num_segments, geometry)
                VALUES (:from_id, :to_id, :cost, :num_segments, ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))
            """), {
                "from_id": path['from_house_id'],
                "to_id": path['to_house_id'],
                "cost": path['total_cost'],
                "num_segments": path['num_segments'],
                "geom": path['path_geometry']
            })
            conn.commit()
            
            return True
    
    def visualize_route(self, path: dict, config, output_path: Path = None) -> None:
        """Visualize the route on a map."""
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import geopandas as gpd
        from shapely.geometry import shape
        
        fig, ax = plt.subplots(figsize=(14, 12))
        
        ax.set_xlim(-5, config.warehouse.width + 5)
        ax.set_ylim(-5, config.warehouse.height + 5)
        
        # Load and plot streets
        streets_gdf = gpd.read_postgis(
            "SELECT street_id, name, coordinates FROM streets",
            self.engine,
            geom_col="coordinates"
        )
        streets_gdf.plot(ax=ax, color="black", linewidth=3, label="Streets")
        
        # Load and plot houses
        houses_gdf = gpd.read_postgis(
            "SELECT house_id, name, coordinates FROM houses",
            self.engine,
            geom_col="coordinates"
        )
        houses_gdf.plot(ax=ax, color="blue", markersize=50, marker="s", label="Houses")
        
        # Load and plot connections
        connections_gdf = gpd.read_postgis(
            "SELECT connection_id, house_id, connection_coordinates FROM connections",
            self.engine,
            geom_col="connection_coordinates"
        )
        connections_gdf.plot(ax=ax, color="gray", linewidth=0.5, alpha=0.3, label="Connections")
        
        # Plot the route path
        route_geom = shape(json.loads(path['path_geometry']))
        route_gdf = gpd.GeoDataFrame([{"geometry": route_geom}])
        route_gdf.plot(ax=ax, color="red", linewidth=4, label="Route")
        
        # Highlight start and end houses
        start_house = houses_gdf[houses_gdf['house_id'] == path['from_house_id']]
        end_house = houses_gdf[houses_gdf['house_id'] == path['to_house_id']]
        start_house.plot(ax=ax, color="green", markersize=200, marker="*", label="Start")
        end_house.plot(ax=ax, color="orange", markersize=200, marker="*", label="End")
        
        # Add labels
        ax.annotate(
            f"Start\nHouse {path['from_house_id']}",
            (start_house.geometry.iloc[0].centroid.x, start_house.geometry.iloc[0].centroid.y),
            textcoords="offset points", xytext=(10, 10), fontsize=10, color="green", fontweight="bold"
        )
        ax.annotate(
            f"End\nHouse {path['to_house_id']}",
            (end_house.geometry.iloc[0].centroid.x, end_house.geometry.iloc[0].centroid.y),
            textcoords="offset points", xytext=(10, 10), fontsize=10, color="orange", fontweight="bold"
        )
        
        ax.legend(loc="upper right", handles=[
            mpatches.Patch(color="black", label="Streets"),
            mpatches.Patch(color="blue", label="Houses"),
            mpatches.Patch(color="gray", label="Connections"),
            mpatches.Patch(color="red", label="Route"),
        ])
        ax.set_title(
            f"GPS Route from House {path['from_house_id']} to House {path['to_house_id']}\n"
            f"Total Distance: {path['total_cost']:.2f} units | {path['num_segments']} segments",
            fontsize=14, fontweight="bold"
        )
        ax.set_xlabel("X Coordinate")
        ax.set_ylabel("Y Coordinate")
        ax.grid(True, linestyle="--", alpha=0.3)
        ax.set_aspect("equal")
        
        plt.tight_layout()
        
        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            print(f"Route visualization saved to: {output_path}")
        
        plt.close()


if __name__ == "__main__":
    from src.config import load_config
    
    config = load_config("data/warehouse_config.yaml")
    routing = RoutingService(config.database)
    
    print("Finding shortest path from house 1 to house 10...")
    path = routing.find_shortest_path(7, 77)
    
    if path:
        print(f"Path found!")
        print(f"  From house: {path['from_house_id']}")
        print(f"  To house: {path['to_house_id']}")
        print(f"  Total distance: {path['total_cost']:.2f} units")
        print(f"  Number of segments: {path['num_segments']}")
        
        # Save route to database
        print("\nSaving route to PostGIS...")
        try:
            routing.save_route_to_postgis(path)
            print("Route saved to PostGIS!")
        except Exception as e:
            print(f"Could not save to PostGIS: {e}")
        
        # Create visualization
        print("\nCreating route visualization...")
        output_path = Path("output/route_map.png")
        routing.visualize_route(path, config, output_path)
        print(f"Route visualization saved to: {output_path}")
    else:
        print("No path found")
