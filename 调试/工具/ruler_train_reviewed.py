"""Train one new offline ruler candidate using the final human review archive."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, output = args.data_root.resolve(), args.output.resolve()
    if output.exists():
        parser.error('Preserve existing results: output must not exist')
    previous = base / '训练实验_第三轮_复核后'
    archive = base / '最终复核归档_20261016'
    final_path = archive / '最终读数.json'
    final = json.loads(final_path.read_text(encoding='utf-8'))
    original = json.loads((previous / 'labels.json').read_text(encoding='utf-8'))['samples']
    previous_results = json.loads((previous / 'training-results.json').read_text(encoding='utf-8'))
    latest = {r['id']: r for r in final['rows']}
    assert len(original) == len(latest) == 62
    assert set(latest) == {r['id'] for r in original}
    algorithm_paths = [base / '训练实验_第一轮' / 'train_reader.py',
        base / '训练实验_第二轮' / 'segmented_reader.py', base / '训练实验_第二轮' / 'train_round2.py']
    protected = {p for root in (previous, archive) for p in root.rglob('*') if p.is_file()}
    protected.update(algorithm_paths)
    samples = []
    for row in original:
        reviewed = latest[row['id']]
        angle = reviewed['effective_human_angle_deg']
        assert type(angle) in (float, int) and math.isfinite(angle)
        assert sha(Path(row['source_image'])) == row['image_sha256'] == reviewed['source_sha256']
        assert row['source_image'] == reviewed['source_image']
        protected.add(Path(row['source_image']))
        samples.append(dict(row, angle_deg=angle, previous_round_angle_deg=row['angle_deg'],
            label_source='final_review_archive_effective_human_angle',label_file=str(final_path),label_file_sha256=sha(final_path),
            second_review_status=reviewed['second_review_status'],effective_value_source=reviewed['effective_value_source'],
            second_review_angle_deg=reviewed['second_review_angle_deg'],include_in_this_training_run=True))
    before = {str(p): sha(p) for p in sorted(protected)}
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(base / '训练实验_第二轮'))
    from segmented_reader import SignedReader, image
    from train_round2 import metrics
    images = {r['id']: image(r['source_image']) for r in samples}
    rows, folds = [], []
    for held in sorted({r['video_id'] for r in samples}):
        train = [r for r in samples if r['video_id'] != held]
        test = [r for r in samples if r['video_id'] == held]
        assert not {r['image_sha256'] for r in train} & {r['image_sha256'] for r in test}
        model = SignedReader(train, [images[r['id']] for r in train])
        for row in test:
            result = model.predict(images[row['id']])
            value = result['angle_deg']
            assert value is None or math.isfinite(value)
            result.update(id=row['id'], video_id=held, human_angle_deg=row['angle_deg'],
                difference_deg=None if value is None else value-row['angle_deg'],
                second_review_status=row['second_review_status'],train_ids=[r['id'] for r in train])
            assert all(not key.startswith(held+'_') for key in result['train_ids'])
            rows.append(result)
        folds.append(dict(held_video=held,training=len(train),test=len(test),same_video_or_identical_image_leakage=False))
        print(f'Trained on 3 videos, held out {held}: {len(test)} predictions',flush=True)
    assert len(rows) == len({r['id'] for r in rows}) == 62
    rescored = []
    for r in previous_results['predictions']:
        human = latest[r['id']]['effective_human_angle_deg']
        rescored.append(dict(r,human_angle_deg=human,difference_deg=None if r['angle_deg'] is None else r['angle_deg']-human))
    assert metrics(rescored)['within_half_degree'] == final['summary']['rescored_within_half_degree']
    summary = {}
    for name, group in (('retrained', rows), ('previous_frozen_predictions_same_labels',rescored)):
        summary[name] = dict(overall=metrics(group),negative=metrics([r for r in group if r['human_angle_deg']<0]),
            zero=metrics([r for r in group if r['human_angle_deg']==0]),positive=metrics([r for r in group if r['human_angle_deg']>0]))
    assert before == {str(p): sha(p) for p in sorted(protected)}, 'Historical input changed'
    output.mkdir(parents=True,exist_ok=False)
    dump(output/'labels.json',dict(samples=samples,total=62,latest_reviewed=12,previous_human_values_carried_without_rereview=50,
        authorization='2026-10-16 user explicitly requested continuing training after final review archive.',
        historical_freeze_policy_preserved=True,label_status='human_read_not_independent_angle_ground_truth'))
    model = SignedReader(samples,[images[r['id']] for r in samples])
    model.save(output)
    metadata = json.loads((output/'signed-model.json').read_text(encoding='utf-8'))
    metadata.update(version='20261016-signed-r4-final-review-trained',algorithm_sources_sha256={str(p):sha(p) for p in algorithm_paths},
        training_label_file=str(output/'labels.json'),training_label_sha256=sha(output/'labels.json'),
        final_human_review_archive_sha256=sha(final_path),label_status='12_latest_reviewed_50_prior_human_not_rereviewed',
        deployment_status='offline_experimental_not_deployed')
    dump(output/'signed-model.json',metadata)
    loaded = SignedReader.load(output)
    for r in samples:
        assert model.predict(images[r['id']]) == loaded.predict(images[r['id']]),r['id']
    invalid = {}
    for name, im in dict(black=np.zeros((1080,1280),np.uint8),white=np.full((1080,1280),255,np.uint8),wrong_size=np.zeros((480,640),np.uint8)).items():
        invalid[name]=loaded.predict(im)
        assert invalid[name]['angle_deg'] is None
    times=[]
    for i in range(186):
        start=time.perf_counter();loaded.predict(images[samples[i%62]['id']]);times.append((time.perf_counter()-start)*1000)
    benchmark=dict(count=186,p50_ms=float(np.percentile(times,50)),p95_ms=float(np.percentile(times,95)),max_ms=max(times),
        scope='PC algorithm only, excludes decode, camera, transfer and display; not board timing')
    dump(output/'training-results.json',dict(summary=summary,predictions=rows,previous_predictions_rescored=rescored,folds=folds,
        benchmark=benchmark,invalid_images=invalid,algorithm_changed=False,
        validation_scope='Same-session leave-one-video-out development validation; not independent accuracy acceptance'))
    with (output/'逐图验证结果.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['图片编号','留出视频','采用人工角度','本轮估计_空值为拒读','差值','是否差值不超过0.5度','原因','本轮标签来源'])
        for r in rows:
            writer.writerow([r['id'],r['video_id'],r['human_angle_deg'],r['angle_deg'],r['difference_deg'],
                r['angle_deg'] is not None and abs(r['difference_deg'])<=.5+1e-9,r['reason'],r['second_review_status']])
    inference = '''"""Single-image inference using the saved round-four model; no training."""
from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
meta=json.loads((ROOT/'signed-model.json').read_text(encoding='utf-8'))
for path,sha in meta['algorithm_sources_sha256'].items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise RuntimeError('Algorithm source changed: '+path)
sys.path.insert(0,str(ROOT.parent/'训练实验_第二轮'))
from segmented_reader import SignedReader,image
if len(sys.argv)!=2:raise SystemExit('Usage: python predict.py IMAGE.png')
try: result=SignedReader.load(ROOT).predict(image(sys.argv[1]))
except (OSError,ValueError) as error: result=dict(angle_deg=None,reason=str(error))
print(json.dumps(result,ensure_ascii=False,allow_nan=False))
'''
    (output/'predict.py').write_text(inference,encoding='utf-8')
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',17)
    sheet=Image.new('RGB',(2040,2420),(22,27,34));draw=ImageDraw.Draw(sheet)
    ordered=sorted(rows,key=lambda r:(r['angle_deg'] is not None,-abs(r['difference_deg'] or 0),r['id']))
    for i,r in enumerate(ordered):
        x,y=(i%6)*340,(i//6)*220
        with Image.open(next(s['source_image'] for s in samples if s['id']==r['id'])) as source:
            thumb=source.convert('RGB').crop((100,180,1120,680)).resize((340,166))
            sheet.paste(thumb,(x,y+54))
        value=r['angle_deg'];good=value is not None and abs(r['difference_deg'])<=.5+1e-9
        color=(114,228,160) if good else (255,189,99)
        text=f'人工{r["human_angle_deg"]:+g}° / 拒读' if value is None else f'人工{r["human_angle_deg"]:+g}° / 估计{value:+.2f}°'
        draw.text((x+5,y+2),r['id'],fill='white',font=font)
        draw.text((x+5,y+26),text,fill=color,font=font)
    sheet.save(output/'62张预测总览.jpg',quality=92)
    current=summary['retrained']['overall'];old=summary['previous_frozen_predictions_same_labels']['overall']
    lines=[]
    for title,key in (('负数','negative'),('零点','zero'),('正数','positive'),('合计','overall')):
        m=summary['retrained'][key]
        mae='—' if m['mae_deg'] is None else f'{m["mae_deg"]:.3f}°'
        maximum='—' if m['max_abs_difference_deg'] is None else f'{m["max_abs_difference_deg"]:.3f}°'
        lines.append(f'| {title} | {m["readings"]}/{m["total"]} | {m["rejected"]} | {mae} | {maximum} | {m["within_half_degree"]}/{m["total"]} |')
    problems=[r for r in rows if r['angle_deg'] is None or abs(r['difference_deg'])>.5+1e-9]
    problem_lines=[]
    for r in problems:
        value='拒读' if r['angle_deg'] is None else f'{r["angle_deg"]:+.3f}°'
        problem_lines.append(f'| {r["id"]} | {r["human_angle_deg"]:+g}° | {value} | {r["reason"]} |')
    report=f'''# 第四轮：按最终人工复核值继续训练

依据用户最新指令继续训练。本轮完整使用62张原图，12张采用最新复核值，50张沿用先前人工值并保留“本轮未复核”来源；不再要求重新标注。原模型、历史结果和原来的停止训练策略作为历史记录保留，本轮授权及训练集合单独记录。

## 训练与验证结果

使用原分段算法，仅更新人工标签及标定/参考参数。四段视频每次取三段训练，剩余整段验证，轮换四次；同视频帧和相同哈希原图不进入对应训练折。统计采用留出预测，不采用装入全部参考后的训练集表现。

| 范围 | 输出/总数 | 拒读 | 输出样本平均绝对差值 | 最大绝对差值 | 全部样本差值≤0.5° |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(lines)}

统一以本次人工标签评分，旧模型冻结预测为{old['within_half_degree']}/62差值≤0.5°、{old['readings']}张输出；本轮重训为{current['within_half_degree']}/62、{current['readings']}张输出。旧模型平均差值{old['mae_deg']:.3f}°、最大{old['max_abs_difference_deg']:.3f}°；本轮平均差值{current['mae_deg']:.3f}°、最大{current['max_abs_difference_deg']:.3f}°。不能把更换标签后的分数变化直接称为模型改善。

PC算法186次：中位数{benchmark['p50_ms']:.2f}ms，95百分位{benchmark['p95_ms']:.2f}ms。仅算法，不含取流、解码、传输和显示，不是开发板测速。

## 简单原理

1. **建立“照片→角度”对照。** 用你给的正负角度，把原图中阴影外观和读数对应起来；左负右正，不用下方刻度或珠子中心代替读点。
2. **能找边缘时按位置换算。** 背景对比找阴影的最右边缘，用已知位置及角度建立标定表；新位置落在两个参考位置之间时，在两者之间插值。
3. **边缘不好分时比局部外观。** 主要用于左侧负值：缩小局部阴影区域，做亮度标准化，找最接近的两张参考图；较像的参考权重更大，给出估计。此分支尚未验证精确最右侧读点，不等于能把模糊刻度恢复清楚。
4. **不可靠就拒读。** 画面异常、超出标定、外观与参考差太多，或两张相似参考的角度差太大时，输出空值和原因；真实0°才输出0。

这是轻量的标定与近邻匹配训练，没有训练大型神经网络。训练主要更新参考图片特征、角度及对应关系；不是让程序凭空看清图片里丢失的细节。

## 仍超差或拒读的样本

| 图片编号 | 人工角度 | 本轮预测 | 原因 |
| --- | ---: | ---: | --- |
{chr(10).join(problem_lines)}

## 交付及边界

- [逐图验证结果.csv](逐图验证结果.csv)：62条留出预测及原因。
- [62张预测总览](62张预测总览.jpg)：只裁切缩放显示，没有锐化恢复细节。
- `signed-model.json`、`signed-model.npz`：已保存本轮全量训练模型。
- `predict.py`：加载保存的模型做单图估计，不重新训练；调用方式为`python predict.py 原图.png`，依赖已安装的NumPy/OpenCV及原实验目录。
- `verification.json`：62张保存重载一致、三类异常图拒读、折间隔离及历史输入哈希核验。

差值相对于你的人工读数；同次安装的四段视频、经看过分歧后修订的标签，仍属于开发验证。全量程逐张±0.5°尚未通过独立验收。没有将本候选部署到上位机或开发板，不再要求你反复复核这一批照片。
'''
    (output/'第四轮训练结果与简单原理.md').write_text(report,encoding='utf-8')
    assert before == {str(p):sha(p) for p in sorted(protected)}, 'Historical input changed'
    dump(output/'verification.json',dict(original_images_verified=62,model_save_reload_matches=62,invalid_images_rejected=3,
        folds=folds,protected_input_files_unchanged=len(before),protected_input_sha256=before,
        training_script_sha256=sha(Path(__file__)),algorithm_sources_unchanged=True,
        final_review_archive_preserved=True,new_training_authorized=True,device_or_app_deployed=False))
    dump(output/'artifact-index.json',{p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in output.iterdir() if p.is_file()})
    print(json.dumps(dict(summary=summary,benchmark=benchmark,output=str(output)),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
