# GitHub 维护说明

目标仓库：[LuckDogGuan/ScoliosisDoc](https://github.com/LuckDogGuan/ScoliosisDoc)，SSH 地址 `git@github.com:LuckDogGuan/ScoliosisDoc.git`，主分支 `main`。

本次分组提交、来源核对与验证范围见 [2026-10-19 整理记录](../调试/记录/github-organization-20261019/整理记录.json)。

## 本次整理范围

2026-10-19 用户确认“保留完整的历史，然后发布即可”。本次采用快进合并，将原工作分支 `codex/capture-stability-20261013` 的完整提交历史并入 `main`，按验收记录、资料导航分别提交；不重写旧提交或移动旧 tag。历史现场 Wi-Fi 配置、设备标识和板端备份亦按该确认保留，不能将本仓库称为已经脱敏的公开资料集。

保留 SDK、虚拟机、镜像、安装器、构建缓存和既有本地证据的排除规则；不删除这些本地文件，不新增下位机工程或正式包镜像。资料原路径保持不变，新增导航通过相对链接连接。

## 后续日常提交

在仓库根目录，先查看状态和差异，再按实际文件名暂存同一用途的一组文件：

```powershell
git status --short --branch
git diff --stat
git add -- README.md docs/资料导航.md
git diff --cached --check
git diff --cached --stat
```

提交前按 `AGENTS.md` 调用 GitNexus `detect_changes(scope="staged", repo="Luckfox")`。改函数前还需先做符号 impact；文档和原始二进制的影响范围以 staged 路径及字节核对补充。确认范围后提交，再推送：

```powershell
git commit -m "docs: update project navigation"
git push origin main
```

首推采用 `git push -u origin main`。不要重复 `remote add`；可用 `git remote -v` 核对。远端已有独立历史时先 fetch 和审查，不使用强制推送。工作分支及 tag 按实际需要逐个发布，不使用 `--mirror`。

## 大文件及证据

当前资料以普通 Git 保存，未新增 LFS 指针或迁移历史。未来新增大文件先确认归属：正式固件在 WSL、上位机交付在 Flutter、本机下载包按来源导航获取。需要长期跟踪的大型资产再单独规划 Git LFS，避免直接提交 SDK 或虚拟机。

新归档的三组历史记录各有 `ARCHIVE-SHA256.json`，记录归档时的原始文件字节。`.gitattributes` 对这三组设为 `-text`，防止 Windows 换行转换破坏哈希。校验清单本身不包含在自己的哈希列表中，后续新增文件应另留增量记录。
