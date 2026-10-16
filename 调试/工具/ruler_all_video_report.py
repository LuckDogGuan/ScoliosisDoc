"""Render a complete audit from actual Dart/native queue results; no re-inference."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.path import Path as PlotPath
from matplotlib.patches import PathPatch
import numpy as np


def valid(point):
    value = point['angle_deg']
    return value is not None and point['error'] is None and np.isfinite(value) and abs(value) <= 10


def bounded_path(points):
    vertices, codes = [], []
    before = previous_slope = None
    for i, point in enumerate(points):
        if not valid(point):
            before = previous_slope = None
            continue
        current = (point['angle_deg'], point['pts_ms'] / 1000)
        if before is None:
            vertices.append(current)
            codes.append(PlotPath.MOVETO)
        else:
            dt = current[1] - before[1]
            slope = (current[0] - before[0]) / dt if dt > 0 else 0
            def tangent(neighbor):
                if neighbor is None:
                    return slope
                return 0 if neighbor * slope <= 0 else 2 * neighbor * slope / (neighbor + slope)
            following = None
            if i + 1 < len(points) and valid(points[i + 1]):
                next_dt = points[i + 1]['pts_ms'] / 1000 - current[1]
                if next_dt > 0:
                    following = (points[i + 1]['angle_deg'] - current[0]) / next_dt
            low, high = sorted([before[0], current[0]])
            vertices.extend([
                (np.clip(before[0] + tangent(previous_slope) * dt / 3, low, high), before[1] + dt / 3),
                (np.clip(current[0] - tangent(following) * dt / 3, low, high), current[1] - dt / 3), current,
            ])
            codes.extend([PlotPath.CURVE4] * 3)
            previous_slope = slope
        before = current
    return PlotPath(vertices, codes) if vertices else None


def local_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M:%S') if value else '时间未记录'


def draw(ax, row, beautified):
    points = row['beautified' if beautified else 'raw']
    ax.set_xlim(-10, 10)
    ax.set_ylim(max(float(row['duration_s']), .01), 0)
    ax.set_xlabel('角度（°）'); ax.set_ylabel('视频时间（秒）↓')
    for value, color in [(0, '#b5c0cc'), (-5, '#edc796'), (5, '#edc796'), (-7, '#e7994f'), (7, '#e7994f')]:
        ax.axvline(value, color=color, ls='-' if value == 0 else '--', lw=.7)
    for gap in row['gaps']:
        ax.axhspan(gap['start_ms'] / 1000, max(gap['end_ms'], gap['start_ms'] + 25) / 1000, color='#f5b544', alpha=.16)
    if beautified:
        path = bounded_path(points)
        if path is not None:
            ax.add_patch(PathPatch(path, fill=False, lw=1.7, edgecolor='#3573ae'))
    else:
        ax.plot([p['angle_deg'] if valid(p) else np.nan for p in points], [p['pts_ms'] / 1000 for p in points], '-o', ms=2, lw=1.1, color='#3573ae')
    usable = [p for p in points if valid(p)]
    if usable:
        peak = max(usable, key=lambda p: abs(p['angle_deg']))
        ax.plot(peak['angle_deg'], peak['pts_ms'] / 1000, 'o', color='#193f68', ms=5)
    else:
        ax.text(.5, .5, '整段拒读\n未产生有效角度', ha='center', va='center', transform=ax.transAxes, color='#b33434', fontsize=13)
    ax.set_title('方案 A：补齐 + 平滑' if beautified else '原始识别：缺失处断开')
    for spine in ax.spines.values():
        spine.set_color('#d4dce5')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    result = json.loads((root / 'results.json').read_text(encoding='utf-8'))
    inventory = json.loads((root / 'inventory.json').read_text(encoding='utf-8'))
    rows = result['videos']
    assert len(rows) == len(inventory['videos']), 'Incomplete run'
    font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'axes.unicode_minus': False})
    cards, table = [], []
    summary_rows, point_rows = [], []
    overview, axes = plt.subplots(2, 5, figsize=(15, 9), layout='constrained')
    for row, mini in zip(rows, axes.flat):
        rid = row['video_id']
        rejected = row['analysis_status'] == 'failed'
        verdict = '整段拒读；当前模型下不可用' if rejected else '流程完成；含推断，需结合原画面复核'
        reasons = '；'.join(f'{key} ×{value}' for key, value in row['reasons'].items()) or '无'
        timestamp = local_time(row['captured_at'])
        peak = '—' if row['peak_beautified_abs'] is None else f'{row["peak_beautified_abs"]:.2f}°'
        fig, axs = plt.subplots(1, 2, figsize=(9, 8.2), layout='constrained')
        draw(axs[0], row, False); draw(axs[1], row, True)
        fig.suptitle(f'{rid} · {timestamp} · 原始有效 {row["raw_valid"]}/{row["samples"]} · 推断 {row["inferred"]}', fontsize=13)
        fig.savefig(root / f'{rid}_曲线.png', dpi=130)
        plt.close(fig)
        draw(mini, row, True)
        mini.set_title(f'{rid}｜有效 {row["raw_valid_rate"]:.1%}\n推断 {row["inferred"]}｜{peak}', fontsize=10)
        table.append(f'<tr><td><a href="#{rid}">{rid}</a></td><td>{timestamp}</td><td>{row["raw_valid"]}/{row["samples"]}</td><td>{row["inferred"]}</td><td>{peak}</td><td>{row["pipeline_wall_ms"]/1000:.2f}s</td><td>{"整段拒读" if rejected else "含推断"}</td></tr>')
        name = Path(row['source']).name
        cards.append(f'''<article id="{rid}" class="{'failed' if rejected else 'inferred'}"><h2>{rid} · {timestamp} <small>{verdict}</small></h2>
<p class="file">{html.escape(name)}</p><p>原始有效 <b>{row['raw_valid']}/{row['samples']}（{row['raw_valid_rate']:.1%}）</b> · 拒读 {row['raw_rejected']} · 推断 {row['inferred']} · 美化后有效 {row['beautified_valid']} · 最大绝对值 {peak}</p>
<p>最长连续拒读 {row['longest_rejected_run']} 点；最长拒读区间跨度（含邻接时点）{row['longest_gap_anchor_ms']/1000:.3f}s。耗时 {row['pipeline_wall_ms']/1000:.2f}s。<br>原因：{html.escape(reasons)}<br>程序状态：{row['analysis_status']}；{html.escape(row['analysis_error'] or row['quality'])}</p>
<a href="{rid}_曲线.png"><img class="curve" src="{rid}_曲线.png" alt="{rid} 原始和美化曲线"></a>
<details><summary>查看原视频及三个时点的画面</summary><video controls preload="none" poster="frames/{rid}_1.png" src="{Path(row['source']).as_uri()}"></video><img class="strip" src="{rid}_画面.png"></details></article>''')
        summary_rows.append([rid, timestamp, name, row['samples'], row['raw_valid'], row['raw_rejected'], row['inferred'], row['beautified_valid'], row['raw_valid_rate'], row['longest_rejected_run'], row['longest_gap_anchor_ms'], row['peak_raw_abs'], row['peak_beautified_abs'], row['analysis_status'], verdict, reasons, row['pipeline_wall_ms']])
        for point in row['beautified']:
            point_rows.append([rid, point['frame_index'] + 1, point['pts_ms'], point['angle_deg'] if valid(point) else None, '是' if point['was_inferred'] else '否', point['error'], point['processing_version']])
    overview.savefig(root / '全部曲线总览.png', dpi=130); plt.close(overview)
    for filename, header, values in [
        ('全部视频_汇总.csv', ['编号','拍摄时间','文件名','采样点','原始有效','原始拒读','推断','美化有效','原始有效比例','最长连续拒读点','最长缺口跨度ms','原始峰值','美化峰值','程序状态','复核说明','拒读原因','全流程耗时ms'], summary_rows),
        ('全部视频_美化逐点.csv', ['编号','原帧号_从1开始','时间戳ms','美化角度','是否推断','失败原因','处理版本'], point_rows),
    ]:
        with (root / filename).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(header); writer.writerows(values)
    done = sum(row['analysis_status'] == 'done' for row in rows)
    complete = [row for row in rows if row['analysis_status'] == 'done']
    coverage_note = (f'产生曲线的 {done} 段原始有效比例为 {min(r["raw_valid_rate"] for r in complete):.1%}–{max(r["raw_valid_rate"] for r in complete):.1%}；最长补齐区间的邻接跨度为 {max(r["longest_gap_anchor_ms"] for r in complete)/1000:.3f}s。' if complete else '本次无视频产生有效曲线。')
    counts = dict(videos=len(rows), completed=done, failed=len(rows)-done, samples=sum(r['samples'] for r in rows), raw_valid=sum(r['raw_valid'] for r in rows), inferred=sum(r['inferred'] for r in rows), wall_seconds=sum(r['pipeline_wall_ms'] for r in rows)/1000)
    (root / 'summary.json').write_text(json.dumps(counts, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
    missing = ''.join(f'<li>{html.escape(r["capture_id"])} · {local_time(r["captured_at"])} · 原文件不存在，未重测</li>' for r in inventory['missing_record_videos'])
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>全部视频 · 当前算法 + 方案 A 测试</title><style>body{font:15px "Microsoft YaHei",sans-serif;color:#243749;background:#f2f5f8;margin:24px auto;max-width:1150px;padding:0 16px;line-height:1.8}h1{font-size:28px}h2{font-size:21px}small{font-size:14px;font-weight:normal}article,.panel{background:white;border-radius:12px;padding:20px;margin:24px 0}.failed{border-left:5px solid #b74646}.inferred{border-left:5px solid #d89a35}table{border-collapse:collapse;width:100%;background:white}td,th{padding:8px;border-bottom:1px solid #d9e0e8;text-align:left}a{color:#2767a1}.curve,.strip{width:100%;height:auto}video{width:100%;max-height:620px}.file{word-break:break-all;color:#657383}.notice{color:#934e18}details{padding:10px;background:#fafbfc}.scroll{overflow:auto}</style>'''
    page += f'''<h1>现存全部 {counts['videos']} 段视频：完整实测结果</h1><div class="panel"><b>识别流程能执行完成；结果可用性需要看原始覆盖，不能只看平滑后的完整曲线。</b><p>执行完成 {done} 段，整段拒读 {counts['failed']} 段；共 {counts['samples']} 个采样点，原始有效 {counts['raw_valid']}，推断 {counts['inferred']}。每 2 帧取 1 帧，第四轮 C DLL、方案 A、双份 SQLite 落盘均复用当前正式代码。全流程合计 {counts['wall_seconds']:.2f}s，含抽帧/读图/模型/保存，不含界面刷新。</p><p class="notice">橙色浅带标出原始拒读时间。补齐后的点属于推断，曲线完整不代表逐帧识别成功；本次没有人工角度真值，不能给出精度合格结论。全部拒读的视频没有生成假角度。</p><p><a href="全部视频_美化结果.xlsx">标准 Excel 结果</a> · <a href="全部视频_汇总.csv">全部视频汇总 CSV</a> · <a href="全部视频_美化逐点.csv">美化逐点 CSV</a> · <a href="results.json">原始/美化完整 JSON</a> · <a href="README.md">复现和证据</a></p></div>'''
    page += '<p>'+coverage_note+'本次编号按实际现存文件排序，与上一份“最近五条”报告编号不同；完整文件名见每段详情。</p>'
    page += '<div class="scroll"><table><tr><th>编号</th><th>拍摄时间（北京时间）</th><th>原始有效/采样</th><th>推断</th><th>美化峰值</th><th>耗时</th><th>状态</th></tr>'+''.join(table)+'</table></div>'+''.join(cards)
    page += '<div class="panel"><h2>数据库中另有原文件缺失的录像</h2><p>这些记录不属于现存文件测试，不能把已保存的历史数据当作本次重测结果。</p><ul>'+missing+'</ul></div></html>'
    (root / '全部视频测试报告.html').write_text(page, encoding='utf-8', newline='\n')
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == '__main__':
    main()
