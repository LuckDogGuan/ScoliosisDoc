"""Same-PC UDP and streaming HTTP diagnostic bridge (stdlib only)."""
import argparse
import base64
import hashlib
import http.client
import http.server
import ipaddress
import json
import logging
import logging.handlers
import pathlib
import secrets
import socket
import time
import traceback
from datetime import datetime, timezone

LOG = logging.getLogger("instrument")


def trace(direction, **fields):
    LOG.info(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),
                            monotonic_ns=time.monotonic_ns(), direction=direction,
                            **fields), ensure_ascii=False))


def restore_direct(data_root, http_port):
    """Reconfirm the saved pairing transaction with Flutter's direct HTTP port."""
    try:
        book = json.loads((data_root / '设备.json').read_text(encoding='utf-8-sig'))
        addresses = {row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
        addresses = {ip for ip in addresses if not ip.startswith(('127.', '169.254.', '198.18.'))}
        for device in book['paired']:
            txn = book.get('committedPairTransactions', {}).get(device)
            if not txn:
                continue
            host = book['hostId']
            restored = False
            for bind in addresses:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                    udp.bind((bind, 0))
                    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    udp.settimeout(1)

                    def ask(op, target, seq, **fields):
                        packet = dict(version=3, op=op, host_id=host, device_id=device,
                                      sequence=seq, nonce=secrets.token_hex(16), **fields)
                        udp.sendto(json.dumps(packet).encode(), target)
                        until = time.monotonic() + 1
                        while time.monotonic() < until:
                            raw, source = udp.recvfrom(4097)
                            reply = json.loads(raw)
                            if source[1] == 37020 and (target[0] == '255.255.255.255' or source == target) and all(
                                    reply.get(k) == packet[k] for k in ('version', 'host_id', 'device_id', 'sequence', 'nonce')):
                                return reply, source
                        raise TimeoutError('no matching instrument reply')

                    try:
                        found, peer = ask('paired_discover', ('255.255.255.255', 37020), 0, txn_id=txn)
                        if not found.get('ok') or found.get('txn_id') != txn:
                            continue
                        state, _ = ask('hello_query', peer, 0)
                        boot, sequence = state['boot_id'], state['control_sequence']
                        requested, _ = ask('pair_request', peer, sequence + 1,
                                           boot_id=boot, txn_id=txn, http_port=http_port)
                        if requested.get('ok'):
                            committed, _ = ask('pair_commit', peer, sequence + 2,
                                               boot_id=boot, txn_id=txn, http_port=http_port)
                            restored = committed.get('ok') is True
                        trace('restore_direct', device_id=device, host_id=host, txn_id=txn,
                              source_endpoint=peer, http_port=http_port, ok=restored)
                        if restored:
                            break
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        trace('restore_direct_error', device_id=device, error=repr(error))
            if not restored:
                trace('restore_direct_pending', device_id=device, action='restart Flutter without debug flag')
    except (OSError, ValueError, KeyError, TypeError) as error:
        trace('restore_direct_error', error=repr(error))


class Bridge(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = ("127.0.0.1", 8080)

    def log_message(self, *_args):
        pass

    def answer(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path == "/debug/udp":
            return self.udp()
        self.forward()

    def do_GET(self):
        self.forward()

    def udp(self):
        # Development control never accepts LAN callers.
        if not ipaddress.ip_address(self.client_address[0]).is_loopback:
            self.answer(403, {"error": "loopback required"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("invalid request length")
            body = json.loads(self.rfile.read(length))
            packet = base64.b64decode(body["packet"], validate=True)
            if len(packet) > 4096:
                raise ValueError("UDP packet too large")
            target = (str(ipaddress.IPv4Address(body["address"])), int(body["port"]))
            if target[1] != 37020:
                raise ValueError("instrument discovery port required")
            wait = max(0.01, min(3, int(body["wait_ms"]) / 1000))
            fields = json.loads(packet)
            trace("pc_to_board", endpoint=target, **fields)
            replies = []
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                udp.bind((body.get("bind_address") or "0.0.0.0", 0))
                udp.sendto(packet, target)
                deadline = time.monotonic() + wait
                while time.monotonic() < deadline:
                    udp.settimeout(max(0.001, deadline - time.monotonic()))
                    try:
                        data, source = udp.recvfrom(4097)
                    except socket.timeout:
                        break
                    if len(data) > 4096:
                        continue
                    try:
                        trace("board_to_pc", source_endpoint=source, **json.loads(data))
                    except (ValueError, TypeError):
                        trace("malformed_udp", source_endpoint=source, size_bytes=len(data))
                    replies.append(dict(packet=base64.b64encode(data).decode(),
                                        address=source[0], port=source[1]))
                    if not body.get("broadcast"):
                        break
            self.answer(200, {"replies": replies})
        except (ValueError, KeyError, OSError, TypeError) as error:
            trace("udp_error", error=repr(error), stack=traceback.format_exc())
            self.answer(400, {"error": str(error)})

    def forward(self):
        if not self.path.startswith("/api/v1/"):
            self.answer(404, {"error": "unknown endpoint"})
            return
        connection = http.client.HTTPConnection(*self.upstream, timeout=60)
        size, digest = 0, hashlib.sha256()
        metadata = bytearray()
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 100 * 1024 * 1024:
                raise ValueError("invalid Content-Length")
            connection.putrequest(self.command, self.path)
            for key, value in self.headers.items():
                if key.lower() not in {"host", "connection", "x-instrument-original-source", "transfer-encoding"}:
                    connection.putheader(key, value)
            connection.putheader("X-Instrument-Original-Source", "%s:%s" % self.client_address)
            connection.putheader("Connection", "close")
            connection.endheaders()
            remaining = length
            while remaining:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    raise EOFError("truncated body")
                connection.send(chunk)
                digest.update(chunk)
                if 'application/json' in self.headers.get('Content-Type', '') and length <= 8192:
                    metadata.extend(chunk)
                size += len(chunk)
                remaining -= len(chunk)
            identity = {key.lower().replace("-", "_"): self.headers.get(key)
                        for key in ("Device-ID", "Capture-ID", "Grant-ID")}
            if metadata:
                try:
                    fields = json.loads(metadata)
                    if isinstance(fields, dict):
                        identity.update({key: fields[key] for key in (
                            'device_id', 'host_id', 'boot_id', 'gate_id', 'capture_id',
                            'event_id', 'grant_id', 'txn_id', 'result') if key in fields})
                except (ValueError, TypeError):
                    pass  # Forward invalid JSON unchanged for Flutter's existing validation.
            trace("board_http_to_pc", path=self.path, source_endpoint=self.client_address,
                  size_bytes=size, sha256=digest.hexdigest(), **identity)
            response = connection.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in {"connection", "transfer-encoding"}:
                    self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            proof = bytearray()
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                if len(proof) + len(chunk) <= 4096:
                    proof.extend(chunk)
                self.wfile.write(chunk)
            trace("pc_http_to_board", path=self.path, status=response.status,
                  response=proof.decode(errors="replace"), **identity)
            self.close_connection = True
        except (OSError, ValueError, EOFError, http.client.HTTPException) as error:
            trace("http_error", path=self.path, error=repr(error), stack=traceback.format_exc(), size_bytes=size)
            self.close_connection = True
        finally:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--flutter-port", type=int, default=8080)
    parser.add_argument("--log", default="instrument-proxy.jsonl")
    parser.add_argument('--data-root', type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parents[4] / 'ScoliosisFlutter' / 'data')
    args = parser.parse_args()
    LOG.setLevel(logging.INFO)
    LOG.addHandler(logging.handlers.RotatingFileHandler(args.log, maxBytes=4 * 1024 * 1024,
                                                       backupCount=2, encoding="utf-8"))
    Bridge.upstream = ("127.0.0.1", args.flutter_port)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), Bridge)
    trace("proxy_start", port=args.port, flutter_port=args.flutter_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        restore_direct(args.data_root, args.flutter_port)
        trace("proxy_stop", action="restart Flutter without INSTRUMENT_DEBUG_PROXY to restore direct endpoint")


if __name__ == "__main__":
    main()
