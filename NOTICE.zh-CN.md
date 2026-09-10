# Notice（声明）

本项目是基于 DesireCore 构建的标书审查系统的一部分。

## 第三方依赖

### Python 标准库

DOCX 提取使用 Python 标准库；可选栅格几何测量另外要求 Pillow，见下文。

使用的模块：`zipfile`、`xml.etree.ElementTree`、`json`、`hashlib`、`argparse`、`codecs`、`re`、`stat`、`struct`

### 运行平台

- **DesireCore** — 提供工具框架、PDF Read 能力和智能体协调的 Agent 操作系统。DesireCore 及其组件单独授权，具体版本遵循其自带 LICENSE；本 Agent 的 MIT 许可不重新许可平台或第三方组件。
- **Python 3.9+** — `extract_docx.py` 所需的运行时。
- **Vision 能力 LLM** — PDF 页图渲染和图像查看所需。模型选择由用户配置；具体模型名称和供应商为运行时配置，非捆绑依赖。

## 云模型声明

当用户选择云模型时，审查过程中处理的文本和图片由该模型的处理通道处理。本项目不承诺全程本地处理。

## 不构成背书

使用本软件不构成合规保证、投标接受或监管批准。本工具提供提取和查看能力，不做合规或投标资格判定。

可选本地栅格测量使用 Pillow 12.3.0（MIT-CMU），见 skills/tender-visual-extract/DEPENDENCIES.zh-CN.md 和 skills/tender-visual-extract/PILLOW-LICENSE.txt。已安装 wheel 保留其内含库的许可与 SBOM。源图片和测量输出属于任务数据，不随技能分发。工具只提供像素连通区域几何统计，不提供 OCR、对象识别、真伪鉴定或投标验收结论。
