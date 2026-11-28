"""Local HTTP app serving the same Python pipeline as the CLI."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
from threading import BoundedSemaphore
from socket import SHUT_WR
from time import monotonic

from .benchmark import resource
from .bridge import error_response, request_action
from .pipeline import InputError, MAX_INPUT_BYTES, load_json
from .stress import generated_case

ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
       "img-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, *, layout_timeout=5.0):
        self.slots = BoundedSemaphore(4)
        self.layout_timeout = layout_timeout
        super().__init__(("127.0.0.1", port), Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(8)
        return connection, address

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            try:
                body = b'{"diagnostics":[{"severity":"error","code":"busy","path":"","message":"Server is busy. Retry in a moment."}]}'
                request.settimeout(.2)
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\n"
                                b"Retry-After: 1\r\nConnection: close\r\nContent-Length: "
                                + str(len(body)).encode() + b"\r\n\r\n" + body)
                request.shutdown(SHUT_WR)
                # Close gracefully even when Windows still has unread request bytes.
                deadline, remaining = monotonic() + .035, 16384
                while remaining > 0 and (wait := deadline-monotonic()) > 0:
                    request.settimeout(wait)
                    chunk = request.recv(min(4096,remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                pass
            finally:
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

    def _error(self, status, message, *, code="input-error"):
        self._json(status, {"diagnostics": [{"severity": "error", "code": code,
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
            samples["benchmark-sparse"] = generated_case("sparse",50)
            samples["benchmark-cycles"] = generated_case("cycles",25)
            samples["benchmark-loops"] = generated_case("loops",25)
            self._json(200, samples)
        elif self.path in ASSETS:
            filename, media = ASSETS[self.path]
            self._send(200, media, files("pretty_smd").joinpath("static", filename).read_bytes())
        else:
            self._error(404, "Resource not found.")

    def do_POST(self):
        if not self._local():
            return
        action = self.path.removeprefix("/api/")
        if action not in ("generate","format","validate") or not self.path.startswith("/api/"):
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
            result = request_action(action,request,timeout=self.server.layout_timeout,max_vertices=120,max_edges=300)
            self._json(200,result)
        except TimeoutError:
            self._error(408, "Request timed out.")
        except (ValueError, UnicodeError, RecursionError) as error:
            self._json(*error_response(error))


def serve(port=8000):
    if not 1 <= port <= 65535:
        raise InputError("Port must be from 1 to 65535.")
    with AppServer(port) as app:
        print(f"Pretty SMD is available at http://127.0.0.1:{port}", flush=True)
        try:
            app.serve_forever()
        except KeyboardInterrupt:
            pass
