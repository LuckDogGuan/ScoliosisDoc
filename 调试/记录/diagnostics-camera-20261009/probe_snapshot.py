"""Use socat to test the real RKiPC snapshot RPC without changing settings."""
from pathlib import Path
import json, struct, time
root = Path(__file__).parent
prelude = (root / 'inspect_board.py').read_text(encoding='utf-8').split('\ntry:\n')[0]
exec(compile(prelude, 'inspect_board.py', 'exec'))
channel = None
try:
    assert read('cat /proc/device-tree/serial-number')['stdout'].strip() == '41eda5f2c5b00de1'
    before = read('ls -l /video0/*.jpeg 2>/dev/null')['stdout']
    channel = transport.open_session(timeout=6); channel.settimeout(5)
    channel.exec_command('socat STDIO UNIX-CONNECT:/var/tmp/rkipc')
    def integer():
        data = b''
        while len(data) < 4:
            part = channel.recv(4-len(data))
            if not part: raise RuntimeError('RPC closed before response')
            data += part
        return struct.unpack('<i', data)[0]
    hello = integer()
    name = b'rk_take_photo' + bytes([0])
    channel.sendall(struct.pack('<i', len(name)) + name)
    result = integer(); channel.close(); channel = None
    time.sleep(3)
    after = read('ls -l /video0/*.jpeg 2>/dev/null')['stdout']
    report = {'rpc_hello': hello, 'rpc_result': result, 'before': before, 'after': after, 'changed': before != after}
    (root / 'snapshot-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    assert hello == 0 and result == 0
    assert before != after, 'FAIL: photo RPC accepted but no JPEG file produced'
finally:
    if channel: channel.close()
    transport.close()
