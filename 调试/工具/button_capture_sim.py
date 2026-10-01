"""PC-only input injector for the firmware's opt-in LwBTN simulation file."""
import argparse
import datetime
import json
import pathlib
import socket
import subprocess
import time
import uuid

ADB = r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe'
SERIAL = '3253c006806f5194'
SIM_PATH = '/opt/instrument/state/buttons.sim'


def write_mask(mask, adb=ADB, serial=SERIAL):
    if mask not in range(8):
        raise ValueError('mask must be 0..7')
    subprocess.run(
        [adb, '-s', serial, 'shell',
         f"printf '%s\\n' {mask} > {SIM_PATH}.tmp && mv {SIM_PATH}.tmp {SIM_PATH}"],
        check=True, capture_output=True, timeout=10,
    )


def snapshot(address, device_id):
    nonce = uuid.uuid4().hex
    request = dict(version=3, op='hello_query', device_id=device_id,
                   host_id='button-sim-observer', sequence=1, nonce=nonce)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.settimeout(1)
        udp.sendto(json.dumps(request).encode(), (address, 37020))
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            raw, source = udp.recvfrom(4097)
            if len(raw) > 4096 or source != (address, 37020):
                continue
            reply = json.loads(raw)
            if all(reply.get(k) == request[k] for k in
                   ('version', 'device_id', 'sequence', 'nonce')) and reply.get('op') == 'hello_reply':
                return {k: reply.get(k) for k in
                        ('device_id', 'boot_id', 'phase', 'gate_enabled', 'capture_id',
                         'wifi_state', 'paired_host_id', 'metrics')}
        raise TimeoutError('no matching V3 snapshot')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mask', type=int, choices=range(8), required=True,
                        help='pressed bits: left=1, middle=2, right=4; 0 releases all')
    parser.add_argument('--hold-ms', type=int, help='release all after this interval')
    parser.add_argument('--adb', default=ADB)
    parser.add_argument('--serial', default=SERIAL)
    parser.add_argument('--address', default='192.168.101.3')
    parser.add_argument('--device-id', default='CAM-000123')
    parser.add_argument('--log', type=pathlib.Path)
    args = parser.parse_args()
    if args.hold_ms is not None and not 0 <= args.hold_ms <= 90000:
        parser.error('--hold-ms must be 0..90000')

    def record(mask, observe=True):
        at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        started = time.monotonic()
        write_mask(mask, args.adb, args.serial)
        state = {}
        if observe:
            try:
                state = snapshot(args.address, args.device_id)
            except (OSError, ValueError, TimeoutError) as error:
                state = {'observation_error': str(error)}
        entry = dict(time_utc=at, source='pc_adb_simulation', mask=mask,
                     command_elapsed_ms=round(1000 * (time.monotonic() - started)),
                     snapshot=state)
        line = json.dumps(entry, ensure_ascii=False)
        print(line)
        if args.log:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            with args.log.open('a', encoding='utf-8') as output:
                output.write(line + '\n')

    record(args.mask, observe=args.hold_ms is None)
    if args.hold_ms is not None:
        try:
            time.sleep(args.hold_ms / 1000)
        finally:
            record(0)


if __name__ == '__main__':
    main()
