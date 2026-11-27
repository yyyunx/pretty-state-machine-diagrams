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

    def test_advanced_comparison_uses_one_model(self):
        source = (ROOT/"examples/basic.smd.json").read_text(encoding="utf-8")
        status,_,data = self.request("POST","/api/generate",{
            "source":source,"algorithm":"advanced","mode":"fast","compare":True})
        self.assertEqual(status,200,data)
        body = json.loads(data)
        self.assertEqual(body["quality"]["optimization"]["mode"],"fast")
        self.assertEqual(body["baseline"]["layout"]["modelId"],body["model"]["id"])
        self.assertEqual(set(body["baseline"]["layout"]["edges"]),set(body["layout"]["edges"]))

    def test_benchmark_inputs_and_layout_deadline(self):
        status,_,data = self.request("GET","/api/examples")
        self.assertEqual(status,200)
        model = json.loads(data)["benchmark-sparse"]
        self.assertEqual(len(model["regions"][0]["vertices"]),50)
        previous = self.app.layout_timeout
        try:
            self.app.layout_timeout = 1e-9
            status,_,data = self.request("POST","/api/generate",{
                "source":json.dumps(model),"algorithm":"advanced","mode":"fast"})
            self.assertEqual(status,504)
            self.assertEqual(json.loads(data)["diagnostics"][0]["code"],"layout-timeout")
        finally:
            self.app.layout_timeout = previous

    def test_overloaded_server_rejects_with_retry(self):
        held = 0
        try:
            for _ in range(4):
                self.assertTrue(self.app.slots.acquire(timeout=2))
                held += 1
            status,_,data = self.request("GET","/")
            self.assertEqual(status,503)
            self.assertEqual(json.loads(data)["diagnostics"][0]["code"],"busy")
        finally:
            for _ in range(held):
                self.app.slots.release()
