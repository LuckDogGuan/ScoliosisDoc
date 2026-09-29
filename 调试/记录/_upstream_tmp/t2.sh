#!/bin/sh
P="python3 /tmp/rkipc_call.py"
now() { cut -d' ' -f1 /proc/uptime; }
D=/userdata/video0
ls $D > /tmp/before.txt
echo "t_start_call $(now)"
$P rk_storage_record_start
echo "t_start_ret $(now)"
$P rk_storage_record_statue_get n=2
sleep 1
F=$(ls $D | grep -v -x -f /tmp/before.txt | head -1)
echo "new file: $F  $(now)"
ls -la $D/$F
free | grep Mem
sleep 9
echo "t_stop_call $(now)"
$P rk_storage_record_stop
echo "t_stop_ret $(now)"
ls -la $D/$F
logread 2>/dev/null | tail -3
