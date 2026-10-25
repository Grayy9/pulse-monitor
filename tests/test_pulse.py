import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pulse import Store, check_monitor, make_server


class FixtureHandler(BaseHTTPRequestHandler):
    status = 200

    def do_GET(self):
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(b"fixture")

    def log_message(self, *_args):
        pass


class AlertHandler(BaseHTTPRequestHandler):
    events = []

    def do_POST(self):
        size = int(self.headers["Content-Length"])
        self.events.append(json.loads(self.rfile.read(size)))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args):
        pass


class PulseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.db = str(Path(self.temp.name) / "pulse.db")
        self.store = Store(self.db)
        self.fixture = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.fixture_thread = threading.Thread(target=self.fixture.serve_forever, daemon=True)
        self.fixture_thread.start()
        FixtureHandler.status = 200
        self.url = f"http://127.0.0.1:{self.fixture.server_port}/"

    def tearDown(self):
        self.fixture.shutdown()
        self.fixture.server_close()
        self.temp.cleanup()

    def test_monitor_persists_and_rejects_invalid_input(self):
        monitor = self.store.add_monitor("Example", self.url, 60)
        self.assertEqual(Store(self.db).get_monitor(monitor["id"])["name"], "Example")
        with self.assertRaises(ValueError):
            self.store.add_monitor("Bad", "file:///etc/passwd", 60)
        with self.assertRaises(ValueError):
            self.store.add_monitor("Bad", self.url, 5)

    def test_checks_record_success_and_failure(self):
        monitor = self.store.add_monitor("Example", self.url, 60)
        good = check_monitor(self.store, monitor["id"])
        self.assertTrue(good["up"])
        self.assertEqual(good["status_code"], 200)
        FixtureHandler.status = 503
        bad = check_monitor(self.store, monitor["id"])
        self.assertFalse(bad["up"])
        self.assertEqual(bad["status_code"], 503)
        self.assertEqual([item["up"] for item in Store(self.db).history(monitor["id"])], [False, True])

    def test_webhook_fires_only_on_status_change(self):
        AlertHandler.events = []
        alert = ThreadingHTTPServer(("127.0.0.1", 0), AlertHandler)
        threading.Thread(target=alert.serve_forever, daemon=True).start()
        try:
            monitor = self.store.add_monitor("Example", self.url, 60)
            webhook = f"http://127.0.0.1:{alert.server_port}/"
            check_monitor(self.store, monitor["id"], webhook)
            check_monitor(self.store, monitor["id"], webhook)
            self.assertEqual(AlertHandler.events, [])
            FixtureHandler.status = 503
            check_monitor(self.store, monitor["id"], webhook)
            self.assertEqual(len(AlertHandler.events), 1)
            self.assertFalse(AlertHandler.events[0]["up"])
            FixtureHandler.status = 200
            check_monitor(self.store, monitor["id"], webhook)
            self.assertEqual(len(AlertHandler.events), 2)
            self.assertTrue(AlertHandler.events[1]["up"])
        finally:
            alert.shutdown()
            alert.server_close()

    def test_http_api_add_list_check_and_delete(self):
        server = make_server(self.store, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            request = Request(base + "/api/monitors", data=json.dumps({"name": "Example", "url": self.url, "interval": 60}).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request) as response:
                monitor = json.load(response)
            with urlopen(base + "/api/monitors") as response:
                self.assertEqual(len(json.load(response)["monitors"]), 1)
            with urlopen(Request(base + f"/api/monitors/{monitor['id']}/check", data=b"{}", method="POST")) as response:
                self.assertTrue(json.load(response)["up"])
            with urlopen(base + f"/api/monitors/{monitor['id']}/history") as response:
                self.assertEqual(len(json.load(response)["history"]), 1)
            with urlopen(Request(base + f"/api/monitors/{monitor['id']}", method="DELETE")) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(self.store.list_monitors(), [])
        finally:
            server.shutdown()
            server.server_close()

    def test_bad_api_input_returns_400(self):
        server = make_server(self.store, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(f"http://127.0.0.1:{server.server_port}/api/monitors", data=b'{"name":"x","url":"javascript:bad","interval":60}', method="POST")
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 400)
            caught.exception.close()
            request = Request(f"http://127.0.0.1:{server.server_port}/api/monitors", data=b"[]", method="POST")
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 400)
            caught.exception.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
