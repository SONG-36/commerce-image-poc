# Commerce Image POC

> 阶段：低成本 AI 可行性验证 / 两页式原型探索  
> 范围：跨境电商商品图包制作（当前参考 TikTok Shop、Temu 的相似制图工作）  
> 状态：**T01 首张真实图片已获用户 PASS；T02 第一页已实现，真实 AI 规划与修改实验待授权。T03、T04 未启动**。

## 1. 我们要解决什么

运营以真实商品图片、Listing、商品描述、设计参考图及制作要求为输入，使用 AI 形成逐图方案、生成图包、逐图审核与修改，最终导出可用图片。

现有工作方式中，运营反馈过**多图前后不一致、长对话上下文混乱及修改难控制**。这些是业务痛点陈述，发生频率、成因和改善幅度还需要实际任务验证。

本项目的目标不是搭建通用 AI 平台，而是验证一个简单的两页式工具能否降低商品图包制作的返工和操作成本。**即使最终只需改进现成工具的使用流程，也属于有效结论。**

## 2. 最小产品形态

- **页面一 Prepare & Plan**：上传商品资料、N 张设计参考图和整体要求；AI 辅助理解商品与参考图，形成可编辑的逐图制作计划。
- **页面二 Generate & Review**：按逐图计划生成真实图片；每图可 `Pass` 或提交修改意见；保留原图与修改版本；导出通过的图片。

详细边界和首次验收见 [`docs/01_PRODUCT_BRIEF.md`](docs/01_PRODUCT_BRIEF.md)。

## 3. 项目地图

```text
commerce-image-poc/
├── README.md                  # 入口与项目地图
├── AGENTS.md                  # Codex 工作边界
├── .gitignore                 # 忽略秘密及运行证据
├── .env.example               # 本地配置文件，已忽略；不纳入 Git
├── docs/
│   ├── 01_PRODUCT_BRIEF.md    # 已讨论的产品雏形及首轮 DoD
│   ├── 02_CURRENT_STATE.md    # 唯一当前状态与下一项任务
│   └── 03_EXPERIMENT_LOG.md   # 真实调用与运营评价的最简记录
├── requirements.txt          # T01 的 Python 依赖
├── src/generate_image.py     # 默认本地检查，显式开启后才付费生图
├── src/prepare_plan.py       # T02 本地准备与规划页面
├── src/templates/prepare.html # 中文页面
├── src/static/               # 原生 JavaScript 与样式
├── tests/test_generate_image.py # 离线安全检查
├── tests/test_prepare_plan.py # 规划、修改与保存的离线检查
└── .runtime/                 # Git 忽略；实物素材、成图及运行证据
    ├── inputs/
    ├── outputs/
    └── evidence/
```

`.runtime/` 为本地数据，不纳入 Git；真实素材与关键证据需要自行安全备份。

## 4. T01 运行说明

Python 3.12；首次准备依赖（已有 `.venv` 时复用）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

仅执行免费本地检查，无需 API Key，不创建 API 客户端：

```bash
.venv/bin/python src/generate_image.py --reference ref_01.webp
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
```

本地检查读取 `.runtime/inputs/case-001/` 的三张商品图、四张参考图及 `listing.md`、`requirements.md`，核验文本和图片可读性，保存文件 SHA-256、拟发送指令及参数。请求只选择三张商品图和**一张**参考图，参考图可用 `--reference ref_01.webp` 至 `ref_04.webp` 指定。原始输入不被修改。离线测试使用本地 Mock transport，结果不是真实模型证据。

**以下命令仅在用户确认新的付费调用及发送真实资料后执行。** T01 已有一次真实实验及用户 PASS，见 `docs/03_EXPERIMENT_LOG.md`；本轮未重新生图。先在当前终端安全设置 `OPENAI_API_KEY` 环境变量；程序不自动读取 `.env`，也不保存密钥。

当前 `.env.example` 含疑似真实密钥，已通过忽略规则保护，内容未改动；不要将其作为可提交的空样例。

```bash
.venv/bin/python src/generate_image.py --reference ref_01.webp --model gpt-image-2.5-sunburst --run-paid
```

使用 OpenAI 官方 Python SDK 的 `images.edit`，固定官方地址 `https://api.openai.com/v1`；支持的模型配置为 `gpt-image-2.5-sunburst`（默认，或由 `OPENAI_IMAGE_MODEL` 指定）和 `gpt-image-2.5-flare`，命令行 `--model` 优先。接口与参数依据 [OpenAI 官方图像生成文档](https://developers.openai.com/api/docs/guides/image-generation)。固定 `n=1`、`quality=low`、`size=1024x1536`、`output_format=png`，采用竖版画幅参考 `ref_01` 的版式；SDK `max_retries=0`，超时 180 秒，不自动重试或切换模型。依赖包含 SOCKS 支持以适配现有代理环境。

首图以商品图保持外观，以参考图借鉴设计；Listing 仍是待核验资料，首轮省略数字与功能宣传，仅允许中性日文品名。指令约束的实际效果需在真实成图后由运营检查。

每次本地检查或真实尝试均创建独立 UTC 时间戳与 UUID 目录：

- `.runtime/evidence/case-001/<run-id>/`：`run.json` 保存状态、开始/结束时间、总耗时、模型、输入标识、参数及可获取的 request ID、usage、错误、输出路径；`request.json` 与 `prompt.txt` 保存请求；真实返回后保留 `response.json`，失败时保存 `error.json`。
- `.runtime/outputs/case-001/<run-id>/image.png`：真实返回的图片字节；不覆盖历史。记录图片 SHA-256 并检查 PNG、尺寸及可解码性；验证失败保留已返回字节且标为失败。

`LOCAL_CHECK_ONLY` 表示未调用模型。`API_IMAGE_SAVED_AWAITING_REVIEW` 仅表示实际图片已保存，不代表运营接受或业务价值通过；usage 缺失时记为 `null`，不编造费用。

本地 Git 的 `main` 尚无提交，仅配置了 origin，**尚未恢复远程历史**；不要初始提交或推送。待连接恢复后，另行安全获取并同步远程历史。

## 5. 先不做

旧工程迁移、C01～C05 强制流水线、复杂 Context Engine、Skill/Agent/RAG、评价平台、复杂权限、全量工作流和平台规则自动化。需要时必须以真实问题为依据重新决定。

参考原则：既有 `FDE_BUSINESS_FIRST_AI_ENGINEERING_METHOD_V0.1.md`；旧 `00_PRODUCT_ENGINEERING_CHARTER_V0.1.md` 仅作为历史线索，**不继承其技术方案或工程计划**。

## 6. T02 准备与规划页面

沿用当前 Python 环境，增加 Flask 和原生 HTML/CSS/JavaScript；无前端构建步骤、数据库或后台任务服务。

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/prepare_plan.py --port 8010
```

浏览器打开 `http://127.0.0.1:8010`。页面仅绑定本机，关闭调试模式。默认规划模型为 `gpt-4.1-mini`；可用 `OPENAI_PLANNING_MODEL` 指定该模型或已核实的快照 `gpt-4.1-mini-2025-04-14`。官方说明确认它支持 [图片输入与 Responses API](https://developers.openai.com/api/docs/models/gpt-4.1-mini)，请求使用 [多图片 data URL 输入](https://developers.openai.com/api/docs/guides/images-vision) 与简单 JSON 输出，不引入独立 Agent 或复杂 Schema。

**免费准备与本地检查**：

1. 点击「加载 case-001 示例资料」；三张商品图、四张参考图及两份文本加载为独立副本。也可上传任意数量的商品/参考图片，输入 Listing、描述和整体要求；至少需要一张商品图及一张参考图。
2. 图片支持 JPG、PNG、WebP，单张不超过 20 MB，一次资料保存总请求不超过 80 MB；这是体积限制，不固定图片数量。可从当前资料副本移除图片，不删除原图。
3. 「保存资料为新任务」不调用模型。更改输入后新建独立任务，旧任务和输入保留；刷新恢复最近已保存的当前任务。尚未保存的表单文字需先保存再刷新。
4. 本地测试：`.venv/bin/python -m unittest discover -s tests -v`；`.venv/bin/python -m pip check`。测试中的 SDK MockTransport 不是真实 AI 交互或质量验收。

**第一次真实规划实验（本轮未执行，待用户确认）**：

1. 确认将当前业务资料发往 OpenAI 并批准调用费用；由运行人员在启动服务的终端安全设置 `OPENAI_API_KEY`，再启动上述服务。程序不读取 `.env`、`.env.example` 或从前端接收密钥。
2. 加载 case-001，点击「AI 理解与规划」。一次真实 `client.responses.create` 请求结合商品理解、参考理解和 N 张计划；不强制拆三次调用。
3. 检查商品、Listing 声称与实拍外观是否分开，参考图的参数/功能是否未被继承。所有内容为待运营确认的候选结果。
4. 在商品理解或单张参考理解下填写自然语言意见，点击「根据意见修正理解」；各自调用一次 AI，只改指定理解。旧计划不静默重写，需点击「按当前理解重新规划全部」，或逐张修改相关计划，再确认。
5. 在目标计划卡片填写意见，点击「根据意见修改计划」。一次请求携带原始商品信息、商品实拍、对应参考图、整体要求、当前修正理解、旧计划及本次意见；只写回目标计划，其他计划不覆盖。可继续修改，并在卡片展开旧计划及意见。
6. 刷新核对保存结果；点击「确认计划」保存整套当前计划，不调用模型。页面显示「出图计划已保存，可进入图片生成阶段。」；T03 尚未开发，确认不生成任何图片。

页面加载、刷新、加载资料、保存资料、确认计划都不会产生模型费用。只有各 AI 按钮明确触发 POST 才调用模型；每次 SDK `max_retries=0`、超时 120 秒，不自动重试或切换模型。失败显示实际错误并保留原计划。重复/过期页面操作在调用前拒绝，避免旧结果覆盖新修改。

数据保存在 `.runtime/prepare-plan/`：

- `sessions/<id>/inputs/`：不可变的上传图片副本与原始文本；商品图与参考图区分保存。
- `sessions/<id>/state.json` 与 `versions/`：当前理解/计划、逐次旧版本、运营意见、计划确认状态。
- `sessions/<id>/calls/<call-id>/`：Prompt、完整 SDK 请求快照（含实际图片 data URL）、图片顺序/MIME/SHA-256、源码 SHA-256、响应、可获取的 usage/request ID、耗时、错误及应用版本。没有返回的信息留空，不编造内部思考。
- `current.json`：最近保存任务的指针，只用于刷新恢复；读取不会触发模型。

当前 T02 只完成本地开发及免费验证。真实模型的账户访问、理解准确性、自然语言修正效果、计划质量与实际费用均为 **PENDING**，须真实实验后再记录。
