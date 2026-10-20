#!/usr/bin/env python3

from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from network import local_addresses

VERSION = "1.0"
WEB = Path(__file__).resolve().parent / "web"
CHUNK = 256 * 1024
MAX_TEXT_BYTES = 64 * 1024


def is_service_file(name: str) -> bool:
    basename = name.replace("\\", "/").rsplit("/", 1)[-1].casefold()
    return basename in {".ds_store", "thumbs.db", "desktop.ini"} or basename.startswith(("._", ".ryadom-"))


def clean_name(raw: str) -> str:
    name = unicodedata.normalize("NFC", raw.replace("\\", "/").split("/")[-1])
    name = "".join("_" if c in '<>:"/\\|?*' or unicodedata.category(c).startswith("C") else c for c in name)
    name = name.strip(" .") or "file"
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        name = "_" + name
    # Leave space for collision suffixes within Windows and POSIX limits.
    while len(name.encode("utf-8")) > 180:
        stem, suffix = os.path.splitext(name)
        name = stem[:-1] + suffix if len(stem) > 1 else name[:-1]
    return name


@dataclass
class Entry:
    id: str
    name: str
    path: Path
    size: int
    created: float
    kind: str
    sender: str = ""

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "size": self.size, "created": self.created, "kind": self.kind}


class Shelf:
    def __init__(self, storage: Path, max_bytes: int):
        self.storage = storage.resolve()
        self.storage.mkdir(parents=True, exist_ok=True)
        self.shared = Path(tempfile.mkdtemp(prefix="ryadom-"))
        self.lock = threading.RLock()
        self.events = threading.Condition(self.lock)
        self.event_sequence = 0
        self.closing = False
        self.slots = threading.BoundedSemaphore(4)
        self.entries: dict[str, Entry] = {}
        self.clients: set[str] = set()
        self.dismissed: dict[str, set[str]] = {}
        self.messages: dict[str, dict] = {}
        self.pending: dict[str, dict] = {}
        self.pairing_secret = secrets.token_bytes(32)
        self.failed_attempts: dict[str, list[float]] = {}
        self.reserved: dict[str, int] = {}
        self.pending_names: set[Path] = set()
        self.max_bytes = max_bytes
        self.owner = secrets.token_urlsafe(32)
        self.guest = secrets.token_urlsafe(24)
        self.csrf = secrets.token_urlsafe(32)
        self.last_guest = 0.0
        self.addresses: list[str] = []
        self.selected_address = ""
        self.port = 0
        for path in self.storage.iterdir():
            if path.is_file() and not path.is_symlink() and not is_service_file(path.name):
                stat = path.stat()
                self.add(path, stat.st_size, "received", stat.st_mtime)

    def add(self, path: Path, size: int, kind: str, created: float | None = None, sender: str = "") -> Entry:
        entry = Entry(secrets.token_hex(12), path.name, path, size, created or time.time(), kind, sender)
        with self.lock:
            self.entries[entry.id] = entry
            self.publish()
        return entry

    def publish(self):
        with self.events:
            self.event_sequence += 1
            self.events.notify_all()

    def reserve(self, name: str, kind: str, size: int) -> Path:
        folder = self.shared if kind == "shared" else self.storage
        with self.lock:
            # Both folders may share a disk: conservatively count all active writes.
            if shutil.disk_usage(folder).free < size + sum(self.reserved.values()) + 16 * 1024 * 1024:
                raise OSError("space")
            candidate = folder / name
            stem, suffix = os.path.splitext(name)
            counter = 2
            while candidate.exists() or candidate.is_symlink() or candidate in self.pending_names:
                candidate = folder / f"{stem} ({counter}){suffix}"
                counter += 1
            self.pending_names.add(candidate)
            self.reserved[str(candidate)] = size
            return candidate

    def release(self, path: Path):
        with self.lock:
            self.pending_names.discard(path)
            self.reserved.pop(str(path), None)

    def close(self):
        shutil.rmtree(self.shared, ignore_errors=True)

    def connection_code(self, step=None):
        step = int(time.time() // 15) if step is None else step
        digest = hmac.new(self.pairing_secret, str(step).encode(), hashlib.sha256).digest()
        return f"{int.from_bytes(digest[:8], 'big') % 1000000:06d}"


class Server(ThreadingHTTPServer):
    daemon_threads = False
    allow_reuse_address = True

    def __init__(self, address, shelf: Shelf):
        self.shelf = shelf
        self.connections = set()
        self.connection_lock = threading.Lock()
        super().__init__(address, Handler)

    def get_request(self):
        connection, address = super().get_request()
        with self.connection_lock:
            self.connections.add(connection)
        return connection, address

    def close_request(self, request):
        with self.connection_lock:
            self.connections.discard(request)
        super().close_request(request)

    def server_close(self):
        # Unblock incomplete requests before joining worker threads and cleaning up.
        with self.shelf.events:
            self.shelf.closing = True
            self.shelf.events.notify_all()
        with self.connection_lock:
            connections = list(self.connections)
        for connection in connections:
            with contextlib.suppress(OSError):
                connection.shutdown(socket.SHUT_RDWR)
        super().server_close()

    def handle_error(self, request, client_address):
        # A browser closing a download isn't a server error worth printing secrets for.
        print("Соединение прервано", file=sys.stderr)


class Handler(BaseHTTPRequestHandler):
    server_version = "Ryadom"
    sys_version = ""

    @property
    def shelf(self) -> Shelf:
        return self.server.shelf

    def setup(self):
        super().setup()
        self.connection.settimeout(120)

    def log_message(self, *_):
        pass  # Join and owner URLs contain session credentials.

    def common_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

    def reply(self, code: int, body: bytes, mime="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.common_headers()
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, value, code=200):
        self.reply(code, json.dumps(value, ensure_ascii=False).encode())

    def fail(self, message, code=400):
        self.json({"error": message}, code)

    def valid_host(self) -> bool:
        # Only literal local addresses are served; DNS rebinding hosts are rejected.
        allowed = {f"{a}:{self.shelf.port}" for a in ["127.0.0.1", "localhost", *self.shelf.addresses]}
        return self.headers.get("Host", "") in allowed

    def actor(self) -> str:
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            value = cookie["ryadom"].value if "ryadom" in cookie else ""
        except Exception:
            return ""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            return ""
        if secrets.compare_digest(value, self.shelf.owner):
            return "host"
        with self.shelf.lock:
            return value if value in self.shelf.clients else ""

    def role(self) -> str | None:
        actor = self.actor()
        return ("host" if actor == "host" else "guest") if actor else None

    def pending_connection(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            value = cookie["ryadom_pending"].value if "ryadom_pending" in cookie else ""
        except Exception:
            return None
        with self.shelf.lock:
            pending = self.shelf.pending.get(value)
            return (value, pending) if pending and pending["expires"] > time.monotonic() else None

    def read_json(self, limit=128 * 1024):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Invalid transfer encoding")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= limit:
            raise ValueError("Invalid body length")
        result = json.loads(self.rfile.read(length))
        if not isinstance(result, dict):
            raise ValueError("Expected an object")
        return result

    def visible_messages(self, actor):
        hidden = self.shelf.dismissed.get(actor, set())
        return [dict(id=m["id"], text=m["text"], created=m["created"], direction="send" if m["sender"] == actor else "receive")
                for m in reversed(list(self.shelf.messages.values()))
                if m["id"] not in hidden and (actor == "host" or m["sender"] in ("host", actor))]

    def mutation_allowed(self) -> bool:
        expected = "http://" + self.headers.get("Host", "")
        return (self.headers.get("Origin") == expected
                and self.headers.get("X-Ryadom-CSRF") == self.shelf.csrf
                and self.headers.get("Sec-Fetch-Site") in (None, "same-origin"))

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.valid_host():
            return self.fail("Неверный адрес сервера", 403)
        path = urllib.parse.urlsplit(self.path).path
        if path.startswith(("/join/", "/host/")):
            prefix, value = path.rsplit("/", 1)
            expected = self.shelf.owner if prefix == "/host" else self.shelf.guest
            # The owner link may only be redeemed on the PC itself.
            if prefix == "/host" and self.client_address[0] != "127.0.0.1":
                return self.fail("Откройте панель на компьютере", 403)
            if not secrets.compare_digest(value, expected):
                return self.reply(401, "Ссылка устарела. Отсканируйте QR-код ещё раз".encode(), "text/plain; charset=utf-8")
            if prefix == "/join":
                with self.shelf.lock:
                    if self.role() == "guest":
                        return self.reply(303, b"", extra={"Location": "/"})
                    self.shelf.pending = {key: item for key, item in self.shelf.pending.items() if item["expires"] > time.monotonic()}
                    if len(self.shelf.pending) >= 256:
                        return self.fail("Слишком много подключений. Повторите позже", 429)
                    credential = secrets.token_urlsafe(32)
                    self.shelf.pending[credential] = {"expires": time.monotonic() + 300, "csrf": secrets.token_urlsafe(24)}
                return self.reply(303, b"", extra={"Location": "/connect", "Set-Cookie": f"ryadom_pending={credential}; HttpOnly; SameSite=Lax; Path=/; Max-Age=300"})
            return self.reply(303, b"", extra={"Location": "/", "Set-Cookie": f"ryadom={expected}; HttpOnly; SameSite=Lax; Path=/"})
        role = self.role()
        pending = self.pending_connection()
        if path in ("/connect", "/connect.js", "/i18n.js", "/style.css", "/favicon.svg") and pending and not role:
            name, mime = {"/connect": ("connect.html", "text/html; charset=utf-8"), "/connect.js": ("connect.js", "text/javascript; charset=utf-8"), "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}[path]
            return self.reply(200, (WEB / name).read_bytes(), mime)
        if path == "/api/pairing" and pending:
            return self.json({"csrf": pending[1]["csrf"]})
        if path == "/connect" and role:
            return self.reply(303, b"", extra={"Location": "/"})
        if path in ("/", "/app.js", "/i18n.js", "/style.css", "/favicon.svg"):
            if not role:
                return self.reply(401, "Open the link from the program window or scan the QR code on your PC | Откройте ссылку из окна программы или отсканируйте QR-код на ПК".encode(), "text/plain; charset=utf-8")
            name, mime = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}[path]
            return self.reply(200, (WEB / name).read_bytes(), mime)
        if not role:
            return self.fail("Подключитесь заново через QR-код", 401)
        if path == "/api/events":
            return self.event_stream()
        if path == "/api/session":
            data = {"role": role, "csrf": self.shelf.csrf, "maxBytes": self.shelf.max_bytes, "maxTextBytes": MAX_TEXT_BYTES, "version": VERSION}
            if role == "host":
                data.update({"addresses": self.shelf.addresses, "address": self.shelf.selected_address, "port": self.shelf.port,
                             "joinUrl": self.join_url(), "storage": str(self.shelf.storage)})
            return self.json(data)
        if path == "/api/code" and role == "host":
            return self.json({"code": self.shelf.connection_code(), "seconds": 15 - int(time.time()) % 15})
        if path == "/api/files":
            if role == "guest":
                self.shelf.last_guest = time.time()
            with self.shelf.lock:
                actor = self.actor()
                hidden = self.shelf.dismissed.get(actor, set())
                entries = []
                for entry in self.shelf.entries.values():
                    if entry.id in hidden or not (role == "host" or entry.kind == "shared" or entry.sender == actor):
                        continue
                    outgoing = entry.kind == "shared" if role == "host" else entry.sender == actor
                    entries.append(dict(entry.public(), direction="send" if outgoing else "receive",
                                        removal="delete" if role == "host" and entry.kind == "received" else "remove"))
                messages = self.visible_messages(actor)
            return self.json({"files": sorted(entries, key=lambda e: e["created"], reverse=True),
                              "texts": messages,
                              "paired": bool(self.shelf.clients),
                              "connected": time.time() - self.shelf.last_guest < 15})
        if path == "/api/qr" and role == "host":
            import qrcode
            from qrcode.image.svg import SvgPathFillImage
            image = qrcode.make(self.join_url(), image_factory=SvgPathFillImage, border=4)
            output = io.BytesIO()
            image.save(output)
            return self.reply(200, output.getvalue(), "image/svg+xml")
        if path.startswith("/download/"):
            return self.download(path.split("/")[-1], role)
        self.fail("Не найдено", 404)

    def join_url(self):
        return f"http://{self.shelf.selected_address}:{self.shelf.port}/join/{self.shelf.guest}"

    def event_stream(self):
        actor = self.actor()
        if not actor:
            return self.fail("Подключитесь заново через QR-код", 401)
        self.send_response(200)
        self.common_headers()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        sequence = -1
        try:
            while True:
                with self.shelf.events:
                    if self.shelf.closing:
                        return
                    if actor != "host" and actor not in self.shelf.clients:
                        self.wfile.write(b"event: revoked\ndata: {}\n\n")
                        self.wfile.flush()
                        return
                    if sequence != self.shelf.event_sequence:
                        sequence = self.shelf.event_sequence
                        data = json.dumps({"paired": bool(self.shelf.clients)}).encode()
                        self.wfile.write(b"event: state\ndata: " + data + b"\n\n")
                    else:
                        self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    self.shelf.events.wait(timeout=10)
        except (OSError, TimeoutError):
            return

    def download(self, file_id: str, role: str):
        with self.shelf.lock:
            actor = self.actor()
            if not actor:
                return self.fail("Подключитесь заново через QR-код", 401)
            entry = self.shelf.entries.get(file_id)
        if not entry or (role != "host" and entry.kind != "shared"):
            return self.fail("Файл недоступен", 404)
        try:
            if entry.path.is_symlink():
                return self.fail("Файл недоступен", 404)
            source = entry.path.open("rb")
        except OSError:
            return self.fail("Файл перемещён или удалён", 404)
        with source:
            size = os.fstat(source.fileno()).st_size
            start, end = 0, size - 1
            range_header = self.headers.get("Range")
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
                try:
                    if not match or not any(match.groups()) or size == 0:
                        raise ValueError
                    left, right = match.groups()
                    if left:
                        start = int(left)
                        end = min(int(right), size - 1) if right else size - 1
                    else:
                        count = int(right)
                        if count == 0:
                            raise ValueError
                        start = max(0, size - count)
                    if start > end or start >= size:
                        raise ValueError
                except ValueError:
                    return self.reply(416, b"", extra={"Content-Range": f"bytes */{size}"})
            self.send_response(206 if range_header else 200)
            self.common_headers()
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f"attachment; filename=\"download\"; filename*=UTF-8''{urllib.parse.quote(entry.name, safe='')}")
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.send_header("Accept-Ranges", "bytes")
            if range_header:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            source.seek(start)
            remaining = end - start + 1
            try:
                while remaining > 0:
                    if role == "guest":
                        with self.shelf.lock:
                            if actor not in self.shelf.clients:
                                return
                    data = source.read(min(CHUNK, remaining))
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)
            except (OSError, TimeoutError):
                pass

    def do_POST(self):
        if not self.valid_host():
            return self.fail("Неверный адрес сервера", 403)
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/connect":
            return self.connect_device()
        role = self.role()
        if not role:
            return self.fail("Подключитесь заново через QR-код", 401)
        if not self.mutation_allowed():
            return self.fail("Обновите страницу и попробуйте снова", 403)
        if path == "/api/upload":
            return self.upload(role)
        if path == "/api/text":
            try:
                text = self.read_json(6 * MAX_TEXT_BYTES + 1024).get("text")
                if not isinstance(text, str) or not text.strip():
                    return self.fail("Введите текст")
                if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
                    return self.fail("Текст больше 64 КБ", 413)
            except (ValueError, TypeError, UnicodeError):
                return self.fail("Не удалось прочитать текст")
            with self.shelf.lock:
                actor = self.actor()
                if not actor:
                    return self.fail("Подключитесь заново через QR-код", 401)
                if len(self.shelf.messages) >= 200:
                    return self.fail("Список текстов заполнен. Уберите ненужные сообщения", 429)
                message = {"id": secrets.token_hex(12), "text": text, "created": time.time(), "sender": actor}
                self.shelf.messages[message["id"]] = message
                self.shelf.publish()
            return self.json({"id": message["id"]}, 201)
        if path.startswith("/api/text/remove/"):
            with self.shelf.lock:
                actor = self.actor()
                message = self.shelf.messages.get(path.rsplit("/", 1)[-1])
                if not message or not (role == "host" or message["sender"] in ("host", actor)):
                    return self.fail("Текст недоступен", 404)
                if role == "host" or message["sender"] == actor:
                    del self.shelf.messages[message["id"]]
                else:
                    self.shelf.dismissed.setdefault(actor, set()).add(message["id"])
                self.shelf.publish()
            return self.json({"ok": True})
        if path.startswith("/api/remove/"):
            with self.shelf.lock:
                actor = self.actor()
                entry = self.shelf.entries.get(path.rsplit("/", 1)[-1])
                if not entry or not (role == "host" or entry.kind == "shared" or entry.sender == actor):
                    return self.fail("Файл недоступен", 404)
                if role != "host":
                    self.shelf.dismissed.setdefault(actor, set()).add(entry.id)
                    self.shelf.publish()
                    return self.json({"ok": True})
                if entry.kind == "received":
                    try:
                        if self.read_json(1024).get("delete") is not True:
                            raise ValueError
                    except (ValueError, TypeError, UnicodeError):
                        return self.fail("Подтвердите удаление полученного файла")
                try:
                    entry.path.unlink(missing_ok=True)
                except OSError:
                    return self.fail("Файл ещё скачивается. Попробуйте позже", 409)
                del self.shelf.entries[entry.id]
                self.shelf.publish()
            return self.json({"ok": True})
        if role != "host":
            return self.fail("Действие доступно только на ПК", 403)
        if path == "/api/rotate":
            with self.shelf.lock:
                self.shelf.guest = secrets.token_urlsafe(24)
                self.shelf.clients.clear()
                self.shelf.pending.clear()
                self.shelf.pairing_secret = secrets.token_bytes(32)
                self.shelf.dismissed = {k: v for k, v in self.shelf.dismissed.items() if k == "host"}
                self.shelf.messages.clear()
                self.shelf.last_guest = 0
                self.shelf.publish()
            return self.json({"joinUrl": self.join_url()})
        if path == "/api/address":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError
                address = json.loads(self.rfile.read(length)).get("address")
                if address not in self.shelf.addresses:
                    raise ValueError
            except (ValueError, AttributeError, TypeError):
                return self.fail("Выберите адрес из списка")
            self.shelf.selected_address = address
            return self.json({"joinUrl": self.join_url()})
        if path == "/api/open-folder":
            try:
                if sys.platform == "win32":
                    os.startfile(self.shelf.storage)
                else:
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(self.shelf.storage)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                return self.fail("Откройте папку вручную: " + str(self.shelf.storage), 500)
            return self.json({"ok": True})
        self.fail("Не найдено", 404)

    def connect_device(self):
        pending = self.pending_connection()
        if not pending:
            return self.fail("Ссылка устарела. Отсканируйте QR-код ещё раз", 401)
        expected_origin = "http://" + self.headers.get("Host", "")
        if (self.headers.get("Origin") != expected_origin
                or self.headers.get("X-Ryadom-CSRF") != pending[1]["csrf"]
                or self.headers.get("Sec-Fetch-Site") not in (None, "same-origin")):
            return self.fail("Обновите страницу", 403)
        try:
            code = self.read_json(1024).get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
                return self.fail("Введите шесть цифр с экрана ПК")
        except (ValueError, TypeError, UnicodeError):
            return self.fail("Не удалось прочитать код")
        with self.shelf.lock:
            # Recheck after reading the body: the owner may have revoked the link.
            if not self.pending_connection():
                return self.fail("Ссылка устарела. Отсканируйте QR-код ещё раз", 401)
            now = time.time()
            self.shelf.failed_attempts = {key: [t for t in values if now - t < 30]
                                          for key, values in self.shelf.failed_attempts.items() if any(now - t < 30 for t in values)}
            attempts = self.shelf.failed_attempts.setdefault(self.client_address[0], [])
            if len(attempts) >= 5 or sum(map(len, self.shelf.failed_attempts.values())) >= 20:
                return self.fail("Много неверных попыток. Подождите 30 секунд", 429)
            valid = secrets.compare_digest(code, self.shelf.connection_code())
            # Three seconds of tolerance when a code changes during typing.
            if now % 15 < 3:
                valid |= secrets.compare_digest(code, self.shelf.connection_code(int(now // 15) - 1))
            if not valid:
                attempts.append(now)
                return self.fail("Неверный код или он уже изменился. Посмотрите новый на ПК", 403)
            if len(self.shelf.clients) >= 256:
                return self.fail("Обновите QR-код на компьютере", 429)
            credential = secrets.token_urlsafe(32)
            self.shelf.clients.add(credential)
            del self.shelf.pending[pending[0]]
            self.shelf.publish()
        self.reply(200, b'{"ok":true}', extra={"Set-Cookie": f"ryadom={credential}; HttpOnly; SameSite=Lax; Path=/"})

    def upload(self, role: str):
        actor = self.actor()
        if self.headers.get("Transfer-Encoding"):
            return self.fail("Неизвестный размер файла", 411)
        try:
            size = int(self.headers["Content-Length"])
            if size < 0:
                raise ValueError
        except (ValueError, TypeError):
            return self.fail("Неизвестный размер файла", 411)
        if size > self.shelf.max_bytes:
            return self.fail("Файл превышает лимит размера", 413)
        raw = self.headers.get("X-File-Name", "")
        if not raw or len(raw) > 4096:
            return self.fail("Не удалось прочитать имя файла")
        decoded_name = urllib.parse.unquote(raw)
        if is_service_file(decoded_name):
            return self.fail("Служебный файл не передаётся")
        name = clean_name(decoded_name)
        if not self.shelf.slots.acquire(blocking=False):
            return self.fail("Уже передаётся несколько файлов. Повторите чуть позже", 429)
        target = temporary = None
        try:
            kind = "shared" if role == "host" else "received"
            target = self.shelf.reserve(name, kind, size)
            descriptor, tmp = tempfile.mkstemp(prefix=".ryadom-", suffix=".part", dir=target.parent)
            temporary = Path(tmp)
            with os.fdopen(descriptor, "wb") as output:
                remaining = size
                while remaining:
                    data = self.rfile.read(min(CHUNK, remaining))
                    if not data:
                        return self.fail("Передача прервана. Отправьте файл ещё раз", 400)
                    output.write(data)
                    remaining -= len(data)
            # Never replace a file that appeared outside the app during the write.
            with self.shelf.lock:
                if role == "guest" and self.actor() != actor:
                    return self.fail("Подключение завершено на ПК", 401)
                with target.open("xb"):
                    pass
                try:
                    os.replace(temporary, target)
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise
                entry = self.shelf.add(target, size, kind, sender=actor)
            self.json({"file": entry.public()}, 201)
        except FileExistsError:
            self.fail("Файл с таким именем уже появился. Повторите отправку", 409)
        except (OSError, TimeoutError):
            with contextlib.suppress(OSError):
                self.fail("Не удалось сохранить файл. Проверьте свободное место и соединение", 507)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
            if target:
                self.shelf.release(target)
            self.shelf.slots.release()


def main():
    parser = argparse.ArgumentParser(description="Ryadom(рядом) — file transfer over a local network")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--ip", help="IPv4-The PC address that will be included in the QR code")
    parser.add_argument("--storage", type=Path, default=Path.home() / "Downloads" / "Ryadom")
    parser.add_argument("--max-file-mb", type=int, default=6144)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or args.max_file_mb < 1:
        parser.error("Check the port and the file size limit")
    addresses = local_addresses()
    if args.ip:
        try:
            ipaddress.IPv4Address(args.ip)
            with socket.socket() as probe:
                probe.bind((args.ip, 0))
        except (ValueError, OSError):
            parser.error("--ip address must be an IPv4 address of this computer")
        addresses = list(dict.fromkeys([args.ip, *addresses]))
    if not addresses:
        print("The local network address was not found. Connect the PC to Wi‑Fi or Ethernet and launch it again")
        return 1
    shelf = Shelf(args.storage, args.max_file_mb * 1024 * 1024)
    shelf.addresses = addresses
    shelf.selected_address = addresses[0]
    server = None
    try:
        candidates = [args.port] if args.port == 0 else range(args.port, min(args.port + 10, 65536))
        for port in candidates:
            try:
                server = Server(("0.0.0.0", port), shelf)
                break
            except OSError as error:
                if error.errno not in (48, 98, 10048) and getattr(error, "winerror", None) != 10048:
                    raise
        if server is None:
            print("Порты заняты. Попробуйте запуск с (try) --port 9000")
            return 1
        shelf.port = server.server_address[1]
        owner_url = f"http://127.0.0.1:{shelf.port}/host/{shelf.owner}"
        print("PC panel: " + owner_url)
        print(f"The path to the received files: {shelf.storage}")
        print("\nConnect your phone to the same network and scan the QR code on the panel")
        print("Leave this window open | Ctrl+C — to close\n", flush=True)
        if not args.no_browser:
            webbrowser.open(owner_url)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nThe transfer is complete. The received files remain in the folder")
    except OSError as error:
        print("Error: " + str(error), file=sys.stderr)
        return 1
    finally:
        if server:
            server.server_close()
        shelf.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
