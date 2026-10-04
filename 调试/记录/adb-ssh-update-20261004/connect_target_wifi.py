"""One-time network preparation for the explicitly selected USB board; no secrets logged."""
import json
from pathlib import Path
import re
import subprocess
import tarfile
import time

root = Path(__file__).resolve().parent
adb = r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe'
serial = '41eda5f2c5b00de1'
identity = subprocess.check_output([adb, '-s', serial, 'shell', 'cat /proc/device-tree/serial-number'])
assert identity.strip(b'\x00\r\n') == serial.encode()
release = 'instrument-v3.3.0-20261004-minmax-volume20-bundle1'
with tarfile.open(root / (release + '.tar.gz')) as archive:
    text = archive.extractfile(release + '/deploy/wpa_supplicant.default.conf').read().decode()
ssid = re.search(r'ssid="([^"]+)"', text).group(1)
psk = re.search(r'psk="([^"]+)"', text).group(1)
assert ssid == 'MinMax-test'
backup = '/userdata/deploy-records/20261004-162128'
subprocess.run([adb, '-s', serial, 'shell', f'cp /userdata/wpa_supplicant.conf {backup}/wpa-before.conf; chmod 600 {backup}/wpa-before.conf; ls -l /data /etc/wpa_supplicant.conf'], check=True)
payload = ('ctrl_interface=/var/run/wpa_supplicant\nupdate_config=1\nnetwork={\n'
           '    ssid=' + json.dumps(ssid) + '\n    psk=' + json.dumps(psk) + '\n    priority=100\n}\n').encode()
subprocess.run([adb, '-s', serial, 'push', str(root / (release + '.tar.gz')), '/tmp/network-defaults.tar.gz'], check=True)
cmd = ('mkdir -p /tmp/network-defaults && gzip -dc /tmp/network-defaults.tar.gz > /tmp/network-defaults/payload.tar && '
       'tar -xf /tmp/network-defaults/payload.tar -C /tmp/network-defaults && '
       f'sh /tmp/network-defaults/{release}/deploy/install_bundle.sh --check && '
       f'cp /tmp/network-defaults/{release}/deploy/wpa_supplicant.default.conf /userdata/wpa_supplicant.conf.deploy-new && '
       'chmod 600 /userdata/wpa_supplicant.conf.deploy-new && mv /userdata/wpa_supplicant.conf.deploy-new /userdata/wpa_supplicant.conf && echo NETWORK_TEMPLATE_APPLIED')
result = subprocess.check_output([adb, '-s', serial, 'shell', cmd])
assert b'NETWORK_TEMPLATE_APPLIED' in result
del psk, payload, text
config = json.loads((root / 'initial-config.json').read_text())
config.update(wifi_ssid=ssid, pc_base_url='http://192.168.101.2:8080')
config['audio']['volume'] = 20
(root / 'target-config-volume20.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
subprocess.run([adb, '-s', serial, 'push', str(root / 'target-config-volume20.json'), '/opt/instrument/config.json.deploy-new'], check=True)
subprocess.run([adb, '-s', serial, 'shell', '/opt/instrument/bin/instrument_app --check-config /opt/instrument/config.json.deploy-new && chmod 600 /opt/instrument/config.json.deploy-new && mv /opt/instrument/config.json.deploy-new /opt/instrument/config.json && wpa_cli -i wlan0 reconfigure && wpa_cli -i wlan0 reassociate'], check=True)
time.sleep(5)
output = subprocess.check_output([adb, '-s', serial, 'shell', 'wpa_cli -i wlan0 status; ip -4 addr show wlan0']).decode(errors='replace').replace('\r', '')
(root / '05-target-wifi.txt').write_text(output, encoding='utf-8')
print(output)
