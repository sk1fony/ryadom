import concurrent.futures
import hashlib
import http.client
import json
from pathlib import Path
from http.cookies import SimpleCookie
from unittest.mock import patch
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ryadom import Shelf, Server, clean_name


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.shelf = Shelf(Path(self.directory.name), 2 * 1024 * 1024)
        self.shelf.addresses = ["127.0.0.1"]
        self.shelf.selected_address = "127.0.0.1"
        self.server = Server(("127.0.0.1", 0), self.shelf)
        self.shelf.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.shelf.port}"
        self.guest_cookie = self.pair()

    def pending_headers(self):
        status, headers, _ = self.request("GET", "/join/" + self.shelf.guest)
        self.assertEqual(status, 303)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, data = self.request("GET", "/api/pairing", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        return {"Cookie": cookie, "X-Ryadom-CSRF": json.loads(data)["csrf"]}

    def pair(self):
        headers = self.pending_headers()
        status, result, data = self.request("POST", "/api/connect", json.dumps({"code": self.shelf.connection_code()}).encode(), headers=headers)
        self.assertEqual(status, 200, data)
        cookie = SimpleCookie(result["Set-Cookie"])
        return cookie["ryadom"].value

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.shelf.close()
        self.directory.cleanup()

    def request(self, method, path, body=None, role=None, headers=None):
        all_headers = {}
        if role:
            all_headers["Cookie"] = "ryadom=" + (self.shelf.owner if role == "host" else self.guest_cookie)
        if method == "POST":
            all_headers.update({"Origin": self.origin, "X-Ryadom-CSRF": self.shelf.csrf})
        all_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.shelf.port, timeout=5)
        connection.request(method, path, body=body, headers=all_headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def upload(self, name, data=b"hello", role="guest"):
        status, _, body = self.request("POST", "/api/upload", data, role, {"X-File-Name": urllib.parse.quote(name)})
        self.assertEqual(status, 201, body)
        return json.loads(body)["file"]

    def test_join_and_owner_link(self):
        status, headers, _ = self.request("GET", "/join/" + self.shelf.guest)
        self.assertEqual(status, 303)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", headers["Set-Cookie"])
        self.assertEqual(headers["Location"], "/connect")
        self.assertEqual(self.request("GET", "/join/wrong")[0], 401)
        self.assertEqual(self.request("GET", "/host/" + self.shelf.owner)[0], 303)

    def test_no_anonymous_access_or_arbitrary_files(self):
        for path in ("/", "/api/session", "/api/files", "/api/qr", "/download/../ryadom.py"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 401)
        self.assertEqual(self.request("GET", "/../../ryadom.py", role="host")[0], 404)
        self.assertEqual(self.request("GET", "/download/../../ryadom.py", role="host")[0], 404)

    def test_no_rebinding_and_cross_origin_writes(self):
        self.assertEqual(self.request("GET", "/api/session", role="host", headers={"Host": f"evil.example:{self.shelf.port}"})[0], 403)
        for override in ({"Origin": "https://evil.example"}, {"X-Ryadom-CSRF": "wrong"}, {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(override=override):
                self.assertEqual(self.request("POST", "/api/rotate", b"{}", "host", override)[0], 403)

    def test_guest_has_no_owner_capabilities(self):
        data = json.loads(self.request("GET", "/api/session", role="guest")[2])
        self.assertEqual(data["role"], "guest")
        self.assertNotIn("storage", data)
        self.assertNotIn("joinUrl", data)
        for path in ("/api/rotate", "/api/open-folder", "/api/address"):
            self.assertEqual(self.request("POST", path, b"{}", "guest")[0], 403)
        self.assertEqual(self.request("GET", "/api/qr", role="guest")[0], 404)

    def test_both_directions_preserve_binary_and_unicode(self):
        payload = bytes(range(256)) * 1200
        received = self.upload("отчёт с телефона.bin", payload)
        shared = self.upload("ПК 你好.bin", payload[::-1], "host")
        for entry, expected, role in ((received, payload, "host"), (shared, payload[::-1], "guest")):
            status, headers, actual = self.request("GET", "/download/" + entry["id"], role=role)
            self.assertEqual(status, 200)
            self.assertEqual(hashlib.sha256(actual).digest(), hashlib.sha256(expected).digest())
            self.assertIn("filename*=UTF-8''", headers["Content-Disposition"])
            self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertTrue((Path(self.directory.name) / received["name"]).is_file())
        self.assertEqual(self.request("GET", "/download/" + received["id"], role="guest")[0], 404)
        guest_files = json.loads(self.request("GET", "/api/files", role="guest")[2])["files"]
        self.assertEqual({f["id"] for f in guest_files}, {shared["id"], received["id"]})
        self.assertEqual({f["direction"] for f in guest_files}, {"send", "receive"})

    def test_collisions_and_path_names(self):
        first = self.upload("../../report.txt", b"one")
        second = self.upload("C:\\private\\report.txt", b"two")
        self.assertEqual(first["name"], "report.txt")
        self.assertEqual(second["name"], "report (2).txt")
        self.assertEqual((Path(self.directory.name) / "report.txt").read_bytes(), b"one")
        self.assertEqual((Path(self.directory.name) / "report (2).txt").read_bytes(), b"two")
        self.assertEqual(self.upload("CON.txt")["name"], "_CON.txt")
        name = self.upload("я" * 200 + ".txt")["name"]
        self.assertLessEqual(len(name.encode()), 180)

    def test_simultaneous_same_name(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            entries = list(pool.map(lambda i: self.upload("same.bin", bytes([i]) * 4096), range(3)))
        self.assertEqual(len({e["name"] for e in entries}), 3)
        self.assertEqual({p.read_bytes()[0] for p in Path(self.directory.name).iterdir()}, {0, 1, 2})

    def test_empty_files_and_download_ranges(self):
        empty = self.upload("empty.txt", b"", "host")
        self.assertEqual(self.request("GET", "/download/" + empty["id"], role="guest")[2], b"")
        entry = self.upload("range.bin", b"0123456789", "host")
        path = "/download/" + entry["id"]
        for range_value, expected in (("bytes=2-5", b"2345"), ("bytes=-3", b"789"), ("bytes=7-", b"789")):
            status, headers, data = self.request("GET", path, role="guest", headers={"Range": range_value})
            self.assertEqual(status, 206)
            self.assertEqual(data, expected)
        self.assertEqual(self.request("GET", path, role="guest", headers={"Range": "bytes=100-200"})[0], 416)
        self.assertEqual(self.request("HEAD", path, role="guest")[2], b"")

    def test_revocation(self):
        previous = self.shelf.guest
        self.assertEqual(self.request("POST", "/api/rotate", b"{}", "host")[0], 200)
        self.assertNotEqual(previous, self.shelf.guest)
        self.assertEqual(self.request("GET", "/api/files", headers={"Cookie": "ryadom=" + previous})[0], 401)
        self.assertEqual(self.request("GET", "/join/" + previous)[0], 401)
        self.assertEqual(self.request("GET", "/api/session", role="host")[0], 200)

    def test_remove_revokes_shared_file(self):
        entry = self.upload("remove.txt", role="host")
        self.assertEqual(self.request("POST", "/api/remove/" + entry["id"], b"{}", "host")[0], 200)
        self.assertEqual(self.request("GET", "/download/" + entry["id"], role="guest")[0], 404)
        self.assertFalse((self.shelf.shared / entry["name"]).exists())

    def test_interrupted_upload_leaves_no_file(self):
        sock = socket.create_connection(("127.0.0.1", self.shelf.port))
        headers = (f"POST /api/upload HTTP/1.0\r\nHost: 127.0.0.1:{self.shelf.port}\r\n"
                   f"Cookie: ryadom={self.guest_cookie}\r\nOrigin: {self.origin}\r\n"
                   f"X-Ryadom-CSRF: {self.shelf.csrf}\r\nX-File-Name: incomplete.txt\r\nContent-Length: 100000\r\n\r\n")
        sock.sendall(headers.encode() + b"unfinished")
        sock.shutdown(socket.SHUT_WR)
        while sock.recv(4096):
            pass
        sock.close()
        for _ in range(100):
            if not list(Path(self.directory.name).iterdir()) and not self.shelf.reserved:
                break
            time.sleep(0.01)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])
        self.assertEqual(self.shelf.reserved, {})

    def test_size_limit_and_bad_transfer_encoding(self):
        headers = {"X-File-Name": "big.bin", "Content-Length": str(self.shelf.max_bytes + 1)}
        self.assertEqual(self.request("POST", "/api/upload", b"", "guest", headers)[0], 413)
        self.assertEqual(self.request("POST", "/api/upload", b"", "guest", {"X-File-Name": "a", "Transfer-Encoding": "chunked"})[0], 411)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_received_persist_but_shared_are_session_only(self):
        received = self.upload("keep.txt", b"keep")
        shared = self.upload("temporary.txt", b"temp", "host")
        temporary = self.shelf.shared
        other = Shelf(Path(self.directory.name), self.shelf.max_bytes)
        try:
            self.assertEqual([e.name for e in other.entries.values()], [received["name"]])
        finally:
            other.close()
        self.shelf.close()
        self.assertFalse(temporary.exists())
        self.assertTrue((Path(self.directory.name) / received["name"]).exists())

    def test_qr_is_local_svg(self):
        status, headers, content = self.request("GET", "/api/qr", role="host")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", content)
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")

    def test_revoke_during_upload_discards_partial_data(self):
        sock = socket.create_connection(("127.0.0.1", self.shelf.port))
        headers = (f"POST /api/upload HTTP/1.0\r\nHost: 127.0.0.1:{self.shelf.port}\r\n"
                   f"Cookie: ryadom={self.guest_cookie}\r\nOrigin: {self.origin}\r\n"
                   f"X-Ryadom-CSRF: {self.shelf.csrf}\r\nX-File-Name: revoked.txt\r\nContent-Length: 100\r\n\r\n")
        sock.sendall(headers.encode() + b"x" * 10)
        for _ in range(100):
            if self.shelf.reserved:
                break
            time.sleep(0.01)
        self.assertTrue(self.shelf.reserved)
        self.request("POST", "/api/rotate", b"{}", "host")
        sock.sendall(b"x" * 90)
        response = b""
        while chunk := sock.recv(4096):
            response += chunk
        sock.close()
        self.assertIn(b"401", response.split(b"\r\n")[0])
        for _ in range(100):
            if not self.shelf.reserved:
                break
            time.sleep(0.01)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_shutdown_cleans_an_incomplete_upload(self):
        sock = socket.create_connection(("127.0.0.1", self.shelf.port))
        headers = (f"POST /api/upload HTTP/1.0\r\nHost: 127.0.0.1:{self.shelf.port}\r\n"
                   f"Cookie: ryadom={self.guest_cookie}\r\nOrigin: {self.origin}\r\n"
                   f"X-Ryadom-CSRF: {self.shelf.csrf}\r\nX-File-Name: closing.txt\r\nContent-Length: 100000\r\n\r\n")
        sock.sendall(headers.encode() + b"x")
        for _ in range(100):
            if self.shelf.reserved:
                break
            time.sleep(0.01)
        self.assertTrue(self.shelf.reserved)
        self.server.shutdown()
        self.server.server_close()
        sock.close()
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])
        self.assertEqual(self.shelf.reserved, {})

    def test_qr_without_code_cannot_read_panel_files_or_text(self):
        shared = self.upload("private.txt", role="host")
        headers = self.pending_headers()
        for path in ("/", "/app.js", "/api/session", "/api/files", "/api/code", "/download/" + shared["id"]):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path, headers=headers)[0], 401)
        self.assertEqual(self.request("POST", "/api/upload", b"x", headers=dict(headers, **{"X-File-Name": "x"}))[0], 401)
        self.assertEqual(self.request("POST", "/api/text", b'{"text":"x"}', headers=headers)[0], 401)
        self.assertEqual(self.request("GET", "/api/files", headers={"Cookie": "ryadom=" + self.shelf.guest})[0], 401)

    def test_connection_code_changes_and_old_code_expires(self):
        self.shelf.pairing_secret = bytes(range(32))
        with patch("ryadom.time.time", return_value=1504):
            old_code = self.shelf.connection_code()
        with patch("ryadom.time.time", return_value=1519):
            self.assertNotEqual(old_code, self.shelf.connection_code())
            headers = self.pending_headers()
            self.assertEqual(self.request("POST", "/api/connect", json.dumps({"code": old_code}).encode(), headers=headers)[0], 403)
            self.assertEqual(self.request("POST", "/api/connect", json.dumps({"code": self.shelf.connection_code()}).encode(), headers=headers)[0], 200)

    def test_pairing_rate_limit_survives_rescanning_qr(self):
        self.shelf.connection_code = lambda step=None: "123456"
        headers = self.pending_headers()
        for _ in range(5):
            self.assertEqual(self.request("POST", "/api/connect", b'{"code":"654321"}', headers=headers)[0], 403)
        other_pending = self.pending_headers()
        self.assertEqual(self.request("POST", "/api/connect", b'{"code":"123456"}', headers=other_pending)[0], 429)
        self.assertEqual(self.request("GET", "/api/code", role="guest")[0], 404)

    def test_pending_auth_has_expiry_csrf_and_revocation(self):
        headers = self.pending_headers()
        body = json.dumps({"code": self.shelf.connection_code()}).encode()
        self.assertEqual(self.request("POST", "/api/connect", body, headers=dict(headers, Origin="https://evil.example"))[0], 403)
        self.assertEqual(self.request("POST", "/api/connect", body, headers=dict(headers, **{"X-Ryadom-CSRF": "wrong"}))[0], 403)
        for pending in self.shelf.pending.values():
            pending["expires"] = time.monotonic() - 1
        self.assertEqual(self.request("POST", "/api/connect", body, headers=headers)[0], 401)
        headers = self.pending_headers()
        self.request("POST", "/api/rotate", b"{}", "host")
        self.assertEqual(self.request("POST", "/api/connect", body, headers=headers)[0], 401)
        self.assertEqual(self.request("GET", "/api/files", role="guest")[0], 401)

    def test_text_roundtrip_limits_and_individual_removal(self):
        text = "  https://example.test/путь\n<script>alert(1)</script>\nстрока  "
        status, _, result = self.request("POST", "/api/text", json.dumps({"text": text}).encode(), "guest")
        self.assertEqual(status, 201)
        message_id = json.loads(result)["id"]
        data = json.loads(self.request("GET", "/api/files", role="host")[2])
        self.assertEqual(data["texts"][0]["text"], text)
        self.assertEqual(data["texts"][0]["direction"], "receive")
        for invalid in ("", "   ", None, 123):
            self.assertEqual(self.request("POST", "/api/text", json.dumps({"text": invalid}).encode(), "host")[0], 400)
        self.assertEqual(self.request("POST", "/api/text", json.dumps({"text": "я" * 32769}).encode(), "host")[0], 413)
        self.assertEqual(self.request("POST", "/api/text", json.dumps({"text": "\n" * 65535 + "x"}).encode(), "host")[0], 201)
        self.assertEqual(self.request("POST", "/api/text/remove/" + message_id, b"{}", "host")[0], 200)
        self.assertNotIn(message_id, self.shelf.messages)

    def test_guests_cannot_see_other_guests_sent_files_or_texts(self):
        entry = self.upload("guest-one.txt")
        message = json.loads(self.request("POST", "/api/text", b'{"text":"guest one"}', "guest")[2])["id"]
        second = self.pair()
        second_headers = {"Cookie": "ryadom=" + second}
        data = json.loads(self.request("GET", "/api/files", headers=second_headers)[2])
        self.assertEqual(data["files"], [])
        self.assertEqual(data["texts"], [])
        self.assertEqual(self.request("POST", "/api/remove/" + entry["id"], b"{}", headers=second_headers)[0], 404)
        self.assertEqual(self.request("POST", "/api/text/remove/" + message, b"{}", headers=second_headers)[0], 404)

    def test_delete_received_requires_confirmation_and_keeps_other_files(self):
        first = self.upload("first.txt", b"first")
        second = self.upload("second.txt", b"second")
        path = "/api/remove/" + first["id"]
        self.assertEqual(self.request("POST", path, b"{}", "host")[0], 400)
        self.assertTrue((Path(self.directory.name) / first["name"]).exists())
        self.assertEqual(self.request("POST", path, b'{"delete":true}', "host")[0], 200)
        self.assertFalse((Path(self.directory.name) / first["name"]).exists())
        self.assertEqual((Path(self.directory.name) / second["name"]).read_bytes(), b"second")

    def test_guest_remove_is_local_to_the_guest(self):
        entry = self.upload("keep-on-pc.txt")
        self.assertEqual(self.request("POST", "/api/remove/" + entry["id"], b"{}", "guest")[0], 200)
        self.assertEqual(json.loads(self.request("GET", "/api/files", role="guest")[2])["files"], [])
        self.assertEqual(len(json.loads(self.request("GET", "/api/files", role="host")[2])["files"]), 1)
        self.assertTrue((Path(self.directory.name) / entry["name"]).exists())

    def test_server_push_revokes_phone_without_a_poll(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.shelf.port, timeout=2)
        connection.request("GET", "/api/events", headers={"Cookie": "ryadom=" + self.guest_cookie})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
        self.assertEqual(response.readline(), b"event: state\n")
        self.assertIn(b'"paired": true', response.readline())
        self.assertEqual(response.readline(), b"\n")
        started = time.monotonic()
        self.request("POST", "/api/rotate", b"{}", "host")
        self.assertEqual(response.readline(), b"event: revoked\n")
        self.assertLess(time.monotonic() - started, 1)
        response.close()
        connection.close()

    def test_revoked_download_stops_and_old_link_is_rejected(self):
        path = self.shelf.shared / "large.bin"
        with path.open("wb") as output:
            for _ in range(32):
                output.write(b"x" * 1024 * 1024)
        entry = self.shelf.add(path, path.stat().st_size, "shared", sender="host")
        connection = http.client.HTTPConnection("127.0.0.1", self.shelf.port, timeout=5)
        connection.request("GET", "/download/" + entry.id, headers={"Cookie": "ryadom=" + self.guest_cookie})
        response = connection.getresponse()
        first = response.read(1024)
        self.request("POST", "/api/rotate", b"{}", "host")
        received = len(first)
        while data := response.read(256 * 1024):
            received += len(data)
        self.assertLess(received, entry.size)
        response.close()
        connection.close()
        self.assertEqual(self.request("GET", "/download/" + entry.id, role="guest")[0], 401)

    def test_owner_can_detect_pairing_and_reset_to_waiting(self):
        self.assertTrue(json.loads(self.request("GET", "/api/files", role="host")[2])["paired"])
        self.request("POST", "/api/rotate", b"{}", "host")
        self.assertFalse(json.loads(self.request("GET", "/api/files", role="host")[2])["paired"])

    def test_os_metadata_is_hidden_but_user_dotfiles_are_kept(self):
        names = [".DS_Store", "Thumbs.db", "desktop.ini", "._photo.jpg", ".ryadom-tmp.part", ".env", "document.txt"]
        folder = Path(self.directory.name)
        for name in names:
            (folder / name).write_bytes(b"fixture")
        other = Shelf(folder, self.shelf.max_bytes)
        try:
            self.assertEqual({entry.name for entry in other.entries.values()}, {".env", "document.txt"})
            self.assertTrue((folder / ".DS_Store").exists())
        finally:
            other.close()
        for name in (".DS_Store", "folder/._photo.jpg", "Thumbs.db", "desktop.ini"):
            status, _, _ = self.request("POST", "/api/upload", b"metadata", "guest", {"X-File-Name": urllib.parse.quote(name)})
            self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
