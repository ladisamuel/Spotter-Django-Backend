"""Geospatial utilities for route optimization.

This module provides pure-Python geospatial calculations for the development
mode (DEBUG=True). In production (DEBUG=False), PostGIS handles these
operations at the database level for superior performance.
"""

import math
from typing import List, Tuple, Optional
import polyline


# Earth's radius in miles
EARTH_RADIUS_MILES = 3959.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth.
    
    Uses the Haversine formula for accurate distance calculation.
    This is used in development mode for Python-side filtering.
    
    Args:
        lat1, lon1: Coordinates of point 1 (decimal degrees)
        lat2, lon2: Coordinates of point 2 (decimal degrees)
    
    Returns:
        Distance in miles
    """
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Haversine formula
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_MILES * c


def decode_polyline(encoded: str) -> List[Tuple[float, float]]:
    """
    Decode an encoded polyline string into a list of (lat, lon) tuples.
    
    Args:
        encoded: Google-encoded polyline string from OSRM
    
    Returns:
        List of (latitude, longitude) coordinate tuples
    """
    return polyline.decode(encoded)


def encode_polyline(coordinates: List[Tuple[float, float]]) -> str:
    """
    Encode a list of coordinates into a polyline string.
    
    Args:
        coordinates: List of (lat, lon) tuples
    
    Returns:
        Encoded polyline string
    """
    return polyline.encode(coordinates)


def point_to_segment_distance(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float
) -> float:
    """
    Calculate the perpendicular distance from a point to a line segment.
    
    Args:
        px, py: Point coordinates (lat, lon)
        x1, y1: Segment start (lat, lon)
        x2, y2: Segment end (lat, lon)
    
    Returns:
        Distance in miles
    """
    # Project point onto segment (using lat/lon as Cartesian approximation
    # for small distances — sufficient for corridor filtering)
    dx = x2 - x1
    dy = y2 - y1
    
    if dx == 0 and dy == 0:
        return haversine_distance(px, py, x1, y1)
    
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    
    closest_lat = x1 + t * dx
    closest_lon = y1 + t * dy
    
    return haversine_distance(px, py, closest_lat, closest_lon)


def is_point_near_route(
    point_lat: float, point_lon: float,
    route_points: List[Tuple[float, float]],
    max_distance_miles: float
) -> bool:
    """
    Check if a point is within a given distance of any segment of a route.
    
    Used in development mode to build the route corridor.
    
    Args:
        point_lat, point_lon: The point to check
        route_points: List of route coordinates
        max_distance_miles: Maximum distance threshold
    
    Returns:
        True if point is within threshold of any route segment
    """
    if not route_points:
        return False
    
    # Check distance to each route segment
    for i in range(len(route_points) - 1):
        seg_start = route_points[i]
        seg_end = route_points[i + 1]
        
        dist = point_to_segment_distance(
            point_lat, point_lon,
            seg_start[0], seg_start[1],
            seg_end[0], seg_end[1]
        )
        
        if dist <= max_distance_miles:
            return True
    
    return False


def calculate_route_distance(route_points: List[Tuple[float, float]]) -> float:
    """
    Calculate the cumulative distance along a route in miles.
    
    Args:
        route_points: List of (lat, lon) tuples
    
    Returns:
        Total route distance in miles
    """
    total = 0.0
    for i in range(len(route_points) - 1):
        total += haversine_distance(
            route_points[i][0], route_points[i][1],
            route_points[i + 1][0], route_points[i + 1][1]
        )
    return total


def find_closest_point_on_route(
    point_lat: float, point_lon: float,
    route_points: List[Tuple[float, float]]
) -> Tuple[int, float]:
    """
    Find the closest route point index and distance for a given point.
    
    Args:
        point_lat, point_lon: The point to check
        route_points: List of route coordinates
    
    Returns:
        Tuple of (closest_index, distance_miles)
    """
    min_dist = float('inf')
    closest_idx = 0
    
    for i, (lat, lon) in enumerate(route_points):
        dist = haversine_distance(point_lat, point_lon, lat, lon)
        if dist < min_dist:
            min_dist = dist
            closest_idx = i
    
    return closest_idx, min_dist


def project_point_distance_along_route(
    point_lat: float, point_lon: float,
    route_points: List[Tuple[float, float]]
) -> float:
    """
    Estimate the distance along the route to the closest point to a given location.
    
    This approximates how far from the start a station is along the route.
    
    Args:
        point_lat, point_lon: The point to project
        route_points: List of route coordinates
    
    Returns:
        Approximate distance from start along route in miles
    """
    closest_idx, _ = find_closest_point_on_route(point_lat, point_lon, route_points)
    
    # Sum distances from start to closest point
    distance = 0.0
    for i in range(closest_idx):
        distance += haversine_distance(
            route_points[i][0], route_points[i][1],
            route_points[i + 1][0], route_points[i + 1][1]
        )
    
    return distance
