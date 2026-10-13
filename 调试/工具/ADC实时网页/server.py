"""Local, read-only ADB SARADC viewer. No third-party dependencies."""
import argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
SERIAL = "3253c006806f5194"
COMMAND = (
    "cat /proc/device-tree/serial-number && "
    "cat /sys/bus/iio/devices/iio:device0/name && "
    "cat /sys/bus/iio/devices/iio:device0/in_voltage_scale && "
    "cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw && "
    "cat /sys/bus/iio/devices/iio:device0/in_voltage1_raw"
)


def parse_sample(output, serial):
    # Device-tree serial is NUL-terminated and may have no trailing newline.
    fields = output.replace("\x00", "\n").split()
    if len(fields) != 5 or fields[0] != serial or fields[1] != "ff3c0000.saradc":
        raise ValueError("设备身份或 ADC 节点不匹配")
    scale = float(fields[2])
    raw = [int(fields[3]), int(fields[4])]
    if not math.isfinite(scale) or scale <= 0 or any(v < 0 or v > 1023 for v in raw):
        raise ValueError("ADC 数据超出有效范围")
    return dict(serial=serial, time=datetime.now().astimezone().isoformat(),
                scale=scale, raw=raw, voltage=[v * scale / 1000 for v in raw])


def read_sample(adb, serial):
    try:
        result = subprocess.run([adb, "-s", serial, "shell", COMMAND],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=4,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as error:
        raise ValueError("ADB 读取超时，请检查 USB 连接") from error
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[:250]
        raise ValueError("ADB 读取失败：" + detail)
    return parse_sample(result.stdout, serial)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default=r"D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe")
    parser.add_argument("--serial", default=SERIAL)
    args = parser.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/adc":
                try:
                    payload = dict(ok=True, service="luckfox-adc", **read_sample(args.adb, args.serial))
                except (OSError, ValueError) as error:
                    payload = dict(ok=False, service="luckfox-adc", error=str(error), serial=args.serial)
                body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif self.path in ("/", "/index.html"):
                body = (ROOT / "index.html").read_bytes()
                content_type = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 8766), Handler)
    print("ADC viewer: http://127.0.0.1:8766", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
