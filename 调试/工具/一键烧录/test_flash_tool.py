import copy
import unittest
from unittest.mock import patch
import flash_tool as tool


class SafetyTests(unittest.TestCase):
    def test_one_device_is_automatic_two_require_selection(self):
        self.assertEqual(tool.choose_serial([("a", "device")]), "a")
        with self.assertRaises(RuntimeError):
            tool.choose_serial([("a", "device"), ("b", "device")])
        self.assertEqual(tool.choose_serial([("a", "device"), ("b", "device")], "b"), "b")
        for devices in ([], [("a", "unauthorized")], [("a", "offline")], [("192.0.2.1:5555", "device")]):
            with self.assertRaises(RuntimeError):
                tool.choose_serial(devices)

    def test_each_busy_flag_and_missing_state_refuses_install(self):
        state = dict(phase="idle", gate_enabled=False, capture_id="", uploading_capture_id="",
                     audio_busy=False, diagnostics_active=False)
        tool.validate_idle(state)
        for key in state:
            busy = copy.copy(state)
            busy[key] = "recording" if key == "phase" else True
            with self.assertRaises(RuntimeError):
                tool.validate_idle(busy)
            missing = copy.copy(state)
            del missing[key]
            with self.assertRaises(RuntimeError):
                tool.validate_idle(missing)
        with self.assertRaises(RuntimeError):
            tool.validate_idle(dict(state, pair_window_remaining_ms=100))

    def test_remote_shell_exit_is_not_adb_exit(self):
        installer = object.__new__(tool.Installer)
        with patch.object(installer, "adb", return_value="__FLASH_EXIT__=0"):
            self.assertEqual(installer.shell("true"), "")
        with patch.object(installer, "adb", return_value="abc\n__FLASH_EXIT__=0"):
            self.assertEqual(installer.shell("echo abc"), "abc")
        for response in ("cat: missing\n__FLASH_EXIT__=1", "disconnected"):
            with patch.object(installer, "adb", return_value=response), self.assertRaises(RuntimeError):
                installer.shell("false")

    def test_wrong_serial_refused_before_config_or_writes(self):
        installer = object.__new__(tool.Installer)
        installer.serial = "expected"
        installer.notify = lambda text: None
        with patch.object(installer, "shell", return_value="other") as shell, self.assertRaises(RuntimeError):
            installer.preflight({})
        self.assertEqual(shell.call_count, 1)

    def test_package_corruption_and_version_order(self):
        from pathlib import Path
        from tempfile import mkdtemp
        import hashlib, io, tarfile
        # Small local test fixture only; no external or board files.
        build = Path(__file__).parent / ".build"
        build.mkdir(exist_ok=True)
        root = Path(mkdtemp(prefix="test-", dir=build))
        try:
            for version in ("3.3.9", "3.3.10"):
                folder = root / version
                folder.mkdir()
                package = folder / f"instrument-v{version}.tar.gz"
                entries = {"VERSION": version.encode(), "instrument_app": b"app", "deploy/RkLunch.sh": b"startup",
                           "config.example.json": b'{}', "deploy/install_bundle.sh": b'installer'}
                entries["SHA256SUMS"] = "".join(hashlib.sha256(data).hexdigest() + "  ./" + name + "\n"
                                               for name, data in entries.items()).encode()
                with tarfile.open(package, "w:gz") as archive:
                    for name, data in entries.items():
                        info = tarfile.TarInfo("instrument-v" + version + "/" + name)
                        info.size = len(data)
                        archive.addfile(info, io.BytesIO(data))
                (folder / "SHA256SUMS").write_text(hashlib.sha256(package.read_bytes()).hexdigest() + "  " + package.name)
            self.assertEqual(tool.latest_package(root)["version"], "3.3.10")
            renamed = root / "任意文件名.tar.gz"
            renamed.write_bytes(package.read_bytes())
            self.assertEqual(tool.read_package(renamed)["version"], "3.3.10")
            package.write_bytes(b"corrupt")
            with self.assertRaises(RuntimeError):
                tool.latest_package(root)
        finally:
            (root / "任意文件名.tar.gz").unlink(missing_ok=True)
            for version in ("3.3.9", "3.3.10"):
                folder = root / version
                (folder / f"instrument-v{version}.tar.gz").unlink(missing_ok=True)
                (folder / "SHA256SUMS").unlink(missing_ok=True)
                folder.rmdir()
            root.rmdir()

    def test_selected_older_package_keeps_its_own_version(self):
        older = tool.RELEASES / "3.3.5/instrument-v3.3.5.tar.gz"
        package = tool.read_package(older)
        self.assertEqual(package["version"], "3.3.5")
        self.assertEqual(package["path"], older)
        self.assertNotEqual(package["version"], tool.latest_package()["version"])

    def test_real_339_package_transfer_hash_and_installer_files(self):
        import hashlib
        import tarfile
        package = tool.read_package(tool.RELEASES / "3.3.9/instrument-v3.3.9.tar.gz")
        self.assertEqual(package["sha256"], hashlib.sha256(package["path"].read_bytes()).hexdigest())
        self.assertNotIn("/opt/instrument/sounds/stability-voice-manifest.json", package["installed_hashes"])
        self.assertIn("/opt/instrument/sounds/boot_ready.wav", package["installed_hashes"])
        self.assertEqual(sum(path.endswith(".wav") for path in package["installed_hashes"]), 22)
        with tarfile.open(package["path"]) as archive:
            installer = archive.extractfile(package["prefix"] + "/deploy/install_bundle.sh").read().decode()
        self.assertIn("for source in sounds/*.wav", installer)

    def test_post_boot_audio_wait_is_bounded_and_other_guards_stay_strict(self):
        state = dict(phase="idle", gate_enabled=False, capture_id="", uploading_capture_id="",
                     audio_busy=False, diagnostics_active=False)
        installer = object.__new__(tool.Installer)
        with patch.object(installer, "hello", side_effect=[dict(state, audio_busy=True), state]), \
             patch.object(installer, "shell", side_effect=['{}', '']), patch.object(tool.time, "sleep"):
            self.assertEqual(installer.idle(wait_startup_audio=True), state)
        with patch.object(installer, "hello", return_value=dict(state, audio_busy=True)), self.assertRaises(RuntimeError):
            installer.idle()
        with patch.object(installer, "hello", return_value=dict(state, audio_busy=True)), \
             patch.object(tool.time, "monotonic", side_effect=[0, 16]), self.assertRaises(RuntimeError):
            installer.idle(wait_startup_audio=True)
        for key in ("gate_enabled", "capture_id", "uploading_capture_id", "diagnostics_active"):
            with patch.object(installer, "hello", return_value=dict(state, audio_busy=True, **{key: True})), \
                 self.assertRaises(RuntimeError):
                installer.idle(wait_startup_audio=True)

    def test_gui_selects_files_and_displays_package_version(self):
        import tkinter as tk
        window = tk.Tk()
        window.withdraw()
        failures = []
        def exercise():
            try:
                widgets = window.winfo_children()
                select = next(w for w in widgets if w.winfo_class() == "TButton" and w.cget("text") == "选择压缩包")
                start = next(w for w in widgets if w.winfo_class() == "TButton" and w.cget("text") == "开始烧录")
                self.assertIn("disabled", start.state())
                for version in ("3.3.5", "3.3.7", "3.3.9"):
                    with patch("tkinter.filedialog.askopenfilename", return_value=str(tool.RELEASES / version / f"instrument-v{version}.tar.gz")):
                        select.invoke()
                    labels = [str(window.getvar(w.cget("textvariable"))) for w in widgets
                              if w.winfo_class() == "TLabel" and w.cget("textvariable")]
                    self.assertIn("版本：" + version, labels)
                    self.assertNotIn("disabled", start.state())
                with patch("tkinter.filedialog.askopenfilename", return_value=str(tool.HOME / "missing.tar.gz")), patch("tkinter.messagebox.showerror"):
                    select.invoke()
                self.assertIn("disabled", start.state())
            except Exception as error:
                failures.append(error)
            finally:
                window.destroy()
        window.after(100, exercise)
        with patch("tkinter.Tk", return_value=window):
            tool.gui()
        if failures:
            raise failures[0]


if __name__ == "__main__":
    unittest.main()
