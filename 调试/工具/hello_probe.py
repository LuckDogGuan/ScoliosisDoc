"""Receive one instrument hello on a temporary HTTP port."""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        print(
            self.path,
            {key: body.get(key) for key in ("device_id", "ip", "storage_free_mb", "storage_total_mb")},
            flush=True,
        )
        data = b'{"ok":true,"received":true,"paired":false}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    address = sys.argv[1]
    port = int(sys.argv[2])
    server = HTTPServer((address, port), Handler)
    server.timeout = 15
    server.handle_request()
    server.server_close()
