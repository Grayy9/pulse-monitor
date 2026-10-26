import json
import csv
import io
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pulse import MonitorRunner, Store, check_monitor, make_server


class FixtureHandler(BaseHTTPRequestHandler):
    status = 200
    block = False
    release = threading.Event()
    both_started = threading.Event()
    started = 0
    guard = threading.Lock()

    def do_GET(self):
        if self.block:
            with self.guard:
                type(self).started += 1
                if self.started == 2:
                    self.both_started.set()
            self.release.wait(2)
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
        FixtureHandler.block = False
        FixtureHandler.release = threading.Event()
        FixtureHandler.both_started = threading.Event()
        FixtureHandler.started = 0
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

    def test_legacy_database_is_migrated_without_losing_monitors(self):
        legacy = str(Path(self.temp.name) / "legacy.db")
        db = sqlite3.connect(legacy)
        db.executescript("""
            CREATE TABLE monitors (id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL, created_at TEXT NOT NULL, last_checked REAL,
                last_up INTEGER, last_status_code INTEGER, last_response_ms INTEGER, last_error TEXT);
            CREATE TABLE checks (id INTEGER PRIMARY KEY, monitor_id INTEGER NOT NULL,
                checked_at TEXT NOT NULL, up INTEGER NOT NULL, status_code INTEGER,
                response_ms INTEGER NOT NULL, error TEXT);
            INSERT INTO monitors VALUES (1,'Legacy','https://example.com',60,'2026-01-01',NULL,NULL,NULL,NULL,NULL);
            INSERT INTO checks VALUES (1,1,'2026-01-01T00:00:00+00:00',1,200,12,NULL);
        """)
        db.close()
        migrated = Store(legacy)
        self.assertEqual(migrated.get_monitor(1)["name"], "Legacy")
        self.assertFalse(migrated.get_monitor(1)["paused"])
        self.assertEqual(len(migrated.history(1)), 1)

    def test_edit_pause_and_resume_preserve_history(self):
        monitor = self.store.add_monitor("Old", self.url, 60)
        self.store.save_check(monitor["id"], True, 200, 12, None)
        edited = self.store.update_monitor(monitor["id"], name="New", interval=300)
        self.assertEqual((edited["name"], edited["interval"]), ("New", 300))
        self.assertEqual(len(self.store.history(monitor["id"])), 1)
        self.store.update_monitor(monitor["id"], paused=True)
        self.assertEqual(self.store.due_monitors(time.time() + 400), [])
        resumed = self.store.update_monitor(monitor["id"], paused=False)
        self.assertFalse(resumed["paused"])
        self.assertIsNone(resumed["up"])
        self.assertIsNone(resumed["last_response_ms"])
        self.assertIn(monitor["id"], self.store.due_monitors())
        changed_url = self.store.update_monitor(monitor["id"], url=self.url + "next")
        self.assertIsNone(changed_url["up"])
        self.assertEqual(len(self.store.history(monitor["id"])), 1)

    def test_statistics_show_check_based_availability_and_incident_period(self):
        monitor = self.store.add_monitor("Example", self.url, 60)
        now = 1_800_000_000.0
        self.store.save_check(monitor["id"], True, 200, 10, None, checked_at=now - 90000)
        self.store.save_check(monitor["id"], False, 503, 10, "HTTP 503", checked_at=now - 7200)
        self.store.save_check(monitor["id"], False, 503, 10, "HTTP 503", checked_at=now - 3600)
        self.store.save_check(monitor["id"], True, 200, 10, None, checked_at=now - 1800)
        self.store.save_check(monitor["id"], True, 200, 10, None, checked_at=now - 10)
        stats = self.store.statistics(monitor["id"], now=now)
        self.assertEqual(stats["checks_24h"], 4)
        self.assertEqual(stats["availability_24h"], 50.0)
        self.assertEqual(len(stats["incidents"]), 1)
        self.assertEqual(stats["incidents"][0]["start"], datetime.fromtimestamp(now - 7200, timezone.utc).isoformat())
        self.assertEqual(stats["incidents"][0]["end"], datetime.fromtimestamp(now - 1800, timezone.utc).isoformat())

    def test_report_buckets_and_empty_values(self):
        monitor = self.store.add_monitor("Report", self.url, 60)
        mid = monitor["id"]
        now = 1_800_000_000.0
        self.store.save_check(mid, True, 200, 80, None, checked_at=now - 86400)
        self.store.save_check(mid, False, 503, 900, "HTTP 503", checked_at=now - 3600)
        self.store.save_check(mid, True, 200, 120, None, checked_at=now - 100)
        self.store.save_check(mid, True, 200, 500, None, checked_at=now)
        report = self.store.report(mid, "24h", now=now)
        self.assertEqual((report["checks"], report["successes"], report["failures"]), (3, 2, 1))
        self.assertEqual((report["availability"], report["average_response_ms"]), (66.7, 100.0))
        self.assertEqual(len(report["buckets"]), 24)
        self.assertEqual(report["buckets"][0]["checks"], 1)
        self.assertEqual(report["buckets"][-2]["checks"], 0)
        self.assertIsNone(report["buckets"][-2]["availability"])
        self.assertIsNone(report["buckets"][-2]["average_response_ms"])
        self.assertEqual(report["buckets"][-1]["checks"], 2)
        self.assertEqual(report["buckets"][-1]["average_response_ms"], 120.0)
        weekly = self.store.report(mid, "7d", now=now)
        self.assertEqual(len(weekly["buckets"]), 7)
        self.assertEqual(weekly["checks"], 3)
        empty = self.store.report(mid, "24h", now=now - 900000)
        self.assertEqual(empty["checks"], 0)
        self.assertIsNone(empty["availability"])
        self.assertIsNone(empty["average_response_ms"])

    def test_report_api_csv_and_invalid_range(self):
        monitor = self.store.add_monitor("Export", self.url, 60)
        self.store.save_check(monitor["id"], False, 503, 21, "=bad()")
        server = make_server(self.store, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}/api/monitors/{monitor['id']}"
        try:
            with urlopen(base + "/report?range=24h") as response:
                self.assertEqual(json.load(response)["checks"], 1)
            with urlopen(base + "/report.csv?range=24h") as response:
                self.assertIn("text/csv", response.headers["Content-Type"])
                rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["error"], "'=bad()")
            for url, status in ((base + "/report?range=30d", 400), (base + "9/report?range=24h", 404)):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(url)
                self.assertEqual(caught.exception.code, status)
                caught.exception.close()
        finally:
            server.shutdown()
            server.server_close()

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

    def test_webhook_fires_after_three_failures_then_once_on_recovery(self):
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
            check_monitor(Store(self.db), monitor["id"], webhook)
            self.assertEqual(AlertHandler.events, [])
            check_monitor(self.store, monitor["id"], webhook)
            self.assertEqual(len(AlertHandler.events), 1)
            self.assertFalse(AlertHandler.events[0]["up"])
            check_monitor(self.store, monitor["id"], webhook)
            self.assertEqual(len(AlertHandler.events), 1)
            FixtureHandler.status = 200
            check_monitor(self.store, monitor["id"], webhook)
            self.assertEqual(len(AlertHandler.events), 2)
            self.assertTrue(AlertHandler.events[1]["up"])
            check_monitor(self.store, monitor["id"], webhook)
            self.assertEqual(len(AlertHandler.events), 2)
        finally:
            alert.shutdown()
            alert.server_close()

    def test_runner_starts_two_slow_monitors_without_overlapping_them(self):
        one = self.store.add_monitor("One", self.url, 60)
        two = self.store.add_monitor("Two", self.url, 60)
        FixtureHandler.block = True
        runner = MonitorRunner(self.store, max_workers=2)
        try:
            runner.schedule_due()
            runner.schedule_due()
            self.assertTrue(FixtureHandler.both_started.wait(1))
            FixtureHandler.release.set()
            runner.shutdown()
            self.assertEqual(FixtureHandler.started, 2)
            self.assertIsNotNone(self.store.get_monitor(one["id"])["last_checked"])
            self.assertIsNotNone(self.store.get_monitor(two["id"])["last_checked"])
        finally:
            FixtureHandler.release.set()
            runner.shutdown()

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
            patch = Request(base + f"/api/monitors/{monitor['id']}", data=b'{"name":"Renamed","paused":true}', method="PATCH")
            with urlopen(patch) as response:
                edited = json.load(response)
            self.assertEqual(edited["name"], "Renamed")
            self.assertTrue(edited["paused"])
            with urlopen(base + f"/api/monitors/{monitor['id']}/statistics") as response:
                self.assertEqual(json.load(response)["checks_24h"], 1)
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
