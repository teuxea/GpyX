🇬🇧 English | [🇫🇷 Français](README.fr.md)

# GpyX 🗺️

> ⚠️ **Alpha — early stage, for enthusiasts.** Things may break. Feedback welcome.

**GPS route converter & planner — 17 formats, zero dependencies, runs in your browser.**

> If you used ITN Converter (ITNConv) and miss it — this is for you.

---

## Quick Start

```bash
python3 server.py
```

Opens `http://localhost:8080` in your browser. No `pip install`, no Docker, no API key.

**Requires:** Python 3.8+

---

## What is GpyX?

GpyX is a self-hosted, open-source GPS route tool that does two things well:

**1. Convert anything to anything.** Got a `.itn` from a TomTom, a `.kml` from Google Earth, a `.gpx` from Garmin, a `.csv` from a spreadsheet? GpyX reads and writes 17 GPS formats. Drag-and-drop a file, get it back in the format your device needs.

**2. Plan and edit routes visually.** Click on the map to add waypoints. Drag them around. Get routing via OSRM with distance and duration. Simplify messy tracks from Calimoto or Garmin down to clean routes. Export to your GPS.

### Features

- 📋 **Paste coordinates** in 12 syntaxes — decimal, DMS, Google Maps URLs, Apple Maps, Waze, geo: URIs, Plus Codes
- ⛰️ **Elevation profile** along your route
- 🏷️ **Auto-naming** — reverse geocoding, sequential numbering, or relative naming with anchor points
- ⚓ **Anchors** — protect key waypoints from simplification, securization, and bulk renaming
- 🔒 **Name lock** — freeze individual waypoint names across all operations
- 🔁 **Undo/Redo** with full history
- 🌍 **12 base maps** — OSM, satellite, topographic, cycling, dark mode...
- 👻 **Ghost track** — overlay the original trace after simplification
- 📏 **Route securization** — resample at fixed intervals for GPS devices that need dense waypoints

---

## Formats (17 read, 18 write)

| Format | Ext | R | W | Used by |
|--------|-----|:-:|:-:|---------|
| GPX | .gpx | ✓ | ✓ | Garmin, Strava, Komoot, most GPS |
| ITN | .itn | ✓ | ✓ | TomTom |
| KML | .kml | ✓ | ✓ | Google Earth, Google My Maps |
| CSV | .csv | ✓ | ✓ | Spreadsheets, custom tools |
| GeoJSON | .geojson | ✓ | ✓ | Web mapping, developers |
| OV2 | .ov2 | ✓ | ✓ | TomTom POI |
| RTE | .rte | ✓ | ✓ | OziExplorer Route |
| PLT | .plt | ✓ | ✓ | OziExplorer Track |
| WPT | .wpt | ✓ | ✓ | OziExplorer Waypoint |
| RT2 | .rt2 | ✓ | ✓ | OziExplorer Route v2 |
| BCR | .bcr | ✓ | ✓ | Marco Polo / MotoPlaner |
| OSM | .osm | ✓ | ✓ | OpenStreetMap XML |
| LMX | .lmx | ✓ | ✓ | Nokia Landmarks |
| DAT | .dat | ✓ | ✓ | Navigon / Destinator |
| TK | .tk | ✓ | ✓ | CompeGPS / TwoNav |
| LOC | .loc | — | ✓ | Geocaching |
| URL | .url | ✓ | — | Google Maps URL |

---

## CLI

```bash
python3 itnconv.py input.gpx output.itn           # Convert
python3 itnconv.py route.kml out.itn out.csv       # Multi-output
python3 itnconv.py track.gpx clean.itn --reverse   # Reverse direction
python3 itnconv.py --info route.gpx                # File info
python3 itnconv.py --formats                       # List formats
```

## Python library

```python
from itnconv_py import convert, read_file, write_file

convert("route.gpx", "route.itn")

arrays = read_file("track.gpx")
route = arrays[0]
route.reverse()
route.douglas_peucker(100)  # Simplify to 100m tolerance
write_file("clean.kml", route)
```

---

## Architecture

```
gpyx/
├── server.py      354 lines — Web server + API
├── index.html    1795 lines — Map UI (Leaflet, vanilla JS)
├── itnconv.py     212 lines — CLI
├── models.py      290 lines — GpsPoint, GpsRoute, Douglas-Peucker
├── formats.py    1267 lines — 17 readers + 18 writers
├── __init__.py     31 lines — Library interface
└── README.md
```

**~4000 lines total.** No framework, no build step, no node_modules.

---

## External services

GpyX is self-contained for file conversion. The web UI optionally calls free, open services:

| Service | Used for | Required? |
|---------|----------|-----------|
| [OpenStreetMap](https://www.openstreetmap.org) | Map tiles | Yes (map display) |
| [OSRM Demo](https://router.project-osrm.org) | Route calculation | No |
| [Nominatim](https://nominatim.org) | Address search & naming | No |
| [OpenTopoData](https://www.opentopodata.org) | Elevation profile | No |

Without internet, GpyX still converts files and lets you place waypoints manually.

---

## Why GpyX?

**ITN Converter is dead.** The site is gone, the Google Maps API it relied on now requires a paid key. The last version (1.94) still circulates on forums, but search and routing no longer work.

**GpyX picks up where ITNConv left off:**

- **Web-based** — Mac, Linux, phone, tablet. No Windows-only .exe.
- **No API key dependency** — built on OpenStreetMap, not Google Maps.
- **Open source (AGPL-3.0)** — fork it, fix it, extend it.
- **Self-hosted** — your routes stay on your machine.

---

## Contributing

Side project. Issues and PRs welcome, especially for:

- New GPS formats (Sygic, CoPilot, Waze...)
- UI improvements
- Translations beyond FR/EN
- Bug reports with real-world GPS files

---

## Credits

Conversion logic inspired by [ITN Converter v1.94](https://github.com/Benichou34/itnconverter) by Benichou Software (MIT License). Rewritten from scratch in Python.

Built with [Leaflet](https://leafletjs.com), [OSRM](https://project-osrm.org), [Nominatim](https://nominatim.org). Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.

## Disclaimer

This software is provided as-is, with no warranty of any kind. GpyX is a conversion and planning tool, not a navigation system. **Always verify your routes before riding.** A GPS file — however well-prepared — is a suggestion, not a guarantee. The road is your only reliable guide. Stay alert, trust your eyes, and ride safe.

## License

[AGPL-3.0](LICENSE)
