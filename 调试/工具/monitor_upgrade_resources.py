"""Read-only aggregate PSS/RSS of instrument_app and its forked workers."""
import argparse
import datetime
import json
import pathlib
import subprocess
import time

BOARD_COMMAND = '''for task_pid in $(pidof instrument_app wget aplay amixer sha256sum rkipc); do
  if [ -r /proc/$task_pid/smaps_rollup ]; then task_maps=/proc/$task_pid/smaps_rollup;
  else task_maps=/proc/$task_pid/smaps; fi
  awk -v pid="$task_pid" '/^Pss:/ {p+=$2} /^Rss:/ {r+=$2} END {print "PROC",pid,p,r}' "$task_maps"
done
awk '/^MemAvailable:/ {print "MEM",$2}' /proc/meminfo'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--stop-file', type=pathlib.Path)
    parser.add_argument('--seconds', type=float, default=600)
    parser.add_argument('--interval', type=float, default=0.5)
    parser.add_argument('--adb', default=r'D:\SoftWare\Android_Studio_SDK\platform-tools\adb.exe')
    parser.add_argument('--serial', default='3253c006806f5194')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    until = time.monotonic() + args.seconds
    samples = []
    with args.output.open('w', encoding='utf-8') as output:
        while time.monotonic() < until and not (args.stop_file and args.stop_file.exists()):
            started = time.monotonic()
            row = dict(time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            try:
                result = subprocess.run([args.adb, '-s', args.serial, 'shell', BOARD_COMMAND],
                                        check=True, capture_output=True, text=True, timeout=5)
                processes = []
                for line in result.stdout.splitlines():
                    fields = line.split()
                    if fields and fields[0] == 'PROC' and len(fields) == 4:
                        processes.append(dict(pid=int(fields[1]), pss_kib=int(fields[2]), rss_kib=int(fields[3])))
                    elif fields and fields[0] == 'MEM':
                        row['mem_available_kib'] = int(fields[1])
                row.update(processes=processes, process_count=len(processes),
                           pss_kib=sum(p['pss_kib'] for p in processes),
                           rss_kib=sum(p['rss_kib'] for p in processes))
                samples.append(row)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                row['error'] = str(error)
            row['sample_elapsed_ms'] = round(1000 * (time.monotonic() - started))
            output.write(json.dumps(row) + '\n')
            output.flush()
            time.sleep(max(0, args.interval - (time.monotonic() - started)))
    print(json.dumps(dict(samples=len(samples),
                          max_pss_kib=max((r['pss_kib'] for r in samples), default=None),
                          max_rss_kib=max((r['rss_kib'] for r in samples), default=None),
                          max_processes=max((r['process_count'] for r in samples), default=None),
                          min_mem_available_kib=min((r['mem_available_kib'] for r in samples), default=None))))


if __name__ == '__main__':
    main()
