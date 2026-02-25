#!/usr/bin/env python3
"""
GpyX — Web Server
Serves the map UI and handles GPS file conversion & simplification API.

Originally inspired by ITN Converter v1.94 by Benichou Software (MIT License)
https://github.com/Benichou34/itnconverter

Usage:
    python server.py                  # Start on port 8080
    python server.py --port 9000      # Custom port
    python server.py --no-browser     # Don't auto-open browser
"""

import http.server
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
import webbrowser
import argparse
import base64
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_HERE = os.path.dirname(os.path.abspath(__file__))

try:
    from models import GpsPoint, GpsRoute, GpsTrack, GpsWaypointArray, ArrayType
    from formats import (
        read_file, write_file, FORMAT_REGISTRY,
        SOFT_FULL_NAME, SOFT_CREDITS,
    )
except ModuleNotFoundError as e:
    print(f"\n❌ Module '{e.name}' introuvable.")
    print(f"   Vérifiez que TOUS les fichiers .py sont dans le même dossier :\n")
    for f in ['server.py', 'formats.py', 'models.py', 'index.html', '__init__.py', 'itnconv.py']:
        path = os.path.join(_HERE, f)
        status = '  ✓' if os.path.exists(path) else '  ✗ MANQUANT'
        print(f"   {status}  {f}")
    print(f"\n   Dossier : {_HERE}\n")
    sys.exit(1)

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))


class GpyXHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def end_headers(self):
        # Prevent browser caching of HTML/JS to avoid stale UI issues
        if hasattr(self, '_headers_buffer'):
            path = self.path if hasattr(self, 'path') else ''
            if path.endswith('.html') or path == '/' or path == '':
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", ""):
            self.path = "/index.html"
            return super().do_GET()
        elif parsed.path == "/api/formats":
            self._send_json({
                "input": [{"ext": f.extension, "name": f.name} for f in FORMAT_REGISTRY if f.reader],
                "output": [{"ext": f.extension, "name": f.name} for f in FORMAT_REGISTRY if f.writer],
            })
        elif parsed.path == "/api/about":
            self._send_json({
                "name": SOFT_FULL_NAME,
                "credits": SOFT_CREDITS,
            })
        elif parsed.path == "/api/resolve-url":
            self._handle_resolve_url(parsed)
        else:
            return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        routes = {
            "/api/import": self._handle_import,
            "/api/export": self._handle_export,
            "/api/convert": self._handle_convert,
            "/api/simplify": self._handle_simplify,
        }
        handler = routes.get(parsed.path)
        if handler:
            handler()
        else:
            self.send_error(404)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length)

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_resolve_url(self, parsed):
        """Follow redirects on a short map URL and return the final URL."""
        try:
            qs = urllib.parse.parse_qs(parsed.query)
            url = qs.get("url", [None])[0]
            if not url:
                self._send_json({"error": "Missing 'url' parameter"}, 400)
                return
            # Security: only allow known map short-link domains
            allowed = ['goo.gl', 'maps.app.goo.gl', 'maps.google.com', 'g.co', 'bit.ly']
            domain = urllib.parse.urlparse(url).hostname or ''
            if not any(domain == d or domain.endswith('.' + d) for d in allowed):
                self._send_json({"error": f"Domain '{domain}' not allowed"}, 403)
                return
            # Follow redirects with a custom opener that doesn't follow automatically
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None  # Don't follow, we'll do it manually
            opener = urllib.request.build_opener(NoRedirect)
            # Follow up to 5 redirects manually
            final_url = url
            for _ in range(5):
                req = urllib.request.Request(final_url, headers={
                    'User-Agent': 'GpyX/1.0 (URL resolver)'
                })
                try:
                    resp = opener.open(req, timeout=5)
                    break  # No redirect, we're at the final URL
                except urllib.error.HTTPError as e:
                    if e.code in (301, 302, 303, 307, 308):
                        location = e.headers.get('Location', '')
                        if location:
                            final_url = location
                        else:
                            break
                    else:
                        raise
            self._send_json({"resolved": final_url})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_import(self):
        try:
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" in content_type:
                # Parse multipart without deprecated cgi module
                boundary = content_type.split("boundary=")[-1].strip()
                content_length = int(self.headers.get("Content-Length", 0))
                body_raw = self.rfile.read(content_length)
                parts = body_raw.split(b"--" + boundary.encode())
                filename, file_data = "upload.gpx", b""
                for part in parts:
                    if b"filename=" in part:
                        header_end = part.find(b"\r\n\r\n")
                        if header_end < 0:
                            continue
                        header_block = part[:header_end].decode("utf-8", errors="replace")
                        for token in header_block.split(";"):
                            token = token.strip()
                            if token.startswith("filename="):
                                filename = token.split("=", 1)[1].strip('" ')
                        file_data = part[header_end + 4:]
                        if file_data.endswith(b"\r\n"):
                            file_data = file_data[:-2]
                        break
            else:
                body = json.loads(self._read_body())
                filename = body.get("filename", "upload.gpx")
                file_data = base64.b64decode(body.get("data", ""))

            ext = Path(filename).suffix
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False, mode="wb") as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name
            try:
                arrays = read_file(tmp_path)
            finally:
                os.unlink(tmp_path)

            result = {"arrays": [], "filename": filename}
            for arr in arrays:
                result["arrays"].append({
                    "type": arr.array_type.value,
                    "name": arr.name,
                    "points": [
                        {"lat": pt.lat, "lng": pt.lng, "alt": pt.alt,
                         "name": pt.name, "comment": pt.comment}
                        for pt in arr
                    ],
                })
            self._send_json(result)
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def _handle_export(self):
        try:
            body = json.loads(self._read_body())
            format_ext = body.get("format", "gpx")
            route_name = body.get("name", "Route")
            points_data = body.get("points", [])

            route = GpsRoute(route_name)
            for pt in points_data:
                route.append(GpsPoint(
                    lat=pt.get("lat", 0), lng=pt.get("lng", 0), alt=pt.get("alt", 0),
                    name=pt.get("name", ""), comment=pt.get("comment", ""),
                ))

            with tempfile.NamedTemporaryFile(suffix=f".{format_ext}", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                write_file(tmp_path, route)
                with open(tmp_path, "rb") as f:
                    file_data = f.read()
            finally:
                os.unlink(tmp_path)

            self._send_json({
                "filename": f"{route_name or 'route'}.{format_ext}",
                "data": base64.b64encode(file_data).decode("ascii"),
                "size": len(file_data),
            })
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def _handle_convert(self):
        try:
            body = json.loads(self._read_body())
            filename = body.get("filename", "upload.gpx")
            file_data = base64.b64decode(body.get("data", ""))
            target_format = body.get("target_format", "gpx")

            in_ext = Path(filename).suffix
            with tempfile.NamedTemporaryFile(suffix=in_ext, delete=False, mode="wb") as tmp:
                tmp.write(file_data)
                in_path = tmp.name
            with tempfile.NamedTemporaryFile(suffix=f".{target_format}", delete=False) as tmp:
                out_path = tmp.name
            try:
                arrays = read_file(in_path)
                merged = GpsRoute(arrays[0].name if arrays else "Route")
                for arr in arrays:
                    for pt in arr:
                        merged.append(pt.copy())
                write_file(out_path, merged)
                with open(out_path, "rb") as f:
                    result_data = f.read()
            finally:
                os.unlink(in_path)
                os.unlink(out_path)

            self._send_json({
                "filename": f"{Path(filename).stem}.{target_format}",
                "data": base64.b64encode(result_data).decode("ascii"),
                "size": len(result_data),
                "points": len(merged),
            })
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def _handle_simplify(self):
        try:
            body = json.loads(self._read_body())
            points_data = body.get("points", [])
            method = body.get("method", "douglas_peucker")
            epsilon = body.get("epsilon", 50.0)
            keep_every = body.get("keep_every", 2)
            target = body.get("target", 50)

            route = GpsRoute("simplify")
            for pt in points_data:
                route.append(GpsPoint(
                    lat=pt.get("lat", 0), lng=pt.get("lng", 0), alt=pt.get("alt", 0),
                    name=pt.get("name", ""), comment=pt.get("comment", ""),
                ))

            original_count = len(route)

            if method == "douglas_peucker":
                route.douglas_peucker(epsilon)
            elif method == "decimate":
                route.decimate(keep_every)
            elif method == "smart":
                route.simplify_for_routing(target)
            else:
                route.remove_duplicates()

            self._send_json({
                "original": original_count,
                "simplified": len(route),
                "points": [
                    {"lat": pt.lat, "lng": pt.lng, "alt": pt.alt,
                     "name": pt.name, "comment": pt.comment}
                    for pt in route
                ],
            })
        except Exception as e:
            self._send_json({"error": str(e)}, 400)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        if "/api/" in str(args[0]):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description=f"{SOFT_FULL_NAME} — Web Interface")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = http.server.HTTPServer((args.host, args.port), GpyXHandler)
    url = f"http://{args.host}:{args.port}"

    print(f"""
┌──────────────────────────────────────────────┐
│  🗺️  {SOFT_FULL_NAME:<38s} │
│  GPS Route Converter & Planner               │
├──────────────────────────────────────────────┤
│  Server: {url:<35s} │
│  Ctrl+C to stop                              │
└──────────────────────────────────────────────┘
    """)

    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
