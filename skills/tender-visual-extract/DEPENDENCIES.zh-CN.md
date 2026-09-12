# 栅格几何依赖

此可选工具要求 Python >= 3.10，严格使用 Pillow 12.3.0；该版本是 2026-09-05 查验时 PyPI 当前发布版本。原有只用标准库的 DOCX 工具不增加依赖。Python 3.9 不支持此可选能力。使用受维护且有对应 wheel 的稳定 Python；无匹配 wheel 时能力不可用，不退回源码构建。

使用本 Agent 已配置的受支持 Python，在它自己的工作区创建私有虚拟环境。在已安装技能目录，用该环境解释器执行：

```text
-m pip install --index-url https://pypi.org/simple --only-binary=:all: --require-hashes -r requirements-geometry.lock
```

明确授权的依赖安装会访问官方包基础设施，测量本身离线。锁文件包含官方 12.3.0 PyPI JSON 的 86 个未撤销 wheel 的 SHA-256，不含源码包，也无传递 Python 包依赖。解释器/平台不匹配时安装失败。选择该可选工具时检查所需依赖；仅在具体执行故障需要诊断时使用非敏感小样本，不要求事先冒烟。不要发布环境，也不要把凭据或运行时路径复制进技能。

Pillow 许可表达式为 MIT-CMU，须保留上游许可声明。二进制 wheel 可能包含另有许可的图像库，需保留 wheel 的许可文件和内嵌 SBOM。`PILLOW-LICENSE.txt` 保留上游 Pillow 许可，不替代 wheel 自带声明。未来升级前重新检查依赖安全公告，精确锁、独立 review 和冒烟一起更新。

官方 12.3.0 说明包含 PDF 解压、EPS 循环、JPEG2000 资源消耗、多类内存访问和 Windows 查看器命令注入的修复。本工具只接收 PNG/JPEG，不调用查看器、OCR、图像显示、PDF 解析或网络函数。版本固定与大小限制不能保证不存在未来解码漏洞，调用方必须设置文档要求的执行超时。

2026-09-05 核验来源：[PyPI 版本元数据](https://pypi.org/pypi/Pillow/12.3.0/json)、[版本说明](https://pillow.readthedocs.io/en/stable/releasenotes/12.3.0.html)、[许可](https://pillow.readthedocs.io/en/stable/about.html#license)。私有来源快照和验证环境只供审计，不进入发布资产。

## 运行时与私有工作区

先查当前回合 `<env>` 的 Managed runtimes，使用其中真实可执行且版本 >=3.10 的 Python 路径，并实际运行版本命令。没有时，通过真实 GUI 的“运行环境”安装 Python（Hatch），等待成功后开启新回合刷新环境信息；不存在名为 Runtime 的 Agent 安装工具，不虚构调用。依赖安装失败须保留命令、退出码和真实错误，能力记为未就绪，不借用 Codex、开发树或其他 Agent 的解释器。

只有本轮上下文已登记的本 Agent 私有 workspace 可放虚拟环境、pip 缓存、临时文件、页图和结果；不能把它们放进发布源根或技能目录，也不使用未登记的全局临时目录。创建新私有目录，将 TEMP/TMP/TMPDIR 与 pip cache 显式设在该目录；从实际解释器执行 `-m venv` 后，用新环境解释器安装锁。路径先验证、正确引用，不猜 home。逐条保存准备、安装、导出和测量的真实退出码/错误；失败修好后仍保留首次失败，不将重试成功写成所有命令均成功。
