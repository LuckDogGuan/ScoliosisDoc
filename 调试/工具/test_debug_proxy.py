"""Actual loopback forwarding test: raw identities, endpoints, streaming bytes."""
import base64
import hashlib
import http.client
import http.server
import json
import io
import logging
import socket
import threading
import instrument_debug_proxy as proxy

payload = bytes(range(256)) * 8192
digest = hashlib.sha256(payload).hexdigest()
logs = io.StringIO()
proxy.LOG.setLevel(logging.INFO)
proxy.LOG.addHandler(logging.StreamHandler(logs))


class Sink(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/v1/capture/status':
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert data['capture_id'] == 'original-capture' and data['event_id'] == 'original-event'
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        check = hashlib.sha256()
        left = int(self.headers['Content-Length'])
        while left:
            chunk = self.rfile.read(min(left, 8192))
            check.update(chunk)
            left -= len(chunk)
        assert check.hexdigest() == digest
        assert self.headers['Capture-ID'] == 'original-capture'
        assert self.headers['X-Instrument-Original-Source'].startswith('127.0.0.1:')
        body = json.dumps({'ok': True, 'sha256': check.hexdigest(), 'capture_id': 'original-capture'}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(('127.0.0.1', 37020))
packet = json.dumps(dict(version=3, host_id='real-host', boot_id='real-boot',
                         capture_id='original-capture', op='hello_query', sequence=12, nonce='abcdef')).encode()


def echo():
    data, source = udp.recvfrom(4096)
    assert data == packet  # no protocol reserialization or identity substitution
    udp.sendto(data, source)


upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Sink)
proxy.Bridge.upstream = ('127.0.0.1', upstream.server_port)
bridge = http.server.ThreadingHTTPServer(('127.0.0.1', 0), proxy.Bridge)
threads = [threading.Thread(target=upstream.serve_forever, daemon=True),
           threading.Thread(target=bridge.serve_forever, daemon=True), threading.Thread(target=echo)]
for thread in threads:
    thread.start()
try:
    client = http.client.HTTPConnection('127.0.0.1', bridge.server_port, timeout=5)
    body = json.dumps(dict(packet=base64.b64encode(packet).decode(), address='127.0.0.1',
                           port=37020, wait_ms=500))
    client.request('POST', '/debug/udp', body, {'Content-Type': 'application/json'})
    response = client.getresponse()
    reply = json.loads(response.read())['replies'][0]
    assert response.status == 200 and reply['address'] == '127.0.0.1' and reply['port'] == 37020
    assert base64.b64decode(reply['packet']) == packet
    client.request('POST', '/api/v1/capture/file', payload,
                   {'Capture-ID': 'original-capture', 'Device-ID': 'real-device', 'Grant-ID': 'real-grant'})
    response = client.getresponse()
    assert response.status == 200 and json.loads(response.read())['sha256'] == digest
    client.request('POST', '/api/v1/capture/status', json.dumps(dict(
        device_id='real-device', capture_id='original-capture', event_id='original-event',
        gate_id='original-gate', boot_id='real-boot', result='success')),
        {'Content-Type': 'application/json'})
    response = client.getresponse()
    assert response.status == 200 and json.loads(response.read())['ok']
    rows = [json.loads(line) for line in logs.getvalue().splitlines()]
    assert any(row.get('event_id') == 'original-event' and row.get('gate_id') == 'original-gate'
               and row.get('boot_id') == 'real-boot' and row.get('result') == 'success' for row in rows)
    client.close()
    print('PASS real UDP identities/source, 2MiB streaming HTTP, original capture/grant and SHA256')
finally:
    bridge.shutdown()
    upstream.shutdown()
    bridge.server_close()
    upstream.server_close()
    udp.close()
    for thread in threads:
        thread.join(timeout=5)
