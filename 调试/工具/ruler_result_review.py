"""Replay archived ruler validation and create an offline result-review page.

Writes only a new output directory. Never saves a model or changes labels/photos.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def preview(path, box=None):
    with Image.open(path) as source:
        im = source.convert("RGB")
        if box:
            im = im.crop(box)
        im.thumbnail((1000, 840))
        stream = io.BytesIO()
        im.save(stream, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


PAGE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>脊柱尺 · 结果复核</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#17212e;font:16px/1.6 "Microsoft YaHei",sans-serif}
header{background:#153349;color:white;padding:20px 28px}header h1{margin:0;font-size:25px}header p{margin:5px 0 0;color:#d9e5ec}
main{max-width:1480px;margin:auto;padding:20px}.bar,.actions,.stats{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
button,select,input{font:inherit;border:1px solid #b5c2cc;border-radius:7px;padding:9px;background:white}button{cursor:pointer}
button:hover{background:#e8f3f8}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #df8b2b;outline-offset:2px}
.primary{background:#126749;color:white}.primary:hover{background:#0c5038}.stats{margin:15px 0}.stat{padding:10px 18px;background:white;border-radius:8px}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:18px}.card{background:white;border-radius:10px;padding:18px}
h2{margin:0 0 12px;font-size:19px}p{margin:8px 0}.warning{color:#9a4a00}.muted{color:#586573;font-size:14px}
.images{display:grid;grid-template-columns:1fr 1fr;gap:12px}.images img{width:100%;background:#111;object-fit:contain;max-height:610px}
.images figure{margin:0}.images figcaption{color:#586573;font-size:14px}dl{display:grid;grid-template-columns:120px 1fr;gap:10px;margin:12px 0}dt{color:#586573}dd{margin:0;font-weight:600}
.actions{margin-top:16px}.actions button{width:100%}input{max-width:100%;width:100%}#caseId{overflow-wrap:anywhere}#message{min-height:24px}
@media(max-width:1000px){.layout{grid-template-columns:1fr}.images{grid-template-columns:1fr}}
</style>
<header><h1>脊柱尺 · 结果复核</h1><p>停止这批照片的追加训练。保留已有人工读数，只复核结果；无需改文件名或圈读点。</p></header>
<main>
<div class="bar"><label>查看 <select id="scope"><option value="priority">优先复核 12 张</option><option value="all">全部 62 张</option></select></label>
<button id="prev">上一张</button><button id="next">下一张</button><span id="position"></span>
<button id="json">导出复核记录 JSON</button><button id="csv">导出结果 CSV</button></div>
<div class="stats"><span class="stat">差值≤0.5°：50/62</span><span class="stat">超差：7 张</span><span class="stat">拒读：5 张</span><span class="stat" id="progress"></span></div>
<div class="layout"><section class="card"><h2 id="caseId"></h2><div class="images">
<figure><img id="original" alt="原图全景预览"><figcaption>原图全景预览；图片未锐化，点击下方可打开原始 PNG。</figcaption></figure>
<figure><img id="zoom" alt="阴影和刻度局部放大"><figcaption>阴影及刻度局部放大；放大不会恢复模糊细节。</figcaption></figure>
</div><a id="raw" target="_blank" rel="noopener">打开原始 PNG</a></section>
<section class="card"><h2>本张结果</h2><dl><dt>已有人工读数</dt><dd id="human"></dd><dt>模型估计</dt><dd id="estimate"></dd><dt>与人工差值</dt><dd id="difference"></dd><dt>当前情况</dt><dd id="reason"></dd><dt>复核状态</dt><dd id="status"></dd></dl>
<p class="warning">模型估计尚未通过全量程验证。看不清就选“无法判读”，不用猜角度。</p>
<label for="correction">需要修正时填写角度（保留正负号）</label><input id="correction" type="number" min="-90" max="90" step="any" placeholder="例如 -3.5 或 0">
<div class="actions"><button class="primary" id="confirm">确认已有人工读数</button><button id="correct">保存修正角度</button><button id="unreadable">无法判读，结果留空</button><button id="pending">撤回复核，恢复待复核</button></div>
<p id="message" role="status" aria-live="polite"></p><p class="muted">本页自动保留当前浏览器中的复核记录，请导出文件留存。复核结果不会写回标签、训练模型或正式软件。</p>
</section></div>
<p class="muted">这些是同次安装、四段视频的留出预测。50/62 表示与已有人工标签的差值≤0.5°，不是独立精度验收。超差或拒读照片保留在完整统计中。</p>
</main><script id="dataset" type="application/json">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('dataset').textContent),rows=data.rows;
const $=id=>document.getElementById(id),key='ruler-result-review:'+data.dataset_sha256;
let saved={},index=0,storageWarning='';
try{const value=JSON.parse(localStorage.getItem(key)||'{}');if(value&&typeof value==='object'&&!Array.isArray(value))saved=value;}
catch(e){storageWarning='浏览器无法读取保存记录，请及时导出文件。';}
for(const [id,r] of Object.entries(saved)){
 if(!r||!['confirmed','corrected','unreadable'].includes(r.status)||!rows.some(x=>x.id===id)||
 (r.status==='unreadable'?r.final_angle_deg!==null:!Number.isFinite(r.final_angle_deg))||
 (r.status==='confirmed'&&r.final_angle_deg!==rows.find(x=>x.id===id).human_angle_deg)||
 (r.status==='corrected'&&Math.abs(r.final_angle_deg)>90))delete saved[id];
}
const selected=()=>rows.filter(r=>$('scope').value==='all'||r.priority);
const fmt=v=>v===null?'—':(v>0?'+':'')+Number(v.toFixed(3))+'°';
function render(){const list=selected();index=(index+list.length)%list.length;const r=list[index],s=saved[r.id];
 $('caseId').textContent=r.id;$('position').textContent=(index+1)+' / '+list.length;
 $('original').src=r.preview;$('zoom').src=r.zoom;$('raw').href=r.raw_uri;
 $('human').textContent=fmt(r.human_angle_deg);$('estimate').textContent=r.angle_deg===null?'拒读 · 未输出角度':fmt(r.angle_deg);
 $('difference').textContent=fmt(r.difference_deg);$('reason').textContent=r.review_reason;
 $('status').textContent=s?({confirmed:'已确认',corrected:'已修正',unreadable:'无法判读'}[s.status]):'待复核';
 $('correction').value=s&&s.status==='corrected'?s.final_angle_deg:'';
 $('progress').textContent='优先已复核 '+rows.filter(r=>r.priority&&saved[r.id]).length+'/12 · 总计 '+Object.keys(saved).length+'/62';
 $('message').textContent=storageWarning;
}
function save(status,angle){const r=selected()[index];if(status==='pending')delete saved[r.id];
 else saved[r.id]={status,final_angle_deg:angle,reviewed_at:new Date().toISOString()};
 try{localStorage.setItem(key,JSON.stringify(saved));storageWarning='';}catch(e){storageWarning='浏览器无法保存记录，请立即导出文件。';}
 render();$('message').textContent=storageWarning||'已保存；可点击下一张继续。';
}
function records(){return rows.map(r=>({id:r.id,source_sha256:r.source_sha256,human_angle_deg:r.human_angle_deg,
 model_angle_deg:r.angle_deg,difference_deg:r.difference_deg,priority:r.priority,model_reason:r.model_reason,
 review_status:saved[r.id]?.status||'pending',final_angle_deg:saved[r.id]?.final_angle_deg??null,
 reviewed_at:saved[r.id]?.reviewed_at||null,include_in_secondary_training:false}));}
function download(content,type,name){const u=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');
 a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
$('prev').onclick=()=>{index--;render();};$('next').onclick=()=>{index++;render();};$('scope').onchange=()=>{index=0;render();};
$('confirm').onclick=()=>save('confirmed',selected()[index].human_angle_deg);
$('unreadable').onclick=()=>save('unreadable',null);$('pending').onclick=()=>save('pending',null);
$('correct').onclick=()=>{const text=$('correction').value,v=Number(text);if(text.trim()===''||!Number.isFinite(v)||Math.abs(v)>90){
 $('message').textContent='请填写 -90 至 +90 之间的有效角度，零点请填 0。';return;}save('corrected',v);};
$('json').onclick=()=>download(JSON.stringify({schema:'ruler-result-review-v1',dataset_sha256:data.dataset_sha256,
 secondary_training_enabled:false,rows:records()},null,2),'application/json','脊柱尺_复核结果.json');
$('csv').onclick=()=>{const head=['图片编号','原图SHA256','已有人工读数','模型估计','与人工差值','优先复核','模型原因','复核状态','最终复核角度','复核时间','参与照片二次训练'];
 const body=records().map(r=>[r.id,r.source_sha256,r.human_angle_deg,r.model_angle_deg,r.difference_deg,r.priority,r.model_reason,r.review_status,r.final_angle_deg,r.reviewed_at,false]);
 const quote=v=>v===null?'':'"'+String(v).replaceAll('"','""')+'"';
 download('\ufeff'+[head,...body].map(r=>r.map(quote).join(',')).join('\r\n'),'text/csv;charset=utf-8','脊柱尺_复核结果.csv');};
render();
</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.experiment.resolve(), args.output.resolve()
    if output.exists() or root == output or root in output.parents:
        parser.error("Use a new output directory outside the archived experiment")
    samples = json.loads((root / "labels.json").read_text(encoding="utf-8"))["samples"]
    archived = json.loads((root / "training-results.json").read_text(encoding="utf-8"))
    rows = archived["predictions"]
    by_id = {r["id"]: r for r in samples}
    assert len(samples) == len(by_id) == len(rows) == len({r["id"] for r in rows}) == 62
    assert set(by_id) == {r["id"] for r in rows}
    protected = {p for p in root.rglob("*") if p.is_file()}
    for folder in (root.parent / "训练实验_第一轮", root.parent / "训练实验_第二轮"):
        protected.update(folder.glob("*.py"))
    for r in samples:
        for field, expected in (("source_image", "image_sha256"), ("label_file", "label_file_sha256")):
            path = Path(r[field])
            assert digest(path) == r[expected], str(path)
            protected.add(path)
    before = {str(p): digest(p) for p in sorted(protected)}
    sys.path.insert(0, str(root.parent / "训练实验_第二轮"))
    sys.dont_write_bytecode = True
    from segmented_reader import SignedReader, image
    from train_round2 import metrics

    images = {key: image(r["source_image"]) for key, r in by_id.items()}
    replayed = []
    fold_checks = []
    for held in sorted({r["video_id"] for r in samples}):
        train = [r for r in samples if r["video_id"] != held]
        model = SignedReader(train, [images[r["id"]] for r in train])
        test = [r for r in rows if r["video_id"] == held]
        for r in test:
            assert r["human_angle_deg"] == by_id[r["id"]]["angle_deg"]
            assert set(r["train_ids"]) == {x["id"] for x in train}
            assert all(by_id[key]["video_id"] != held for key in r["train_ids"])
            result = model.predict(images[r["id"]])
            assert json.loads(json.dumps(result)) == {k: v for k, v in r.items() if k not in (
                "id", "video_id", "human_angle_deg", "difference_deg", "train_ids", "method")}, r["id"]
            value = result["angle_deg"]
            assert value is None or math.isfinite(value)
            expected_diff = None if value is None else value - r["human_angle_deg"]
            assert r["difference_deg"] == expected_diff
            replayed.append(r)
        fold_checks.append(dict(held_video=held,training=len(train),test=len(test),exact_replay=True))
        print(f"Replayed {held}: {len(test)} archived predictions", flush=True)
    actual = metrics(replayed)
    assert actual == archived["comparison"]["retrained_with_reviewed_labels"]["overall"]
    old = metrics(archived["previous_predictions_rescored"])
    assert old == archived["comparison"]["previous_predictions_rescored_with_reviewed_labels"]["overall"]
    loaded = SignedReader.load(root)
    invalid = {}
    for name, im in dict(black=np.zeros((1080,1280),np.uint8),white=np.full((1080,1280),255,np.uint8),wrong_size=np.zeros((480,640),np.uint8)).items():
        invalid[name] = loaded.predict(im)
        assert invalid[name]["angle_deg"] is None
    point_root = root / "读点标记_只需2张"
    point_requests = json.loads((point_root / "manifest.json").read_text(encoding="utf-8"))["requests"]
    point_unchanged = all(digest(point_root / r["annotation_file"]) == r["annotation_original_sha256"] for r in point_requests)
    priority = [r for r in rows if r["angle_deg"] is None or abs(r["difference_deg"]) > .5 + 1e-9]
    assert len(priority) == 12
    dataset_hash = hashlib.sha256(((root / "labels.json").read_bytes() + (root / "training-results.json").read_bytes())).hexdigest()
    reason_names = {"left_neighbors_disagree":"相近图像对应的参考角度不一致", "left_shadow_outside_reference_appearance":"阴影外观超出参考范围", "outside_calibrated_right_edge":"超出已标定位置"}
    review_rows = []
    for r in sorted(rows, key=lambda x:(x["angle_deg"] is not None, -abs(x["difference_deg"] or 0), x["id"])):
        source = Path(by_id[r["id"]]["source_image"])
        bad = r in priority
        reason = reason_names.get(r["reason"], r["reason"]) if r["angle_deg"] is None else ("与人工差值超过0.5°" if bad else "与已有人工差值≤0.5°；仍待人工确认")
        review_rows.append(dict(id=r["id"],human_angle_deg=r["human_angle_deg"],angle_deg=r["angle_deg"],difference_deg=r["difference_deg"],
            priority=bad,review_reason=reason,model_reason=r["reason"],source_sha256=digest(source),raw_uri=source.as_uri(),
            preview=preview(source),zoom=preview(source,(100,180,1120,680))))
    assert before == {str(p): digest(p) for p in sorted(protected)}, "Archived input changed"
    output.mkdir(parents=True, exist_ok=False)
    payload = json.dumps(dict(dataset_sha256=dataset_hash,rows=review_rows),ensure_ascii=False,allow_nan=False).replace("<", "\\u003c")
    (output / "结果复核.html").write_text(PAGE.replace("__DATA__",payload),encoding="utf-8")
    policy = dict(schema="ruler-result-review-policy-v1",created_at=datetime.now(timezone.utc).isoformat(),dataset_sha256=dataset_hash,
        secondary_training_enabled=False,point_annotation_required=False,automatic_label_changes=False,production_deployment_allowed=False,
        all_samples_retained_for_evaluation=62,priority_review_count=12,scope="Freeze this photo batch; review results only. No automatic production use.",
        rows=[dict(id=r["id"],source_sha256=r["source_sha256"],priority_review=r["priority"],review_status="pending",final_angle_deg=None,include_in_secondary_training=False) for r in review_rows])
    write_json(output / "review-policy.json",policy)
    with (output / "逐图复核清单.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(["图片编号","已有人工读数","模型估计_空值为拒读","与人工差值","优先复核","原因","复核状态","最终复核角度","参与照片二次训练"])
        for r in review_rows:
            writer.writerow([r["id"],r["human_angle_deg"],r["angle_deg"],r["difference_deg"],r["priority"],r["review_reason"],"待复核",None,False])
    write_json(output / "audit.json",dict(dataset_sha256=dataset_hash,source_experiment=str(root),script_sha256=digest(Path(__file__)),
        replayed_predictions=62,folds=fold_checks,overall=actual,previous_predictions_same_labels=old,priority_review_ids=[r["id"] for r in priority],
        invalid_images=invalid,old_point_requests_unmodified=point_unchanged,input_files_unchanged=len(before),input_sha256=before,
        new_model_saved=False,labels_changed=False,app_or_board_changed=False))
    report = f"""# 脊柱尺审核与处理结果 · 2026-10-16

结论：停止这批照片的追加/二次训练，转为结果复核。62张原图、人工角度、历史权重和历史统计完整保留。无需继续改图片文件名或圈读点；第三轮报告中的两张圈点请求已被本处理决定取代。

## 审核发现

1. **精度仍不达标。** 独立重放四个按视频留出折，62条预测及原因与第三轮逐条完全一致。57张输出、5张拒读；50/62与人工差值≤0.5°，7张超差，最大2°。具体例子：`V02_f000199_t007283ms`人工−3°，模型−1°。
2. **重训没有整体改善。** 统一用当前复核标签评分：第二轮原预测51/62差值≤0.5°，平均差值{old['mae_deg']:.3f}°；第三轮50/62，平均差值{actual['mae_deg']:.3f}°。平均数仅统计输出样本，拒读仍计入总数。
3. **负端尚未证明看对读点。** `segmented_reader.py`的负端分支返回`point=None`，用局部外观与两个邻近样本匹配。它不是已经验收的最右侧阴影定位；不能通过继续重填角度或剔除难样本宣布精度通过。
4. **验证边界有限。** 没有同视频帧进入对应训练折；但四段视频来自同次安装，标签已在看到分歧后复核，算法选择也参考过验证表现。这是开发复现，不是独立角度基准或新批次盲测。

## 已执行处理

- 冻结本批62张的追加训练，`review-policy.json`全部标记`include_in_secondary_training=false`；模型、标签和原图不删除、不改写。
- 全部62张继续保留在统计中，其中7张超差、5张拒读列为优先复核，禁止用排除它们后的数字代替原结果。
- 生成[结果复核页](结果复核.html)和[逐图清单](逐图复核清单.csv)。默认只看12张问题图，可切到全部62张；已有人工读数、模型估计、最终复核值分开保存，未复核最终值为空。
- 可确认已有人工值、保存修正角度或标记无法判读；拒读和无法判读保留空值，真实零点保留0。浏览器保存进度并可导出JSON/CSV，导出不会触发训练或修改原标签。
- 对原始输入及历史文件完成SHA256前后核对，共{len(before)}个文件未改变；模型黑图、白图、错误尺寸拒读复测通过。

## 使用与限制

打开`结果复核.html`即可，无需安装依赖或联网。先处理默认12张，其余50张可按需查看；“与人工差值≤0.5°”不等于程序已自动确认正确。浏览器本地记录可能被清理，请导出留存。原始PNG链接依赖原数据路径，页面内全景和局部预览可独立查看。

当前没有将这个实验模型接入上位机或开发板，也没有进行新一轮模型训练或实板全量程验收。正式算法不凭本批结果替换。历史训练脚本保留用于追溯；本页与本工具均不提供重训入口。
"""
    (output / "审核与处理结果.md").write_text(report,encoding="utf-8")
    write_json(output / "artifact-index.json",{p.name:dict(bytes=p.stat().st_size,sha256=digest(p)) for p in output.iterdir() if p.is_file()})
    print(json.dumps(dict(output=str(output),replayed=62,within_half_degree=actual["within_half_degree"],priority=len(priority),protected_files=len(before)),ensure_ascii=False))


if __name__ == "__main__":
    main()
