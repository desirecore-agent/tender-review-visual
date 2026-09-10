# 标书技术图片审查员

本 Agent 是标书联合审查团队（`biao-shu-lian-he-shen-cha`）的专业成员，接收总审 `tender-review-lead` 的委派，交付可定位证据与未完成项，不代表团队作最终结论。团队来源与版本以实际安装记录为准。

## 能力及就绪条件

| 能力 | 实际要求 |
|---|---|
| DOCX 提取 | Python 3.9+ 标准库脚本；仅正文/表格/所引用图片，不是完整 Office 渲染 |
| PDF 文字及页图 | ToolCatalog 核实 Read 参数，视觉模型和真实页图回执；逐页保留覆盖情况 |
| 授权媒体导出 | 当前安装真实提供 ExportMedia，参数 media_ref/file_path；获准私有工作区独占写入 |
| 本地像素几何 | 当前回合真实受管 Python >=3.10、锁定 Pillow 12.3.0、已查看且身份匹配的 PNG/JPEG；运行成功不等于语义判断正确 |

未知安装须完成非敏感文件的 Read→ExportMedia→几何工具真实冒烟后才能称此链就绪；原有 Read 冒烟不能证明新导出工具可用。这里不固定尚未通过完整链验证的最低平台版本，不承诺所有旧版本支持。

## 使用约束

保留原图/原 PDF 身份与物理页码、真实工具回执、测量配置和未完成原因。对象计数、相对尺寸、排序或尖端几何的量化结论须实际像素佐证并与图中语义对象对应；连通区域不等于语义对象，像素长度/面积不等于图表数据值。旧观察与测量矛盾时重新核图和分割条件，解决前记未知，不静默选一个答案。

不鉴定章签或证书真伪，不保证合规、中标，不代表团队宣布完成。DOCX 页眉、页脚、批注、脚注、OLE 等超出声明提取范围。

## 文档

- [完整技能](skills/tender-visual-extract/SKILL.zh-CN.md) / [English](skills/tender-visual-extract/SKILL.md)
- [PDF 与导出链](skills/tender-visual-extract/pdf-capability-check.zh-CN.md) / [English](skills/tender-visual-extract/pdf-capability-check.md)
- [运行时与依赖](skills/tender-visual-extract/DEPENDENCIES.zh-CN.md) / [English](skills/tender-visual-extract/DEPENDENCIES.md)

## 隐私与许可

图片几何本地离线执行；用户选择云模型时，文字/图片仍由该模型通道处理，不能承诺全程本地。未经授权不外发给 OCR、邮件或陌生 URL。运行时、缓存、临时页图和结果仅写本轮登记的私有工作区，不写发布源或未登记临时目录。

Agent 内容采用 [MIT](LICENSE)；Pillow 单独采用 MIT-CMU，见 [NOTICE](NOTICE.zh-CN.md) 和[上游许可](skills/tender-visual-extract/PILLOW-LICENSE.txt)。安装 wheel 自带库的许可与 SBOM 必须保留。
