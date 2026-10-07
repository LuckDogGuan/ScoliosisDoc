"""Small regression checks. Hardware acceptance is deliberately separate."""
from __future__ import annotations
import json
import queue
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
import uvc_support as u


def run_checks(core):
    checks = 0
    tallies = [core.Tally() for _ in core.KEYS]
    core.apply_sample(tallies, [0, 1, 1], 1.0, "first")
    core.apply_sample(tallies, [1, 1, 1], 2.0, "release")
    assert tallies[0].presses == tallies[0].releases == 0, "held at start must not pass"
    core.apply_sample(tallies, [0, 0, 0], 3.0, "pressed")
    core.apply_sample(tallies, [0, 0, 0], 3.5, "held")
    assert core.passed(tallies) == [], "press alone must not pass"
    core.apply_sample(tallies, [1, 1, 1], 4.0, "released")
    assert [t.presses for t in tallies] == [1, 1, 1]
    assert [t.releases for t in tallies] == [1, 1, 1]
    assert [t.hold_ms for t in tallies] == [1000, 1000, 1000]
    assert core.verdict(tallies) == "三个按键全部通过"
    checks += 1

    fake = lambda text: subprocess.CompletedProcess([], 0, text, "")
    with patch.object(core, "invoke_adb", return_value=fake(
        "board-a device transport_id:1\n192.168.1.2:5555 device usb:fake\nadb-remote._adb-tls-connect._tcp device\nboard-b offline\n")), patch.object(core, "run", return_value=fake("BOARD-A\n")):
        assert core.list_devices() == ["board-a"]
    checks += 1
    with patch.object(core, "invoke_adb", return_value=fake("GADGET=rockchip\nFUNCS=uvc.gs1\nLINKED=1\nFEEDER=1\nUDC=configured\n")) as called, patch.object(core, "windows_cameras", return_value=[]), patch.object(core, "log"):
        lines = core.probe_uvc("board-a")
        assert called.call_args.args == ("-s", "board-a", "shell", core.PROBE_SCRIPT)
        assert any("实际读帧" in line for line in lines)
    checks += 1

    devices = [{"name": "Integrated Camera", "path": "usb#vid_04f2&pid_b875#local#", "index": 0},
               {"name": "ISG1321 USB Camera", "path": "usb#vid_2207&pid_0016#board-a#global", "index": 1},
               {"name": "ISG1321 USB Camera", "path": "usb#vid_2207&pid_0016#board-b#global", "index": 2}]
    assert u.target_cameras(devices, "board-a") == [devices[1]]
    assert u.camera_serial(devices[2]) == "board-b"
    assert u.target_cameras(devices, "missing") == []
    checks += 1
    manifest = {"board_libraries": {"LIBROCKIT": "rockit", "LIBRKAIQ": "aiq"}}
    board = {"MODEL": "Luckfox Pico Zero", "ARCH": "armv7l", "SENSORS": "mia1321", "UVC": "yes", "IQ": "yes", "LIBROCKIT": "rockit", "LIBRKAIQ": "aiq"}
    u.validate_board(board, manifest)
    for key, bad in (("MODEL", "other"), ("ARCH", "aarch64"), ("SENSORS", ""), ("UVC", "no"), ("IQ", "no"), ("LIBRKAIQ", "other")):
        try:
            u.validate_board({**board, key: bad}, manifest)
        except RuntimeError:
            pass
        else:
            raise AssertionError("accepted incompatible board: " + key)
    checks += 1

    with patch.object(u, "shell") as run:
        busy = {"ok": True, "phase": "recording", "gate_enabled": True, "capture_id": "cap", "uploading_capture_id": "", "audio_busy": False}
        def reply(core, serial, script, timeout=15):
            if "pidof" == script[:5]: return "100"
            if script.startswith("cat "): return '{"device_id":"instrument"}'
            if "/udp_query " in script:
                import shlex
                request = json.loads(shlex.split(script.split("; ", 1)[1])[-1])
                return json.dumps({**busy, "nonce": request["nonce"], "device_id": "instrument"})
            raise AssertionError("unexpected command: " + script)
        run.side_effect = reply
        try:
            u.stop_idle_instrument(core, "board-a")
        except RuntimeError:
            pass
        else:
            raise AssertionError("must not stop recording instrument")
        assert not any("killall" in call.args[2] for call in run.call_args_list)
    checks += 1

    import tkinter as tk
    with tempfile.TemporaryDirectory() as temporary, patch.object(core, "REPORT_ROOT", Path(temporary)), patch.object(u.App, "reload_devices"):
        root = tk.Tk(); root.withdraw()
        app = u.App(root, core)
        assert len(app.key_cards) == 3
        app.reset_session("board-a")
        app.board = {"serial": "board-a", "SENSORS": "mia1321"}
        app.camera_result = {"status": "frames_received", "serial": "board-a"}
        app.tallies = tallies
        app.on_save_report()
        reports = list(Path(temporary).glob("*/*.json"))
        assert len(reports) == 1
        assert reports[0].with_suffix(".txt").is_file()
        assert json.loads(reports[0].read_text(encoding="utf-8"))["serial"] == "board-a"
        app.reset_session("board-b")
        assert not app.board and not app.camera_result and not core.passed(app.tallies)
        # Late events from an old board cannot contaminate the new report.
        app.events.put((app.generation - 1, "keys", ([0, 0, 0], 99, "old")))
        app.tick()
        assert app.levels is None
        app.on_keys_stop()
        assert all(str(state["text"]) == "未知" for _, state, _ in app.key_cards)
        core.apply_sample(app.tallies, [1, 1, 1], 100, "idle")
        core.apply_sample(app.tallies, [0, 1, 1], 101, "down")
        app.on_keys_stop()
        core.apply_sample(app.tallies, [1, 1, 1], 102, "after-disconnect")
        assert app.tallies[0].releases == 0, "an interrupted press must not pass after reconnect"
        # An open/read that never returns is terminated and old pixels cleared.
        proc = Mock(); proc.is_alive.return_value = True
        app.camera_process, app.camera_stop, app.camera_queue = proc, Mock(), Mock()
        app.camera_queue.get_nowait.side_effect = queue.Empty
        app.capture_deadline = 0
        with patch.object(core, "log"):
            app.tick()
        proc.terminate.assert_called_once()
        assert app.camera_process is None and app.camera_result["status"] == "disconnected_or_timeout"
        app.on_close()
    checks += 1
    print(f"PASS {checks} regression groups: keys, USB filtering, probe args, identity, compatibility, busy guard, UI lifecycle")
