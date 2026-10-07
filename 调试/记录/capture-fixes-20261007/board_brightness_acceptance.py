"""Real board PWM readback; does not equate duty readback with visible brightness."""
import json, secrets, socket, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SERIAL='41eda5f2c5b00de1'; DEVICE='CAM-'+SERIAL; ADDRESS='192.168.101.4'
def shell(cmd):
    return subprocess.check_output(['adb','-s',SERIAL,'shell',cmd],timeout=15).decode().replace('\x00','').replace('\r','').strip()
assert shell('cat /proc/device-tree/serial-number')==SERIAL
assert json.loads(shell('cat /opt/instrument/config.json'))['device_id']==DEVICE
host=json.loads(shell('cat /opt/instrument/state/pair-v3.json'))['host_id']
sequence=0;boot=None
def ask(op,**fields):
    global sequence,boot
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(4);sequence+=1;nonce=secrets.token_hex(8)
        packet=dict(version=3,op=op,device_id=DEVICE,host_id=host,sequence=sequence,nonce=nonce,**fields)
        if boot:packet['boot_id']=boot
        sock.sendto(json.dumps(packet).encode(),(ADDRESS,37020))
        while True:
            answer=json.loads(sock.recv(4096))
            if answer.get('nonce')==nonce:
                assert answer['device_id']==DEVICE
                if op=='hello_query':
                    boot=answer['boot_id'];sequence=max(sequence,answer['control_sequence'])
                return answer
hello=ask('hello_query')
assert not hello['gate_enabled'] and not hello['diagnostics_active'] and hello['phase']=='idle'
assert not hello['uploading_capture_id']
assert 'backlight_brightness' in hello['capabilities']
token='acceptance-'+secrets.token_hex(8); rows=[]
try:
    assert ask('diagnostics_start',diagnostics_id=token,ttl_ms=5000)['ok']
    for percent in [0,25,50,75,100]:
        assert ask('diagnostics_renew',diagnostics_id=token,ttl_ms=5000)['ok']
        reply=ask('diagnostics_backlight',diagnostics_id=token,brightness=percent)
        assert reply['ok'] and reply['brightness']==percent,reply
        output=shell('for chip in /sys/class/pwm/pwmchip*; do case "$(readlink "$chip/device")" in *ff490030.pwm*) echo "$chip"; cat "$chip/pwm0/period" "$chip/pwm0/duty_cycle" "$chip/pwm0/enable";; esac; done')
        if percent:
            parts=output.splitlines(); assert [int(p) for p in parts[-3:]]==[1000000,percent*10000,1],output
        else:assert shell('cat /sys/class/gpio/gpio55/value')=='0'
        rows.append(dict(percent=percent,reply=reply,pwm=output))
        print('PASS: real PWM '+str(percent)+'%',flush=True)
    assert json.loads(shell('cat /opt/instrument/state/backlight.json'))['brightness']==100
finally:
    ask('hello_query')
    ended=ask('diagnostics_end',diagnostics_id=token)
    rows.append(dict(end=ended))
    time.sleep(.2)
    output=shell('for chip in /sys/class/pwm/pwmchip*; do case "$(readlink "$chip/device")" in *ff490030.pwm*) cat "$chip/pwm0/duty_cycle";; esac; done')
    assert output=='0',output
    (ROOT/'brightness-board.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print('PASS: end switches PWM duty to 0; configured brightness remains 100',flush=True)
token='expire-'+secrets.token_hex(8)
assert ask('diagnostics_start',diagnostics_id=token,ttl_ms=1000)['ok']
assert ask('diagnostics_backlight',diagnostics_id=token,brightness=50)['ok']
time.sleep(1.3)
assert not ask('hello_query')['diagnostics_active']
assert shell('for chip in /sys/class/pwm/pwmchip*; do case "$(readlink "$chip/device")" in *ff490030.pwm*) cat "$chip/pwm0/duty_cycle";; esac; done')=='0'
print('PASS: real lease timeout switches PWM duty to 0',flush=True)
token='restore-'+secrets.token_hex(8)
assert ask('diagnostics_start',diagnostics_id=token,ttl_ms=2000)['ok']
assert ask('diagnostics_backlight',diagnostics_id=token,brightness=100)['ok']
assert ask('diagnostics_end',diagnostics_id=token)['ok']
assert json.loads(shell('cat /opt/instrument/state/backlight.json'))['brightness']==100
(ROOT/'after.json').write_text(json.dumps(ask('hello_query'),indent=2),encoding='utf-8')
(ROOT/'timezone-camera-after.txt').write_text(shell("date; cat /etc/TZ; grep -A7 '^\\[video.jpeg\\]' /userdata/rkipc.ini; cat /proc/$(pidof rkipc)/environ | tr '\\000' '\\n' | grep '^TZ='"),encoding='utf-8')
