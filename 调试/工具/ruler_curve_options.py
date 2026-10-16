"""Read-only latest-five curve study. Saves raw data and three derived alternatives."""
from pathlib import Path
import argparse
import csv
from datetime import datetime, timedelta
import hashlib
import html
import json
import math
import sqlite3

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import scipy
from scipy.interpolate import PchipInterpolator
from scipy.signal import savgol_filter

METHODS = {
    'A': dict(name='轻度平滑', short='直线补点＋局部加权平均', color='#238465',
              detail='缺口按时间直线连接，再做半径 0.18 秒的三角加权平均。变化小，保留更多原始起伏。',
              parameters=dict(gap='linear', triangular_radius_seconds=0.18)),
    'B': dict(name='均衡平滑', short='保形补点＋局部多项式', color='#2867ad',
              detail='缺口用保形插值推断，再做约 0.55 秒窗口的三阶局部多项式平滑。尽量兼顾圆滑与峰值。',
              parameters=dict(gap='pchip', grid_seconds=0.02, smoothing_window_seconds=0.55, polynomial_order=3)),
    'C': dict(name='较强平滑', short='双向卡尔曼推断', color='#8451a3',
              detail='将角度和变化速度一起估计，缺失时预测，再用整段前后信息校正。更顺滑，峰值和急转弯改变可能更大。',
              parameters=dict(process_noise_density=6.0, measurement_std_degrees=0.35, backward_smoothing=True)),
}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def read_dataset(root, capture_ids=None):
    path = root / 'screening.sqlite3'
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=10) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        if capture_ids is None:
            captures = db.execute("SELECT capture_id,captured_at,video_path,video_sha256,analysis_status FROM captures WHERE video_path IS NOT NULL AND analysis_status='done' ORDER BY julianday(COALESCE(captured_at,updated_at)) DESC,capture_id DESC LIMIT 5").fetchall()
        else:
            captures = [db.execute('SELECT capture_id,captured_at,video_path,video_sha256,analysis_status FROM captures WHERE capture_id=?', (key,)).fetchone() for key in capture_ids]
        result = []
        for i, capture in enumerate(captures):
            meta = dict(capture)
            samples = [dict(row) for row in db.execute('SELECT frame_index,pts_ms,angle_deg,error,model_version,input_image FROM angle_samples WHERE capture_id=? ORDER BY pts_ms,frame_index', (meta['capture_id'],))]
            assert samples, f'No stored frame readings: {meta["capture_id"]}'
            meta['review_id'] = f'V{i+1:02}'
            meta['video_exists'] = (root / meta['video_path']).is_file()
            meta['local_time'] = (datetime.fromisoformat(meta['captured_at'].replace('Z','+00:00'))+timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
            result.append(dict(metadata=meta, samples=samples))
        db.execute('COMMIT')
    return result


def fingerprint(dataset):
    content = [dict(capture_id=c['metadata']['capture_id'], samples=c['samples']) for c in dataset]
    return sha_bytes(json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8'))


def sample_arrays(samples):
    t = np.array([s['pts_ms']/1000 for s in samples], dtype=float)
    y = np.array([s['angle_deg'] if s['angle_deg'] is not None else np.nan for s in samples], dtype=float)
    valid = np.isfinite(y) & (np.abs(y) <= 10) & np.array([s['error'] is None for s in samples])
    outside = np.isfinite(y) & (np.abs(y) > 10)
    assert len(t) == 1 or np.all(np.diff(t) > 0), 'Non-increasing stored timestamps'
    return t, y, valid, outside


def fill(t, y, valid, shape):
    if not valid.any():
        return np.full(len(y), np.nan)
    x, values = t[valid], y[valid]
    if len(values) == 1 or shape == 'linear':
        return np.interp(t, x, values)
    return PchipInterpolator(x, values)(np.clip(t, x[0], x[-1]))


def smooth_kalman(t, y, valid):
    if not valid.any():
        return np.full(len(y), np.nan)
    config = METHODS['C']['parameters']
    state = np.array([y[valid][0], 0.0])
    covariance = np.diag([1.0, 100.0])
    filtered, covariances, predicted, predicted_cov, transitions = [], [], [], [], []
    noise = config['measurement_std_degrees']**2
    for i in range(len(t)):
        dt = t[i]-t[i-1] if i else 0.0
        transition = np.array([[1.0, dt], [0.0, 1.0]])
        process = config['process_noise_density']*np.array([[dt**3/3, dt**2/2], [dt**2/2, dt]])
        state = transition@state
        covariance = transition@covariance@transition.T+process
        predicted.append(state.copy()); predicted_cov.append(covariance.copy()); transitions.append(transition)
        if valid[i]:
            gain = covariance[:,0]/(covariance[0,0]+noise)
            state = state+gain*(y[i]-state[0])
            update = np.eye(2)-np.outer(gain, [1.0,0.0])
            covariance = update@covariance@update.T+noise*np.outer(gain,gain)
        filtered.append(state.copy()); covariances.append(covariance.copy())
    smoothed = np.array(filtered)
    for i in range(len(t)-2,-1,-1):
        gain = np.linalg.solve(predicted_cov[i+1], transitions[i+1]@covariances[i]).T
        smoothed[i] += gain@(smoothed[i+1]-predicted[i+1])
    return smoothed[:,0]


def alternatives(t, y, valid, outside):
    linear, shaped = fill(t,y,valid,'linear'), fill(t,y,valid,'pchip')
    if not valid.any():
        return {key: linear.copy() for key in METHODS}
    radius = METHODS['A']['parameters']['triangular_radius_seconds']
    light = np.array([np.average(linear, weights=np.maximum(0, 1-np.abs(t-ti)/radius)) for ti in t])
    if len(t) > 1:
        grid = np.linspace(t[0],t[-1],max(3,math.ceil((t[-1]-t[0])/0.02)+1))
        step = grid[1]-grid[0]
        dense = PchipInterpolator(t,shaped)(grid)
        window = max(5,round(0.55/step) | 1)
        window = min(window,len(grid) if len(grid)%2 else len(grid)-1)
        fitted = savgol_filter(dense,window,min(3,window-1),mode='interp')
        balanced = np.interp(t,grid,fitted)
        # Clip polynomial ringing to the surrounding observed/interpolated range.
        for i,ti in enumerate(t):
            neighborhood = shaped[np.abs(t-ti)<=0.55/2]
            balanced[i] = np.clip(balanced[i],neighborhood.min(),neighborhood.max())
    else:
        balanced = shaped
    strong = smooth_kalman(t,y,valid)
    result = dict(A=light,B=balanced,C=strong)
    for key in result:
        result[key] = np.clip(result[key],max(-10,y[valid].min()),min(10,y[valid].max()))
        result[key][outside] = np.nan
    return result


def gap_runs(t, valid):
    runs = []
    i = 0
    while i < len(t):
        if valid[i]:
            i+=1; continue
        start = i
        while i < len(t) and not valid[i]: i+=1
        runs.append(dict(start_index=start,end_index=i-1,count=i-start,
                         first_time_s=float(t[start]),last_time_s=float(t[i-1]),
                         bounded_span_s=float(t[min(i,len(t)-1)]-t[max(0,start-1)])))
    return runs


def metrics(t, raw, valid, result):
    finite = np.isfinite(result)
    peak = float(np.max(np.abs(result[finite]))) if finite.any() else None
    measured_shift = np.abs(result[valid]-raw[valid])
    return dict(peak_abs_deg=peak, minimum_deg=float(np.min(result[finite])) if finite.any() else None,
                maximum_deg=float(np.max(result[finite])) if finite.any() else None,
                inferred_count=int(np.sum(~valid & finite)), remaining_missing=int(np.sum(~finite)),
                average_change_at_measured_deg=float(np.mean(measured_shift)) if len(measured_shift) else None,
                maximum_change_at_measured_deg=float(np.max(measured_shift)) if len(measured_shift) else None,
                peak_change_deg=peak-float(np.max(np.abs(raw[valid]))) if valid.any() else None)


def draw_curve(ax, t, raw, valid, values, key, title):
    original = np.where(valid,raw,np.nan)
    if key != 'raw':
        ax.plot(original,t,color='#bfc8d1',linewidth=0.8,alpha=0.65,zorder=1)
    for run in gap_runs(t,valid):
        lo=max(0,run['start_index']-1); hi=min(len(t)-1,run['end_index']+1)
        ax.axhspan(t[lo],t[hi],color='#f7c886',alpha=0.14,zorder=0)
    color = '#657789' if key=='raw' else METHODS[key]['color']
    if key=='raw':
        ax.plot(original,t,color=color,linewidth=1.4,marker='o',markersize=2.2,zorder=3)
    else:
        finite=np.isfinite(values)
        start=0
        while start<len(t):
            if not finite[start]: start+=1;continue
            stop=start+1
            while stop<len(t) and finite[stop]:stop+=1
            if stop-start>1:
                dense_t=np.linspace(t[start],t[stop-1],max(20,int((t[stop-1]-t[start])/0.008)))
                dense_y=PchipInterpolator(t[start:stop],values[start:stop])(dense_t)
                ax.plot(dense_y,dense_t,color=color,linewidth=2.0,zorder=3)
            else:
                ax.plot(values[start],t[start],'.',color=color,zorder=3)
            start=stop
    for v in [-7,-5,5,7]: ax.axvline(v,color='#e4b487',linestyle=(0,(4,4)),linewidth=0.7,zorder=0)
    ax.axvline(0,color='#d2dae2',linewidth=0.9,zorder=0)
    ax.set_xlim(-10,10); ax.set_ylim(math.ceil(t[-1]*10)/10,0)
    ax.set_xticks([-10,-5,0,5,10]); ax.set_xlabel('角度（°）'); ax.set_ylabel('视频时间（秒）↓')
    ax.set_title(title,pad=12,fontsize=12,fontweight='bold')
    ax.tick_params(labelsize=9,colors='#536273')
    for spine in ax.spines.values(): spine.set_color('#d7dfe6')
    ax.set_facecolor('#ffffff')


def write_csv(path, rows, fields):
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def self_checks():
    t=np.linspace(0,2,25)
    for value in [0.0,-5.0,10.0]:
        y=np.full(len(t),value);valid=np.ones(len(t),dtype=bool); valid[7:12]=False
        y[~valid]=np.nan
        for output in alternatives(t,y,valid,np.zeros(len(t),dtype=bool)).values():
            assert np.allclose(output,value,atol=1e-9)
    empty=alternatives(t,np.full(len(t),np.nan),np.zeros(len(t),dtype=bool),np.zeros(len(t),dtype=bool))
    assert all(np.isnan(v).all() for v in empty.values())
    y=np.linspace(-10,10,len(t));valid=np.ones(len(t),dtype=bool);valid[8:15]=False
    outside=np.zeros(len(t),dtype=bool);outside[2]=True;valid[2]=False
    for output in alternatives(t,y,valid,outside).values():
        assert np.isnan(output[2]) and np.isfinite(output[8:15]).all()
        assert np.nanmax(np.abs(output))<=10


def report_html(output, summary, dataset):
    cards=''.join(f'<article><h2>方案 {k} · {m["name"]}</h2><h3>{m["short"]}</h3><p>{m["detail"]}</p><a href="beautified_{k}.csv">下载美化数据 {k}</a></article>' for k,m in METHODS.items())
    metric_rows=[];sections=[]
    for c,info in zip(dataset,summary):
        meta=c['metadata'];rid=meta['review_id']; clock=meta['local_time'][11:]
        metric_rows.append('<tr><td>'+rid+' · '+clock+'</td><td>'+str(info['sample_count'])+'</td><td>'+str(info['missing_count'])+'</td><td>'+f'{info["raw_peak_abs_deg"]:.2f}°'+'</td>'+''.join('<td>'+f'{info["methods"][key]["peak_abs_deg"]:.2f}°'+'</td>' for key in METHODS)+'</tr>')
        local_rows=''.join('<tr><td>方案 '+key+'</td><td>'+str(m['inferred_count'])+'</td><td>'+f'{m["average_change_at_measured_deg"]:.3f}°'+'</td><td>'+f'{m["maximum_change_at_measured_deg"]:.3f}°'+'</td><td>'+f'{m["peak_change_deg"]:+.3f}°'+'</td></tr>' for key,m in info['methods'].items())
        sections.append(f'<section id="{rid}"><h2>{rid} · {clock}</h2><p>{info["sample_count"]} 个原始位置，{info["missing_count"]} 个缺失；最长连续缺失 {info["max_missing_run"]} 点。三方案使用相同原帧号和时间戳。</p><a class="figure" href="{rid}.png"><img src="{rid}.svg" alt="{rid} 原始与三种美化曲线对照"></a><p class="caption">从左到右：原始、A、B、C。淡橙横带表示原始缺失区间；浅灰线为原始有效读数。点击图片查看高清 PNG。</p><div class="table"><table><tr><th>方案</th><th>推断点</th><th>原有效点平均改动</th><th>原有效点最大改动</th><th>绝对峰值变化</th></tr>{local_rows}</table></div></section>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>最近五次录像 · 三种曲线优化对照</title><style>
body{margin:0;background:#f3f5f7;color:#243648;font:15px/1.65 "Microsoft YaHei",sans-serif}main{max-width:1480px;margin:auto;padding:28px}h1{font-size:26px;margin:0 0 12px}h2{font-size:20px}h3{font-size:15px}.options{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:22px 0}article,section{background:white;border:1px solid #dae2e9;border-radius:10px;padding:18px}section{margin:26px 0}.figure{display:block}.figure img{display:block;width:100%;height:auto}.note{background:#fff5e4;padding:12px 16px;border-left:4px solid #d59b50}.caption{font-size:13px;color:#677687}nav{display:flex;flex-wrap:wrap;gap:18px;margin:18px 0}a{color:#2467a6}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;border-bottom:1px solid #dfe5eb;padding:9px 12px}th{background:#edf2f6}.table{overflow:auto}footer{margin:24px 0;font-size:13px;color:#637384}@media(max-width:800px){main{padding:14px}.options{grid-template-columns:1fr}section{padding:10px}}
</style><main><h1>最近五次录像：原始曲线与三种美化方案</h1><p>独立对照实验，尚未替换上位机。原始数据单独保存；每种方案另存一份美化数据。选定后，展示与导出统一使用所选美化数据。</p>
<div class="note">本工作区最近五次录像的 MP4 已不在原路径，本页读取的是数据库保存的逐帧原始结果。485 个位置中有 39 个缺失，其中 14 个原因是“超出右侧标定范围”。这些区间是否实际超过 ±10°，不能靠插值确认；美化值属于推断。</div>'''
    page+=f'<div class="options">{cards}</div><p>三个方案均推断本批全部缺失点并进行数值平滑，绘图也使用平滑连线。保留 ±10°量程，不把失败当作 0°。不再沿用“连续三点不补”的旧展示规则。</p><nav>'+''.join(f'<a href="#{c["metadata"]["review_id"]}">{c["metadata"]["review_id"]} · {c["metadata"]["local_time"][11:]}</a>' for c in dataset)+'</nav>'
    page+='<div class="table"><table><tr><th>录像时间</th><th>原始点数</th><th>缺失</th><th>原始绝对峰值</th><th>A 峰值</th><th>B 峰值</th><th>C 峰值</th></tr>'+''.join(metric_rows)+'</table></div>'+''.join(sections)
    page+='''<section><h2>你选定后的保存与使用规则</h2><p>原始版：保留识别角度、拒读、帧号与时间戳，永不被美化覆盖。美化版：保存完整处理后的角度、推断标记、算法及参数版本、原始数据哈希。展示和导出使用同一份已保存的美化版，峰值等显示指标也据此计算；仍可追溯原始版和原始有效率。选择不同方案会生成新版本，不能默默改写旧原始值。</p><p>本页三份 CSV 正是三种美化数据，均保留原采样位置；绘图加密只用于连线，不增加导出采样点。</p><p>回复 A、B 或 C 即可。建议先比较 B 的连续性与峰值，再与 A、C 对照。</p></section><footer><a href="raw.csv">下载原始数据 CSV</a> · <a href="raw.json">原始快照 JSON</a> · <a href="summary.json">全部参数与指标</a> · <a href="overview.png">五次录像总览 PNG</a><p>只比较形状与读数变化，没有人工逐帧真值，不能用“更顺滑”证明更准确。没有写回业务数据库，也没有重训或安装软件。</p></footer></main></html>'''
    (output/'对照报告.html').write_text(page,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root,output=args.workspace.resolve(),args.output.resolve()
    if output.exists(): parser.error('Output already exists; preserve earlier comparisons')
    self_checks()
    dataset=read_dataset(root)
    assert len(dataset)==5
    original_hash=fingerprint(dataset)
    output.mkdir(parents=True,exist_ok=False)
    dump(output/'raw.json',dict(source_workspace=str(root),selection='Latest five completed captures, by captured_at descending',dataset_sha256=original_hash,captures=dataset))
    font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'svg.fonttype':'none'})
    raw_rows=[];derived={key:[] for key in METHODS};stats=[];plot_inputs=[]
    for capture in dataset:
        meta,samples=capture['metadata'],capture['samples'];rid=meta['review_id']
        t,y,valid,outside=sample_arrays(samples)
        results=alternatives(t,y,valid,outside)
        info=dict(review_id=rid,capture_id=meta['capture_id'],local_time=meta['local_time'],sample_count=len(t),valid_count=int(valid.sum()),missing_count=int((~valid).sum()),max_missing_run=max((r['count'] for r in gap_runs(t,valid)),default=0),gap_runs=gap_runs(t,valid),raw_peak_abs_deg=float(np.max(np.abs(y[valid]))),methods={})
        for key,values in results.items():
            assert len(values)==len(samples) and np.nanmax(np.abs(values))<=10
            assert np.isfinite(values[~outside]).all()
            info['methods'][key]=metrics(t,y,valid,values)
        for i,sample in enumerate(samples):
            base=dict(video_id=rid,capture_id=meta['capture_id'],captured_local=meta['local_time'],frame_number=sample['frame_index']+1,frame_index=sample['frame_index'],pts_ms=sample['pts_ms'])
            raw_rows.append(dict(**base,angle_deg=sample['angle_deg'],error=sample['error'],model_version=sample['model_version'],input_image=sample['input_image']))
            for key,values in results.items():
                value=float(values[i]) if np.isfinite(values[i]) else None
                inferred=bool(not valid[i] and value is not None)
                derived[key].append(dict(**base,angle_deg=value,was_inferred=inferred,source_kind='超量程隐藏' if outside[i] else '拒读推断' if inferred else '平滑实测',original_error=sample['error'],method_version=f'curve-review-{key}-v1',raw_dataset_sha256=original_hash))
        stats.append(info);plot_inputs.append((meta,t,y,valid,results))
        fig,axes=plt.subplots(1,4,figsize=(15.8,8.2),layout='constrained')
        fig.suptitle(f'{rid} · {meta["local_time"]}    原始与三种补点＋平滑对照',fontsize=16)
        draw_curve(axes[0],t,y,valid,y,'raw',f'原始：缺失 {info["missing_count"]} 点 · 峰值 {info["raw_peak_abs_deg"]:.2f}°')
        for ax,(key,values) in zip(axes[1:],results.items()):
            draw_curve(ax,t,y,valid,values,key,f'{key} · {METHODS[key]["name"]} · 峰值 {info["methods"][key]["peak_abs_deg"]:.2f}°')
        fig.savefig(output/f'{rid}.png',dpi=150);fig.savefig(output/f'{rid}.svg');plt.close(fig)
    write_csv(output/'raw.csv',raw_rows,list(raw_rows[0]))
    for key,rows in derived.items():
        write_csv(output/f'beautified_{key}.csv',rows,list(rows[0]))
        dump(output/f'beautified_{key}.json',dict(method_version=f'curve-review-{key}-v1',parameters=METHODS[key]['parameters'],source_dataset_sha256=original_hash,samples=rows))
    fig,axes=plt.subplots(5,4,figsize=(15.8,25),layout='constrained')
    fig.suptitle('最近五次录像 · 同一原始数据 · 三种推断与平滑',fontsize=18)
    for row,(meta,t,y,valid,results) in zip(axes,plot_inputs):
        clock=meta['local_time'][11:]
        draw_curve(row[0],t,y,valid,y,'raw',f'{meta["review_id"]} {clock} · 原始')
        for ax,(key,values) in zip(row[1:],results.items()):draw_curve(ax,t,y,valid,values,key,f'{key} · {METHODS[key]["name"]}')
    fig.savefig(output/'overview.png',dpi=130);plt.close(fig)
    after=read_dataset(root,[c['metadata']['capture_id'] for c in dataset])
    assert fingerprint(after)==original_hash,'Stored source readings changed during the comparison'
    summary=dict(source_workspace=str(root),raw_dataset_sha256=original_hash,stored_source_readings_unchanged=True,source_connection='SQLite mode=ro plus query_only=ON; one read transaction',source_videos_present=sum(c['metadata']['video_exists'] for c in dataset),total_samples=len(raw_rows),total_original_valid=sum(c['valid_count'] for c in stats),total_missing=sum(c['missing_count'] for c in stats),right_calibration_rejections=sum(r['error']=='超出右侧标定范围' for r in raw_rows),methods=METHODS,captures=stats,self_checks='constant signed values, true zero, all-invalid, long gaps, numeric out-of-range masking passed',numpy=np.__version__,scipy=scipy.__version__,script_sha256=sha_bytes(Path(__file__).read_bytes()),scope='Independent proposal comparison only; no production change, no DB write, no retraining or installation')
    dump(output/'summary.json',summary)
    report_html(output,stats,dataset)
    dump(output/'file-hashes.json',{str(p.relative_to(output)):sha_bytes(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps(dict(output=str(output),samples=len(raw_rows),missing=summary['total_missing'],source_hash=original_hash,metrics=[dict(video=c['review_id'],peaks={key:round(v['peak_abs_deg'],4) for key,v in c['methods'].items()}) for c in stats]),ensure_ascii=True))


if __name__=='__main__':
    main()
