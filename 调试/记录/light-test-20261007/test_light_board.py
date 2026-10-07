"""Opt-in real board light regression; never installs or restarts production."""
import getpass
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"工具/Python中间层"))
from light_test import connect_verified

password = sys.stdin.readline().rstrip("\r\n") if "--password-stdin" in sys.argv else getpass.getpass("SSH password: ")
client, fingerprint = connect_verified("127.0.0.1",12222,"root",password,
    Path(__file__).resolve().parents[1]/"SSH登录/known_hosts","192.168.101.3",
    "41eda5f2c5b00de1","CAM-41eda5f2c5b00de1")
del password
app="/tmp/instrument-light-test-331/instrument_app"
rows=[]
def run(command, expected=0):
    start=time.monotonic()
    _,out,err=client.exec_command(command,timeout=45)
    text,errors=out.read().decode(),err.read().decode()
    status=out.channel.recv_exit_status()
    row=dict(command=command,stdout=text,stderr=errors,exit_status=status,elapsed=round(time.monotonic()-start,3))
    rows.append(row)
    assert status==expected,row
    return text
snapshot="sha256sum /opt/instrument/bin/instrument_app /opt/instrument/config.json /opt/instrument/state/pair-v3.json; cat /sys/class/gpio/gpio3/value /sys/class/gpio/gpio4/value /sys/class/gpio/gpio0/value"
try:
    before=run(snapshot)
    run(f"{app} --light-test center breathe",2)
    run(f"{app} --light-test backlight slow",2)
    for mode in ("off","on","slow","fast","breathe"):
        run(f"{app} --light-test center {mode} --ground-verified --seconds 3")
        run("test ! -d /sys/kernel/config/device-tree/overlays/instrument-light-test; test ! -d /sys/class/gpio/gpio32")
    run(f"{app} --light-test backlight on --seconds 2")
    run(f"{app} --light-test backlight off")
    for target,extra in (("center","--ground-verified"),("backlight","")):
        run(f"{app} --light-test {target} on {extra} & p=$!; sleep 1; kill -TERM $p; wait $p",143)
    run(f"{app} --light-test backlight on --seconds 2 & p=$!; sleep 1; {app} --light-test backlight off --seconds 1; conflict=$?; wait $p; test $conflict -eq 1")
    after=run(snapshot)
    assert before==after,"Production binary/config/pairing/buttons changed"
    run("cat /sys/firmware/devicetree/base/pwm@ff350020/status; test ! -d /sys/class/pwm/pwmchip2; test ! -d /sys/class/gpio/gpio55")
    report=dict(result="PASS",host_key_sha256=fingerprint,identity="CAM-41eda5f2c5b00de1",
                electrical_confirmation="User replied 核对正确; no measured current/voltage numbers supplied",
                visual_acceptance="PENDING: physical light appearance, smoothness, cold boot and keys pressed",
                rows=rows)
except BaseException as error:
    report=dict(result="FAIL",error=repr(error),rows=rows)
    raise
finally:
    client.close()
    Path(__file__).with_name("board-tests.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print("PASS: board five modes, 30s timeout, TERM cleanup, conflict guard, production hashes and three key idle levels")
