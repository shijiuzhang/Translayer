# Translayer（v0.2.3）

[English](README.md) | 简体中文 | [Deutsch](README.de.md)

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Status](https://img.shields.io/badge/status-active%20development-orange.svg)](#)

**任何格式输入，任何语言输出——尽可能保持版式、排版和图片内文字。**

Translayer 是一个 AI 原生的文档本地化中间层。它把 PPTX、DOCX 和 HTML 解析成统一的 `DocumentIR`，补充布局、术语和 OCR 信息，再通过可人工审核的翻译流程进行本地化，最后写回原始文档。它不仅翻译普通文本，也能识别并修改图片中的文字。

## v0.2.3 更新

- 本地 Tesseract OCR 会放大小尺寸截图、过滤噪声、合并换行段落，并按
  文本行精确擦除原文。
- 纯文本密集截图可以重排为干净的目标语言文本画布，必要时自动增加高度。
- 翻译结果不再按字符数硬截断，排版阶段会保留完整单词和语义。
- PPTX 译文会同时遵守前景图片和视觉底框边界。
- 页面已存在双语内容时，系统会保留作者写好的目标语言，并移除相邻且
  语义匹配的源语言副本。
- API 地址、Key、模型名和引擎选择会保存在当前浏览器中，并可在三语言
  界面中一键清除。

## 主要特性

- 支持 PPTX、DOCX 和 HTML 的解析与回写。
- 支持英语、简体中文和德语互译。
- 使用精确的页面、形状、段落和表格坐标写回译文。
- 支持 PPTX SmartArt、表格、组合图形和图片资源。
- 使用本地 Tesseract 筛选图片，避免不必要的付费调用。
- 支持 OCR、局部擦除和目标语言字体重绘。
- 支持 Gemini 整图本地化，并在生成前后执行 OCR 质量检查。
- 提供人工图片审核、费用预测和严格预算上限。
- 支持任意 OpenAI Chat Completions 兼容接口，包括本机及内网部署。
- 支持 Moonshot Kimi K2.5/K2.6 的兼容请求参数。
- 支持 DeepL Free/Pro API。
- OpenAI-compatible、DeepL 和 Gemini 凭据可保存在当前浏览器中重复使用，
  可随时清除，并且不会进入公开任务响应。
- 文本和图片长任务提供真实完成数量与当前处理阶段。

## 工作流程

```text
输入文档
  → 解析为 DocumentIR
  → 语义、术语、布局和图片 OCR 增强
  → 普通文字翻译
  → 图片本地筛选与人工审核
  → 局部重绘或 Gemini 整图修改
  → OCR 质量验证
  → 写回并生成目标文档
```

图片会被路由到以下处理方式之一：

- `skip`：装饰图、图标或无有效文字，保留原图。
- `reuse`：与已处理图片完全相同，复用结果。
- `region`：OCR 后擦除局部原文并重绘译文。
- `whole_image`：使用 Gemini 修改整张图片。
- `review`：信息不足，由用户决定。

## 安装

### Windows EXE

Windows 用户可以从 GitHub Release 下载
`Translayer-v0.2.3-windows-x64.zip`，解压后双击 `Translayer.exe`。这个
EXE 会在本机启动 Translayer 服务并自动打开浏览器界面；它不会在用户电脑
上编译项目，也不会运行测试。

便携包已经内置 Tesseract OCR、英语/德语/简体中文 OCR 语言包，以及
Poppler 的 `pdftoppm.exe`。如果需要完整的 PPTX 页面预览，仍需安装
LibreOffice，或确保 `soffice.exe` 已经在 `PATH` 中。

### 从源码安装

要求 Python 3.11 或更高版本。图片筛选和页面预览建议安装 LibreOffice、Poppler、Tesseract 及相应语言包。

macOS：

```bash
brew install libreoffice poppler tesseract tesseract-lang
```

Ubuntu/Debian：

```bash
sudo apt-get update
sudo apt-get install -y \
  libreoffice poppler-utils \
  tesseract-ocr tesseract-ocr-eng \
  tesseract-ocr-chi-sim tesseract-ocr-deu
```

安装 Python 包：

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
```

如果需要调用 Gemini：

```bash
uv pip install -e ".[gemini]"
```

## 启动 Web 界面

```bash
translayer serve --host 127.0.0.1 --port 8000
```

然后打开 <http://127.0.0.1:8000>。

创建任务时可以选择以下文字翻译引擎：

1. **OpenAI 兼容 API**：填写 API 基础地址、可选 API Key 和模型名。本地接口未启用鉴权时，Key 可以留空。
2. **DeepL API**：填写 DeepL API Key，程序会根据 `:fx` 后缀自动选择 Free 或 Pro 地址。
3. **离线演示**：不调用外部服务，仅用于测试工作流。

使用 Moonshot Kimi 时选择 **OpenAI 兼容 API**，并填写：

```text
API 基础地址：https://api.moonshot.cn/v1
模型名称：    kimi-k2.6
API Key：     你的 Moonshot API Key
```

文本翻译期间，进度条显示当前页、总页数和文本块数量。图片计划锁定后，
进度条显示已完成图片数和当前 OCR、翻译、擦除、重绘、生成、质量检查或
复用阶段。`GET /jobs/{job_id}` 的 `progress.text` 和 `progress.images`
也会返回同一组进度数据。

**离线演示不进行真正的语义翻译**，只会在原文前添加目标语言标记，用于
验证上传、审核和导出流程。

Gemini API Key 是可选项，**只有选择修改复杂图片里的文字时才需要**。普通文档文字翻译不需要 Gemini Key。如果图片审核方案包含整图处理，确认窗口会再次提示输入 Key。

页面会显示：

- 预计需要修改的图片数量；
- 预计付费 API 调用次数；
- 单张图片的计划费用；
- 预计总费用；
- 用户批准的最高预算。

费用为安全规划估算，实际金额以服务商账单为准。默认单次预测可通过 `TRANSLAYER_IMAGE_ESTIMATED_COST_USD` 配置。

## 命令行使用

使用 OpenAI 兼容的本地或内网模型翻译文档：

```bash
translayer translate input.pptx -o output.pptx \
  --from en \
  --to zh \
  --engine openai \
  --api-url http://llm.internal:8000/v1 \
  --api-key optional-local-key \
  --model local-model \
  --ocr-engine tesseract
```

使用 DeepL：

```bash
translayer translate input.pptx -o output.pptx \
  --from en \
  --to de \
  --engine deepl \
  --api-key YOUR_DEEPL_KEY
```

生成零 API 调用的图片路由和费用计划：

```bash
translayer plan-images input.pptx -o cost-plan.json \
  --from en \
  --targets zh,de \
  --budget-usd 1.50
```

只翻译一张图片：

```bash
translayer translate-image input.png -o output.png \
  --from en \
  --to zh \
  --allow-paid-api \
  --max-cost-usd 0.10
```

## 配置变量

常用环境变量：

| 变量 | 用途 |
|---|---|
| `TRANSLAYER_TRANSLATION` | 默认文字翻译引擎 |
| `OPENAI_API_KEY` | 默认 OpenAI-compatible API Key |
| `OPENAI_BASE_URL` | 默认 OpenAI-compatible 基础地址 |
| `TRANSLAYER_OPENAI_MODEL` | 默认文字模型 |
| `DEEPL_API_KEY` | 默认 DeepL Key |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | 默认 Gemini Key |
| `TRANSLAYER_GEMINI_IMAGE_MODEL` | 默认 Gemini 图片模型 |
| `TRANSLAYER_IMAGE_ESTIMATED_COST_USD` | 单次图片调用的计划费用 |
| `TRANSLAYER_IMAGE_CACHE_DIR` | Gemini 图片缓存目录 |

前端输入的配置优先于这些默认值。连接信息会保存在当前浏览器的本地存储中，
可在页面上一键清除。任务提交后，密钥只进入当前服务进程的任务对象，不会写入
`DocumentIR` 或公开 API 响应。

## 当前限制

- 文档解析、首次图片筛选和最终渲染目前只显示阶段名称，没有逐项百分比。
- OCR 准确率受分辨率、字体、对比度和图片复杂度影响。小字号、密集或艺术化
  的中文可能出现乱码或残留，因此导出前仍需人工检查图片结果。
- 局部 OCR 重绘更适合少量、边界清晰的文字区域；复杂信息图通常应选择整图
  本地化，并保留人工审核。

## 项目结构

```text
src/translayer/
├── api/             FastAPI、任务状态和审核接口
├── engines/         翻译、OCR、擦除和整图引擎
├── enrich/          语义、术语和图片筛选
├── ir/              DocumentIR 模型与 JSON Schema
├── localize/        文字、图片和质量验证流程
├── parsers/         PPTX、DOCX、HTML 解析器
├── renderers/       原格式写回
└── web/             英中德三语单页界面
```

核心流水线：

```text
Parse → Enrich → Localize → Render
```

## 开发与测试

```bash
ruff check src/translayer tests
pytest -q
```

第三方扩展可以通过 `translayer.plugins` entry point 注册新的解析器、渲染器、翻译、OCR、擦除或图片本地化引擎。

## 许可证

Translayer 使用 [Apache License 2.0](LICENSE) 开源许可证。
