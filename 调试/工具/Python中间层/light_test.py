"""Bounded light diagnostic through the existing SSH profile and pinned known_hosts."""
import argparse
import base64
import getpass
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time
import paramiko

def connect_verified(address, port, user, password, known_hosts, host_key_name, serial, device_id):
    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    # ADB SSH forwarding can reuse the already recorded board key; never trust a new key automatically.
    if host_key_name:
        keys = client.get_host_keys().lookup(host_key_name)
        if not keys:
            raise ValueError("No saved host key for " + host_key_name)
        endpoint = address if port == 22 else f"[{address}]:{port}"
        for kind, key in keys.items():
            client.get_host_keys().add(endpoint, kind, key)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(address, port=port, username=user, password=password, timeout=5,
                       banner_timeout=5, auth_timeout=5, look_for_keys=False, allow_agent=False)
        command = ("cat /proc/device-tree/serial-number; printf '\\n'; "
                   "cat /opt/instrument/config.json; printf '\\n'; "
                   "cat /opt/instrument/state/active-v3.json; printf '\\n'; "
                   "find /opt/instrument/capture/writing -type f")
        _, out, err = client.exec_command(command, timeout=10)
        text, errors = out.read().decode().replace("\x00", ""), err.read().decode()
        if out.channel.recv_exit_status() or errors:
            raise ValueError("Identity/idle read failed: " + errors)
        actual_serial, data = text.strip().split("\n", 1)
        decoder = json.JSONDecoder()
        config, end = decoder.raw_decode(data.lstrip())
        remainder = data.lstrip()[end:].lstrip()
        active, end = decoder.raw_decode(remainder)
        if actual_serial.strip() != serial or config.get("device_id") != device_id:
            raise ValueError("Board serial or application device ID mismatch")
        if active or remainder[end:].strip():
            raise ValueError("Board has an active capture/gate or unfinished writing; light test refused")
        key = client.get_transport().get_remote_server_key()
        fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        return client, fingerprint
    except BaseException:
        client.close()
        raise

def command_for(args):
    if not 1 <= args.seconds <= 300:
        raise ValueError("seconds must be 1..300")
    if args.target == "backlight" and args.mode not in ("off", "on"):
        raise ValueError("backlight supports off/on only")
    if args.target == "center" and not args.ground_verified:
        raise ValueError("GPIO32 return must be verified before center testing")
    if not args.app.startswith("/") or "\n" in args.app:
        raise ValueError("app must be an absolute board path")
    parts = [args.app, "--light-test", args.target, args.mode, "--seconds", str(args.seconds)]
    if args.ground_verified:
        parts.append("--ground-verified")
    if args.active_low:
        parts.append("--active-low")
    return " ".join(shlex.quote(part) for part in parts)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", default="root")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--known-hosts", type=Path,
                        default=Path(__file__).resolve().parents[2]/"记录/SSH登录/known_hosts")
    parser.add_argument("--host-key-name", help="Existing saved host name for an ADB SSH tunnel")
    parser.add_argument("--password-stdin", action="store_true")
    parser.add_argument("--app", default="/opt/instrument/bin/instrument_app")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--ground-verified", action="store_true")
    parser.add_argument("--active-low", action="store_true")
    parser.add_argument("--log", type=Path,
                        default=Path(__file__).resolve().parents[2]/"记录/light-test-20261007/python-light.jsonl")
    parser.add_argument("target", choices=("center", "backlight"))
    parser.add_argument("mode", choices=("off", "on", "slow", "fast", "breathe"))
    args = parser.parse_args()
    record = dict(local_time=time.strftime("%Y-%m-%dT%H:%M:%S%z"), serial=args.serial,
                  device_id=args.device_id, address=args.address, port=args.port)
    client = None
    result = 1
    try:
        command = command_for(args)
        password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("SSH password (not saved): ")
        try:
            client, fingerprint = connect_verified(args.address, args.port, args.user, password,
                                                    args.known_hosts, args.host_key_name, args.serial, args.device_id)
        finally:
            del password
        record.update(host_key_sha256=fingerprint, command=command)
        _, out, err = client.exec_command(command, timeout=args.seconds+15)
        # Output is only two bounded diagnostic lines, so no large stream buffering.
        record["stdout"], record["stderr"] = out.read().decode(), err.read().decode()
        result = out.channel.recv_exit_status()
        record["exit_status"] = result
    except KeyboardInterrupt:
        # The remote program catches HUP/TERM and has its own deadline even if SSH is lost.
        record["error"] = "Interrupted; remote test will stop by its own deadline"
        result = 130
    except Exception as error:
        record["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if client:
            client.close()
        record["ok"] = result == 0
        args.log.parent.mkdir(parents=True,exist_ok=True)
        with args.log.open("a",encoding="utf-8") as file:
            file.write(json.dumps(record,ensure_ascii=False)+"\n")
        print(json.dumps(record,ensure_ascii=False,indent=2))
    return result

if __name__ == "__main__":
    raise SystemExit(main())
