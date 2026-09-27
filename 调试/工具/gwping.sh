#!/bin/sh
# One ping per second so each exit flushes a line into the log.
rm -f /tmp/gw-live.txt
i=0
while [ "$i" -lt 500 ]; do
	ping -c 1 -W 1 192.168.1.1 >> /tmp/gw-live.txt 2>&1
	sleep 1
	i=$((i + 1))
done
echo done >> /tmp/gw-live.txt
