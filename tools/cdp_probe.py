"""以短連線讀取專用 Chromium 的 CDP（開發者工具協定）；不附著偵錯器。"""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
from urllib.parse import urlparse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def exact(sock, count):
    out = bytearray()
    while len(out) < count:
        block = sock.recv(count - len(out))
        if not block:
            raise ConnectionError("CDP 連線提前關閉")
        out.extend(block)
    return bytes(out)


def send_text(sock, payload):
    payload = payload.encode("utf8")
    mask = os.urandom(4)
    header = bytearray([0x81])
    if len(payload) < 126:
        header.append(0x80 | len(payload))
    elif len(payload) < 65536:
        header.extend([0x80 | 126]); header.extend(struct.pack("!H", len(payload)))
    else:
        header.extend([0x80 | 127]); header.extend(struct.pack("!Q", len(payload)))
    sock.sendall(bytes(header) + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))


def recv_text(sock):
    first, second = exact(sock, 2)
    opcode = first & 15
    length = second & 127
    if length == 126:
        length = struct.unpack("!H", exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", exact(sock, 8))[0]
    mask = exact(sock, 4) if second & 128 else None
    payload = exact(sock, length)
    if mask:
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
    if opcode == 8:
        raise ConnectionError("CDP WebSocket 已關閉")
    if opcode != 1:
        return None
    return json.loads(payload)


def endpoint_for(target, timeout, page_id=None):
    port = int((ROOT / "runtime/browser-profile/DevToolsActivePort").read_text().splitlines()[0])
    pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=timeout))
    if page_id is not None:
        return next(p for p in pages if p.get("id") == page_id)["webSocketDebuggerUrl"]
    if target == "browser":
        return json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout))["webSocketDebuggerUrl"]
    return next(p for p in pages if p.get("url") == target)["webSocketDebuggerUrl"]


class Session:
    def __init__(self, target="browser", timeout=5, page_id=None):
        self.endpoint = endpoint_for(target, timeout, page_id)
        self.timeout = timeout
        self.sock = None
        self.next_id = 1

    def __enter__(self):
        endpoint = self.endpoint
        timeout = self.timeout
        parsed = urlparse(endpoint)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        sock = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
        sock.settimeout(timeout)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        request = (f"GET {path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n"
                   f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                   "Sec-WebSocket-Version: 13\r\n\r\n")
        sock.sendall(request.encode("ascii"))
        response = bytearray()
        while b"\r\n\r\n" not in response:
            response.extend(sock.recv(4096))
            if len(response) > 8192:
                raise ValueError("WebSocket 回應過長")
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError("WebSocket 升級失敗")
        # 回應與首個影格極少合併；保守起見，此短命令若遇合併即重試。
        if response.split(b"\r\n\r\n", 1)[1]:
            raise ConnectionError("WebSocket 首影格與握手合併")
        self.sock = sock
        return self

    def __exit__(self, *_):
        if self.sock:
            self.sock.close()

    def call(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        send_text(self.sock, json.dumps({"id": request_id, "method": method, "params": params or {}}))
        for _ in range(100):
            message = recv_text(self.sock)
            if message and message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})
        raise TimeoutError("沒有收到 CDP 回應")


def call(method, params=None, target="browser", timeout=5):
    with Session(target, timeout) as session:
        return session.call(method, params)


if __name__ == "__main__":
    print(json.dumps(call("SystemInfo.getProcessInfo"), ensure_ascii=False, indent=2))
