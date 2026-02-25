#!/usr/bin/env python3
"""
GpyX — GPS Route Converter
================================
Convert GPS route files between formats, with track simplification tools.

Originally inspired by ITN Converter v1.94 by Benichou Software (MIT License).

Usage:
    python itnconv.py input.gpx output.itn           # Convert GPX → ITN
    python itnconv.py route.kml route.csv             # Convert KML → CSV
    python itnconv.py input.itn output.gpx --info     # Convert + show info
    python itnconv.py --formats                       # List all formats
    python itnconv.py --info route.gpx                # Show file info only
    python itnconv.py input.gpx output1.kml output2.csv  # Multi-output
"""

from __future__ import annotations
import argparse
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import GpsPoint, GpsPointArray, GpsRoute, ArrayType
from formats import (
    FORMAT_REGISTRY, read_file, write_file, convert,
    supported_input_formats, supported_output_formats,
    get_format, SOFT_FULL_NAME,
)


def format_distance(meters: float) -> str:
    """Format distance in human-readable form."""
    if meters >= 1000:
        return f"{meters / 1000:.2f} km"
    return f"{meters:.0f} m"


def show_info(arrays, filepath: str = ""):
    """Display information about GPS data."""
    if filepath:
        print(f"\n📁 File: {filepath}")
        ext = Path(filepath).suffix.lower().lstrip(".")
        fmt = get_format(ext)
        if fmt:
            print(f"   Format: {fmt.name} (.{fmt.extension})")

    for i, arr in enumerate(arrays):
        type_names = {
            ArrayType.ROUTE: "🛣️  Route",
            ArrayType.TRACK: "📍 Track",
            ArrayType.WAYPOINT: "📌 Waypoints",
            ArrayType.POI: "⭐ POI",
        }
        type_name = type_names.get(arr.array_type, "Unknown")
        name = arr.name or "(unnamed)"
        print(f"\n   [{i+1}] {type_name}: {name}")
        print(f"       Points: {len(arr)}")

        if arr:
            dist = arr.total_distance()
            print(f"       Distance: {format_distance(dist)}")
            min_lat, min_lng, max_lat, max_lng = arr.bounds()
            print(f"       Bounds: ({min_lat:.6f}, {min_lng:.6f}) → ({max_lat:.6f}, {max_lng:.6f})")

            # Show first/last points
            first = arr[0]
            last = arr[-1]
            print(f"       Start: {first.lat:.6f}, {first.lng:.6f}  {first.name}")
            if len(arr) > 1:
                print(f"       End:   {last.lat:.6f}, {last.lng:.6f}  {last.name}")


def list_formats():
    """Display all supported formats."""
    print(f"\n{SOFT_FULL_NAME}")
    print("=" * 55)
    print(f"{'Extension':<12} {'Format Name':<30} {'R':>3} {'W':>3}")
    print("-" * 55)
    for fmt in sorted(FORMAT_REGISTRY, key=lambda f: f.extension):
        r = "✓" if fmt.reader else "-"
        w = "✓" if fmt.writer else "-"
        print(f"  .{fmt.extension:<10} {fmt.name:<30} {r:>3} {w:>3}")
    print("-" * 55)
    print(f"  Total: {len(FORMAT_REGISTRY)} formats")
    print(f"  Readable: {len(supported_input_formats())}, Writable: {len(supported_output_formats())}\n")


def main():
    parser = argparse.ArgumentParser(
        prog="itnconv",
        description=f"{SOFT_FULL_NAME} — GPS Route Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.gpx output.itn          Convert GPX to TomTom ITN
  %(prog)s route.kml route.csv            Convert KML to CSV
  %(prog)s --info route.gpx               Show file information
  %(prog)s --formats                      List all supported formats
  %(prog)s in.itn out.gpx out.kml         Convert to multiple formats
  %(prog)s in.csv out.gpx --csv-sep ";"   Use semicolon CSV separator
        """)

    parser.add_argument("input", nargs="?", help="Input GPS file")
    parser.add_argument("outputs", nargs="*", help="Output GPS file(s)")
    parser.add_argument("--formats", action="store_true", help="List supported formats")
    parser.add_argument("--info", action="store_true", help="Show file info")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--reverse", action="store_true", help="Reverse route direction")
    parser.add_argument("--dedup", action="store_true", help="Remove duplicate points")
    parser.add_argument("--name", type=str, help="Set route name")

    # CSV options
    csv_group = parser.add_argument_group("CSV options")
    csv_group.add_argument("--csv-sep", default=",", help="CSV separator (default: ,)")
    csv_group.add_argument("--csv-dec", default=".", help="CSV decimal separator (default: .)")
    csv_group.add_argument("--csv-col-lat", type=int, default=0, help="CSV latitude column (0-based)")
    csv_group.add_argument("--csv-col-lng", type=int, default=1, help="CSV longitude column (0-based)")
    csv_group.add_argument("--csv-col-alt", type=int, default=2, help="CSV altitude column (-1 to skip)")
    csv_group.add_argument("--csv-col-name", type=int, default=3, help="CSV name column (-1 to skip)")
    csv_group.add_argument("--csv-col-comment", type=int, default=4, help="CSV comment column (-1 to skip)")

    # ITN options
    itn_group = parser.add_argument_group("ITN options")
    itn_group.add_argument("--itn-max-points", type=int, default=0,
                           help="Split ITN into files of max N points (0 = no split)")

    args = parser.parse_args()

    if args.formats:
        list_formats()
        return 0

    if not args.input:
        parser.print_help()
        return 1

    # Build options dict
    opts = {
        "separator": args.csv_sep,
        "decimal": args.csv_dec,
        "col_lat": args.csv_col_lat,
        "col_lng": args.csv_col_lng,
        "col_alt": args.csv_col_alt,
        "col_name": args.csv_col_name,
        "col_comment": args.csv_col_comment,
        "max_points": args.itn_max_points,
    }

    # Read input
    try:
        arrays = read_file(args.input, **opts)
    except Exception as e:
        print(f"❌ Error reading {args.input}: {e}", file=sys.stderr)
        return 1

    if not arrays:
        print(f"❌ No GPS data found in {args.input}", file=sys.stderr)
        return 1

    total_points = sum(len(a) for a in arrays)
    if args.verbose or args.info:
        show_info(arrays, args.input)

    if args.info and not args.outputs:
        return 0

    if not args.outputs:
        # Just info mode
        if not args.info:
            print(f"✅ Read {total_points} points from {args.input}")
            print("   (specify output file(s) to convert, or use --info for details)")
        return 0

    # Merge all arrays into single route
    merged = GpsRoute(arrays[0].name)
    for arr in arrays:
        for pt in arr:
            merged.append(pt.copy())

    # Apply transforms
    if args.name:
        merged.name = args.name
    if args.reverse:
        merged.reverse()
        if args.verbose:
            print("   ↩️  Route reversed")
    if args.dedup:
        before = len(merged)
        merged.remove_duplicates()
        if args.verbose:
            print(f"   🔄 Removed {before - len(merged)} duplicates")

    # Write output(s)
    for output_path in args.outputs:
        try:
            write_file(output_path, merged, **opts)
            ext = Path(output_path).suffix.lower().lstrip(".")
            fmt = get_format(ext)
            fmt_name = fmt.name if fmt else ext.upper()
            print(f"✅ Converted → {output_path} ({fmt_name}, {len(merged)} points)")
        except Exception as e:
            print(f"❌ Error writing {output_path}: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
