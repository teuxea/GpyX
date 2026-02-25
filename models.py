"""
GpyX — GPS Route Converter & Planner
Data models: GpsPoint, GpsRoute, GpsTrack, GpsWaypointArray

Originally inspired by ITN Converter v1.94 by Benichou Software (MIT License)
https://github.com/Benichou34/itnconverter
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class ArrayType(Enum):
    ROUTE = "route"
    TRACK = "track"
    WAYPOINT = "waypoint"
    POI = "poi"


@dataclass
class GpsPoint:
    """A single GPS point with coordinates and metadata."""
    lat: float = 0.0
    lng: float = 0.0
    alt: float = 0.0
    name: str = ""
    comment: str = ""

    def __bool__(self) -> bool:
        return self.lat != 0.0 or self.lng != 0.0

    def clear(self):
        self.lat = 0.0
        self.lng = 0.0
        self.alt = 0.0
        self.name = ""
        self.comment = ""

    def distance_from(self, other: GpsPoint) -> float:
        """Haversine distance in meters."""
        R = 6371000  # Earth radius in meters
        lat1, lat2 = math.radians(self.lat), math.radians(other.lat)
        dlat = math.radians(other.lat - self.lat)
        dlng = math.radians(other.lng - self.lng)
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def copy(self) -> GpsPoint:
        return GpsPoint(self.lat, self.lng, self.alt, self.name, self.comment)


class GpsPointArray:
    """Base class for collections of GPS points."""

    def __init__(self, array_type: ArrayType, name: str = ""):
        self._points: List[GpsPoint] = []
        self._name: str = name
        self._type: ArrayType = array_type

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    @property
    def array_type(self) -> ArrayType:
        return self._type

    def __len__(self) -> int:
        return len(self._points)

    def __getitem__(self, index) -> GpsPoint:
        return self._points[index]

    def __setitem__(self, index, value: GpsPoint):
        self._points[index] = value

    def __iter__(self):
        return iter(self._points)

    def __bool__(self) -> bool:
        return len(self._points) > 0

    @property
    def empty(self) -> bool:
        return len(self._points) == 0

    def append(self, point: GpsPoint):
        self._points.append(point)

    # Alias for C++ push_back
    push_back = append

    def insert(self, pos: int, point: GpsPoint):
        self._points.insert(pos, point)

    def pop(self, index: int = -1) -> GpsPoint:
        return self._points.pop(index)

    def clear(self):
        self._points.clear()
        self._name = ""

    def reverse(self):
        self._points.reverse()

    @property
    def upper_bound(self) -> int:
        return max(0, len(self._points) - 1)

    def remove_empties(self):
        self._points = [p for p in self._points if p]

    def remove_duplicates(self):
        seen = set()
        unique = []
        for p in self._points:
            key = (p.lat, p.lng)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        self._points = unique

    def sort_by_name(self):
        self._points.sort(key=lambda p: p.name)

    def total_distance(self) -> float:
        """Total distance in meters."""
        total = 0.0
        for i in range(1, len(self._points)):
            total += self._points[i - 1].distance_from(self._points[i])
        return total

    def bounds(self):
        """Returns (min_lat, min_lng, max_lat, max_lng)."""
        if not self._points:
            return (0, 0, 0, 0)
        lats = [p.lat for p in self._points if p]
        lngs = [p.lng for p in self._points if p]
        return (min(lats), min(lngs), max(lats), max(lngs))

    # ─── Simplification algorithms ────────────────────────────

    def decimate(self, keep_every_n: int = 2):
        """Keep only every Nth point (always keeps first and last)."""
        if keep_every_n < 2 or len(self._points) < 3:
            return
        result = [self._points[0]]
        for i in range(1, len(self._points) - 1):
            if i % keep_every_n == 0:
                result.append(self._points[i])
        result.append(self._points[-1])
        self._points = result

    @staticmethod
    def _perpendicular_distance(pt: GpsPoint, line_start: GpsPoint, line_end: GpsPoint) -> float:
        """
        Perpendicular distance from a point to a line segment, in meters.
        Uses a flat-earth approximation scaled by latitude (accurate enough
        for the small distances involved in track simplification).
        """
        cos_lat = math.cos(math.radians(pt.lat))
        # Convert to approximate meters
        x0 = pt.lng * cos_lat
        y0 = pt.lat
        x1 = line_start.lng * cos_lat
        y1 = line_start.lat
        x2 = line_end.lng * cos_lat
        y2 = line_end.lat

        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            # line_start == line_end
            ddx = x0 - x1
            ddy = y0 - y1
        else:
            t = max(0.0, min(1.0, ((x0 - x1) * dx + (y0 - y1) * dy) / (dx * dx + dy * dy)))
            ddx = x0 - (x1 + t * dx)
            ddy = y0 - (y1 + t * dy)

        # Convert degree-distance to meters (1° lat ≈ 111320 m)
        return math.sqrt((ddx * 111320) ** 2 + (ddy * 111320) ** 2)

    def douglas_peucker(self, epsilon_m: float = 50.0):
        """
        Douglas-Peucker simplification. Removes points that don't significantly
        alter the route shape. epsilon_m is the tolerance in meters.
        
        Iterative implementation to avoid stack overflow on huge tracks.
        """
        n = len(self._points)
        if n < 3 or epsilon_m <= 0:
            return

        # Iterative Douglas-Peucker using an explicit stack
        keep = [False] * n
        keep[0] = True
        keep[n - 1] = True

        stack = [(0, n - 1)]
        while stack:
            start, end = stack.pop()
            if end - start < 2:
                continue

            max_dist = 0.0
            max_idx = start
            for i in range(start + 1, end):
                d = self._perpendicular_distance(
                    self._points[i], self._points[start], self._points[end]
                )
                if d > max_dist:
                    max_dist = d
                    max_idx = i

            if max_dist > epsilon_m:
                keep[max_idx] = True
                stack.append((start, max_idx))
                stack.append((max_idx, end))

        self._points = [p for i, p in enumerate(self._points) if keep[i]]

    def simplify_for_routing(self, target_points: int = 50):
        """
        Smart simplification for routing: auto-tunes Douglas-Peucker epsilon
        to reach approximately the target number of points. Always keeps first
        and last points.
        """
        if len(self._points) <= target_points:
            return

        # Binary search for the right epsilon
        lo, hi = 1.0, 50000.0  # meters
        best_pts = list(self._points)

        for _ in range(30):  # converge quickly
            mid = (lo + hi) / 2
            # Work on a copy
            test = GpsPointArray(self._type, self._name)
            test._points = [p.copy() for p in self._points]
            test.douglas_peucker(mid)
            count = len(test)

            if count > target_points:
                lo = mid
            else:
                hi = mid
                best_pts = test._points

            if abs(count - target_points) <= max(2, target_points * 0.05):
                best_pts = test._points
                break

        self._points = best_pts


class GpsRoute(GpsPointArray):
    def __init__(self, name: str = ""):
        super().__init__(ArrayType.ROUTE, name)

    @classmethod
    def from_array(cls, array: GpsPointArray, start: int = 0, count: int = -1) -> GpsRoute:
        route = cls(array.name)
        end = len(array) if count < 0 else min(start + count, len(array))
        for i in range(start, end):
            route.append(array[i].copy())
        return route


class GpsTrack(GpsPointArray):
    def __init__(self, name: str = ""):
        super().__init__(ArrayType.TRACK, name)


class GpsWaypointArray(GpsPointArray):
    def __init__(self, name: str = ""):
        super().__init__(ArrayType.WAYPOINT, name)


class GpsPoiArray(GpsPointArray):
    def __init__(self, name: str = ""):
        super().__init__(ArrayType.POI, name)
