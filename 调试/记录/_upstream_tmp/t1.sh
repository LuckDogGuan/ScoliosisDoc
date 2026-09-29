#!/bin/sh
P="python3 /tmp/rkipc_call.py"
now() { cut -d' ' -f1 /proc/uptime; }
echo "t0 $(now)"
$P rk_video_set_frame_rate 0 s=60/2
$P rk_video_set_max_rate 0 4000
$P rk_video_set_gop 0 30
echo "t_set $(now)"
sleep 1
md5sum /userdata/rkipc.ini
grep -E '^(max_rate|gop|dst_frame_rate_den|dst_frame_rate_num|mid_rate) ' /userdata/rkipc.ini
dmesg | grep -E 'fps fix|bps \[' | tail -4
free | grep Mem
