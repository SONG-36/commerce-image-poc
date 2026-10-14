# Commerce Image POC

> 阶段：低成本 AI 可行性验证 / 两页式原型探索  
> 范围：跨境电商商品图包制作（当前参考 TikTok Shop、Temu 的相似制图工作）  
> 状态：**T01 首图用户 PASS；T02 已有确认计划；T03 已核实四张真实成图，业务验收待完成；T04 与任务中心、等待反馈已本地实现，真实图片修改质量及完整运营闭环待人工验证**。

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

本地 Git 的 `main` 已有 T01、T02、T03 三个本地提交（T03：`ede6f6a`），**尚未恢复远程历史**；本轮不提交 T04 或推送。待连接恢复后，另行安全获取并同步远程历史。

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
