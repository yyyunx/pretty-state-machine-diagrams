from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Thread
import unittest

from pretty_smd.web import AppServer

ROOT = Path(__file__).resolve().parents[1]


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = AppServer(0)
        cls.thread = Thread(target=cls.app.serve_forever)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown()
        cls.thread.join()
        cls.app.server_close()

    def request(self, method, path, data=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.app.server_port, timeout=8)
        content = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {"Content-Type":"application/json", **(headers or {})}
        try:
            connection.request(method, path, content, headers)
            reply = connection.getresponse()
            return reply.status, reply.getheader("Content-Security-Policy"), reply.read()
        finally:
            connection.close()

    def test_generate_and_shell_are_one_local_app(self):
        status, csp, data = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"/app.js", data)
        self.assertIn("frame-ancestors 'none'", csp)
        status, _, data = self.request("POST", "/api/generate", {
            "source": (ROOT/"examples/basic.smd.json").read_text(encoding="utf-8"),
            "format": "smd", "options": {"direction": "vertical"},
        })
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result["model"]["id"], result["layout"]["modelId"])
        self.assertIn("待機", result["svg"])

    def test_local_origin_input_size_and_unknown_files(self):
        self.assertEqual(self.request("GET", "/", headers={"Host":"other.invalid"})[0], 403)
        self.assertEqual(self.request("GET", "/unknown")[0], 404)
        status, _, data = self.request("POST", "/api/generate", {"source":"i1 . ◉","format":"pa"})
        self.assertEqual(status, 422)
        self.assertIn("Converter", json.loads(data)["diagnostics"][0]["message"])
        status, _, _ = self.request("POST", "/api/generate", headers={"Content-Length":"1048577"})
        self.assertEqual(status, 413)

    def test_generation_reports_source_diagnostics(self):
        source = json.dumps({"kind":"unresolved","operator":"ref","sourceText":"ref Missing"})
        status, _, data = self.request("POST", "/api/generate", {"source":source,"format":"mock"})
        self.assertEqual(status, 422)
        issue = json.loads(data)["diagnostics"][0]
        self.assertEqual(issue["path"], "/operator")
        self.assertEqual(issue["source_text"], "ref Missing")
