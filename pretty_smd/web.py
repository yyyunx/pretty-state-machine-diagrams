"""Local HTTP app serving the same Python pipeline as the CLI."""

from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
from threading import BoundedSemaphore

from src.layout.engine import LayoutOptions
from src.model import ModelError

from .benchmark import resource
from .pipeline import InputError, MAX_INPUT_BYTES, generate, load_json

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
       "img-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port):
        self.slots = BoundedSemaphore(4)
        super().__init__(("127.0.0.1", port), Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(8)
        return connection, address

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "PrettySMD"

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, body):
        self._send(status, "application/json; charset=utf-8",
                   json.dumps(body, ensure_ascii=True, allow_nan=False).encode("ascii"))

    def _error(self, status, message):
        self._json(status, {"diagnostics": [{"severity": "error", "code": "input-error",
                                            "path": "", "message": message}]})

    def _local(self):
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        if host not in allowed or (origin and origin != "http://" + host):
            self._error(403, "Requests must originate from the local application.")
            return False
        return True

    def do_GET(self):
        if not self._local():
            return
        if self.path == "/api/examples":
            samples = {}
            for version in ("p1", "p2"):
                samples.update({k: v for k, v in json.loads(
                    resource(f"mock-converter-{version}.json")).items() if isinstance(v, dict)})
            self._json(200, samples)
        elif self.path in ASSETS:
            filename, media = ASSETS[self.path]
            self._send(200, media, files("pretty_smd").joinpath("static", filename).read_bytes())
        else:
            self._error(404, "Resource not found.")

    def do_POST(self):
        if not self._local():
            return
        if self.path != "/api/generate":
            self._error(404, "Resource not found.")
            return
        if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
            self._error(415, "Send a JSON request with a Content-Length header.")
            return
        length = self.headers.get("Content-Length", "")
        if not length.isascii() or not length.isdecimal() or len(length) > 7 or int(length) > MAX_INPUT_BYTES:
            self._error(413, "Request body exceeds 1 MiB or has no valid length.")
            return
        try:
            request = load_json(self.rfile.read(int(length)))
            if not isinstance(request, dict) or not isinstance(request.get("source"), str):
                raise InputError("The request needs a JSON source string.")
            input_format = request.get("format", "auto")
            if input_format == "pa":
                raise InputError("Raw Process Algebra requires a confirmed R/S Converter.")
            config = request.get("options", {})
            if not isinstance(config, dict) or set(config) - set(vars(LayoutOptions())):
                raise InputError("Unknown or invalid layout settings.")
            result = generate(load_json(request["source"]), input_format=input_format,
                              options=LayoutOptions(**config), algorithm=request.get("algorithm", "topology"),
                              max_vertices=48, max_edges=96)
            self._json(200, {"svg": result.svg, "model": result.model, "layout": result.layout,
                             "quality": result.quality,
                             "diagnostics": [asdict(item) for item in result.warnings]})
        except ModelError as error:
            self._json(422, {"diagnostics": [asdict(item) for item in error.diagnostics]})
        except TimeoutError:
            self._error(408, "Request timed out.")
        except (ValueError, UnicodeError, RecursionError) as error:
            self._error(422, str(error))


def serve(port=8000):
    if not 1 <= port <= 65535:
        raise InputError("Port must be from 1 to 65535.")
    with AppServer(port) as app:
        print(f"Pretty SMD is available at http://127.0.0.1:{port}", flush=True)
        try:
            app.serve_forever()
        except KeyboardInterrupt:
            pass
