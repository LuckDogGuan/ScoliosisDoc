"""One-time, source-preserving import of the user's exported second review."""
from pathlib import Path
from datetime import datetime
from collections import Counter
import csv
import hashlib
import json
import math

BASE = Path('D:/code/Scoliosis/PythonProject/视频切片评估_20261016')
REVIEW = BASE / '脊柱尺_复核结果.json'
PREVIOUS = BASE / '结果复核_20261016'
EXPERIMENT = BASE / '训练实验_第三轮_复核后'
OUTPUT = BASE / '最终复核归档_20261016'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    assert not OUTPUT.exists(), 'Preserve existing output; never overwrite a finalized review'
    raw = REVIEW.read_bytes()
    review = json.loads(raw.decode('utf-8-sig'))
    old_audit = json.loads((PREVIOUS / 'audit.json').read_text(encoding='utf-8'))
    policy = json.loads((PREVIOUS / 'review-policy.json').read_text(encoding='utf-8'))
    samples = json.loads((EXPERIMENT / 'labels.json').read_text(encoding='utf-8'))['samples']
    predictions = json.loads((EXPERIMENT / 'training-results.json').read_text(encoding='utf-8'))['predictions']
    by_id = {r['id']: r for r in samples}
    predicted = {r['id']: r for r in predictions}
    prior_policy = {r['id']: r for r in policy['rows']}
    expected_hash = hashlib.sha256((EXPERIMENT / 'labels.json').read_bytes() + (EXPERIMENT / 'training-results.json').read_bytes()).hexdigest()
    assert review['schema'] == 'ruler-result-review-v1'
    assert review['dataset_sha256'] == policy['dataset_sha256'] == old_audit['dataset_sha256'] == expected_hash
    assert review['secondary_training_enabled'] is False
    assert len(review['rows']) == len({r['id'] for r in review['rows']}) == 62
    assert {r['id'] for r in review['rows']} == set(by_id) == set(predicted) == set(prior_policy)
    protected = dict(old_audit['input_sha256'])
    protected.update({str(p): sha(p) for p in PREVIOUS.iterdir() if p.is_file()})
    protected[str(REVIEW)] = hashlib.sha256(raw).hexdigest()
    assert all(sha(Path(path)) == value for path, value in protected.items())
    merged = []
    for r in sorted(review['rows'], key=lambda x: x['id']):
        key = r['id']; sample = by_id[key]; prediction = predicted[key]
        assert r['source_sha256'] == sample['image_sha256'] == sha(Path(sample['source_image'])), key
        assert r['human_angle_deg'] == sample['angle_deg'], key
        assert r['model_angle_deg'] == prediction['angle_deg'], key
        assert r['difference_deg'] == prediction['difference_deg'], key
        assert r['model_reason'] == prediction['reason'], key
        assert r['priority'] is prior_policy[key]['priority_review'], key
        assert r['include_in_secondary_training'] is False, key
        status, final = r['review_status'], r['final_angle_deg']
        assert status in ('pending', 'confirmed', 'corrected', 'unreadable'), key
        if status in ('confirmed', 'corrected'):
            assert type(final) in (float, int) and math.isfinite(final) and abs(final) <= 90, key
            if status == 'confirmed':
                assert final == sample['angle_deg'], key
        else:
            assert final is None, key
        if status == 'pending':
            assert r['reviewed_at'] is None, key
        else:
            assert isinstance(r['reviewed_at'], str), key
            assert datetime.fromisoformat(r['reviewed_at'].replace('Z', '+00:00')).utcoffset() is not None, key
        assert not r['priority'] or status != 'pending', 'Priority review incomplete: ' + key
        effective = sample['angle_deg'] if status == 'pending' else final
        difference = None if effective is None or prediction['angle_deg'] is None else prediction['angle_deg'] - effective
        merged.append(dict(id=key, source_image=sample['source_image'], source_sha256=r['source_sha256'],
            previous_human_angle_deg=sample['angle_deg'], second_review_status=status,
            second_review_angle_deg=final, effective_human_angle_deg=effective,
            effective_value_source='previous_human_label_not_rereviewed' if status == 'pending' else 'user_second_review',
            reviewed_at=r['reviewed_at'], priority_review=r['priority'],
            model_angle_deg=prediction['angle_deg'], model_reason=prediction['reason'],
            previous_model_difference_deg=prediction['difference_deg'], model_difference_vs_effective_human_deg=difference,
            include_in_secondary_training=False))
    counts = dict(Counter(r['second_review_status'] for r in merged))
    errors = [abs(r['model_difference_vs_effective_human_deg']) for r in merged if r['model_difference_vs_effective_human_deg'] is not None]
    summary = dict(total=62, priority_reviewed=sum(r['priority_review'] and r['second_review_status'] != 'pending' for r in merged),
        review_status_counts=counts, changed_values=sum(r['second_review_status'] == 'corrected' and r['second_review_angle_deg'] != r['previous_human_angle_deg'] for r in merged),
        previous_values_carried_without_rereview=counts.get('pending', 0),
        model_predictions_unchanged=True, model_readings=sum(r['model_angle_deg'] is not None for r in merged),
        model_rejections=sum(r['model_angle_deg'] is None for r in merged),
        rescored_within_half_degree=sum(e <= .5 + 1e-9 for e in errors),
        rescored_over_half_degree=sum(e > .5 + 1e-9 for e in errors),
        rescored_mae_deg=sum(errors)/len(errors) if errors else None,
        rescored_max_abs_difference_deg=max(errors) if errors else None,
        secondary_training_enabled=False, independent_accuracy_acceptance=False, app_or_board_changed=False)
    assert summary['priority_reviewed'] == 12
    assert sum(counts.values()) == len(merged) == 62
    assert all(r['second_review_angle_deg'] is None for r in merged if r['second_review_status'] == 'pending')
    assert all(sha(Path(path)) == value for path, value in protected.items()), 'Input changed during import'
    OUTPUT.mkdir(exist_ok=False)
    (OUTPUT / '用户导出原件.json').write_bytes(raw)
    write_json(OUTPUT / '最终读数.json', dict(schema='ruler-final-human-readings-v1', dataset_sha256=expected_hash,
        review_export_sha256=hashlib.sha256(raw).hexdigest(), summary=summary, rows=merged))
    with (OUTPUT / '最终读数.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['图片编号','原人工角度','本轮复核状态','本轮复核角度_空值为本轮未复核或无法判读','采用的人工角度','采用值来源','原模型估计_空值为拒读','模型与采用人工值差值','本轮复核时间','参与照片二次训练'])
        for r in merged:
            writer.writerow([r['id'],r['previous_human_angle_deg'],r['second_review_status'],r['second_review_angle_deg'],r['effective_human_angle_deg'],r['effective_value_source'],r['model_angle_deg'],r['model_difference_vs_effective_human_deg'],r['reviewed_at'],False])
    table = '\n'.join(f"| {r['id']} | {r['previous_human_angle_deg']:+g}° | {r['second_review_angle_deg']:+g}° | {'确认' if r['second_review_status']=='confirmed' else '修正'} |" for r in merged if r['second_review_status'] in ('confirmed','corrected'))
    report = f'''# 最终复核归档 · 2026-10-16

本批按用户“就这样了”的指令收尾，不再要求补标、圈点或继续训练。

优先复核12张全部完成：**{counts.get('corrected',0)}张修正，{counts.get('confirmed',0)}张确认**。其余{counts.get('pending',0)}张沿用已有人工角度，并明确标为“本轮未复核”；没有伪造为本轮已确认。

## 本轮复核结果

| 图片编号 | 原人工角度 | 本轮角度 | 操作 |
| --- | ---: | ---: | --- |
{table}

## 交付与保留

- [最终读数.csv](最终读数.csv)：全部62张，原角度、本轮复核值、采用的人工角度及模型估计分列保存。
- [最终读数.json](最终读数.json)：附来源、原图哈希、复核时间，所有照片均保持不参与二次训练。
- [用户导出原件.json](用户导出原件.json)：逐字节归档用户导出的JSON，不修改原件。
- [导入核验.json](导入核验.json)：数据集哈希、62张ID/原图哈希/模型值绑定及历史文件未变检查。

## 模型结论不因标签变化而改变

没有重新训练，也没有改变任何模型预测。仅用这次人工值重新评分：{summary['rescored_within_half_degree']}/62差值≤0.5°，{summary['rescored_over_half_degree']}张仍超差，5张模型拒读；输出样本最大差值{summary['rescored_max_abs_difference_deg']:.3f}°。这只是标签修订后的对照，不能宣称模型进步或精度验收通过。

本轮人工为原来的5张拒读图填写了读数，但模型仍然是拒读，未把人工值冒充自动输出。原始50/62验证记录、历史标签、权重、照片及复核页面均保留原样。正式上位机和开发板未替换算法。本批结果复核归档完成；独立精度验收仍未通过。
'''
    (OUTPUT / '最终复核说明.md').write_text(report, encoding='utf-8')
    write_json(OUTPUT / '导入核验.json', dict(review_export=str(REVIEW),review_export_sha256=hashlib.sha256(raw).hexdigest(),
        dataset_sha256=expected_hash,summary=summary,checks=dict(unique_ids=62,source_image_hashes=62,
        export_bound_to_archived_predictions=62,priority_review_complete=12,unreviewed_final_values_null=counts.get('pending',0),
        archived_inputs_unchanged=len(protected),source_preserving_export=True),protected_input_sha256=protected,script_sha256=sha(Path(__file__))))
    write_json(OUTPUT / 'artifact-index.json', {p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in OUTPUT.iterdir() if p.is_file()})
    print(json.dumps(dict(output=str(OUTPUT),summary=summary),ensure_ascii=False,indent=2))
