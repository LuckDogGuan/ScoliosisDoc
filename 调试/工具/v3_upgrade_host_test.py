"""Exercise the actual C coordinator; isolated host paths, no board deployment."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time

SOURCE = Path('/home/guanjx/luckfox/Scoliosis')
root = Path(tempfile.mkdtemp(prefix='v3-independent-'))
port = 37021
binary = root / 'instrument_review'
cflags = ("-std=c11 -D_POSIX_C_SOURCE=200809L -D_DEFAULT_SOURCE -Wall -Wextra -Werror -O2 "
          "-Iinclude -Ithird_party/cjson -Ithird_party/lwbtn/include "
          f"-DINSTRUMENT_ROOT='\"{root}/state-root\"' -DDISCOVER_PORT={port}")
subprocess.run(['make', 'CC=gcc', f'TARGET={binary}', f'CFLAGS={cflags}'], cwd=SOURCE, check=True)
config = json.loads((SOURCE / 'config.example.json').read_text())
config['pc_base_url'] = 'http://127.0.0.1:49159'
config_file = root / 'config.json'
config_file.write_text(json.dumps(config))
button = root / 'buttons'
button.write_text('0\n')
env = {**os.environ, 'INSTRUMENT_HOST_TEST': '1', 'INSTRUMENT_BUTTON_FILE': str(button)}
log = (root / 'runtime.log').open('wb')
process = subprocess.Popen([str(binary), str(config_file)], cwd=SOURCE, env=env, stdout=log, stderr=log)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(1)
host = 'review-host'
device = config['device_id']
boot = None
sequence = 0
checks = []

def packet(op, **fields):
    global sequence
    sequence += 1
    return dict(version=3, op=op, device_id=device, host_id=host, sequence=sequence,
                nonce=secrets.token_hex(16), **({'boot_id': boot} if boot else {}), **fields)

def send(request):
    sock.sendto(json.dumps(request).encode(), ('127.0.0.1', port))
    while True:
        reply = json.loads(sock.recv(4096))
        if reply.get('nonce') == request['nonce']:
            assert reply['sequence'] == request['sequence'] and reply['device_id'] == device
            return reply

def ask(op, **fields):
    return send(packet(op, **fields))

def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)
    print('PASS', name, flush=True)

try:
    for attempt in range(20):
        try:
            hello = ask('hello_query')
            boot = hello['boot_id']
            break
        except socket.timeout:
            time.sleep(.05)
    else:
        raise AssertionError('runtime startup')
    check('startup gate disabled', not hello['gate_enabled'])
    check('pair outside physical window rejected', not ask('pair_request', txn_id='review-txn', http_port=49159)['ok'])
    time.sleep(.08)
    button.write_text('2\n')
    time.sleep(3.2)
    button.write_text('0\n')
    time.sleep(.08)
    check('physical input opens pair window', ask('hello_query')['pair_window_remaining_ms'] > 0)
    check('pair request', ask('pair_request', txn_id='review-txn', http_port=49159)['ok'])
    check('pair commit', ask('pair_commit', txn_id='review-txn', http_port=49159)['ok'])
    check('idempotent committed pair request', ask('pair_request', txn_id='review-txn', http_port=49159)['ok'])
    check('idempotent committed pair commit', ask('pair_commit', txn_id='review-txn', http_port=49159)['ok'])
    time.sleep(.2)
    check('saved pair recovery allowed', ask('paired_discover', txn_id='review-txn')['ok'])
    check('foreign pair recovery rejected', not ask('paired_discover', txn_id='wrong')['ok'])
    check('volume save accepted', ask('volume_set', volume=18, operation_id='audio-one')['ok'])
    time.sleep(.2)
    hello = ask('hello_query')
    check('volume saved and acknowledged', hello['volume'] == 18 and hello['audio_operation_result'] == 0)
    check('volume test accepted', ask('volume_test', volume=9, operation_id='audio-two')['ok'])
    time.sleep(.2)
    check('audition restores saved volume', ask('hello_query')['volume'] == 18 and json.loads(config_file.read_text())['audio']['volume'] == 18)
    original_config = config_file.read_text()
    config_file.write_text('invalid config')
    check('volume persistence failure accepted for asynchronous result', ask('volume_set', volume=16, operation_id='audio-failed')['ok'])
    time.sleep(.2)
    hello = ask('hello_query')
    check('volume persistence failure restores old value and reports failure', hello['volume'] == 18 and hello['audio_operation_result'] != 0)
    config_file.write_text(original_config)
    request = packet('capture_enable', gate_id='gate-one', ttl_ms=6000)
    check('enable gate one', send(request)['ok'])
    check('prepare preassigned capture', ask('capture_prepare', gate_id='gate-one', capture_id=device+'-review-a')['ok'])
    check('stop gate one', ask('capture_disable', gate_id='gate-one')['ok'])
    check('replayed old enable rejected', not send(request)['ok'])
    check('newer renew cannot revive stopped gate', not ask('capture_renew', gate_id='gate-one', ttl_ms=6000)['ok'])
    check('stopped gate remains closed', not ask('hello_query')['gate_enabled'])
    check('new gate permits new enable', ask('capture_enable', gate_id='gate-two', ttl_ms=200)['ok'])
    time.sleep(.3)
    check('expired renew cannot revive', not ask('capture_renew', gate_id='gate-two', ttl_ms=6000)['ok'])
    check('expired gate remains closed', not ask('hello_query')['gate_enabled'])
    stale_boot = packet('capture_enable', gate_id='gate-three', ttl_ms=6000)
    stale_boot['boot_id'] = 'stale-boot'
    check('wrong boot mutation rejected', not send(stale_boot)['ok'])
    hello = ask('hello_query')
    check('control sequence available for computer restart', hello['control_sequence'] > 0)
    original_boot = boot
    process.terminate()
    process.wait(timeout=10)
    process = subprocess.Popen([str(binary), str(config_file)], cwd=SOURCE, env=env, stdout=log, stderr=log)
    time.sleep(.2)
    hello = ask('hello_query')
    boot = hello['boot_id']
    check('firmware reboot new boot id', boot != original_boot)
    check('firmware reboot closes gate and retains pairing', not hello['gate_enabled'] and hello['paired_host_id'] == host)
    check('pair transaction recoverable after firmware reboot', ask('pair_commit', txn_id='review-txn', http_port=49159)['ok'])
    sock.close()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.2', 0))
    sock.settimeout(1)
    check('changed computer IP initially denied', not ask('capture_enable', gate_id='gate-ip', ttl_ms=6000)['ok'])
    check('same transaction reconfirm request at changed IP', ask('pair_request', txn_id='review-txn', http_port=49159)['ok'])
    check('same transaction reconfirm commit at changed IP', ask('pair_commit', txn_id='review-txn', http_port=49159)['ok'])
    check('changed computer IP accepted after reconfirm', ask('capture_enable', gate_id='gate-ip', ttl_ms=6000)['ok'])
    check('old gate stop cannot disable new gate', not ask('capture_disable', gate_id='gate-two')['ok'] and ask('hello_query')['gate_enabled'])
    check('matching new gate stop accepted', ask('capture_disable', gate_id='gate-ip')['ok'])
    button.write_text('2\n')
    time.sleep(3.2)
    check('middle alone locally unpairs', ask('hello_query')['paired_host_id'] == '')
    time.sleep(.2)
    check('holding middle does not reopen window', ask('hello_query')['pair_window_remaining_ms'] == 0)
    button.write_text('0\n')
    time.sleep(.08)
    hello = ask('hello_query')
    check('unpair clears host and retains event', hello['paired_host_id'] == '' and bool(hello['unpair_event_id']))
    check('old host capture denied after unpair', not ask('capture_enable', gate_id='gate-four', ttl_ms=6000)['ok'])
    event = hello['unpair_event_id']
    process.terminate()
    process.wait(timeout=10)
    process = subprocess.Popen([str(binary), str(config_file)], cwd=SOURCE, env=env, stdout=log, stderr=log)
    time.sleep(.2)
    hello = ask('hello_query')
    boot = hello['boot_id']
    check('offline unpair event survives reboot', hello['unpair_event_id'] == event and hello['paired_host_id'] == '')
    check('unpair event ack', ask('event_ack', event_id=event)['ok'])
    check('unpair event ack persisted clear', ask('hello_query')['unpair_event_id'] == '')
finally:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    log.close()
    sock.close()
    result = {'passed': checks, 'temp_root': str(root), 'source': str(SOURCE),
              'scope': 'actual C host coordinator and LwBTN; no RKiPC, no board, no Flutter mock'}
    (root / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
