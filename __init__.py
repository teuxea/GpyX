"""
GpyX — GPS Route Converter & Planner
==========================================
Convert GPS routes between 17+ formats. Zero external dependencies.

Originally inspired by ITN Converter v1.94 by Benichou Software (MIT License)
https://github.com/Benichou34/itnconverter

Quick start:
    python server.py              # Web UI with map
    python itnconv.py in.gpx out.itn   # CLI

Library:
    from itnconv_py import convert, read_file, write_file
    convert("route.gpx", "route.itn")
"""

from models import GpsPoint, GpsRoute, GpsTrack, GpsWaypointArray, GpsPoiArray, ArrayType
from formats import (
    read_file, write_file, convert,
    supported_input_formats, supported_output_formats,
    get_format, FORMAT_REGISTRY,
)

__version__ = "1.0.0"
__all__ = [
    "GpsPoint", "GpsRoute", "GpsTrack", "GpsWaypointArray", "GpsPoiArray",
    "ArrayType", "read_file", "write_file", "convert",
    "supported_input_formats", "supported_output_formats",
    "get_format", "FORMAT_REGISTRY",
]
