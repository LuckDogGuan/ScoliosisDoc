"""PC-only three-button input monitor. Run: python button_monitor.py."""
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ADB = r"D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe"
LOG = Path(__file__).parents[1] / "记录" / "三键电平_2026-09-30.jsonl"
STATE = {"values": None, "baseline": None, "error": "等待读取", "updated": 0}
LOCK = threading.Lock()
HTML = """<!doctype html><meta charset=utf-8><title>下位机三键实测</title>
<style>body{font:24px sans-serif;background:#f4f6fa;color:#17243b;margin:40px}main{display:flex;gap:24px}.key{flex:1;background:white;border:4px solid #cad3df;border-radius:20px;padding:30px;text-align:center}.changed{border-color:#ee8b18;background:#fff1d8}b{display:block;font-size:48px;margin:28px}small{font-size:18px}#info{margin-top:28px}</style>
<h1>下位机三个按键 · 实时状态</h1><p>低电平有效：0 = 按下（橙色），1 = 松开。左 A3、中 A4、右 A0。</p>
<main><div class=key><h2>左键</h2>GPIO0_A3 · GPIO 3<b>—</b><small>等待读取</small></div><div class=key><h2>中键</h2>GPIO0_A4 · GPIO 4<b>—</b><small>等待读取</small></div><div class=key><h2>右键</h2>GPIO0_A0 · GPIO 0<b>—</b><small>等待读取</small></div></main><p id=info></p>
<script>async function refresh(){try{let s=await(await fetch('/state',{cache:'no-store'})).json();document.querySelectorAll('.key').forEach((e,i)=>{let ok=s.values&&Date.now()/1000-s.updated<3;e.querySelector('b').textContent=ok?(s.values[i]===0?'按下':'松开'):'未知';let pressed=ok&&s.values[i]===0;e.classList.toggle('changed',pressed);e.querySelector('small').textContent=ok?('电平 '+s.values[i]):'读取失败';});document.querySelector('#info').textContent=s.error||('更新时间：'+new Date(s.updated*1000).toLocaleTimeString()+' · 三键均为输入，未触发录像或配对');}catch(e){document.querySelectorAll('.key').forEach(e=>{e.querySelector('b').textContent='未知';e.classList.remove('changed')});document.querySelector('#info').textContent='监视服务断开';}setTimeout(refresh,250)}refresh();</script>"""


def sample():
    previous = None
    while True:
        try:
            result = subprocess.run([ADB, "-s", "3253c006806f5194", "shell",
                "cat /sys/class/gpio/gpio3/value /sys/class/gpio/gpio4/value /sys/class/gpio/gpio0/value"],
                capture_output=True, text=True, timeout=2, check=True)
            values = result.stdout.split()
            if len(values) != 3 or any(v not in ("0", "1") for v in values):
                raise ValueError("GPIO 返回值无效")
            values = list(map(int, values))
            with LOCK:
                STATE.update(values=values, error="", updated=time.time())
                if STATE["baseline"] is None:
                    STATE["baseline"] = values[:]
            if values != previous:
                event = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "left_A3": values[0], "center_A4": values[1], "right_A0": values[2]}
                with LOG.open("a", encoding="utf-8") as output:
                    output.write(json.dumps(event, ensure_ascii=False) + "\n")
                print(event, flush=True)
                previous = values
        except (subprocess.SubprocessError, OSError, ValueError) as error:
            with LOCK:
                STATE.update(values=None, error=str(error), updated=time.time())
        time.sleep(0.08)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/state":
            with LOCK:
                body = json.dumps(STATE).encode()
            content_type = "application/json"
        else:
            body = HTML.encode("utf-8")
            content_type = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    threading.Thread(target=sample, daemon=True).start()
    print("BUTTON_MONITOR http://127.0.0.1:8766", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
