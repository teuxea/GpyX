"""
GpyX — GPS Format Readers & Writers

Conversion logic originally inspired by ITN Converter v1.94 by Benichou Software (MIT License)
https://github.com/Benichou34/itnconverter

Supported formats:
  Read & Write: ITN, GPX, KML, CSV, OV2, OZI/RTE, PLT, WPT, RT2, BCR, OSM, LMX, TK, DAT, GeoJSON
  Read only:  URL (Google Maps links)
  Write only: LOC (geocaching)
"""

from __future__ import annotations
import struct
import math
import os
import sys
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Callable
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (
    GpsPoint, GpsPointArray, GpsRoute, GpsTrack,
    GpsWaypointArray, GpsPoiArray, ArrayType,
)

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

SOFT_NAME = "GpyX"
SOFT_VERSION = "1.0"
SOFT_FULL_NAME = f"{SOFT_NAME} v{SOFT_VERSION}"
SOFT_CREDITS = "Based on ITN Converter v1.94 by Benichou Software (MIT License) — https://github.com/Benichou34/itnconverter"


def _safe_float(s: str, default: float = 0.0) -> float:
    try:
        return float(s.strip())
    except (ValueError, TypeError):
        return default


def _safe_int(s: str, default: int = 0) -> int:
    try:
        return int(s.strip())
    except (ValueError, TypeError):
        return default


def _xml_prettify(root: ET.Element) -> str:
    rough = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return minidom.parseString(rough).toprettyxml(indent="  ", encoding=None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────
# ITN (TomTom Itinerary) - .itn
# ─────────────────────────────────────────────────────────────

ITN_FACTOR = 100000.0
TT_DEPARTURE = 4
TT_WAYPOINT = 0
TT_DESTINATION = 2


def read_itn(filepath: str) -> List[GpsPointArray]:
    """Read TomTom .itn file."""
    route = GpsRoute()
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) >= 4:
                pt = GpsPoint()
                pt.lng = _safe_int(parts[0]) / ITN_FACTOR
                pt.lat = _safe_int(parts[1]) / ITN_FACTOR
                pt.name = parts[2]
                route.append(pt)
    return [route] if route else []


def write_itn(filepath: str, route: GpsRoute, max_points: int = 0):
    """Write TomTom .itn file."""
    def _write_one(path: str, rte: GpsRoute):
        with open(path, "w", encoding="utf-8") as f:
            for i, pt in enumerate(rte):
                if i == 0:
                    flag = TT_DEPARTURE
                elif i == rte.upper_bound:
                    flag = TT_DESTINATION
                else:
                    flag = TT_WAYPOINT
                lng = int(math.floor(pt.lng * ITN_FACTOR) + 0.5)
                lat = int(math.floor(pt.lat * ITN_FACTOR) + 0.5)
                f.write(f"{lng:06d}|{lat:07d}|{pt.name}|{flag}|\r\n")

    if max_points <= 0 or len(route) <= max_points:
        _write_one(filepath, route)
    else:
        base, ext = os.path.splitext(filepath)
        current = 0
        part = 0
        while current < len(route):
            part += 1
            start = max(0, current - (1 if current > 0 else 0))
            count = min(max_points, len(route) - start)
            sub = GpsRoute.from_array(route, start, count)
            _write_one(f"{base}_{part}{ext}", sub)
            current = start + count


# ─────────────────────────────────────────────────────────────
# GPX (GPS Exchange Format) - .gpx
# ─────────────────────────────────────────────────────────────

_GPX_NS = {"": "http://www.topografix.com/GPX/1/0", "gpx11": "http://www.topografix.com/GPX/1/1"}


def read_gpx(filepath: str) -> List[GpsPointArray]:
    """Read GPX file (routes, tracks, waypoints)."""
    results: List[GpsPointArray] = []
    tree = ET.parse(filepath)
    root = tree.getroot()

    # Strip namespace for easier parsing
    ns = ""
    m = re.match(r"\{(.+?)\}", root.tag)
    if m:
        ns = m.group(1)

    def _tag(name):
        return f"{{{ns}}}{name}" if ns else name

    def _parse_point(elem) -> GpsPoint:
        pt = GpsPoint()
        pt.lat = _safe_float(elem.get("lat", "0"))
        pt.lng = _safe_float(elem.get("lon", "0"))
        name_el = elem.find(_tag("name"))
        if name_el is not None and name_el.text:
            pt.name = name_el.text
        ele_el = elem.find(_tag("ele"))
        if ele_el is not None and ele_el.text:
            pt.alt = _safe_float(ele_el.text)
        cmt_el = elem.find(_tag("cmt"))
        if cmt_el is not None and cmt_el.text:
            pt.comment = cmt_el.text
        desc_el = elem.find(_tag("desc"))
        if desc_el is not None and desc_el.text and not pt.comment:
            pt.comment = desc_el.text
        return pt

    # Waypoints
    wpts = root.findall(_tag("wpt"))
    if wpts:
        wpt_array = GpsWaypointArray()
        for wpt in wpts:
            wpt_array.append(_parse_point(wpt))
        if wpt_array:
            results.append(wpt_array)

    # Routes
    for rte in root.findall(_tag("rte")):
        route = GpsRoute()
        name_el = rte.find(_tag("name"))
        if name_el is not None and name_el.text:
            route.name = name_el.text
        for rtept in rte.findall(_tag("rtept")):
            route.append(_parse_point(rtept))
        if route:
            results.append(route)

    # Tracks
    for trk in root.findall(_tag("trk")):
        track = GpsTrack()
        name_el = trk.find(_tag("name"))
        if name_el is not None and name_el.text:
            track.name = name_el.text
        for trkseg in trk.findall(_tag("trkseg")):
            for trkpt in trkseg.findall(_tag("trkpt")):
                track.append(_parse_point(trkpt))
        if track:
            results.append(track)

    return results


def write_gpx(filepath: str, route: GpsRoute, **kwargs):
    """Write GPX file."""
    root = ET.Element("gpx")
    root.set("version", "1.0")
    root.set("creator", SOFT_FULL_NAME)
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns", "http://www.topografix.com/GPX/1/0")
    root.set("xsi:schemaLocation",
             "http://www.topografix.com/GPX/1/0 http://www.topografix.com/GPX/1/0/gpx.xsd")

    ET.SubElement(root, "time").text = _now_iso()

    if route:
        min_lat, min_lng, max_lat, max_lng = route.bounds()
        bounds = ET.SubElement(root, "bounds")
        bounds.set("minlat", str(min_lat))
        bounds.set("minlon", str(min_lng))
        bounds.set("maxlat", str(max_lat))
        bounds.set("maxlon", str(max_lng))

    rte = ET.SubElement(root, "rte")
    if route.name:
        ET.SubElement(rte, "name").text = route.name

    for pt in route:
        rtept = ET.SubElement(rte, "rtept")
        rtept.set("lat", str(pt.lat))
        rtept.set("lon", str(pt.lng))
        if pt.alt != 0:
            ET.SubElement(rtept, "ele").text = str(pt.alt)
        if pt.name:
            ET.SubElement(rtept, "name").text = pt.name
        if pt.comment:
            ET.SubElement(rtept, "desc").text = pt.comment

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_xml_prettify(root))


# ─────────────────────────────────────────────────────────────
# KML (Google Earth) - .kml
# ─────────────────────────────────────────────────────────────

_KML_NS = "http://www.opengis.net/kml/2.2"
_KML_GX_NS = "http://www.google.com/kml/ext/2.2"


def read_kml(filepath: str) -> List[GpsPointArray]:
    """Read Google Earth KML file."""
    results: List[GpsPointArray] = []
    tree = ET.parse(filepath)
    root = tree.getroot()

    ns = ""
    m = re.match(r"\{(.+?)\}", root.tag)
    if m:
        ns = m.group(1)

    def _tag(name):
        return f"{{{ns}}}{name}" if ns else name

    def _parse_coords(text: str) -> List[GpsPoint]:
        points = []
        for token in text.strip().split():
            parts = token.split(",")
            if len(parts) >= 2:
                pt = GpsPoint()
                pt.lng = _safe_float(parts[0])
                pt.lat = _safe_float(parts[1])
                if len(parts) >= 3:
                    pt.alt = _safe_float(parts[2])
                if pt:
                    points.append(pt)
        return points

    def _process_folder(elem):
        waypoints = GpsWaypointArray()
        name_el = elem.find(_tag("name"))
        if name_el is not None and name_el.text:
            waypoints.name = name_el.text

        for pm in elem.findall(_tag("Placemark")):
            pt = GpsPoint()
            pm_name = pm.find(_tag("name"))
            if pm_name is not None and pm_name.text:
                pt.name = pm_name.text

            snippet = pm.find(_tag("Snippet"))
            if snippet is not None and snippet.text:
                pt.comment = snippet.text
            desc = pm.find(_tag("description"))
            if desc is not None and desc.text and not pt.comment:
                pt.comment = desc.text

            # Point geometry
            point_el = pm.find(f".//{_tag('Point')}/{_tag('coordinates')}")
            if point_el is not None and point_el.text:
                coords = point_el.text.strip().split(",")
                if len(coords) >= 2:
                    pt.lng = _safe_float(coords[0])
                    pt.lat = _safe_float(coords[1])
                if len(coords) >= 3:
                    pt.alt = _safe_float(coords[2])
                if pt:
                    waypoints.append(pt)

            # LineString geometry → track
            ls = pm.find(f".//{_tag('LineString')}/{_tag('coordinates')}")
            if ls is not None and ls.text:
                track = GpsTrack(pt.name)
                for trkpt in _parse_coords(ls.text):
                    track.append(trkpt)
                if track:
                    results.append(track)

        if waypoints:
            results.append(waypoints)

        # Recurse into sub-folders
        for subfolder in elem.findall(_tag("Folder")):
            _process_folder(subfolder)

    # Process Document or root
    doc = root.find(_tag("Document"))
    if doc is not None:
        _process_folder(doc)
    else:
        _process_folder(root)

    return results


def write_kml(filepath: str, route: GpsRoute, **kwargs):
    """Write Google Earth KML file."""
    root = ET.Element("kml")
    root.set("xmlns", _KML_NS)
    root.set("xmlns:gx", _KML_GX_NS)

    doc = ET.SubElement(root, "Document")
    doc.set("id", "DOC")
    ET.SubElement(doc, "open").text = "1"
    ET.SubElement(doc, "description").text = f"Generated by {SOFT_FULL_NAME}"
    if route.name:
        ET.SubElement(doc, "name").text = route.name

    # Route line
    pm_road = ET.SubElement(doc, "Placemark")
    ET.SubElement(pm_road, "name").text = f"Route ({len(route)} waypoints)"
    mg = ET.SubElement(pm_road, "MultiGeometry")
    ls = ET.SubElement(mg, "LineString")
    coords_text = " ".join(f"{pt.lng},{pt.lat},0" for pt in route)
    ET.SubElement(ls, "coordinates").text = coords_text

    # Waypoints folder
    folder = ET.SubElement(doc, "Folder")
    ET.SubElement(folder, "name").text = "Waypoints"

    for pt in route:
        pm = ET.SubElement(folder, "Placemark")
        if pt.name:
            ET.SubElement(pm, "name").text = pt.name
        if pt.comment:
            ET.SubElement(pm, "Snippet").text = pt.comment
        point = ET.SubElement(pm, "Point")
        ET.SubElement(point, "coordinates").text = f"{pt.lng},{pt.lat},{pt.alt}"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_xml_prettify(root))


# ─────────────────────────────────────────────────────────────
# CSV (Comma Separated Values) - .csv
# ─────────────────────────────────────────────────────────────

# Default CSV column layout
CSV_DEFAULTS = {
    "separator": ",",
    "decimal": ".",
    "col_lat": 0,
    "col_lng": 1,
    "col_alt": 2,
    "col_name": 3,
    "col_comment": 4,
}


def read_csv(filepath: str, **opts) -> List[GpsPointArray]:
    """Read CSV file. Options: separator, decimal, col_lat, col_lng, col_alt, col_name, col_comment."""
    cfg = {**CSV_DEFAULTS, **opts}
    sep = cfg["separator"]
    dec = cfg["decimal"]

    route = GpsRoute()
    with open(filepath, "r", encoding="utf-8-sig") as f:
        first_line = True
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = _csv_split(line, sep)

            # Try to skip header
            if first_line:
                first_line = False
                # If first col_lat field doesn't parse as float, skip header
                if cfg["col_lat"] < len(parts):
                    test = parts[cfg["col_lat"]].strip().strip('"')
                    if dec != ".":
                        test = test.replace(dec, ".")
                    try:
                        float(test)
                    except ValueError:
                        continue

            pt = GpsPoint()
            if cfg["col_lat"] >= 0 and cfg["col_lat"] < len(parts):
                val = parts[cfg["col_lat"]].strip().strip('"')
                if dec != ".":
                    val = val.replace(dec, ".")
                pt.lat = _safe_float(val)
            if cfg["col_lng"] >= 0 and cfg["col_lng"] < len(parts):
                val = parts[cfg["col_lng"]].strip().strip('"')
                if dec != ".":
                    val = val.replace(dec, ".")
                pt.lng = _safe_float(val)
            if cfg.get("col_alt", -1) >= 0 and cfg["col_alt"] < len(parts):
                val = parts[cfg["col_alt"]].strip().strip('"')
                if dec != ".":
                    val = val.replace(dec, ".")
                pt.alt = _safe_float(val)
            if cfg.get("col_name", -1) >= 0 and cfg["col_name"] < len(parts):
                pt.name = parts[cfg["col_name"]].strip().strip('"')
            if cfg.get("col_comment", -1) >= 0 and cfg["col_comment"] < len(parts):
                pt.comment = parts[cfg["col_comment"]].strip().strip('"')

            if pt:
                route.append(pt)
    return [route] if route else []


def _csv_split(line: str, sep: str) -> List[str]:
    """Split CSV line respecting quotes."""
    result = []
    current = ""
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
            current += ch
        elif ch == sep and not in_quotes:
            result.append(current)
            current = ""
        else:
            current += ch
    result.append(current)
    return result


def write_csv(filepath: str, route: GpsRoute, **opts):
    """Write CSV file."""
    cfg = {**CSV_DEFAULTS, **opts}
    sep = cfg["separator"]
    dec = cfg["decimal"]

    headers = [""] * 5
    headers[cfg["col_lat"]] = "Latitude"
    headers[cfg["col_lng"]] = "Longitude"
    if cfg.get("col_alt", -1) >= 0:
        headers[cfg["col_alt"]] = "Altitude"
    if cfg.get("col_name", -1) >= 0:
        headers[cfg["col_name"]] = "Name"
    if cfg.get("col_comment", -1) >= 0:
        headers[cfg["col_comment"]] = "Comment"
    headers = [h for h in headers if h]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(sep.join(headers) + "\r\n")
        for pt in route:
            fields = [""] * 5
            lat_s = str(pt.lat)
            lng_s = str(pt.lng)
            alt_s = str(pt.alt)
            if dec != ".":
                lat_s = lat_s.replace(".", dec)
                lng_s = lng_s.replace(".", dec)
                alt_s = alt_s.replace(".", dec)
            fields[cfg["col_lat"]] = lat_s
            fields[cfg["col_lng"]] = lng_s
            if cfg.get("col_alt", -1) >= 0:
                fields[cfg["col_alt"]] = alt_s
            if cfg.get("col_name", -1) >= 0:
                fields[cfg["col_name"]] = f'"{pt.name}"'
            if cfg.get("col_comment", -1) >= 0:
                fields[cfg["col_comment"]] = f'"{pt.comment}"'
            fields = [fld for fld in fields if fld != "" or True][:len(headers)]
            f.write(sep.join(fields) + "\r\n")


# ─────────────────────────────────────────────────────────────
# OV2 (TomTom POI) - .ov2 (binary)
# ─────────────────────────────────────────────────────────────

OV2_FACTOR = 100000.0
OV2_SIMPLE = 0x02
OV2_EXTENDED = 0x03
OV2_TYPE_1 = 0x01
OV2_DELETED = 0x00
OV2_TYPE_1_LEN = 21
OV2_HEADER_LEN = 13


def read_ov2(filepath: str) -> List[GpsPointArray]:
    """Read TomTom OV2 POI binary file."""
    pois = GpsPoiArray()
    with open(filepath, "rb") as f:
        data = f.read()

    pos = 0
    while pos < len(data):
        record_type = data[pos]
        if record_type == OV2_DELETED:
            rec_len = struct.unpack_from("<I", data, pos + 1)[0]
        elif record_type in (OV2_SIMPLE, OV2_EXTENDED):
            rec_len = struct.unpack_from("<I", data, pos + 1)[0]
            lng = struct.unpack_from("<i", data, pos + 5)[0]
            lat = struct.unpack_from("<i", data, pos + 9)[0]
            name_data = data[pos + 13:pos + rec_len]
            name = name_data.split(b"\x00")[0].decode("latin-1", errors="replace")
            pt = GpsPoint(lat=lat / OV2_FACTOR, lng=lng / OV2_FACTOR, name=name)
            pois.append(pt)
        elif record_type == OV2_TYPE_1:
            rec_len = OV2_TYPE_1_LEN
        else:
            break
        pos += rec_len
    return [pois] if pois else []


def write_ov2(filepath: str, route: GpsRoute, **kwargs):
    """Write TomTom OV2 POI binary file."""
    with open(filepath, "wb") as f:
        for pt in route:
            name_bytes = pt.name.encode("latin-1", errors="replace") + b"\x00"
            rec_len = OV2_HEADER_LEN + len(name_bytes)
            lng = int(math.floor(pt.lng * OV2_FACTOR) + 0.5)
            lat = int(math.floor(pt.lat * OV2_FACTOR) + 0.5)
            f.write(struct.pack("<B", OV2_SIMPLE))
            f.write(struct.pack("<I", rec_len))
            f.write(struct.pack("<i", lng))
            f.write(struct.pack("<i", lat))
            f.write(name_bytes)


# ─────────────────────────────────────────────────────────────
# OZI Explorer Route - .rte
# ─────────────────────────────────────────────────────────────

OZI_HEADER = "OziExplorer Route File Version 1.0"


def read_ozi(filepath: str) -> List[GpsPointArray]:
    """Read OziExplorer route .rte file."""
    results: List[GpsPointArray] = []
    current_route: Optional[GpsRoute] = None
    current_route_num = -1
    header_found = False

    with open(filepath, "r", encoding="latin-1") as f:
        for line in f:
            parts = line.strip().split(",")
            if not parts:
                continue
            if not header_found:
                if parts[0].strip() == OZI_HEADER:
                    header_found = True
                continue
            tag = parts[0].strip()
            if tag == "R" and len(parts) > 3:
                current_route = GpsRoute()
                current_route_num = _safe_int(parts[1])
                current_route.name = parts[2].strip()
                results.append(current_route)
            elif tag == "W" and current_route is not None and len(parts) > 7:
                rte_num = _safe_int(parts[1])
                if rte_num == current_route_num:
                    pt = GpsPoint()
                    pt.name = parts[4].strip() if len(parts) > 4 else ""
                    pt.lat = _safe_float(parts[5])
                    pt.lng = _safe_float(parts[6])
                    if len(parts) > 13:
                        pt.comment = parts[13].strip()[:40]
                    current_route.append(pt)
    return results


def write_ozi(filepath: str, route: GpsRoute, **kwargs):
    """Write OziExplorer route .rte file."""
    with open(filepath, "w", encoding="latin-1", newline="") as f:
        f.write(f"{OZI_HEADER}\r\nWGS 84\r\nReserved 1\r\nReserved 2\r\n")
        name = route.name.replace(",", " ")
        f.write(f"R,1,{name},,\r\n")
        for i, pt in enumerate(route):
            pt_name = pt.name.replace(",", " ")
            pt_desc = pt.comment.replace(",", " ")[:40]
            f.write(f"W,1,{i+1},{i+1},{pt_name},{pt.lat:.7f},{pt.lng:.7f},,0,1,3,0,65535,{pt_desc},0,0\r\n")


# ─────────────────────────────────────────────────────────────
# OZI Explorer Track - .plt
# ─────────────────────────────────────────────────────────────

def read_plt(filepath: str) -> List[GpsPointArray]:
    """Read OziExplorer track .plt file."""
    track = GpsTrack()
    with open(filepath, "r", encoding="latin-1") as f:
        line_num = 0
        for line in f:
            line_num += 1
            if line_num <= 6:
                if line_num == 4:
                    # Track name on line 4 (0-indexed field)
                    pass
                continue
            parts = line.strip().split(",")
            if len(parts) >= 2:
                pt = GpsPoint()
                pt.lat = _safe_float(parts[0])
                pt.lng = _safe_float(parts[1])
                if len(parts) > 3:
                    pt.alt = _safe_float(parts[3])
                if pt:
                    track.append(pt)
    return [track] if track else []


def write_plt(filepath: str, route: GpsRoute, **kwargs):
    """Write OziExplorer track .plt file."""
    with open(filepath, "w", encoding="latin-1", newline="") as f:
        f.write("OziExplorer Track Point File Version 2.1\r\n")
        f.write("WGS 84\r\n")
        f.write("Altitude is in Feet\r\n")
        f.write("Reserved 3\r\n")
        f.write(f"0,2,255,{route.name},0,0,2,8421376\r\n")
        f.write(f"{len(route)}\r\n")
        for pt in route:
            alt_feet = pt.alt / 0.3048
            f.write(f"{pt.lat:.7f},{pt.lng:.7f},0,{alt_feet:.1f},0,,\r\n")


# ─────────────────────────────────────────────────────────────
# OZI Explorer Waypoint - .wpt
# ─────────────────────────────────────────────────────────────

def read_wpt(filepath: str) -> List[GpsPointArray]:
    """Read OziExplorer waypoint .wpt file."""
    waypoints = GpsWaypointArray()
    with open(filepath, "r", encoding="latin-1") as f:
        line_num = 0
        for line in f:
            line_num += 1
            if line_num <= 4:
                continue
            parts = line.strip().split(",")
            if len(parts) >= 4:
                pt = GpsPoint()
                pt.name = parts[1].strip() if len(parts) > 1 else ""
                pt.lat = _safe_float(parts[2])
                pt.lng = _safe_float(parts[3])
                if len(parts) > 14:
                    pt.alt = _safe_float(parts[14]) * 0.3048  # feet to meters
                if len(parts) > 10:
                    pt.comment = parts[10].strip()[:40]
                if pt:
                    waypoints.append(pt)
    return [waypoints] if waypoints else []


def write_wpt(filepath: str, route: GpsRoute, **kwargs):
    """Write OziExplorer waypoint .wpt file."""
    with open(filepath, "w", encoding="latin-1", newline="") as f:
        f.write("OziExplorer Waypoint File Version 1.1\r\n")
        f.write("WGS 84\r\n")
        f.write("Reserved 2\r\n")
        f.write("garmin\r\n")
        for i, pt in enumerate(route):
            name = pt.name.replace(",", " ")[:8]
            desc = pt.comment.replace(",", " ")[:40]
            alt_feet = pt.alt / 0.3048
            f.write(f"{i+1},{name},{pt.lat:.7f},{pt.lng:.7f},,,1,3,3,0,65535,{desc},0,0,0,{alt_feet:.1f}\r\n")


# ─────────────────────────────────────────────────────────────
# RT2 (OziExplorer Route v2) - .rt2
# ─────────────────────────────────────────────────────────────

def read_rt2(filepath: str) -> List[GpsPointArray]:
    """Read OziExplorer Route v2 .rt2 file."""
    results: List[GpsPointArray] = []
    current_route = None

    with open(filepath, "r", encoding="latin-1") as f:
        line_num = 0
        for line in f:
            line_num += 1
            if line_num <= 4:
                continue
            parts = line.strip().split(",")
            if not parts:
                continue
            tag = parts[0].strip()
            if tag == "R" and len(parts) > 2:
                current_route = GpsRoute(parts[2].strip())
                results.append(current_route)
            elif tag == "W" and current_route and len(parts) > 6:
                pt = GpsPoint()
                pt.name = parts[3].strip()
                pt.lat = _safe_float(parts[4])
                pt.lng = _safe_float(parts[5])
                current_route.append(pt)
    return results


def write_rt2(filepath: str, route: GpsRoute, **kwargs):
    """Write OziExplorer Route v2 .rt2 file."""
    with open(filepath, "w", encoding="latin-1", newline="") as f:
        f.write("OziExplorer Route2 File Version 1.0\r\n")
        f.write("WGS 84\r\n")
        f.write("Reserved 1\r\n")
        f.write("Reserved 2\r\n")
        name = route.name.replace(",", " ")
        f.write(f"R,0,{name},,255\r\n")
        for i, pt in enumerate(route):
            pt_name = pt.name.replace(",", " ")
            f.write(f"W,0,{i+1},{pt_name},{pt.lat:.7f},{pt.lng:.7f},0,0\r\n")


# ─────────────────────────────────────────────────────────────
# BCR (Marco Polo / Motorrad Routenplaner) - .bcr
# ─────────────────────────────────────────────────────────────

# BCR uses Mercator projection x,y coordinates
def _lat_lng_to_mercator(lat: float, lng: float) -> Tuple[int, int]:
    """Convert WGS84 lat/lng to Mercator X,Y (as used in BCR)."""
    x = int(lng * 100000.0)
    lat_rad = math.radians(lat)
    y = int(math.log(math.tan(lat_rad / 2 + math.pi / 4)) * 180.0 / math.pi * 100000.0)
    return x, y


def _mercator_to_lat_lng(x: int, y: int) -> Tuple[float, float]:
    """Convert Mercator X,Y to WGS84 lat/lng."""
    lng = x / 100000.0
    lat_deg = y / 100000.0
    lat = math.degrees(2 * math.atan(math.exp(math.radians(lat_deg))) - math.pi / 2)
    return lat, lng


def read_bcr(filepath: str) -> List[GpsPointArray]:
    """Read BCR (Marco Polo) INI-style file."""
    import configparser
    config = configparser.ConfigParser(interpolation=None)
    config.read(filepath, encoding="latin-1")

    route = GpsRoute()

    if config.has_section("CLIENT") and config.has_option("CLIENT", "ROUTENAME"):
        route.name = config.get("CLIENT", "ROUTENAME")

    i = 1
    while True:
        key = f"STATION{i}"
        if not config.has_section("COORDINATES") or not config.has_option("COORDINATES", key):
            break
        coords_str = config.get("COORDINATES", key)
        parts = coords_str.split(",")
        if len(parts) >= 2:
            x, y = _safe_int(parts[0]), _safe_int(parts[1])
            lat, lng = _mercator_to_lat_lng(x, y)
            pt = GpsPoint(lat=lat, lng=lng)

            if config.has_section("DESCRIPTION") and config.has_option("DESCRIPTION", key):
                pt.name = config.get("DESCRIPTION", key)

            route.append(pt)
        i += 1

    return [route] if route else []


def write_bcr(filepath: str, route: GpsRoute, **kwargs):
    """Write BCR (Marco Polo) INI-style file."""
    import configparser
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str  # Keep case

    config["CLIENT"] = {"REQUEST": "TRUE", "ROUTENAME": route.name}
    for i, pt in enumerate(route):
        config["CLIENT"][f"STATION{i+1}"] = "Standort,999999999"

    config["COORDINATES"] = {}
    for i, pt in enumerate(route):
        x, y = _lat_lng_to_mercator(pt.lat, pt.lng)
        config["COORDINATES"][f"STATION{i+1}"] = f"{x},{y}"

    config["DESCRIPTION"] = {}
    for i, pt in enumerate(route):
        config["DESCRIPTION"][f"STATION{i+1}"] = pt.name

    config["ROUTE"] = {}

    with open(filepath, "w", encoding="latin-1") as f:
        config.write(f)


# ─────────────────────────────────────────────────────────────
# OSM (OpenStreetMap) - .osm
# ─────────────────────────────────────────────────────────────

def read_osm(filepath: str) -> List[GpsPointArray]:
    """Read OpenStreetMap .osm file (nodes)."""
    tree = ET.parse(filepath)
    root = tree.getroot()
    waypoints = GpsWaypointArray()

    for node in root.findall("node"):
        pt = GpsPoint()
        pt.lat = _safe_float(node.get("lat", "0"))
        pt.lng = _safe_float(node.get("lon", "0"))
        for tag in node.findall("tag"):
            k = tag.get("k", "")
            v = tag.get("v", "")
            if k == "name":
                pt.name = v
            elif k in ("description", "note"):
                pt.comment = v
        if pt:
            waypoints.append(pt)
    return [waypoints] if waypoints else []


def write_osm(filepath: str, route: GpsRoute, **kwargs):
    """Write OpenStreetMap .osm file."""
    root = ET.Element("osm")
    root.set("version", "0.6")
    root.set("generator", SOFT_FULL_NAME)

    for i, pt in enumerate(route):
        node = ET.SubElement(root, "node")
        node.set("id", str(-(i + 1)))
        node.set("lat", str(pt.lat))
        node.set("lon", str(pt.lng))
        node.set("visible", "true")
        if pt.name:
            tag = ET.SubElement(node, "tag")
            tag.set("k", "name")
            tag.set("v", pt.name)
        if pt.comment:
            tag = ET.SubElement(node, "tag")
            tag.set("k", "description")
            tag.set("v", pt.comment)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_xml_prettify(root))


# ─────────────────────────────────────────────────────────────
# LMX (Nokia Landmarks Exchange) - .lmx
# ─────────────────────────────────────────────────────────────

_LMX_NS = "http://www.nokia.com/schemas/location/landmarks/1/0"


def read_lmx(filepath: str) -> List[GpsPointArray]:
    """Read Nokia LMX file."""
    tree = ET.parse(filepath)
    root = tree.getroot()
    ns = ""
    m = re.match(r"\{(.+?)\}", root.tag)
    if m:
        ns = m.group(1)

    def _tag(name):
        return f"{{{ns}}}{name}" if ns else name

    waypoints = GpsWaypointArray()
    for lm in root.iter(_tag("landmark")):
        pt = GpsPoint()
        name_el = lm.find(_tag("name"))
        if name_el is not None and name_el.text:
            pt.name = name_el.text
        desc_el = lm.find(_tag("description"))
        if desc_el is not None and desc_el.text:
            pt.comment = desc_el.text

        coords = lm.find(f".//{_tag('coordinates')}")
        if coords is not None:
            lat_el = coords.find(_tag("latitude"))
            lng_el = coords.find(_tag("longitude"))
            alt_el = coords.find(_tag("altitude"))
            if lat_el is not None:
                pt.lat = _safe_float(lat_el.text)
            if lng_el is not None:
                pt.lng = _safe_float(lng_el.text)
            if alt_el is not None:
                pt.alt = _safe_float(alt_el.text)
        if pt:
            waypoints.append(pt)
    return [waypoints] if waypoints else []


def write_lmx(filepath: str, route: GpsRoute, **kwargs):
    """Write Nokia LMX file."""
    root = ET.Element("lm:lmx")
    root.set("xmlns:lm", _LMX_NS)
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

    coll = ET.SubElement(root, "lm:landmarkCollection")
    if route.name:
        ET.SubElement(coll, "lm:name").text = route.name

    for pt in route:
        lm = ET.SubElement(coll, "lm:landmark")
        if pt.name:
            ET.SubElement(lm, "lm:name").text = pt.name
        if pt.comment:
            ET.SubElement(lm, "lm:description").text = pt.comment
        coords_el = ET.SubElement(lm, "lm:coordinates")
        ET.SubElement(coords_el, "lm:latitude").text = str(pt.lat)
        ET.SubElement(coords_el, "lm:longitude").text = str(pt.lng)
        if pt.alt != 0:
            ET.SubElement(coords_el, "lm:altitude").text = str(pt.alt)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_xml_prettify(root))


# ─────────────────────────────────────────────────────────────
# DAT (Destinator / NaviGon) - .dat
# ─────────────────────────────────────────────────────────────

def read_dat(filepath: str) -> List[GpsPointArray]:
    """Read DAT (Navigon/Destinator) binary file."""
    route = GpsRoute()
    with open(filepath, "rb") as f:
        data = f.read()

    # DAT files have a 4-byte header with point count
    if len(data) < 4:
        return []

    # Try to detect if it's a simple text-based DAT or binary
    try:
        text = data.decode("utf-16-le")
        lines = text.strip().split("\r\n")
        for line in lines:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                pt = GpsPoint()
                pt.lng = _safe_float(parts[0])
                pt.lat = _safe_float(parts[1])
                if len(parts) > 2:
                    pt.name = parts[2]
                if pt:
                    route.append(pt)
    except (UnicodeDecodeError, ValueError):
        pass

    return [route] if route else []


def write_dat(filepath: str, route: GpsRoute, **kwargs):
    """Write DAT file (UTF-16 tab-separated)."""
    lines = []
    for pt in route:
        name = pt.name or ""
        lines.append(f"{pt.lng}\t{pt.lat}\t{name}")

    with open(filepath, "wb") as f:
        text = "\r\n".join(lines) + "\r\n"
        f.write(text.encode("utf-16-le"))


# ─────────────────────────────────────────────────────────────
# TK (Compe GPS / TwoNav) - .tk
# ─────────────────────────────────────────────────────────────

def read_tk(filepath: str) -> List[GpsPointArray]:
    """Read CompeGPS/TwoNav .tk file."""
    track = GpsTrack()
    with open(filepath, "r", encoding="latin-1") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("G") or line.startswith("U") or line.startswith("C") or line.startswith("N"):
                continue
            if line.startswith("T"):
                parts = line[1:].strip().split()
                if len(parts) >= 2:
                    pt = GpsPoint()
                    pt.lat = _safe_float(parts[1])
                    pt.lng = _safe_float(parts[0])
                    if len(parts) > 5:
                        pt.alt = _safe_float(parts[5]) if parts[5] != "0.000000" else 0
                    if pt:
                        track.append(pt)
    return [track] if track else []


def write_tk(filepath: str, route: GpsRoute, **kwargs):
    """Write CompeGPS/TwoNav .tk file."""
    with open(filepath, "w", encoding="latin-1", newline="") as f:
        f.write("G  WGS 84\r\n")
        f.write("U  1\r\n")
        for pt in route:
            f.write(f"T {pt.lng:.6f} {pt.lat:.6f} 00-00-00 00:00:00 {pt.alt:.6f}\r\n")


# ─────────────────────────────────────────────────────────────
# LOC (Geocaching .loc) - write only
# ─────────────────────────────────────────────────────────────

def write_loc(filepath: str, route: GpsRoute, **kwargs):
    """Write Geocaching .loc file."""
    root = ET.Element("loc")
    root.set("version", "1.0")
    root.set("src", SOFT_FULL_NAME)

    for pt in route:
        wpt = ET.SubElement(root, "waypoint")
        name_el = ET.SubElement(wpt, "name")
        name_el.set("id", pt.name[:6] if pt.name else "WP")
        name_el.text = pt.name
        coord = ET.SubElement(wpt, "coord")
        coord.set("lat", str(pt.lat))
        coord.set("lon", str(pt.lng))

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_xml_prettify(root))


# ─────────────────────────────────────────────────────────────
# Google Maps URL - .url (read only)
# ─────────────────────────────────────────────────────────────

def read_url(filepath: str) -> List[GpsPointArray]:
    """Read Google Maps URL file."""
    route = GpsRoute()
    with open(filepath, "r") as f:
        content = f.read()

    # Extract URL
    url_match = re.search(r'URL\s*=\s*(.+)', content, re.IGNORECASE)
    if url_match:
        url = url_match.group(1).strip()
    else:
        url = content.strip()

    # Parse coordinates from URL
    # Google Maps URL patterns: @lat,lng | saddr=lat,lng | daddr=lat,lng
    coord_pattern = r'(-?\d+\.\d+),\s*(-?\d+\.\d+)'
    matches = re.findall(coord_pattern, url)
    for lat_s, lng_s in matches:
        pt = GpsPoint(lat=float(lat_s), lng=float(lng_s))
        if pt:
            route.append(pt)

    return [route] if route else []


# ─────────────────────────────────────────────────────────────
# GeoJSON - .geojson (bonus format not in original)
# ─────────────────────────────────────────────────────────────

def read_geojson(filepath: str) -> List[GpsPointArray]:
    """Read GeoJSON file."""
    import json
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    results: List[GpsPointArray] = []

    def _process_feature(feat):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        name = props.get("name", "")
        comment = props.get("description", props.get("comment", ""))

        if gtype == "Point" and len(coords) >= 2:
            pt = GpsPoint(lat=coords[1], lng=coords[0], name=name, comment=comment)
            if len(coords) >= 3:
                pt.alt = coords[2]
            return pt
        elif gtype == "LineString":
            track = GpsTrack(name)
            for c in coords:
                pt = GpsPoint(lat=c[1], lng=c[0])
                if len(c) >= 3:
                    pt.alt = c[2]
                track.append(pt)
            if track:
                results.append(track)
        return None

    if data.get("type") == "FeatureCollection":
        wpts = GpsWaypointArray()
        for feat in data.get("features", []):
            pt = _process_feature(feat)
            if pt:
                wpts.append(pt)
        if wpts:
            results.append(wpts)
    elif data.get("type") == "Feature":
        wpts = GpsWaypointArray()
        pt = _process_feature(data)
        if pt:
            wpts.append(pt)
        if wpts:
            results.append(wpts)

    return results


def write_geojson(filepath: str, route: GpsRoute, **kwargs):
    """Write GeoJSON file."""
    import json
    features = []

    # Route as LineString
    if len(route) > 1:
        line_coords = []
        for pt in route:
            coord = [pt.lng, pt.lat]
            if pt.alt != 0:
                coord.append(pt.alt)
            line_coords.append(coord)
        features.append({
            "type": "Feature",
            "properties": {"name": route.name or "Route"},
            "geometry": {"type": "LineString", "coordinates": line_coords}
        })

    # Individual waypoints
    for pt in route:
        coord = [pt.lng, pt.lat]
        if pt.alt != 0:
            coord.append(pt.alt)
        props = {}
        if pt.name:
            props["name"] = pt.name
        if pt.comment:
            props["description"] = pt.comment
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Point", "coordinates": coord}
        })

    geojson = {"type": "FeatureCollection", "features": features}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────
# Format Registry
# ─────────────────────────────────────────────────────────────

@dataclass
class FormatDesc:
    """Description of a file format."""
    extension: str
    name: str
    reader: Optional[Callable] = None
    writer: Optional[Callable] = None


# Master format registry
FORMAT_REGISTRY: List[FormatDesc] = [
    FormatDesc("itn",     "TomTom Itinerary",              read_itn,     write_itn),
    FormatDesc("gpx",     "GPS Exchange Format",            read_gpx,     write_gpx),
    FormatDesc("kml",     "Google Earth KML",               read_kml,     write_kml),
    FormatDesc("csv",     "Comma Separated Values",         read_csv,     write_csv),
    FormatDesc("ov2",     "TomTom POI",                     read_ov2,     write_ov2),
    FormatDesc("rte",     "OziExplorer Route",              read_ozi,     write_ozi),
    FormatDesc("plt",     "OziExplorer Track",              read_plt,     write_plt),
    FormatDesc("wpt",     "OziExplorer Waypoint",           read_wpt,     write_wpt),
    FormatDesc("rt2",     "OziExplorer Route v2",           read_rt2,     write_rt2),
    FormatDesc("bcr",     "Marco Polo / Routenplaner",      read_bcr,     write_bcr),
    FormatDesc("osm",     "OpenStreetMap",                  read_osm,     write_osm),
    FormatDesc("lmx",     "Nokia Landmarks Exchange",       read_lmx,     write_lmx),
    FormatDesc("dat",     "Navigon / Destinator",           read_dat,     write_dat),
    FormatDesc("tk",      "CompeGPS / TwoNav Track",        read_tk,      write_tk),
    FormatDesc("loc",     "Geocaching LOC",                 None,         write_loc),
    FormatDesc("url",     "Google Maps URL",                read_url,     None),
    FormatDesc("geojson", "GeoJSON",                        read_geojson, write_geojson),
]

# Build lookup dicts
_READERS: Dict[str, Callable] = {}
_WRITERS: Dict[str, Callable] = {}
_FORMAT_BY_EXT: Dict[str, FormatDesc] = {}

for fmt in FORMAT_REGISTRY:
    _FORMAT_BY_EXT[fmt.extension] = fmt
    if fmt.reader:
        _READERS[fmt.extension] = fmt.reader
    if fmt.writer:
        _WRITERS[fmt.extension] = fmt.writer


def get_format(ext: str) -> Optional[FormatDesc]:
    """Get format descriptor by extension."""
    return _FORMAT_BY_EXT.get(ext.lower().lstrip("."))


def supported_input_formats() -> List[str]:
    """List of readable format extensions."""
    return sorted(_READERS.keys())


def supported_output_formats() -> List[str]:
    """List of writable format extensions."""
    return sorted(_WRITERS.keys())


def _filter_kwargs(func: Callable, opts: dict) -> dict:
    """Filter kwargs to only include parameters accepted by the function."""
    import inspect
    sig = inspect.signature(func)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return opts  # Function accepts **kwargs
    valid = set(sig.parameters.keys())
    return {k: v for k, v in opts.items() if k in valid}


def read_file(filepath: str, **opts) -> List[GpsPointArray]:
    """Auto-detect format and read GPS file."""
    ext = Path(filepath).suffix.lower().lstrip(".")
    reader = _READERS.get(ext)
    if not reader:
        raise ValueError(f"Unsupported input format: .{ext}\n"
                         f"Supported: {', '.join(supported_input_formats())}")
    filtered = _filter_kwargs(reader, opts)
    return reader(filepath, **filtered)


def write_file(filepath: str, route: GpsRoute, **opts):
    """Auto-detect format and write GPS file."""
    ext = Path(filepath).suffix.lower().lstrip(".")
    writer = _WRITERS.get(ext)
    if not writer:
        raise ValueError(f"Unsupported output format: .{ext}\n"
                         f"Supported: {', '.join(supported_output_formats())}")
    filtered = _filter_kwargs(writer, opts)
    writer(filepath, route, **filtered)


def convert(input_path: str, output_path: str, **opts) -> GpsRoute:
    """Convert a GPS file from one format to another."""
    arrays = read_file(input_path, **opts)
    if not arrays:
        raise ValueError(f"No GPS data found in {input_path}")

    # Merge all arrays into a single route for output
    merged = GpsRoute(arrays[0].name)
    for arr in arrays:
        for pt in arr:
            merged.append(pt.copy())

    write_file(output_path, merged, **opts)
    return merged
