#!/bin/sh
set -eu
cd /tmp/instrument-uvc-test
sleep 2
# Do not interrupt unknown instrument activity.
if pidof instrument_app >/dev/null; then echo 'instrument_app still running'; exit 20; fi
killall rkipc 2>/dev/null || true
sleep 2
# Stop only the USB restart watcher, not global device management.
killall S99usb0config 2>/dev/null || true
G=/sys/kernel/config/usb_gadget/rockchip
echo '' > "$G/UDC"
killall adbd 2>/dev/null || true
if [ -L "$G/configs/b.1/f1" ]; then rm "$G/configs/b.1/f1"; fi
if [ -L "$G/configs/b.1/f2" ]; then rm "$G/configs/b.1/f2"; fi
sh ./usb_config.sh
LD_LIBRARY_PATH=/oem/usr/lib:/usr/lib ./rk_mpi_uvc -c /tmp/instrument-uvc-test/rkuvc.ini -a /oem/usr/share/iqfiles > /tmp/instrument-uvc-test/feeder.log 2>&1 &
echo $! > /tmp/instrument-uvc-test/feeder.pid
