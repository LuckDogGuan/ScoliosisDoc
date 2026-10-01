#!/bin/sh
# RV1106 GPIO0_A3/A4/A0 -> GND buttons. Only A0/A4 bias bits are changed.
# Official pinctrl-rockchip.c: GPIO0 pull offset 0x38, two bits per pin,
# 0=disabled, 1=pull-up, 2=pull-down; PMUIOC base 0xff388000.
set -eu
register=0xff388038
mask=0x0303
backup=/tmp/button-input-pull-before.txt
before=$(devmem "$register" 32)
if [ "${1:-}" = "--restore" ]; then
    saved=$(cat "$backup")
    value=$(( (mask << 16) | (saved & mask) ))
    devmem "$register" 32 "$value"
    echo "Restored A0/A4 bias: $(devmem "$register" 32)"
    exit 0
fi
[ -f "$backup" ] || printf '%s\n' "$before" > "$backup"
devmem "$register" 32 0x03030101
after=$(devmem "$register" 32)
expected=$(( (before & ~mask) | 0x0101 ))
[ "$((after))" -eq "$expected" ] || { echo 'Bias readback failed' >&2; exit 1; }
for pin in 3 4 0; do
    path=/sys/class/gpio/gpio$pin
    if [ ! -d "$path" ]; then echo "$pin" > /sys/class/gpio/export; fi
    echo in > "$path/direction"
    [ "$(cat "$path/direction")" = in ] || exit 1
done
printf 'left_A3=%s center_A4=%s right_A0=%s\n' \
    "$(cat /sys/class/gpio/gpio3/value)" \
    "$(cat /sys/class/gpio/gpio4/value)" \
    "$(cat /sys/class/gpio/gpio0/value)"
