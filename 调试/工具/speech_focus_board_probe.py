"""Identity-bound live speech lease probe. Never enables capture or changes pairing."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
import uuid


def main(args):
    def shell(command):
        return subprocess.check_output([args.adb,'-s',args.serial,'shell',command],timeout=10).decode().replace('\x00','').strip()
    assert shell('cat /proc/device-tree/serial-number')==args.serial
    assert shell('/opt/instrument/bin/instrument_app --version')=='3.3.10'
    pair=json.loads(shell('cat /opt/instrument/state/pair-v3.json'))
    assert pair['host_id'] and not pair['revoking']
    ip=shell("ip -4 addr show wlan0").split('inet ')[1].split('/')[0]
    peer=pair['peer_ip']
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind((peer,0));sock.settimeout(2)
    device='CAM-'+args.serial;boot='';sequence=0;events=[]
    def query(op='hello_query',**fields):
        nonlocal sequence
        sequence+=1;nonce=uuid.uuid4().hex
        packet=dict(version=3,op=op,device_id=device,host_id=pair['host_id'],sequence=sequence,nonce=nonce,boot_id=boot,**fields)
        sock.sendto(json.dumps(packet).encode(),(ip,37020))
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            data,source=sock.recvfrom(4096);reply=json.loads(data)
            if source==(ip,37020) and reply.get('nonce')==nonce and reply.get('sequence')==sequence and reply.get('device_id')==device:
                if boot: assert reply['boot_id']==boot
                events.append(dict(op=op,action=fields.get('action'),ok=reply.get('ok'),audio_busy=reply.get('audio_busy'),speech_focus_active=reply.get('speech_focus_active')))
                return reply
        raise TimeoutError(op)
    held=None
    try:
        state=query();boot=state['boot_id'];sequence=max(sequence,state['control_sequence'])
        assert state['firmware_version']=='3.3.10' if 'firmware_version' in state else True
        assert 'speech_focus' in state['capabilities']
        assert state['phase']=='idle' and not state['gate_enabled'] and not state['audio_busy']
        held='probe-'+uuid.uuid4().hex
        assert query('speech_focus',action='acquire',speech_id=held,ttl_ms=6000)['ok']
        state=query();assert state['speech_focus_active'] and state['audio_busy']
        assert not query('speech_focus',action='release',speech_id='wrong-token')['ok']
        assert not query('speech_focus',action='renew',speech_id=held,ttl_ms=6001)['ok']
        assert query('speech_focus',action='renew',speech_id=held,ttl_ms=6000)['ok']
        assert query('speech_focus',action='release',speech_id=held)['ok'];held=None
        assert not query()['speech_focus_active']
        held='expire-'+uuid.uuid4().hex
        assert query('speech_focus',action='acquire',speech_id=held,ttl_ms=1000)['ok']
        time.sleep(1.7)
        assert not query()['speech_focus_active']
        assert not query('speech_focus',action='renew',speech_id=held,ttl_ms=6000)['ok'];held=None
        final=query();assert not final['gate_enabled'] and final['phase']=='idle'
        record=dict(serial=args.serial,device_id=device,version='3.3.10',boot_id=boot,events=events,result='PASS',physical_voice_listening='not verified',capture_or_pairing_changed=False)
        Path(args.output).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print('SPEECH_FOCUS_BOARD_PASS')
    finally:
        if held:
            try:query('speech_focus',action='release',speech_id=held)
            except Exception:pass
        sock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--adb',required=True);parser.add_argument('--serial',required=True);parser.add_argument('--output',required=True)
    main(parser.parse_args())
