# Commerce Image POC

> 阶段：低成本 AI 可行性验证 / 两页式原型探索  
> 范围：跨境电商商品图包制作（当前参考 TikTok Shop、Temu 的相似制图工作）  
> 状态：**T01 首图用户 PASS；T02 已有确认计划；T03 已核实四张真实成图，业务验收待完成；T04 与任务中心、等待反馈已本地实现，真实图片修改质量及完整运营闭环待人工验证**。
> I01：**PRODUCT INTEGRATION IMPLEMENTED / BUSINESS VALIDATION PENDING**。快速重设计已本地接入，Mac mini 本轮未部署；仅一个真实样本获用户正面反馈，不代表普遍商业效果通过。
> I02：**IMPLEMENTED / REAL EDIT VALIDATION PENDING**。两种模式共用的图片修改已支持文字加一张辅助图；本轮仅免费离线验证，未部署 Mac mini。

## 1. 我们要解决什么

运营以真实商品图片、Listing、商品描述、设计参考图及制作要求为输入，使用 AI 形成逐图方案、生成图包、逐图审核与修改，最终导出可用图片。

现有工作方式中，运营反馈过**多图前后不一致、长对话上下文混乱及修改难控制**。这些是业务痛点陈述，发生频率、成因和改善幅度还需要实际任务验证。

本项目的目标不是搭建通用 AI 平台，而是验证一个简单的两页式工具能否降低商品图包制作的返工和操作成本。**即使最终只需改进现成工具的使用流程，也属于有效结论。**

## 2. 最小产品形态

- **任务模式**：新建时选择「商品图包制作」或「快速重设计」。后者无需 Listing 或 T02 规划，按 N 张原图直接进入共用的生成与审核页；使用方式见第 13 节。历史任务缺少模式字段时仍按商品图包制作处理。
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
├── src/generate_plan_image.py # T03 逐图生成，复用 T01 客户端
├── src/templates/prepare.html # 中文页面
├── src/templates/generate.html # 已确认计划的第二页
├── src/static/               # 原生 JavaScript 与样式
├── tests/test_generate_image.py # 离线安全检查
├── tests/test_prepare_plan.py # 规划、修改与保存的离线检查
├── tests/test_generate_plan_image.py # 逐图生成的离线检查
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

本地 Git 的 `main` 已有 T01～T04 本地提交（T03：`ede6f6a`；T04：`7a692f3`），**尚未恢复远程历史**；本轮获授权提交 T04 并部署，不推送。待连接恢复后，另行安全获取并同步远程历史。

## 5. 先不做

旧工程迁移、C01～C05 强制流水线、复杂 Context Engine、Skill/Agent/RAG、评价平台、复杂权限、全量工作流和平台规则自动化。需要时必须以真实问题为依据重新决定。

参考原则：既有 `FDE_BUSINESS_FIRST_AI_ENGINEERING_METHOD_V0.1.md`；旧 `00_PRODUCT_ENGINEERING_CHARTER_V0.1.md` 仅作为历史线索，**不继承其技术方案或工程计划**。

## 6. T02 准备与规划页面

沿用当前 Python 环境，增加 Flask 和原生 HTML/CSS/JavaScript；无前端构建步骤、数据库或后台任务服务。

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/prepare_plan.py --port 8010
```

浏览器打开 `http://127.0.0.1:8010`。页面仅绑定本机，关闭调试模式。2026-10-15 起默认规划模型为 `gpt-5.4-mini`，设置 `reasoning.effort=low`；通过 `OPENAI_PLANNING_MODEL` 可显式回退 `gpt-4.1-mini` 或 `gpt-4.1-mini-2025-04-14`，回退请求不携带 reasoning 参数，不自动切换或重试。模型允许列表集中在 `src/prepare_plan.py`。官方确认新模型支持 [图片输入与 Responses API](https://developers.openai.com/api/docs/models/gpt-5.4-mini)，仍使用原有多图片 data URL、`instructions`、JSON 对象输出、`store=false` 和 6000/2500 输出 token 上限，不改变输入或 T03/T04 图像模型。新模型实际质量、速度、账户权限和费用待人工验证；它不承诺比 4.1 mini 更便宜。

**免费准备与本地检查**：

首页现在是任务中心。先点击「创建新任务」或打开已有任务，进入准备页后执行以下步骤；新建页不自动恢复上次任务。任务名称、商品/参考图片及三个文本字段保存到独立 Task ID，case-001 加载入口仍在准备页。

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
6. 刷新核对保存结果；点击「确认计划」保存整套当前计划，不调用模型。页面显示「出图计划已保存，可进入图片生成阶段。」；点击「进入图片生成」访问第二页，切换页面不生成图片。

页面加载、刷新、加载资料、保存资料、确认计划都不会产生模型费用。只有各 AI 按钮明确触发 POST 才调用模型；每次 SDK `max_retries=0`、超时 120 秒，不自动重试或切换模型。失败显示实际错误并保留原计划。重复/过期页面操作在调用前拒绝，避免旧结果覆盖新修改。

数据保存在 `.runtime/prepare-plan/`：

- `sessions/<id>/inputs/`：不可变的上传图片副本与原始文本；商品图与参考图区分保存。
- `sessions/<id>/state.json` 与 `versions/`：当前理解/计划、逐次旧版本、运营意见、计划确认状态。
- `sessions/<id>/calls/<call-id>/`：Prompt、完整 SDK 请求快照（含实际图片 data URL）、图片顺序/MIME/SHA-256、源码 SHA-256、响应、可获取的 usage/request ID、耗时、错误及应用版本。没有返回的信息留空，不编造内部思考。
- `current.json`：最近保存任务的指针，只用于刷新恢复；读取不会触发模型。

当前现存 T02 数据中已有真实理解/规划的保存记录和四张确认计划；用户曾反馈操作体验良好。这不代表所有 T02 验收项自动通过，理解修正、单张计划修改质量及普遍业务效果仍需分别验证。

## 7. T03 第二页：逐张生成

继续启动同一个 Flask 服务，无新增依赖或架构：

```bash
.venv/bin/python src/prepare_plan.py --port 8010
```

若旧服务仍在运行，请先停止并重新启动以载入新代码。打开 `http://127.0.0.1:8010` 的任务中心，创建或打开任务；确认整套当前计划后点击「进入图片生成」。第二页 `/generate/<session-id>` 按实际参考图数量展示独立卡片。返回准备页或首页可继续同一任务，也可切换其他任务。

**本轮不执行真实付费生成。** 用户确认真实实验并在服务端终端安全配置环境密钥后，再点击目标卡片的「生成图片」。每次请求仅使用当前商品原图、Listing/描述、整体要求、本张参考图、本张确认计划及保存的对应理解，不重新规划，不把其他图片或它们的修改历史发送给模型。

复用 T01 的 `make_client`、已核实模型列表和请求参数：默认 `gpt-image-2.5-sunburst`，`n=1`、`quality=low`、`size=1024x1536`、PNG、SDK 零自动重试。`OPENAI_IMAGE_MODEL` 可指定 T01 支持的模型。本轮不改写 T01 生图代码，不自动批量生成。

生成结果及证据保存在 `.runtime/prepare-plan/sessions/<session-id>/generations/<confirmed-revision>/<reference-id>/runs/<run-id>/`：

- `plan.json`：本张确认计划、确认版本和本次使用的原始文本/理解；不混入其他图片的历史。
- `inputs/`：本次实际商品图、单张参考图及 Listing/描述/运营要求副本；原始资料不改动。
- `prompt.txt`、`request.json`：实际客户端指令、模型参数、图片顺序/MIME/SHA-256、计划与 Prompt SHA-256。
- `run.json`、`response.json`、`error.json`（失败时）：开始/结束与实际耗时、API 尝试状态、可获取 request ID/usage、SDK 解析后的响应或真实错误。没有返回的值不伪造。
- `image.png`：实际返回图片字节；格式或尺寸验证失败时保留字节并标为失败，不当作成功结果展示。

每次显式点击生成均建立独立 Run ID；各卡片使用自己的状态指针。单图失败不清除其他成图，重复生成失败仍保留该图上次成功结果并明确标注。生成后刷新可恢复图片；运行中仅轮询本地状态，不调用 OpenAI。服务中断后的未完成 Run 标为状态待确认，保留证据，不自动付费重试。

结果绑定确认计划版本。回到第一页改动并重新确认后，新版本从未生成状态开始，旧版本图片与证据仍保留，避免把旧计划结果展示为新计划成图。

本地检查覆盖 45 项测试（原有 34 + 图片审核修改 6 + 任务中心 3 + 等待状态 2）。图像接口通过官方 SDK + 本地 MockTransport 验证序列化、隔离、错误与恢复。T03 已有真实成图证据，但业务接受仍待核验；T04 的真实模型编辑效果与修改稳定性仍 **PENDING**，不能以 Mock 测试替代。

## 8. T03 补充：实验记录与 ZIP 导出

仍使用同一个服务：`.venv/bin/python src/prepare_plan.py --port 8010`，修改代码后需要重启。打开已有任务的第二页，点击「导出实验包」，浏览器下载 `case-001-experiment-<UTC时间>.zip`。无需配置 API Key；此按钮只读取本地文件，不调用模型、不重试、不覆盖记录，也不会在每次 AI 调用后自动复制 ZIP。导出在内存中打包，下载文件由浏览器保存，不在服务端重复留存。

新 T02 调用补充 Run ID、Case ID、操作类型、修改前版本、实际 API 起始时间及耗时；`prompt.txt` 包括实际发送的图片标签，`request.json` 保留完整 SDK 参数与图片 data URL。图片顺序、SHA-256 和不可变 session 输入可相互核验。`applied.json` 链接修改前后版本，仍复用现有 `versions/`、反馈与确认事件，不建立第二套历史。T03 补充 Case ID、操作类型与已确认版本文件关联，继续使用原有逐次输入副本、Prompt、请求、结果、响应、用量、错误和图片。认证字段及隐藏推理不保存；可获取的普通结果、usage、request ID 保留。

导出范围是当前页面的已保存任务；加载内置资料的新任务明确标识 `case-001`，其他新资料使用独立 Case ID。历史 session 没有 Case ID 时，只有原始文本、图片内容与 SHA-256 匹配，才关联 case-001 的 T01 记录；这是 **RECONSTRUCTED** 的关联，不回写旧 Evidence。不同任务或无法确认来源的记录不会混入当前包。

实际包结构复用现有文件内容：

```text
case-001-experiment/
  inputs/                   # 原始图片、texts.json、便于阅读的文本；原始 case 文本位于 original/
  planning/state.json       # 当前理解、计划、人工意见、确认状态
  planning/revisions/       # 原有完整版本快照
  planning/calls/            # T02 实际请求、响应、结果、输入顺序、错误、应用版本
  generations/runs/         # T03 逐次计划、Prompt、请求、响应、错误、文本输入
  generations/images/       # 逐次实际返回图片，包括保留的失败输出（如有）
  generations/<版本>/<参考>/current.json
  evidence/T01/             # 匹配当前 Case 的既有 T01 检查/真实运行及图片
  manifest.json
```

相同输入图片按内容去重；manifest 的 `sources` 与每条 Run 的 `inputs` 给出原路径、顺序、SHA-256 和包内文件映射。SDK 响应保留当时保存的内容，可能包含图片 base64；这是响应证据，不能为了缩小包冒充原始记录进行删改。

manifest 记录 Case/任务、导出时间、Run ID、确认版本、原有事件形成的版本关联、文件大小与 SHA-256，以及逐项缺失说明。**ACTUAL** 是保存的原始字节；**RECONSTRUCTED** 包括关联索引及从已有 state 提取的便读 `.md`，不冒充当时的独立文件；**MISSING** 如实标明未保存内容。manifest 自身不递归记录自身哈希。

历史限制：T01 `revised_prompt` 为 null；不能恢复服务端内部 Effective Prompt、隐藏推理、原始 HTTP/完整响应头或实际账单。早期 T02 `prompt.txt` 没含逐图标签，但原始 `request.json` 已保存这些实际标签及图片；早期 Run 未直接写 Case ID/修改前版本，原有 events、versions 和 applied 保留供核对。T03 那次失败没有 SDK 成功响应/usage，不能补造。没有记录过的修改、人工评价或调用不会生成虚构记录。

导出仅接受任务 ID，无任意文件路径参数。读取使用目录/文件白名单，拒绝符号链接、越界路径、哈希不一致，以及含认证信息/隐藏推理的证据；错误会显示在页面，原文件不修改。正在执行的理解/规划或生成需结束后导出；中断 Run 保留并报告，不自动调用或重试。此功能用于实验分析，不是 T04 的最终商品图包。

## 9. T04：审核、编辑、版本与最终图片包

仍使用 `.venv/bin/python src/prepare_plan.py --port 8010`；没有新增依赖、数据库、后台队列或模型框架。首页展示任务名称、创建时间、业务状态、生成/通过数量和继续入口；`/prepare/<task-id>`、`/generate/<task-id>` 显式恢复任务。修改原始输入仍保存为新任务，旧任务保留，不在两个商品之间共享理解、计划或图片历史。

每张图片独立操作：

1. 点击「生成图片」产生首个版本 V1，原有生图能力保留。
2. 选择历史版本查看，填写修改意见后点击「修改图片」，生成 V2、V3 等新版本。可选择 V1 继续修改形成后续版本，并保存其父 Run；失败只新增错误记录，不创建可用图片版本。
3. 「Pass · 接受当前版本」绑定当前选中的具体 Run。生成/修改新版本、选择其他版本均不自动替换已接受版本；新版本须再次人工审核。
4. 「导出通过的图片」下载当前任务、当前确认计划中已 Pass 的版本，可导出已通过的子集。ZIP 仅有 PNG 图片（例如 `图片_01_V1.png`），不带开发证据。若当前查看 V2、已接受 V1，则导出 V1。
5. 「导出实验包」继续下载当前任务完整实验证据，另含 T04 编辑输入、父版本、修改意见与审核事件；与最终商品图片包分开。

编辑复用 T01 的官方 SDK `images.edit` 和已有模型/参数。图片输入顺序为：**当前选中生成图片 → 当前商品实拍 → 本张设计参考**；Prompt 带原始 Listing/描述、整体要求、当前商品及参考理解、本张确认计划和本次意见。当前图片与其父 Run/版本/hash 被保存，不带其他图片的修改记录，不重新运行 T02，不重生成整套图。模型未修改区域、商品结构和文字保持效果必须由真实实验检查，不保证 100% 不变。

版本与审核直接扩展现有 `sessions/<task-id>/generations/<确认版本>/<参考>/`：每次运行仍保存独立 `runs/<run-id>/`；新 Run 增加 action、version、parent_run_id、parent_version、feedback、operation_id，当前编辑图片快照为 `inputs/current_image.png`。`current.json` 增加选中/通过 Run 与卡片修订号；`reviews/<id>.json` 追加选择与人工 Pass 事件。旧 T03 成功 Run 按已有时间顺序显示历史版本标签，**不回写或迁移旧 Run**。修改前后图片、实际 Prompt/输入顺序/参数/响应/耗时都保留。确认计划改变后仍按原 T03 规则隔离新旧计划结果，旧图片保留在原确认版本中。

AI 操作立即显示操作名、正在执行状态及实际等待秒数；多图显示已生成 X/N、已 Pass 数量。只使用不确定动画，无模拟百分比或思考过程。刷新仅读取当前记录；服务中断显示状态待确认，不自动重试。按钮在处理中禁用；服务端同卡锁、修订号及新页面的 operation_id 防止重复执行。连接失败保留旧图，明确提示服务端执行/计费可能需要核对。

本轮浏览器验证使用独立合成资料和 MockTransport：创建任务、规划、生成/编辑、V1/V2 选择、Pass、刷新与任务切换、两种 ZIP 下载均已检查，最终包仍取指定已 Pass 的 V1，实验包哈希全部匹配。检查资料在 `.runtime/prepare-plan/local-checks/t04-ui-20261014T081319Z/`，不等同真实模型或商品质量验收。

人工体验时可从任务中心打开现有 case-001，核对原有四张图片后选择一张，明确输入意见并主动点击「修改图片」。密钥只由服务端环境读取，程序不加载 `.env` 或 `.env.example`。本轮未付费调用；真实编辑账户访问、结果展示、商品/日文保持能力、连续修改稳定性及运营闭环接受等待人工验证，不自动批量或重试。

## 10. Mac mini 内部试用 — 2026-10-14

定位为 **INTERNAL PILOT / BUSINESS VALIDATION**。服务器 `andy_server@192.168.112.37`，首次部署版本为 T04 本地 Commit **`7a692f30d73b69b26cfbd74cb9e4d6aec456e25b`**，提交信息 `feat: implement T04 review revision and task management`；当前增量版本见下节。通过 `git archive` 传输已提交版本，28 个受版本控制文件逐文件 SHA-256 一致；代码归档不含 `.env`、`.env.example`、本地密钥、虚拟环境、原始业务资料或历史 ZIP。用户另行确认后，单独迁移 case-001 原始资料、任务 `7e0c5261dd6b40b9aa81f0750c626517`、T01 真实首图及证据、T02 实际计划与 T03 四张真实成图/失败记录，101 个文件在本地和服务器逐文件 hash 一致；没有迁移其他本地任务、Mock、LOCAL_CHECK_ONLY 或历史 ZIP，原件未改动。

访问地址：**https://192.168.112.37:8444/**，**不设置登录账号或密码**。本轮改为网段配置：服务器 `/Users/andy_server/commerce-image-poc-pilot/config/settings.json` 的 `PILOT_ALLOWED_CIDRS` 默认允许 **`192.168.112.0/24`、`127.0.0.1/32`、`::1/128`**。所有页面、API、图片与下载使用同一访问控制层，以实际 `REMOTE_ADDR` 和标准库 `ipaddress` 判断，不信任 `X-Forwarded-For`。仅监听 LAN IP、IPv4/IPv6 回环的 8444，不监听公网或通配地址，拒绝其他 Host；未添加公网映射或修改其他服务。获准网段内设备可查看全部试用任务；Task ID 只隔离资料，不构成每人权限系统。

更改允许来源只需编辑配置文件并重启，无需改 Python。可配置多个 CIDR（JSON 数组或逗号分隔字符串）；服务进程环境变量 `PILOT_ALLOWED_CIDRS` 优先于文件，例如 `192.168.112.0/24,127.0.0.1,::1`。环境覆盖应放在本服务 LaunchAgent 的环境配置，API Key 仍不能放入 plist。无效 CIDR、空列表、公网范围或 `0.0.0.0/0` / `::/0` 会拒绝启动。

```json
"PILOT_ALLOWED_CIDRS": ["192.168.112.0/24", "127.0.0.1/32", "::1/128"]
```

采用专用自签名 HTTPS 证书，需由管理员安全分发并在每台运营设备核对、信任。证书有效期至 2027-10-14；SHA-256 指纹：

```text
86:6C:F7:D5:5A:59:D0:75:E8:B9:9D:65:20:D5:6D:A7:7F:AF:DF:BC:7E:75:26:E8:39:9E:12:85:94:18:B8:44
```

公开证书位于服务器 `config/server.crt`（本地检查副本 `.runtime/deployment/pilot-20261014/server.crt`），不要分发 `server.key`。用户已手动处理浏览器证书警告，Codex 随后验证了无登录的任务中心、真实成图、新建/恢复及合成任务审核下载。Edge 地址栏仍显示 `Not Secure`，不声称已建立系统信任链；运营设备仍应按指纹核对并安装信任证书。Codex 没有代为绕过证书警告。

独立目录如下，根目录及数据/配置目录为用户私有，密钥文件为 `0600`：

```text
/Users/andy_server/commerce-image-poc-pilot/
├── releases/7a692f30d73b69b26cfbd74cb9e4d6aec456e25b/  # 已提交的应用源码
├── venv/                         # Python 3.12.13；OpenAI 2.54.0；Flask 3.1.3
├── config/                       # 部署入口、设备 IP 白名单、TLS 与密钥录入工具
├── data/.runtime/prepare-plan/   # 原有 sessions 机制，全部运营任务/历史/Evidence
├── data/.runtime/inputs/         # 已迁移的 case-001 原始资料
├── backups/                      # 独立时间戳备份及校验清单
└── logs/                         # 仅本服务日志，不记录认证请求头
```

WSGI 使用 [Gunicorn](https://gunicorn.org/reference/settings/) 26.2.0，1 个 `gthread` worker、4 个线程、TLS 1.2 及以上；单进程保持现有锁有效，独占数据文件锁阻止第二个服务进程。TLS 客户端连接 IO 设置 10 秒超时，模型调用仍使用原有 120/180 秒超时，不改变费用与重试规则。外部部署入口复用 `create_app(runtime_dir, case_dir)`，不修改 T01～T04 业务源码或数据结构。所有 POST 使用单个非阻塞写锁，忙时返回明确提示，不排队、不自动重试；GET 可继续读取。生图请求必须带当前卡片修订号与操作 ID。代码更新应解包到新的 `releases/<SHA>/`，只调整 launchd 的源码路径，不覆盖 `data/`、`config/` 或 `backups/`。

macOS 用户 LaunchAgent：`~/Library/LaunchAgents/com.song36.commerce-image-pilot.plist`，Label `com.song36.commerce-image-pilot`，运行于 `gui/501`。该方式需要 `andy_server` 登录会话；本轮验证服务进程重启，未验证整机重启或注销后的可用性。以下命令在服务器 SSH 终端执行，先确认没有 AI 请求正在执行：

```bash
# 停止
launchctl bootout gui/501 ~/Library/LaunchAgents/com.song36.commerce-image-pilot.plist
# 启动（仅在已停止时）
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.song36.commerce-image-pilot.plist
# 重启已运行的服务
launchctl kickstart -k gui/501/com.song36.commerce-image-pilot
# 查看状态
launchctl print gui/501/com.song36.commerce-image-pilot
```

服务器启动时从用户私有文件 `/Users/andy_server/commerce-image-poc-pilot/config/openai_api_key` 注入 `OPENAI_API_KEY`，launchd plist 不含密钥。配置目录必须为用户自有 `0700`，密钥必须为用户自有普通文件 `0600`；不读取 `.env.example`。**2026-10-14 检查为未配置；2026-10-15 检查文件权限为 `0600`，重启后的服务返回 `ai_configured=true`。本轮未显示或传输密钥内容；免费模型元数据查询成功，但未执行推理，不能据此确认推理权限或旧密钥已轮换。** 未配置时，AI 操作返回明确 503，模型和运行证据写入之前停止，免费资料操作仍可用。

管理员在自己的终端执行下列命令：只接受交互终端，隐藏输入失败时拒绝录入；以 `0600` 临时文件原子保存，不输出密钥，不进入 Shell 历史、前端或证据。录入后确认无 AI 操作，再重启服务使其加载配置。不要向聊天发送密钥；本轮曾出现对话内密钥，已提醒撤销轮换，未保存或使用。

```bash
ssh -t -o ClearAllForwardings=yes andy_server@192.168.112.37 '/Users/andy_server/commerce-image-poc-pilot/venv/bin/python /Users/andy_server/commerce-image-poc-pilot/config/configure_secret.py openai'
```

服务器现有 `127.0.0.1:7897` 代理能连接 OpenAI，未带密钥请求返回 401、TLS 校验正常；直连失败。仅在本试用进程配置代理，未修改 Clash、Jellyfin、Nextcloud、FileBrowser 或其他服务。代理可用性是后续真实调用的依赖，账户/模型访问仍须人工验证。

**备份**：在服务器执行以下命令。工具先检查未完成 AI Run，存在 RUNNING/PREPARING 时拒绝暂停，须先核对状态与 Evidence；随后仅停止本试用服务、等待独占数据锁、打包 `data/`，校验包内每个文件 SHA-256，再启动本服务。每次独立时间戳，不覆盖历史，不包含代码、配置密钥或日志。需要恢复时先停止本服务，将备份解到独立恢复目录并按清单核对，再人工切换数据目录；不直接覆盖现有任务。

```bash
/Users/andy_server/commerce-image-poc-pilot/venv/bin/python /Users/andy_server/commerce-image-poc-pilot/config/backup.py
```

首份验证备份 `backups/20261014T091328Z-94c8a05b.tar.gz` 保留。最新备份 **`backups/20261014T094115Z-8bd1dc9c.tar.gz`**，包含 case-001 与独立合成检查任务共 163 个文件，逐文件 hash 一致；归档 SHA-256 `b5996ecf6a282b1dd1eb8fe1e528294db083dbe28601c9639053cb6a48f08ea8`。持有空闲 TLS 连接时，暂停/备份/重启在 8.353 秒内完成。这是同机本地备份，尚无异机副本或自动定时备份。

**本轮免费验收**：本地与服务器各 45 项测试通过，依赖检查通过；launchd 启动、HTTPS、无登录/IP 白名单与 Host 限制、HTTP 创建/上传/读取、合成计划/图片恢复、V1/V2 选择、Pass、最终包仅含通过的 V1、实验包全部文件 hash、任务隔离、备份及服务重启恢复通过。用户处理证书警告后，浏览器验证真实 case-001 四张成图、合成新建上传/保存/刷新、版本选择/Pass 和两种下载；下载实验包 42 个文件 hash 一致。服务器保留三个明确命名的合成检查任务，SDK MockTransport 记录标记 `OFFLINE_MOCK_NO_PAID_CALL`，不作为真实实验；真实图片未由 Codex 标记 Pass。检查记录为服务器 `config/deployment-checks.json`，本地 `.runtime/deployment/pilot-20261014/browser-checks.json`，以及同目录迁移/部署清单。

**本轮配置免费检查**：原有 45 项回归、7 项配置检查通过（配置检查同时在本地和服务器执行），覆盖多个 CIDR/环境覆盖、同网段允许、公网及伪造转发头拒绝、密钥权限、隐藏输入约束和临时 Canary 的日志/前端/ZIP 隔离。确认无 AI Run 后仅重启一次；LAN、IPv4/IPv6 回环 TLS 连接返回 200。回环测试保留 LAN IP 作为证书校验名称（使用 `curl --connect-to`），证书未新增 localhost SAN。case-001 四张成图可读取，实验包 77 文件 hash 一致；全部 163 个业务数据文件和 28 个已提交源码文件 hash 未变。其他 LAN 设备来源通过访问控制逻辑测试，实际其他设备联测留给运营。服务器记录 `config/access-adjustment-checks.json`，本地副本位于 `.runtime/deployment/pilot-20261014/`；未执行付费调用。

**运营开始方式**：管理员先配置新的服务器密钥并分发证书；可信 LAN `192.168.112.0/24` 内设备打开任务中心，按指纹信任证书，无需登录。可直接继续已迁移的 case-001，或创建自己的任务、上传商品/参考图及保存文本。新任务由运营主动点击 AI 理解与规划、检查并确认计划，再逐张生成。选择一张真实成图，填写如「保留布局，背景改浅粉色，商品和日文尽量不变」，明确点击「修改图片」；检查新版本、原图保留、其他图不变，再 Pass 指定版本并导出。每次 AI 点击产生费用，本轮 Codex 未执行这些操作。

真实规划、生成、编辑、编辑后版本保存与人工 Pass，以及商品/文字保持、连续编辑稳定性和实际费用，仍待人工验收。连接中断期间原请求可能继续执行：同一处理中请求、同操作 ID 重放和过期卡片会被拒绝或返回原记录；失败后人工建立新请求仍可能重复远端执行/计费，不能承诺超时即免费。先查看当前状态与 Evidence，再决定是否人工重试。

## 11. 规划模型升级与安全增量部署 — 2026-10-15

已提交并部署 `a2e1123d1d80a3f15194872365340bdaee9b6349`（`chore: update planning model configuration`）。服务器新 release 位于 `releases/a2e1123d1d80a3f15194872365340bdaee9b6349/`；只经 SSH 传输 `src/prepare_plan.py`、`tests/test_prepare_plan.py`，其余原 release 文件在服务器本地复制，旧目录不改动。部署脚本仅在 MacBook 使用。`gpt-5-mini` 已被官方标为 Deprecated，因此没有选为新默认；[官方弃用记录](https://developers.openai.com/api/docs/deprecations)列出其快照关闭计划。选用仍受支持的 `gpt-5.4-mini`，官方标准文本价格为每百万输入/输出 token $0.75/$4.50，低于 `gpt-5.6-terra` 的 $2/$12；这只是配置取舍，非业务质量或总成本实测。

规划模型显式保存在服务器 `~/Library/LaunchAgents/com.song36.commerce-image-pilot.plist` 的 `EnvironmentVariables.OPENAI_PLANNING_MODEL`，当前值 `gpt-5.4-mini`，重启后 worker 启动环境已核对。密钥仍由原 `config/pilot_wsgi.py` 从原私有文件加载；未修改 `config/`、WSGI、Gunicorn、CIDR 或 HTTPS 8444。数据继续保存在 `data/.runtime/`。

在 MacBook 项目根目录执行，默认仅只读预检；**确认运营空闲后**才加 `--apply`：

```bash
.venv/bin/python scripts/deploy_pilot.py --planning-model gpt-5.4-mini \
  --file src/prepare_plan.py --file tests/test_prepare_plan.py
# 将来发布新的已提交版本时，重复指定本次实际需要同步的文件，再执行：
.venv/bin/python scripts/deploy_pilot.py --planning-model gpt-5.4-mini \
  --file src/prepare_plan.py --file tests/test_prepare_plan.py --apply
```

脚本只读取指定 Git Commit 的普通文件，限定源码/测试/README/依赖路径，拒绝未提交的选中文件及隐藏路径，不复制 env、`config/` 密钥文件、runtime 或虚拟环境；提交前仍须检查源码中未误写密钥。它不执行 Push 或 rsync 删除。先核对服务器所有清单文件，无独立修改且未遗漏必要变更才继续；在 `backups/deploy-<时间戳>/` 保存并逐文件核验代码备份、保存原 LaunchAgent，再建立新的 release 并运行免费测试。重复发布到已存在的 release 会停止，不覆盖旧目录。检查无 RUNNING/PREPARING Run 后，仅通过原 LaunchAgent 优雅停止本服务、等待数据锁、持久化非密钥模型配置并启动；启动失败会恢复原 LaunchAgent。前后核对数据与 `config/` 的文件字节；不恢复或覆盖运营数据。成功后写入新 release 的 `.pilot-source.json` 与备份目录的 `result.json`。没有后台部署平台或模型调用。

本轮代码/LaunchAgent 备份：`backups/deploy-20261015T030737Z-4844112e/`。本地和服务器各 47 项离线测试通过；依赖检查通过。HTTPS 任务中心 6 个任务可读取，case-001 的 7 张输入图及 4 张历史成图 SHA-256 匹配，实验包 77 个文件 SHA-256 匹配；全部 217 个运行数据文件、服务器配置及 T01/T03/T04 图像源码未改动。服务器另执行一次免费的 `GET /v1/models/gpt-5.4-mini`，HTTP 200 返回同名模型，确认账户模型可见性；未调用 Responses/Images 或发送业务资料，不代表推理权限/额度已验收。检查记录为备份目录的 `result.json`、`http-checks.json`、`model-metadata-check.json`；MacBook 副本在 `.runtime/deployment/planning-upgrade-20261015/`。本轮未付费调用。

**人工验证新模型**：打开 https://192.168.112.37:8444/ ，创建新任务并加载 case-001 为独立副本，或上传新资料；检查后主动点击一次「AI 理解与规划」。不要在旧确认任务上为测试而重做全部计划。成功后核对该任务 `calls/<call-id>/request.json` 的 `model`、`reasoning`，以及 `run.json` 的 `model`、`returned_model`、`request_id`、`usage`、状态与 `applied.json`；服务返回的真实模型 ID 也在 `response.json`。这才是新模型真实调用证据，不能用本轮 Mock 测试替代。失败时先核对原请求，不自动或连续付费重试。

**只回退模型、不传源码**：在 MacBook 执行以下命令，先去掉 `--apply` 预检，再确认无 AI 请求后执行。它持久修改同一个 LaunchAgent 并重启，不改计划、成图或 Evidence；无自动付费回退。

```bash
.venv/bin/python scripts/deploy_pilot.py --planning-model gpt-4.1-mini --apply
```

若要回退整份代码，先确认运营空闲，使用上述备份的 `launchagent.plist` 恢复原源码入口再启动；原 T04 release 一直保留，禁止恢复数据备份覆盖当前任务。本轮 README/CURRENT_STATE 的使用记录与原有文档修改保留在工作区，未混入上述源码提交；未 Push 或处理远程历史。

## 12. I01 — Quick Redesign 可行性实验（2026-10-16）

本节保留 **AI FEASIBILITY EXPERIMENT 免费准备阶段**的命令与证据约定，当时状态为 ACTIVE / REAL RUN PENDING；最新本地产品集成见第 13 节。独立入口 `src/quick_redesign.py` 复用 T01 的官方客户端、图像模型允许列表、参数、SHA-256/JSON 写入及既有 Evidence 脱敏与路径检查。初次检查时资料目录不存在，因此保存了缺资料记录；该历史阻断现已解除，不代表当前仍缺样本。

原实验建议准备 2～3 张真实业务原图，每张独立；下列仅为命名示例，并非当前文件清单。最新用户指令基于一个正面样本直接集成，不要求增加实验样本：

```text
.runtime/inputs/i01-quick-redesign/
  sample_01.jpg            # 第一轮只明确选择这一张
  sample_02.jpg            # 第一张评价后再决定是否测试
  requirements.md         # 可选：运营设计要求，UTF-8
  product_facts.md         # 可选：必要商品依据/约束，UTF-8
  design_reference.webp   # 可选：仅用于设计方法的参考图
```

支持 JPG、PNG、WebP，单张小于 50 MB；只读取显式选择的文件。第一张输入始终为本次原图，可另选一张设计参考置于第二位；不扫描并批量发送目录里的其他样本。文字会进入 Prompt；拒绝含疑似密钥的文本，API Key 只从当前进程环境读取，不加载 `.env` 或 `.env.example`。模型默认 `gpt-image-2.5-sunburst`，可通过现有 `OPENAI_IMAGE_MODEL` 或显式 `--model` 选择 T01 允许的模型。沿用 `n=1`、`quality=low`、`size=1024x1536`、PNG、180 秒超时、零自动重试；首轮低成本配置不等于已验证模型的最高商业设计质量。

资料准备后，先执行免费检查（用实际文件名替换示例；可选文件未提供时不加对应参数）：

```bash
.venv/bin/python src/quick_redesign.py --image sample_01.jpg
# 如有运营提供的要求、商品依据和设计参考，可显式选择：
.venv/bin/python src/quick_redesign.py --image sample_01.jpg \
  --requirements requirements.md --facts product_facts.md --reference design_reference.webp
.venv/bin/python -m unittest discover -s tests -q
```

默认不创建 API 客户端、不调用模型。缺少资料保存 `LOCAL_CHECK_FAILED`，`request_ready=false`；没有实际输入时不会伪造完整请求或 Prompt。有有效样本后才保存输入副本、`context.json`、`prompt.txt` 与 `request.json`，状态为 `LOCAL_CHECK_ONLY`；没有提供运营要求时采用明确标记 `experiment_default` 的通用重设计目标，不冒充运营提交的要求。

**以下命令本轮未执行。只有用户确认所选业务资料、画幅/低成本参数及一次付费调用后，才在已安全设置环境密钥的终端执行：**

```bash
.venv/bin/python src/quick_redesign.py --image sample_01.jpg \
  --model gpt-image-2.5-sunburst --run-paid
```

如运营提供自定义要求，先用相同 `--requirements` / `--facts` / `--reference` 参数执行免费检查，确认后在相同命令末尾加 `--run-paid`。每次命令最多一次 `images.edit`，不自动批量、不重试或切换模型；失败仍可能在服务端执行或计费，应先核对 Evidence，等待评价，不进入自动 Prompt 调试循环。原图是主要依据；允许重新排版、改善层级、光影、背景和场景，尽可能保留外观、关键文字及卖点基本含义，不新增未经确认的功能、参数、附件或承诺。Amazon 风格仅是设计偏好，不是白底主图模式或发布合规声明。[官方 Images API 编辑能力](https://developers.openai.com/api/docs/guides/image-generation#edit-images)与既有调用方式一致；账户真实可用性及效果仍待验证。

每次运行独立保存：

- `.runtime/evidence/i01-quick-redesign/<run-id>/`：`run.json` 保存 I01/Run ID、所选路径、实际输入标识、模型/参数、源码哈希、时间/耗时、可获取的 request ID/usage、错误和输出关联；有效输入另保存 `inputs/` 原字节副本、`context.json`、`prompt.txt`、含图片顺序/MIME/SHA-256 的 `request.json`。真实响应保存 `response.json`，失败保存 `error.json`，不记录密钥或内部思考。
- `.runtime/outputs/i01-quick-redesign/<run-id>/image.png`：保留实际返回字节；PNG、尺寸、解码检查失败也不丢弃已返回图片，但不标为技术成功。旧 Run 和原图不覆盖。
- 技术成功仅为 `API_IMAGE_SAVED_AWAITING_REVIEW`；此时新建 `review.json` 的空白人工评价记录，decision 尚未填写，允许 `PASS / MODIFY / REJECT`，填写简短原因及 Product Fidelity、Information Fidelity、Visual Quality、Hallucination、Revision Effort、Cost & Latency。实际费用缺失时为 null，不用 usage 编造金额；不改写请求/响应来代替人工评价。

免费准备阶段 56 项离线测试通过（原有 47 + I01 9），SDK 请求只经过 MockTransport，合成图片不充当业务原图或真实模型证据。首次资料检查 `20261016T012440Z-f41214714e514459b9c64e83f5b8717d` 因目录缺失而停止，该 Run 没有有效请求或输出。随后已有真实成功 Run `20261016T013618Z-c0952e3ddfff430189e350a8bbb27c00`，耗时 21.445 秒，保存图片及 API usage；用户本轮反馈正面评价。其原始 `review.json` 尚未填写，实际账单费用仍为 null，原记录保持不变。一个样本不能推导普遍结论；本轮集成没有新增真实调用。

## 13. I01 — 快速重设计模式（本地集成，2026-10-16）

**PRODUCT INTEGRATION IMPLEMENTED / BUSINESS VALIDATION PENDING**。复用原任务中心、第二页、图像客户端与审核/导出，无新增依赖；Mac mini 继续运行原部署，本轮未同步。

启动或在空闲时重启本地服务：

```bash
.venv/bin/python src/prepare_plan.py --port 8010
```

打开 `http://127.0.0.1:8010` →「创建新任务」→ 工作模式选择「快速重设计」→ 填写名称、上传 N 张待重设计原图、修改整体要求，可选填商品事实说明或上传风格参考 →「保存并进入重设计」。支持 JPG/PNG/WebP，单图 20 MB、保存总请求 80 MB；不固定图片数量。Listing/商品理解/参考理解/逐图规划均非前置条件。整体要求有可编辑默认值；风格参考仅提供设计方法，原图信息和商品说明仍需运营核实。Amazon 信息图/场景图/卖点图是视觉偏好，不是平台合规承诺。

每张原图对应一张卡片，单独点击「生成图片」才调用模型。默认仍为 `gpt-image-2.5-sunburst`，遵循 `OPENAI_IMAGE_MODEL` 和 T01 允许列表；`images.edit`，n=1、low、PNG、180 秒、零自动重试。可选竖图 1024×1536、方图 1024×1024、横图 1536×1024，采用[官方支持的输出尺寸](https://developers.openai.com/api/docs/guides/image-generation#customize-image-output)，原商品图包模式参数不变。

- **生成输入**：本张原图在第一位，随后为当前任务可选风格参考；Prompt 使用整体要求和可选商品约束。不会发送其他待重设计原图或修改历史，不执行 T02。
- **修改输入**：当前选中成图 → 本张原图 → 已保存风格参考，结合整体要求、商品约束、本次自然语言意见。直接复用「修改图片」、V1/V2/V3、历史选择及父 Run 关联；I01 初始集成仅支持文字修改，后续 I02 辅助图片见第 14 节，不承诺所有未修改区域保持不变。
- **审核与导出**：Pass 绑定指定版本，新生成/修改/选择不会静默替换已 Pass 版本。「导出通过的图片」仅含当前任务已通过的 PNG；「导出实验包」包含当前任务输入、生成/修改/审核证据及 SHA-256 清单，二者继续共用 T04 实现。
- **持久化**：`.runtime/prepare-plan/sessions/<task-id>/` 保持原结构。`state.json` 保存 `mode=quick_redesign`、输出尺寸和文本，原图及风格图仍在 `inputs/` 按 product/reference 分类；`generations/<输入修订号>/product_NNN/runs/<run-id>/` 保存实际输入副本、Prompt、请求参数/顺序/hash、图片、响应、usage、耗时和错误。复用的 `plan.json` 在此模式保存本次有效输入 Context，不冒充 AI 制作计划；历史字段 `confirmed_revision` 对应已保存输入版本。选择/Pass 仍写原 `current.json` 与 `reviews/`，不另建版本系统。
- **恢复与费用**：从任务中心打开已有任务或刷新恢复；模式缺失的旧任务默认商品图包制作，不迁移/回写旧数据。改资料仍保存为新任务，不覆盖原任务。单卡锁、操作 ID、卡片修订号和禁用按钮防重复；失败保留已有结果与错误，不自动重试。连接中断时仍需核对服务端执行/费用，不保证人工新请求不会重复计费。

本轮 65 项免费离线测试通过（含原有 56 项与 9 项集成检查），依赖和 JavaScript 语法检查通过；接口测试覆盖多图上传/保存、两模式兼容、实际 SDK 序列化、尺寸、隔离、失败保留、去重、修改/选择/Pass/重启恢复、两种 ZIP 与哈希。浏览器检查模式切换、卡片展示及临时 Mock 图片 Pass；浏览器原生上传对话框未完成自动化验证，上传/保存由接口测试覆盖。未执行付费调用，真实多图重设计效果、商品/文字保持、修改稳定性及费用仍待运营评价。I02、I03 保持 PENDING，本轮停止，不自动开发或部署。

## 14. I02 — 图片辅助修改（本地集成，2026-10-16）

**I02 IMPLEMENTED / REAL EDIT VALIDATION PENDING**。第 13 节末尾的 I02 PENDING 是 I01 交付时的历史状态。本轮在现有编辑链路做最小扩展，没有新增页面、依赖、版本系统或 Evidence 平台；I03 单页工作台仍 PENDING，Mac mini 未部署本轮代码。

启动或在空闲时重启本地服务 `.venv/bin/python src/prepare_plan.py --port 8010`，打开 `http://127.0.0.1:8010` 并进入任一模式已有成图的第二页：

1. 选择要编辑的历史版本。
2. 可选上传一张辅助图，查看预览，明确选择「商品外观修正 / 设计风格参考 / 局部内容参考」。可移除或替换；不上传仍按原纯文字方式修改。
3. 填写本次自然语言意见，点击「修改图片」。上传、预览、用途选择、刷新和 Pass 不调用模型；只有明确点击修改才发请求，无自动付费重试。
4. 查看新版本并人工审核。旧版本和已 Pass 版本保留，未再次 Pass 的新版本不会替换最终图片包中的已接受版本。

辅助图须为可读取的 JPG、PNG 或 WebP，最多 20 MB；服务端验证实际格式、解码、用途和数量，拒绝疑似认证内容及无效/跨任务父版本，不接受服务器路径或其他任务的图片 ID 代替上传。两种模式统一通过原 `/revise/<图片-id>`：纯文字继续使用 JSON，带图使用 multipart，文件实际加入官方 SDK 的 `image` 列表，不能仅在 Prompt 中描述图片。[OpenAI 官方 Images 编辑接口](https://developers.openai.com/api/reference/python/resources/images/methods/edit)支持多图；本轮不新增模型参数或切换图像模型。

实际顺序为：**当前选中的成图 → 必要商品原图 → 本张原有设计/风格参考 → 本次辅助图**。商品图包模式带原 Listing/描述、整体要求、商品及对应参考理解、本张确认计划；Quick Redesign 使用本张原图、整体要求及商品约束，不要求计划。两者共享本次用途指令：外观修正图是本次修正依据，风格图只借鉴设计，局部图只对应意见明确的局部；用途由运营声明，程序不验证同 SKU，不把其他商品结构/宣称自动变为当前事实，不更新全局资料或其他图片。

辅助图原字节在本次 Run 的 `inputs/auxiliary_reference.jpg|png|webp` 独立保存，不重新编码；`run.json`、`plan.json`、`request.json` 的输入顺序关联用途、SHA-256、Task/图片 ID、父 Run，保留 Prompt、参数、响应、usage/耗时、结果和失败信息。实验包白名单扩展到此固定文件名，并保留角色/用途和哈希映射；最终图片包仍只含已 Pass PNG。辅助图不加入任务的 `state.images`，不自动用于下一次修改；要继续使用须重新选择，旧辅助图仍在历史 Run/实验包中可追溯。未提交的文字及辅助图预览仅保留当前页面，刷新前请先明确决定是否执行修改。

免费验证：**75 项离线测试通过（原有 65 + I02 10）**，覆盖两种模式、三种用途、真实 SDK multipart 字节/顺序、格式/大小/数量与归属检查、去重/并发拒绝、版本/Pass/重启恢复、失败保留、辅助图实验包/哈希、纯文字后续修改不自动带入旧辅助图或意见；pip check、JavaScript 语法、diff 检查通过。浏览器在独立临时目录用 MockTransport 完成上传/预览/用途/文字加图修改得到 V2，并刷新恢复；不是真实 AI 验收。

人工真实验证仍需运营主动点击，确认商品外观修正、原布局/风格/日文保持、错误商品信息、连续修改稳定性、耗时和费用。正确传递图片不保证未修改区域 100% 不变，连接失败也不证明服务端未执行或未计费。本轮没有真实付费调用、Commit、Push 或部署，完成后停止，不自动进入 I03。
