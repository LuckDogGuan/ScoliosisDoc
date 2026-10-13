"""Temporary CoreAudio mute/zero-volume testing with unconditional restoration.

ABI: IMMDeviceEnumerator::GetDefaultAudioEndpoint, IMMDevice::Activate,
IAudioEndpointVolume::GetMute/SetMute/GetMasterVolumeLevelScalar/SetMasterVolumeLevelScalar.
https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nn-endpointvolume-iaudioendpointvolume
"""
import argparse
import ctypes as c
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


class GUID(c.Structure):
    _fields_ = [('data1', c.c_uint32), ('data2', c.c_uint16),
                ('data3', c.c_uint16), ('data4', c.c_ubyte * 8)]

    @classmethod
    def parse(cls, text):
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


def checked(value):
    if value < 0:
        raise OSError(f'CoreAudio HRESULT 0x{value & 0xffffffff:08x}')


def call(pointer, slot, argtypes, *args):
    table = c.cast(pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
    function = c.WINFUNCTYPE(c.c_long, c.c_void_p, *argtypes)(table[slot])
    checked(function(pointer, *args))


class Endpoint:
    def __init__(self):
        self.ole = c.OleDLL('ole32')
        self.ole.CoInitializeEx.argtypes = [c.c_void_p, c.c_uint32]
        checked(self.ole.CoInitializeEx(None, 2))
        self.enumerator = c.c_void_p()
        self.device = c.c_void_p()
        self.volume = c.c_void_p()
        clsid = GUID.parse('bcde0395-e52f-467c-8e3d-c4579291692e')
        iid = GUID.parse('a95664d2-9614-4f35-a746-de8db63617e6')
        self.ole.CoCreateInstance.argtypes = [c.POINTER(GUID), c.c_void_p,
          c.c_uint32, c.POINTER(GUID), c.POINTER(c.c_void_p)]
        checked(self.ole.CoCreateInstance(c.byref(clsid), None, 1, c.byref(iid), c.byref(self.enumerator)))
        call(self.enumerator, 4, [c.c_int, c.c_int, c.POINTER(c.c_void_p)],
             0, 1, c.byref(self.device))
        endpoint_iid = GUID.parse('5cdf2c82-841e-4546-9722-0cf74078229a')
        call(self.device, 3, [c.POINTER(GUID), c.c_uint32, c.c_void_p, c.POINTER(c.c_void_p)],
             c.byref(endpoint_iid), 23, None, c.byref(self.volume))

    def state(self):
        mute = c.c_int()
        volume = c.c_float()
        call(self.volume, 15, [c.POINTER(c.c_int)], c.byref(mute))
        call(self.volume, 9, [c.POINTER(c.c_float)], c.byref(volume))
        return dict(mute=bool(mute.value), volume=volume.value)

    def set(self, mute, volume):
        assert 0 <= volume <= 1
        call(self.volume, 14, [c.c_int, c.c_void_p], True, None)
        call(self.volume, 7, [c.c_float, c.c_void_p], volume, None)
        call(self.volume, 14, [c.c_int, c.c_void_p], mute, None)
        actual = self.state()
        assert actual['mute'] == mute and abs(actual['volume'] - volume) < 0.00001
        return actual

    def close(self):
        # Release returns a reference count rather than HRESULT.
        for pointer in [self.volume, self.device, self.enumerator]:
            if pointer:
                table = c.cast(pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
                c.WINFUNCTYPE(c.c_ulong, c.c_void_p)(table[2])(pointer)
        self.ole.CoUninitialize()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--read-only', action='store_true')
    parser.add_argument('--transitions-only', action='store_true')
    parser.add_argument('--evidence-root', default=str(Path(__file__).with_name('windows-audio-facts')))
    parser.add_argument('--flutter-root', default=r'D:\code\Scoliosis\ScoliosisFlutter')
    parser.add_argument('--flutter', default=r'D:\SoftWare\Flutter\flutter_windows_3.41.9-stable\flutter\bin\flutter.bat')
    args = parser.parse_args()
    endpoint = Endpoint()
    original = endpoint.state()
    if args.read_only:
        print(json.dumps(original))
        endpoint.close()
        return
    root = Path(args.evidence_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = dict(utc=datetime.now(timezone.utc).isoformat(), original=original,
      scenarios=[], actual_speaker_listening='not_verified',
      missing_output_device='not_mutated; device/service removal outside ordinary-user test',
      source='Microsoft CoreAudio IMMDeviceEnumerator and IAudioEndpointVolume')
    try:
        volume = original['volume'] if original['volume'] > 0 else 0.1
        states = {'normal': (False, volume), 'system_mute': (True, volume),
                  'volume_zero': (False, 0.0), 'sound_restored': (False, volume)}
        for name, (mute, scalar) in ([] if args.transitions_only else states.items()):
            before = endpoint.set(mute, scalar)
            evidence = root / (name + '.jsonl')
            env = dict(os.environ, STABILITY_SPEECH_SCENARIO=name,
                       STABILITY_SPEECH_EVIDENCE=str(evidence))
            result = subprocess.run([args.flutter, 'test', '--no-pub',
               'tool/windows_speech_fact_test.dart', '--reporter', 'expanded'],
               cwd=args.flutter_root, env=env, capture_output=True, timeout=150)
            (root / (name + '.log')).write_bytes(result.stdout + result.stderr)
            after = endpoint.state()
            preserved = after['mute'] == before['mute'] and abs(after['volume'] - before['volume']) < 0.00001
            report['scenarios'].append(dict(name=name, before=before, after=after,
                 state_preserved=preserved, exit_code=result.returncode))
            print(json.dumps(report['scenarios'][-1]), flush=True)
            assert result.returncode == 0 and preserved, f'{name} failed; inspect log'
        endpoint.set(False, volume)
        control = root / ('transitions-' + str(time.monotonic_ns()))
        control.mkdir()
        env = dict(os.environ, STABILITY_SPEECH_SCENARIO='same_instance_transitions',
                   STABILITY_SPEECH_EVIDENCE=str(control / 'speech.jsonl'),
                   STABILITY_SPEECH_CONTROL_ROOT=str(control))
        with (control / 'flutter.log').open('wb') as log:
            process = subprocess.Popen([args.flutter, 'test', '--no-pub',
                'tool/windows_speech_fact_test.dart', '--reporter', 'expanded'],
                cwd=args.flutter_root, env=env, stdout=log, stderr=subprocess.STDOUT)
            handled = 0
            deadline = time.monotonic() + 150
            try:
                while process.poll() is None:
                    if time.monotonic() > deadline:
                        raise TimeoutError('same-instance speech transition test')
                    request = control / 'request.json'
                    if request.exists():
                        try:
                            item = json.loads(request.read_text(encoding='utf-8'))
                        except ValueError:
                            time.sleep(0.03)
                            continue
                        if item['sequence'] == handled + 1:
                            actual = endpoint.set(*states[item['mode']])
                            ack = control / ('ack-' + str(item['sequence']) + '.json')
                            temporary = ack.with_suffix('.tmp')
                            temporary.write_text(json.dumps(actual), encoding='utf-8')
                            temporary.replace(ack)
                            handled = item['sequence']
                    time.sleep(0.03)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
        final = endpoint.state()
        report['same_instance_transitions'] = dict(exit_code=process.returncode,
             transitions=handled, final=final, evidence=str(control))
        assert process.returncode == 0 and handled == 3
        assert final['mute'] is False and abs(final['volume'] - volume) < 0.00001
        print(json.dumps(report['same_instance_transitions']), flush=True)
    finally:
        try:
            report['restored'] = endpoint.set(**original)
            report['original_state_restored'] = True
        finally:
            endpoint.close()
            (root / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(dict(original_state_restored=report.get('original_state_restored', False))), flush=True)


if __name__ == '__main__':
    main()
