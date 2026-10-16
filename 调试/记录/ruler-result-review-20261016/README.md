# 脊柱尺：审核后停止追加训练，改为结果复核

日期：2026-10-16。依据用户当前指令，先审核关联聊天“评估脊柱尺识别方案”及本地第三轮证据，随后收敛交付。

> 后续已导入用户的12张二次复核：10张修正、2张确认，结果归档完成。见[最终复核归档记录](../ruler-result-review-final-20261016/README.md)。下文保留为归档前审核记录。

## 审核结论

- 四个按视频留出折的62条预测与记录逐条复现，包括拒读原因和定位/匹配信息。
- 57张输出、5张拒读；50/62与人工差值≤0.5°，7张超差，最大差值2°。
- 按同一组当前人工标签评分，第二轮原预测为51/62、MAE 0.213°；重训后50/62、MAE 0.236°，没有整体改善。
- 负端用局部外观匹配，返回`point=None`；尚未证明定位了实际最右侧阴影读点。全量程精度未通过，不替换正式算法。
- 已确认每个验证折都排除了整段对应视频，但这四段仍属同次安装，且标签曾在看过分歧后复核，不是独立盲测。

## 已执行

停止本批照片的追加/二次训练；62张均在策略中标为不参与追加训练，原图、已有人工角度、模型和完整统计不删除、不改写。保留全部超差/拒读图作结果复核，取消此前继续改名和两张圈读点的待办。历史脚本仅作追溯，本次工具没有保存模型的入口。

新增独立Windows/PC工具：[ruler_result_review.py](../../工具/ruler_result_review.py)。只读取历史材料、复现验证并写入一个全新输出目录，不接入上位机或板端调用链。所有现有识别函数未修改。

交付目录：`D:\code\Scoliosis\PythonProject\视频切片评估_20261016\结果复核_20261016`。

- `结果复核.html`：离线单文件页面，默认12张问题图，可查看全部62张；确认已有人工值、修正或无法判读，浏览器保存进度并导出JSON/CSV。
- `逐图复核清单.csv`：完整62张，初始最终值为空。
- `审核与处理结果.md`：审核、决策和边界。
- `review-policy.json`：冻结策略及逐图状态；页面导出不会自动写回标签或触发训练。
- 原评估目录的`当前处理状态.md`及首页提示已指向本次交付，取代旧补标/圈点要求。

本仓库仅保存工具和审计JSON，不复制原图、实验模型或整个HTML到Git。

## 验证与限制

- `audit.json`：62条重放、四折排除关系、三个无效输入拒读，以及216个历史/原图/标签文件SHA256前后不变。
- `page-logic-verification.json`：页面原有脚本在隔离存储中的14项逻辑检查通过，包括真实零值、无法判读空值、空输入拦截、精度保留、撤回、保存重载、损坏/不可用存储、62条JSON/CSV导出及训练标志关闭。测试不改用户复核记录。
- `review-artifact-index.json`：外部交付文件哈希索引。
- 浏览器安全策略禁止打开`file:`URL，未绕过；本轮没有完成浏览器实际渲染/点击验收。页面交互使用隔离脚本测试，不能冒充真实浏览器验收。
- 未部署、未烧录、未验证实板端到端读数或新批次精度。页面模型数值为开发预测，最终复核值必须有明确人工动作才记录；浏览器存储可能被清理，需导出留存。

## 复现命令

```powershell
& 'C:\Users\31186\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B `
  'D:\code\Scoliosis\Luckfox\调试\工具\ruler_result_review.py' `
  --experiment 'D:\code\Scoliosis\PythonProject\视频切片评估_20261016\训练实验_第三轮_复核后' `
  --output '<一个尚不存在的输出目录>'

& 'C:\Users\31186\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' `
  'D:\code\Scoliosis\Luckfox\调试\记录\ruler-result-review-20261016\verify_review_page.cjs' `
  'D:\code\Scoliosis\PythonProject\视频切片评估_20261016\结果复核_20261016\结果复核.html'
```

此前PythonProject的`.venv`指向已不存在的Administrator Python，本次使用已验证可用的Codex运行时及现有OpenCV、NumPy、Pillow，没有改动该虚拟环境或安装依赖。
