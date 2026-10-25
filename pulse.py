"""Small local HTTP uptime monitor built with Python's standard library."""

import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"


def stamp(value=None):
    return datetime.fromtimestamp(time.time() if value is None else value, timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS monitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_checked REAL,
                    last_up INTEGER,
                    last_status_code INTEGER,
                    last_response_ms INTEGER,
                    last_error TEXT,
                    paused INTEGER NOT NULL DEFAULT 0,
                    failure_streak INTEGER NOT NULL DEFAULT 0,
                    alert_state INTEGER
                );
                CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_id INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
                    checked_at TEXT NOT NULL,
                    up INTEGER NOT NULL,
                    status_code INTEGER,
                    response_ms INTEGER NOT NULL,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS checks_monitor ON checks(monitor_id, id DESC);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(monitors)")}
            for name, definition in (
                ("paused", "INTEGER NOT NULL DEFAULT 0"),
                ("failure_streak", "INTEGER NOT NULL DEFAULT 0"),
                ("alert_state", "INTEGER"),
            ):
                if name not in columns:
                    db.execute(f"ALTER TABLE monitors ADD COLUMN {name} {definition}")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def monitor_dict(row):
        item = dict(row)
        item["up"] = None if item.pop("last_up") is None else bool(row["last_up"])
        item["paused"] = bool(item["paused"])
        item["alert_state"] = None if item["alert_state"] is None else bool(item["alert_state"])
        item["interval"] = item.pop("interval_seconds")
        item["last_checked"] = stamp(item["last_checked"]) if item["last_checked"] else None
        return item

    @staticmethod
    def validate_monitor(name, url, interval):
        name = str(name or "").strip()
        url = str(url or "").strip()
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as exc:
            raise ValueError("URL 无效") from exc
        if not name or len(name) > 80:
            raise ValueError("名称长度须为 1–80 个字符")
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or port == 0 or len(url) > 2048:
            raise ValueError("请输入有效的 HTTP 或 HTTPS 地址")
        try:
            interval = int(interval)
        except (ValueError, TypeError) as exc:
            raise ValueError("检查间隔须为 30–3600 秒") from exc
        if not 30 <= interval <= 3600:
            raise ValueError("检查间隔须为 30–3600 秒")
        return name, url, interval

    def add_monitor(self, name, url, interval):
        name, url, interval = self.validate_monitor(name, url, interval)
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO monitors(name,url,interval_seconds,created_at) VALUES(?,?,?,?)",
                (name, url, interval, stamp()),
            )
            mid = cursor.lastrowid
        return self.get_monitor(mid)

    def update_monitor(self, mid, **changes):
        old = self.get_monitor(mid)
        if old is None:
            raise ValueError("监控项不存在")
        if not changes.keys() <= {"name", "url", "interval", "paused"}:
            raise ValueError("包含不支持的设置")
        name, url, interval = self.validate_monitor(
            changes.get("name", old["name"]),
            changes.get("url", old["url"]),
            changes.get("interval", old["interval"]),
        )
        paused = changes.get("paused", old["paused"])
        if not isinstance(paused, bool):
            raise ValueError("暂停状态须为布尔值")
        url_changed = url != old["url"]
        resumed = old["paused"] and not paused
        with self.connect() as db:
            db.execute(
                """UPDATE monitors SET name=?,url=?,interval_seconds=?,paused=?,
                   last_checked=CASE WHEN ? THEN NULL ELSE last_checked END,
                   last_up=CASE WHEN ? THEN NULL ELSE last_up END,
                   last_status_code=CASE WHEN ? THEN NULL ELSE last_status_code END,
                   last_response_ms=CASE WHEN ? THEN NULL ELSE last_response_ms END,
                   last_error=CASE WHEN ? THEN NULL ELSE last_error END,
                   failure_streak=CASE WHEN ? THEN 0 ELSE failure_streak END,
                   alert_state=CASE WHEN ? THEN NULL ELSE alert_state END WHERE id=?""",
                (name, url, interval, int(paused), int(url_changed or resumed),
                 int(url_changed), int(url_changed), int(url_changed), int(url_changed),
                 int(url_changed), int(url_changed), mid),
            )
        return self.get_monitor(mid)

    def get_monitor(self, mid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM monitors WHERE id=?", (mid,)).fetchone()
        return self.monitor_dict(row) if row else None

    def list_monitors(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM monitors ORDER BY id DESC").fetchall()
        return [self.monitor_dict(row) for row in rows]

    def due_monitors(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            rows = db.execute(
                "SELECT id FROM monitors WHERE paused=0 AND (last_checked IS NULL OR last_checked + interval_seconds <= ?) ORDER BY id",
                (now,),
            ).fetchall()
        return [row["id"] for row in rows]

    def save_check(self, mid, up, status_code, response_ms, error, checked_at=None):
        now = time.time() if checked_at is None else checked_at
        with self.connect() as db:
            row = db.execute("SELECT failure_streak,alert_state FROM monitors WHERE id=?", (mid,)).fetchone()
            if row is None:
                raise ValueError("监控项不存在")
            streak = 0 if up else row["failure_streak"] + 1
            notify = None
            alert_state = row["alert_state"]
            if up:
                if alert_state == 0:
                    notify = True
                alert_state = 1
            elif streak >= 3 and alert_state != 0:
                notify = False
                alert_state = 0
            db.execute(
                "INSERT INTO checks(monitor_id,checked_at,up,status_code,response_ms,error) VALUES(?,?,?,?,?,?)",
                (mid, stamp(now), int(up), status_code, response_ms, error),
            )
            db.execute(
                "UPDATE monitors SET last_checked=?,last_up=?,last_status_code=?,last_response_ms=?,last_error=?,failure_streak=?,alert_state=? WHERE id=?",
                (now, int(up), status_code, response_ms, error, streak, alert_state, mid),
            )
            db.execute("DELETE FROM checks WHERE monitor_id=? AND id NOT IN (SELECT id FROM checks WHERE monitor_id=? ORDER BY id DESC LIMIT 4000)", (mid, mid))
        return notify

    def statistics(self, mid, now=None):
        now = time.time() if now is None else now
        cutoff = stamp(now - 86400)
        with self.connect() as db:
            rows = db.execute(
                "SELECT checked_at,up FROM checks WHERE monitor_id=? AND checked_at>=? ORDER BY id",
                (mid, cutoff),
            ).fetchall()
        incidents = []
        start = None
        for row in rows:
            if not row["up"] and start is None:
                start = row["checked_at"]
            elif row["up"] and start is not None:
                incidents.append({"start": start, "end": row["checked_at"]})
                start = None
        if start is not None:
            incidents.append({"start": start, "end": None})
        count = len(rows)
        return {
            "checks_24h": count,
            "availability_24h": round(100 * sum(row["up"] for row in rows) / count, 1) if count else None,
            "incidents": list(reversed(incidents))[:10],
        }

    def history(self, mid):
        with self.connect() as db:
            rows = db.execute("SELECT checked_at,up,status_code,response_ms,error FROM checks WHERE monitor_id=? ORDER BY id DESC LIMIT 50", (mid,)).fetchall()
        return [{**dict(row), "up": bool(row["up"])} for row in rows]

    def delete_monitor(self, mid):
        with self.connect() as db:
            return db.execute("DELETE FROM monitors WHERE id=?", (mid,)).rowcount > 0


def check_monitor(store, mid, webhook_url=None):
    monitor = store.get_monitor(mid)
    if monitor is None:
        raise ValueError("监控项不存在")
    start = time.monotonic()
    code, error = None, None
    try:
        with urlopen(Request(monitor["url"], headers={"User-Agent": "PulseMonitor/1.0"}), timeout=5) as response:
            code = response.status
    except HTTPError as exc:
        code = exc.code
        error = f"HTTP {code}"
        exc.close()
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        error = str(exc.reason if isinstance(exc, URLError) else exc)[:200]
    elapsed = round((time.monotonic() - start) * 1000)
    up = code is not None and 200 <= code < 400
    if not up and error is None:
        error = f"HTTP {code}"
    notify = store.save_check(mid, up, code, elapsed, error)
    result = {"up": up, "status_code": code, "response_ms": elapsed, "error": error, "checked_at": stamp()}
    if webhook_url and notify is not None:
        payload = json.dumps({"monitor": monitor["name"], "url": monitor["url"], **result}).encode()
        try:
            urlopen(Request(webhook_url, payload, {"Content-Type": "application/json"}, method="POST"), timeout=5).close()
        except (URLError, TimeoutError, OSError, ValueError):
            pass
    return result


class BusyError(Exception):
    pass


class MonitorRunner:
    def __init__(self, store, webhook_url=None, max_workers=8):
        self.store = store
        self.webhook_url = webhook_url
        self.pool = ThreadPoolExecutor(max_workers=max_workers)
        self.lock = threading.Lock()
        self.inflight = set()

    def _reserve(self, mid):
        with self.lock:
            if mid in self.inflight:
                return False
            self.inflight.add(mid)
            return True

    def _perform(self, mid):
        try:
            return check_monitor(self.store, mid, self.webhook_url)
        finally:
            with self.lock:
                self.inflight.discard(mid)

    def schedule_due(self):
        for mid in self.store.due_monitors():
            if self._reserve(mid):
                self.pool.submit(self._perform, mid)

    def run_now(self, mid):
        if not self._reserve(mid):
            raise BusyError("该监控项正在检查中")
        try:
            return self.pool.submit(self._perform, mid).result()
        except RuntimeError:
            with self.lock:
                self.inflight.discard(mid)
            raise

    def shutdown(self):
        self.pool.shutdown(wait=True)


def make_server(store, host="127.0.0.1", port=3001, webhook_url=None, runner=None):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def path_parts(self):
            return self.path.split("?", 1)[0].strip("/").split("/")

        def do_GET(self):
            parts = self.path_parts()
            if parts == ["api", "monitors"]:
                self.send_json(200, {"monitors": store.list_monitors(), "server_time": stamp()})
            elif len(parts) == 4 and parts[:2] == ["api", "monitors"] and parts[2].isdigit() and parts[3] == "history":
                mid = int(parts[2])
                if store.get_monitor(mid):
                    self.send_json(200, {"history": store.history(mid)})
                else:
                    self.send_json(404, {"error": "监控项不存在"})
            elif len(parts) == 4 and parts[:2] == ["api", "monitors"] and parts[2].isdigit() and parts[3] == "statistics":
                mid = int(parts[2])
                if store.get_monitor(mid):
                    self.send_json(200, store.statistics(mid))
                else:
                    self.send_json(404, {"error": "监控项不存在"})
            elif self.path.split("?", 1)[0] in ("/", "/style.css", "/app.js"):
                name = "index.html" if self.path == "/" else self.path.lstrip("/")
                content = (STATIC / name).read_bytes()
                mime = {"index.html": "text/html", "style.css": "text/css", "app.js": "application/javascript"}[name]
                self.send_response(200)
                self.send_header("Content-Type", mime + "; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_json(404, {"error": "未找到"})

        def do_POST(self):
            parts = self.path_parts()
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size > 8192:
                    raise ValueError("请求内容过大")
                data = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError("请求内容须为 JSON 对象")
                if parts == ["api", "monitors"]:
                    self.send_json(201, store.add_monitor(data.get("name"), data.get("url"), data.get("interval", 60)))
                elif len(parts) == 4 and parts[:2] == ["api", "monitors"] and parts[2].isdigit() and parts[3] == "check":
                    self.send_json(200, runner.run_now(int(parts[2])) if runner else check_monitor(store, int(parts[2]), webhook_url))
                else:
                    self.send_json(404, {"error": "未找到"})
            except BusyError as exc:
                self.send_json(409, {"error": str(exc)})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})

        def do_PATCH(self):
            parts = self.path_parts()
            if len(parts) != 3 or parts[:2] != ["api", "monitors"] or not parts[2].isdigit():
                self.send_json(404, {"error": "未找到"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size > 8192:
                    raise ValueError("请求内容过大")
                data = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError("请求内容须为 JSON 对象")
                self.send_json(200, store.update_monitor(int(parts[2]), **data))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})

        def do_DELETE(self):
            parts = self.path_parts()
            if len(parts) == 3 and parts[:2] == ["api", "monitors"] and parts[2].isdigit():
                if store.delete_monitor(int(parts[2])):
                    self.send_json(200, {"deleted": True})
                else:
                    self.send_json(404, {"error": "监控项不存在"})
            else:
                self.send_json(404, {"error": "未找到"})

        def log_message(self, fmt, *args):
            print("%s %s" % (self.address_string(), fmt % args))

    return ThreadingHTTPServer((host, port), Handler)


def main():
    store = Store(os.environ.get("DATABASE_PATH", str(BASE / "pulse.db")))
    webhook = os.environ.get("WEBHOOK_URL")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "3001"))
    runner = MonitorRunner(store, webhook)
    server = make_server(store, host, port, webhook, runner)
    stop = threading.Event()

    def scheduler():
        while not stop.is_set():
            runner.schedule_due()
            stop.wait(3)

    threading.Thread(target=scheduler, daemon=True).start()
    print(f"Pulse Monitor: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        runner.shutdown()


if __name__ == "__main__":
    main()
