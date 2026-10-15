import hashlib
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

import paramiko
import flash_tool as tool


class WifiTests(unittest.TestCase):
    def test_reply_requires_source_identity_and_nonce(self):
        udp = MagicMock()
        udp.__enter__.return_value = udp
        packet = dict(version=3, op="hello_reply", ok=True, device_id="CAM-test",
                      host_id="wifi-flash-tool", sequence=0, nonce="nonce")
        udp.recvfrom.side_effect = [
            (b"bad-json", ("192.0.2.1", 37020)),
            (b"[]", ("192.0.2.1", 37020)),
            (json.dumps(packet).encode(), ("192.0.2.2", 37020)),
            (json.dumps(dict(packet, nonce="wrong")).encode(), ("192.0.2.1", 37020)),
            (json.dumps(packet).encode(), ("192.0.2.1", 37020)),
        ]
        with patch.object(tool.socket, "socket", return_value=udp), \
             patch.object(tool.uuid, "uuid4", return_value=MagicMock(hex="nonce")):
            result = tool.wifi_exchange("192.0.2.1", "CAM-test")
        self.assertEqual(result["device_id"], "CAM-test")
        self.assertEqual(udp.recvfrom.call_count, 5)

    def test_changed_ssh_key_refused_before_password(self):
        installer = object.__new__(tool.WifiInstaller)
        installer.address, installer.password = "192.0.2.1", "test-secret"
        installer.transport, installer.fingerprint = None, "SHA256:old-key"
        transport = MagicMock()
        transport.get_remote_server_key().asbytes.return_value = b"different-key"
        with patch.object(tool.socket, "create_connection"), patch.object(paramiko, "Transport", return_value=transport):
            with self.assertRaisesRegex(RuntimeError, "密钥改变"):
                installer.connect()
        transport.auth_password.assert_not_called()
        transport.close.assert_called_once()

    def test_wrong_identity_refused_before_staging_or_cache_write(self):
        device = dict(device_id="CAM-test", address="192.0.2.1")
        with patch.object(tool, "wifi_saved", return_value={}), \
             patch.object(tool, "wifi_exchange", return_value=dict(state={})), \
             patch.object(tool.WifiInstaller, "connect"), \
             patch.object(tool.WifiInstaller, "execute", side_effect=["serial", '{"device_id":"other"}']), \
             patch.object(tool.Installer, "__init__") as staging:
            with self.assertRaisesRegex(RuntimeError, "身份不匹配"):
                tool.WifiInstaller(device)
        staging.assert_not_called()

    def test_busy_refused_before_shared_preflight(self):
        installer = object.__new__(tool.WifiInstaller)
        installer.address, installer.expected_id = "192.0.2.1", "CAM-test"
        state = dict(phase="idle", gate_enabled=True, capture_id="", uploading_capture_id="",
                     audio_busy=False, diagnostics_active=False)
        with patch.object(tool, "wifi_exchange", return_value=dict(state=state)), \
             patch.object(tool.Installer, "preflight") as shared:
            with self.assertRaises(RuntimeError):
                installer.preflight({})
        shared.assert_not_called()

    def test_adapter_uses_no_adb_and_detaches_reboot(self):
        installer = object.__new__(tool.WifiInstaller)
        with patch.object(installer, "execute", return_value="ok") as execute, \
             patch.object(installer, "record"), patch.object(tool, "command") as adb:
            installer.adb("shell", "sync; reboot")
            self.assertIn("sleep 1; reboot", execute.call_args.args[0])
            installer.adb("push", "source", "/tmp/destination")
            self.assertEqual(execute.call_args.kwargs["upload"], "source")
            installer.adb("pull", "/tmp/source", "destination")
            self.assertEqual(execute.call_args.kwargs["download"], "destination")
            adb.assert_not_called()

    def test_real_ssh_stream_transfer_hash_and_remote_exit(self):
        # Exercise SSH channel flow control with more than a window of binary data.
        content = bytes(range(256)) * 12288
        received = []
        errors = []
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(10)
        key = paramiko.RSAKey.generate(2048)

        class Server(paramiko.ServerInterface):
            def check_auth_password(self, username, password):
                return paramiko.AUTH_SUCCESSFUL

            def check_channel_request(self, kind, chanid):
                return paramiko.OPEN_SUCCEEDED

            def check_channel_exec_request(self, channel, command):
                def respond():
                    try:
                        if command == b"upload":
                            result = bytearray()
                            while chunk := channel.recv(65536):
                                result.extend(chunk)
                            received.append(bytes(result))
                            channel.send_exit_status(0)
                        elif command == b"download":
                            channel.sendall(content)
                            channel.send_exit_status(0)
                        else:
                            channel.send_stderr(b"failed deliberately")
                            channel.send_exit_status(7)
                        channel.shutdown_write()
                    except Exception as error:
                        errors.append(error)
                threading.Thread(target=respond, daemon=True).start()
                return True

        def serve():
            try:
                sock, _ = listener.accept()
                with paramiko.Transport(sock) as transport:
                    transport.add_server_key(key)
                    transport.start_server(server=Server())
                    for _ in range(3):
                        channel = transport.accept(10)
                        if channel is None:
                            raise RuntimeError("missing test channel")
                        # Keep channels alive until the client closes the connection.
                        channels.append(channel)
                    finished.wait(10)
            except Exception as error:
                errors.append(error)

        channels, finished = [], threading.Event()
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        installer = object.__new__(tool.WifiInstaller)
        installer.transport = paramiko.Transport(socket.create_connection(listener.getsockname()))
        try:
            installer.transport.start_client(timeout=5)
            installer.transport.auth_password("root", "test")
            root = tool.HOME / ".build"
            root.mkdir(exist_ok=True)
            # Only the two explicitly named local fixture files are removed.
            folder = Path(tempfile.mkdtemp(prefix="wifi-test-", dir=root))
            source, target = folder / "source.bin", folder / "target.bin"
            try:
                source.write_bytes(content)
                installer.execute("upload", upload=source)
                installer.execute("download", download=target)
                self.assertEqual(hashlib.sha256(received[0]).digest(), hashlib.sha256(content).digest())
                self.assertEqual(target.read_bytes(), content)
                with self.assertRaisesRegex(RuntimeError, "failed deliberately"):
                    installer.execute("fail")
            finally:
                source.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                folder.rmdir()
        finally:
            installer.transport.close()
            finished.set()
            listener.close()
            thread.join(5)
        self.assertFalse(errors, errors)

    def test_wifi_gui_requires_connection_before_install(self):
        import tkinter as tk
        window = tk.Tk()
        window.withdraw()
        failures = []
        device = dict(device_id="CAM-test", address="192.0.2.1")
        connected = MagicMock(serial="test-serial")
        attempts = 0

        def exercise():
            nonlocal attempts
            try:
                def descendants(widget):
                    return [child for w in widget.winfo_children() for child in [w, *descendants(w)]]
                widgets = descendants(window)
                start = next(w for w in widgets if w.winfo_class() == "TButton" and w.cget("text") == "开始烧录")
                connect = next(w for w in widgets if w.winfo_class() == "TButton" and w.cget("text") == "配对连接")
                if not attempts:
                    self.assertIn("disabled", start.state())
                    self.assertNotIn("disabled", connect.state())
                    connect.invoke()
                attempts += 1
                if "disabled" in start.state():
                    if attempts > 50:
                        raise AssertionError("Wi-Fi GUI connection did not complete")
                    window.after(30, exercise)
                    return
                self.assertTrue(connected.close.called)
                labels = [str(window.getvar(w.cget("textvariable"))) for w in widgets
                          if w.winfo_class() == "TLabel" and w.cget("textvariable")]
                self.assertIn("已连接 CAM-test", labels)
            except Exception as error:
                failures.append(error)
            for callback in window.tk.call("after", "info"):
                window.after_cancel(callback)
            window.destroy()

        window.after(50, exercise)
        with patch("tkinter.Tk", return_value=window), patch.object(tool, "wifi_devices", return_value=[device]), \
             patch.object(tool, "WifiInstaller", return_value=connected), patch("tkinter.messagebox.showerror") as errors:
            tool.gui(tool.RELEASES / "3.3.11/instrument-v3.3.11.tar.gz", wifi=True)
        if failures:
            raise failures[0]
        errors.assert_not_called()


if __name__ == "__main__":
    unittest.main()
