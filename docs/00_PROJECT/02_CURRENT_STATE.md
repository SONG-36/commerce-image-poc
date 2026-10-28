# Current State

> 语义同步：2026-10-27（Asia/Shanghai）。本轮仅核对本地 Git、现有文档和引用；未访问 Pilot Runtime、启动服务、读取密钥、运行模型或重跑工程测试。

**CURRENT VERIFIED STATE｜2026-10-27 本地核验**

- **Git：** `main / 36251cc386233a5a8c76177818dd831174f0014b`，2026-10-26 的 `fix: support dynamic Quick slots, per-image sizes and inspector entry`。CP1+CP2 已在 `b508c27889e4c1fedfc577ec2f2efeed11920646` 提交；动态图位、逐图尺寸、Inspector 入口修复已包含于当前 HEAD，不再是未提交源码。
- **待审工作树：** 当前待提交的是文档目录整理、语义同步及已有 V0.1 删除/V0.2 替代稿。三个 `git mv` 重命名已在上一轮暂存，其余文档改动尚未完整暂存；本轮不自动 add / commit / push。
- **业务与研究：** 当前业务权威是 [V1 Business Baseline V0.3（本条历史记录原引 V0.2）](../02_BUSINESS_MODELING/V1_BUSINESS_BASELINE_V0.3.md)。Quick-A / Quick-B 是 Quick 的子场景，Listing 为另一模式；新信息沿用、主体替换及尺寸素材规则不因业务确认就视为代码已实现。工程符合性与真实质量仍待验证；[能力与技术适配研究](../04_AI_AGENT_SUITABILITY/IMAGE_AI_DECISION_STUDY_V0.1.md)为 ACTIVE，未授权新的 AI 决策增强 Coding。
- **验证边界：** 下文 393 项 Python / 56 项 Node 是 2026-10-26 已记录结果，Python 包含 Node 包装，不累加；不是本轮执行结果。历史工程验收中的 `REAL IMAGE GENERATED = 0` 只指该轮匿名 Mock 验证，不表示项目没有真实 Run。模型质量、运营接受与新 SOP / Agent 增益不能由这些数字证明。
- **UNKNOWN｜当前运行：** 本轮未连接本地服务或 Mac mini，当前 Pilot 在线 SHA、WSGI、进程、数据及备份状态未核验。已有部署/运行观察保留其日期和范围，不推断今日已部署或未部署；不将本地 HEAD 当成线上版本。

**HISTORICAL SNAPSHOT｜阅读约定：** 下述旧 SHA、测试、部署、学习与“本轮”描述按原记录所属日期解释；以下历史快照不覆盖上方本地核验，也不替代当前运行核验。

> HISTORICAL SNAPSHOT｜原同步日期：2026-10-26（Asia/Shanghai）；当时本地 Git 基线：`main` / `b508c27889e4c1fedfc577ec2f2efeed11920646`，`feat: implement Quick V1 slot-based image workflow`；CP1+CP2 已提交；当时动态图位、逐图尺寸和开发者入口修复尚未提交，现已包含于上方核验的 `36251cc`。此前文档同步起点 `cb8ec3944c5df5473d5e1a6b404cc1a9c6a717e8` 为历史检查点。
> FINAL CUTOVER `78c68f9f25639d77abfdc3792a36541912f8af09` 是历史源码检查点；其后 Inspector/Live Debug 实现不包含在该 SHA 中。已提交的 Inspector 源码与文档检查点见第 5 节。Mac mini 线上状态 **UNKNOWN / UNVERIFIED**，核验 **DEFER**。

**HISTORICAL SNAPSHOT｜2026-10-26 工程摘要**：Inspector V0～V0.7 与本地 Live Debug 已实现；Quick V1 CP1+CP2 已提交，最新三项修复及匿名浏览器验证见下。该次完整离线回归 393 项、独立 Node 56 项（Python 包含 Node 包装，不累加）。不将本轮验证扩大为整个 Inspector 交互清单或真实模型验收；完整运营交互与真实图片质量仍待验收。第 6 节保留历史记录；当前本地提交状态以上方 CURRENT VERIFIED STATE 为准。

**当前核心问题**：用户/运营反馈的商品主体变形及商品身份保持；这是待逐 Run 核验的业务问题，不是已证明的模型根因。近期停止扩张 Inspector UI，以现有证据工具推进 Context、图片角色与人工 Evaluation；具体案例差异见第 6 节，下一会话交接见 [P3 主文档](../learning/P3_SOURCE_WALKTHROUGH_STUDY_V0.1.md#10-下一会话接续2026-10-23)。

**Quick V1 CP1（2026-10-24）：CORE ENGINEERING IMPLEMENTED / BUSINESS VALIDATION PENDING。** 首片（现已与 CP2 一并提交）通过现有保存 API 显式接收 `quick_business_version=v1` 与图位配置，按启用图位建立稳定输出，校验 1/1/1/3/2 上限、参考归属及可选要求。CP1 使用共同商品素材与本图位主参考，暂不使用全局风格图片，不执行 Planning；三素材全量发送仅为本片策略，不冻结为长期素材选择规则。新 Context、实际 Prompt、输入顺序及 Run 保存输出身份和绑定，编辑沿用父 Run、锁、去重、版本、Pass 与 ZIP；无显式新版的历史 Quick、功能 B 和 CLI 保持原行为，不迁移历史数据。
CP1 隔离环境修改前 366 项通过，新增 15 项 Quick V1 测试通过，最终完整回归 **381 项通过（19.459 秒）**；原测试和历史行为指纹未修改，未调用真实模型或操作真实 runtime。该检查点当时仅支持保存 API，页面与 Inspector 适配由下述 CP2 完成。Mac mini 未核验、未部署；工程通过不代表商品身份、事实、视觉质量或运营接受通过。

**Quick V1 CP2（2026-10-24）：ENGINEERING VERIFIED / BROWSER VERIFIED（匿名 SDK Mock 范围）；REAL IMAGE GENERATED = 0；BUSINESS ACCEPTED = PENDING。** 当时新建 Quick 页面提供同 SKU 商品素材、固定展开的 1/1/1/3/2 八个可选图位（动态操作由下述修复取代）、单张主参考预览/替换/移除和可空补充要求；显式提交 CP1 `v1` 与图位契约。商品素材数量不决定卡片数；新 V1 隐藏全局风格图片入口，整体要求继续适用。刷新恢复绑定；资料改动只另存新任务，并重映射参考资产编号、保留输出身份，原 Task/Run/Pass 不改写。历史 Quick 和商品图包保留原入口与业务语义。
输出选择/详情展示图位、主参考与本图要求；生成、顺序批量、修改、历史版本、Pass 和两种 ZIP 复用原流程。Inspector 只读投影识别 V1 输出身份，按实际清单区分共同商品素材和当前图位参考；缺少 Context 或有歧义的文字来源仍为 UNKNOWN，不重建历史 Prompt、不改变 Evidence。
本轮修改前 **381 项通过（18.935 秒）**；最终完整隔离回归 **387 项通过（18.986 秒）**，独立 Node **53 项通过**，均零跳过，二者不累加。真实 Edge 浏览器使用 NEW FIXTURE / SDK Mock：三素材三图位创建、第四素材另存仍三卡、刷新恢复、尺寸图生成与修改、父 Run、选 V1 Pass 后看 V2、两种 ZIP、Inspector 随 Run 读取，以及 390px 上传布局通过；最终图片 ZIP 核对仅含明确 Pass 的 V1。浏览器两次 SDK Mock（一次生成、一次修改），不是付费调用。截图、下载和原始验证日志只在仓库外临时目录，未加入 Git；未验证真实商品质量、生产环境或 Mac mini。

**Quick V1 真实使用问题修复（2026-10-26，当时未提交；现已提交于 `36251cc`）：ENGINEERING VERIFIED / BROWSER VERIFIED（匿名 SDK Mock）；REAL IMAGE GENERATED = 0；BUSINESS ACCEPTED = PENDING。**
- 主图/尺寸/对比固定显示；卖点、场景使用虚线添加框，按 3/2 上限动态增删。输出 ID 独立于显示序号，删除中间项不重编号其他绑定；刷新/另存恢复数量、顺序、参考、要求和尺寸。旧 CP2 未使用的空占位仅在页面收起，不改历史文件。
- Quick V1 和 Listing 参考均可设置 `1024x1024` / `1024x1536` / `1536x1024`；复用当前客户端尺寸枚举。任务新增可选 `image_sizes` 输出 ID 映射，创建及读取时校验归属/尺寸；单图配置优先于任务默认，旧任务无该字段仍用原默认。生成/批量/修改使用本图尺寸，实际参数沿用原 request.json / Run Evidence。输入尺寸修改仍另存新 Task，不原地改历史 Run 或确认记录，Listing 保留理解及逐图确认流程。
- Inspector 未被 Quick 移除：原本只在显式隔离调试工厂启用。工作台按钮改为「开发者视图 / Inspector」；普通本机工作台提供 Live Debug 导航和现有一键命令，仍不开放运营 Inspector API。无 Run 显示真实空状态，已有 Run 可看 Context、Prompt、角色、实际请求尺寸及输出；继续复用 V0.7 和原权限校验。
- 修改前隔离回归 **387 项通过（20.516 秒）**；新增 [逐图参数/兼容测试](../../tests/test_quick_operational_fixes.py) 6 项，更新并补充 [上传交互测试](../../tests/quick_v1_upload.test.cjs)。最终完整回归 **393 项通过（20.014 秒）**；独立 Node **56 项通过，零失败/跳过**，不重复累加。旧 Quick、功能 B、CLI、锁/去重、失败保留、父 Run、Pass、ZIP 及历史请求/Evidence 指纹回归通过。
- Edge 真实浏览器使用 NEW FIXTURE / 匿名 SDK Mock，验证两类动态图位增删/再添/上限、中间删除不串参考、保存/刷新/第四素材另存仍三输出；Quick 三图批量尺寸依次为方/竖/横，修改继承竖图，V1 Pass 不被 V2 替换，最终 ZIP 仅含 V1；Listing 经原理解和逐图确认后同样按方/竖/横生成。共 **7 次 Images SDK Mock**，请求尺寸为 `1024x1024, 1024x1536, 1536x1024, 1024x1536, 1024x1024, 1024x1536, 1536x1024`；另有匿名 Responses Mock，不是真实模型请求。Inspector 无 Run/随 Task 和 Run 更新、图片加载、Prompt/模型/尺寸、390px 上传与抽屉已核验，无浏览器脚本异常。截图和 JSON 报告仅存仓库外临时目录；真实 `.env`、运营 runtime、Mac mini 和现有 8012/8013 未访问或重启，不证明真实模型质量或账户尺寸可用性。

## 1. 定位与当前阶段

`commerce-image-poc` 是多工作流 AIGC 系统的第一个真实业务切入点，当前服务于跨境电商 AI 商品图制作与修改，未来系统不局限于商品图。
阶段仍为 **INTERNAL PILOT / BUSINESS VALIDATION**。源码结构整理阶段已结束，不继续目录重构或预建通用平台。
严格区分工程实现、软件测试、真实模型效果与运营验收；模型返回成功不等于业务接受。

## 2. 已实现的业务闭环

- **输入与任务**：任务中心创建/恢复独立 Task；保存商品原图、设计参考、Listing、描述、商品事实说明及整体要求。改原始输入保存为新任务，不覆盖旧任务。
- **商品图包**：一次理解请求可完成商品/参考理解与 N 张计划；支持理解修正、单张计划修改、逐图人工确认及过期保护，不强制拆分模型阶段。
- **Quick Redesign**：新建 Web Quick 使用 V1：同 SKU 商品素材共同作为依据，输出由启用图位及各自主要参考决定；整体要求、商品事实说明和逐图补充要求可选，无 Planning。历史 Quick 仍每张原图对应一张输出并保留全局风格参考；两者均不强制 Listing。
- **生成与修改**：单张主动生成；显式批准后浏览器顺序批量生成符合条件的图片。共用纯文字/一张辅助图编辑，辅助图必须声明用途且只影响本次当前图片。
- **共享工作台**：INPUT 按需折叠，OUTPUT 选图、详情与单一交互区；操作冻结 Task/Image/计划或 Run 身份，草稿/附件隔离。界面记录不作为共享模型历史。
- **审核与交付**：历史版本可选、可分支修改；Pass 绑定实际 Run，独立于当前选中版本。新图不静默替换旧 Pass；最终图片 ZIP 与完整实验 ZIP 分开。
- **费用边界**：加载、刷新、确认、选版本、Pass、导出不调用模型；AI 操作须主动触发，无自动付费重试或刷新续跑。未知请求先查询，不直接重发。

| 范围 | 当前工程状态 | 模型效果 / 业务验收 |
|---|---|---|
| T01 | COMPLETE：真实首图与保存通路 | 历史首图获用户 PASS，仅限该样本 |
| T02 | IMPLEMENTED，已有真实 Responses 记录 | 参考理解存在已观察偏差；理解/计划质量 PENDING |
| T03 | IMPLEMENTED / REAL RUN VERIFIED | 历史 case-001 四张成功图片；视觉遵从、商品/文字质量及失败计费 PENDING |
| T04 / OF-01～03 | IMPLEMENTED：审核、编辑、版本、任务中心及等待反馈 | 真实编辑稳定性与完整运营闭环 PENDING |
| I01 | PRODUCT INTEGRATION IMPLEMENTED | 单一真实样本获正面反馈，BUSINESS VALIDATION PENDING；原评价未自动改为 Pass |
| I02 | IMPLEMENTED / REAL EDIT VALIDATION PENDING | 实际辅助图输入由软件测试保护，外观/文字保持待人工评价 |
| I03 / Follow-up / 逐图确认与批量 | IMPLEMENTED / OPERATOR REVIEW PENDING | 操作成本、批量费用及运营接受待验 |
| D01/D02 | VISUAL PROTOTYPE IMPLEMENTED | USER VISUAL REVIEW PENDING，不自动启动 D03 |

## 3. 当前 Python 组织与执行链

| 位置 | 实际职责与边界 |
|---|---|
| [app.py](../../src/app.py) | 正式 `create_app()`、配置与依赖组装；`create_local_debug_app()` 显式组合隔离调试；保留 Store 适配、Planning IO 注入和进程内活动状态 |
| [api/](../../src/api/) | `register_routes()`：请求解析、HTTP 响应和错误映射；原 23 条路由身份保留 |
| [image_workflow/tasks/](../../src/image_workflow/tasks/) | `rules` 状态规则，`service` Task 用例，`queries` 查询，`storage` 资料校验/存取；`images` 协调图片操作，`generation` 拥有锁/去重，`generation_runtime` 绑定依赖，`review` 适配审核 |
| [image_workflow/planning/](../../src/image_workflow/planning/) | 纯请求构建、结果结构/身份校验、Responses 执行与调用 Evidence；不进行人工语义验收 |
| [image_workflow/generation/](../../src/image_workflow/generation/) | 商品包/Quick 的 Context 与 Prompt、Images 执行、结果校验及 Run 保存；辅助图策略归于此处 |
| [image_workflow/review/](../../src/image_workflow/review/) | 成功版本查询、选择、Pass、审核事件和最终图片 ZIP，不执行图像模型 |
| [image_workflow/experiment_export.py](../../src/image_workflow/experiment_export.py) | 当前任务实验包，保留 ACTUAL / RECONSTRUCTED / MISSING 来源等级与哈希校验 |
| [infrastructure/](../../src/infrastructure/) | `evidence` 通用脱敏/私密字段过滤；`openai_images` Images SDK 客户端及参数，无业务/CLI 反向依赖 |
| [persistence/](../../src/persistence/) / [file_ops.py](../../src/file_ops.py) | Task 当前状态/不可变快照、审核文件、路径/哈希/JSON；不替调用方推进业务状态，不提供多文件事务 |
| [cli/](../../src/cli/) | T01/Quick 实验默认免费检查；`debug_workspace` 负责本地 Live 配置/启动，不自动调用模型；CLI 不成为正式业务的导入依赖 |
| [api/inspector.py](../../src/api/inspector.py) / [image_workflow/inspector.py](../../src/image_workflow/inspector.py) / [inspector_graph.py](../../src/image_workflow/inspector_graph.py) | 本地显式启用的只读 API、受限证据读取及纯图投影；复用历史数据，不写 Evidence 或调用模型 |
| [templates/](../../src/templates/) / [static/](../../src/static/) | 原生前端；prepare/workspace/generate 协同，批次由浏览器顺序执行，无后台 Worker |

主要执行链：HTTP → API → Task 用例/协调 → Planning、Generation 或 Review → Persistence / Infrastructure。
模型在当前 HTTP 处理内同步执行；运行时回调提供 IO/能力，不另建锁或第二套状态。CLI 独立执行实验，不经过 Web Task 编排。
兼容入口：`prepare_plan.create_app()` 为正式工厂的同一函数；旧 `src/prepare_plan.py`、`src/generate_image.py`、`src/quick_redesign.py` 命令仍可用。
已退役：根目录 `generate_plan_image.py`、`image_review.py`、`experiment_export.py`、`evidence.py`；正式代码不再导入它们。

## 4. 状态、请求与 Evidence

Web 默认使用 `.runtime/prepare-plan/sessions/<task-id>/`；`create_app(runtime_dir, case_dir)` 支持独立业务数据目录。

- `inputs/`：上传原字节与文本；`state.json`、`versions/<revision>.json`：当前状态及不可变任务快照。持久化仍按先独占写快照、后替换当前状态的顺序执行。
- `plan_versions`、`plan_confirmations` 按 Image ID 绑定计划哈希、理解版本和确认快照；修改本图计划只撤销本图确认。旧整体 confirmed 只读派生兼容，不批量改写历史。
- `calls/<call-id>/`：T02 实际 SDK 请求（含图片 data URL）、图片顺序/身份/hash、Prompt、响应、result、错误、usage、`applied.json` 与任务版本关联。
- `generations/<confirmed_revision>/<image-id>/runs/<run-id>/`：有效 Context、输入副本/顺序、Prompt、参数、响应、图片、耗时、错误、父 Run/意见/辅助图。Quick 的 confirmed_revision 指输入快照，`plan.json` 不代表执行过独立规划。
- 图片 `current.json`、`reviews/`：card_revision、selected_run、passed_run 与审核事件。Task revision、计划版本、卡片修订号、显示 V 编号和 Run ID 不是同一种身份；最终导出选取明确 Pass 的历史版本。
- T01 / Quick CLI 分别使用 `.runtime/evidence/case-001/`、`.runtime/evidence/i01-quick-redesign/`，图片在对应 `.runtime/outputs/`；每次独立 Run，不覆盖原始资料。

代码默认配置（本轮未调用模型）：Planning 为 `gpt-5.4-mini`，允许显式回退 `gpt-4.1-mini` 或其 `2025-04-14` 快照；Responses 使用 instructions、JSON Context、图片标签与 data URL。
Images 默认 `gpt-image-2.5-sunburst`，另允许 `gpt-image-2.5-flare`；`images.edit`、n=1、low、PNG。默认竖图；Quick V1 和 Listing 可逐输出配置已有方图/竖图/横图尺寸，历史 Quick 保留任务默认尺寸。
**既有代码策略记录（非业务规范）：**商品资料决定事实依据，参考只借鉴设计；图片编辑先送当前选中成图，再送必要原始依据、本图参考和本次辅助图/意见，不重跑完整规划或无条件携带全部历史。
这描述既有 Prompt/Context 策略，不覆盖 V0.2 对 Quick-A / 经运营确认的 Quick-B 适用参考信息的沿用权限；两者的工程符合性仍待核对，本轮不改 Prompt。
源码依据：[Planning request](../../src/image_workflow/planning/request.py)、[Generation request](../../src/image_workflow/generation/request.py)、[Quick Prompt](../../src/image_workflow/generation/quick_prompt.py)、[Images 配置](../../src/infrastructure/openai_images.py)。

来源追踪仍是单文件：Planning 的 source_sha256 指 `app.py`，Generation 指 `tasks/generation_runtime.py`；其 T01/Quick 字段及 Quick CLI 指向正式 `cli/` 源文件。
T01 CLI 自身原本没有 source_sha256；这些字段都不代表完整 Package、依赖集合或部署 Git 版本。源码移动使新哈希自然变化，不改写旧 Evidence。
实验包只导出既有证据与明确标记的重建索引；Usage/request ID 只记录实际返回内容，缺失值不伪造。SDK 请求快照不等于服务端内部 Effective Prompt、隐藏推理或完整 HTTP 抓包。

## 5. 本地工程验证与结构整理结论

- **已提交源码检查点**：FINAL CUTOVER `78c68f9f25639d77abfdc3792a36541912f8af09`，`refactor: complete source layout cutover`。37 个路径（27 修改、4 删除、6 新增）；Git 将一组删除/新增识别为重命名，默认摘要为 36 项。
- **已完成结构节点**：T02 Request Builder / G1 file_ops，G2 Task Snapshot 首片，B1 Planning、B2 Generation、B3 Review、B4/B5 Task Application + API，C1 脱敏、C2 实验导出、C3 图像能力、C4 协调、C5 辅助图策略及最终入口切换。Git 为各节点提供检查点；不再保留“G2 未提交/B1～B5 尚未实现”的现行结论。
- **验证记录**：Cutover 提交前完整离线回归 279 项通过，15.066 秒；本轮按 README 的 unittest 参数在隔离保护下再次执行，**279 项通过，15.315 秒，0 失败/错误**。43 个内部链接、启动/安装参数的帮助入口及 pip check 检查通过；未实际安装依赖或启动服务。
- **保护范围**：HTTP 的 23 条 URL/Methods/endpoint、工厂与 CLI、纯请求与输入图片顺序、Context/Prompt、版本/确认/Pass、锁/operation_id、JSON 字节/写入顺序、脱敏与两类 ZIP 均有离线回归。
- **独立审核事实**：19 个已修改测试文件中的原测试方法均保留；固定请求/Evidence 指纹未改。新来源哈希先与实际文件比较再归一化。43 个 Python 模块静态无环；额外探针确认同一 App 共享一个协调器及锁/active。部分测试 legacy/core 别名已指同一模块，不能把它们作为独立新旧实现对照。
- **验收边界**：本地源码组织与软件兼容性 PASS；多文件事务/崩溃恢复未解决，线上部署、真实模型质量和运营闭环没有因此 PASS。

- **Inspector / Live Debug 源码检查点（2026-10-23，已提交）**：`39199acc42ec056eae87247f17b267f1adbfd05a`，`feat: add context flow inspector and local live debug`。从 dfcf6df 起累计的 28 个源码、资源、配置及测试文件构成完整功能检查点，未改变模型、Prompt 或业务状态规则。该阶段本文对应此 C1 源码；工程文档 C2 与学习记录 C3 已分别提交，不改变该源码基线，也不代表线上发布。
- **历史检查点回归（2026-10-23，C1 提交前）**：暂存内容与已审计工作树一致，受控完整离线回归 **366 项通过（21.140 秒），0 失败/错误**；独立 Node **46 项通过，0 失败/跳过**，不与 Python 包装重复累加。测试只用匿名临时目录与 Mock，保护器禁止联网及项目真实 `.env` / `.runtime` 读取、临时目录外写入。本次文档同步不重跑此回归、不新增运行 Evidence；只核对源码/Git、文档链接、Diff 与安全。浏览器完整验收、真实 GPT 效果及运营接受不由这些测试证明。
- **Inspector 收尾已提交**：C1 源码 `39199acc42ec056eae87247f17b267f1adbfd05a`、C2 工程文档 `331a13b3374e23f13607df78142810ff1e36b2f7`、C3 学习记录 `cb8ec3944c5df5473d5e1a6b404cc1a9c6a717e8`，共 32 个独立路径，无遗漏未跟踪模块。当时文档 Commit 不改变 C1 源码，也不等于服务已重启加载或 Mac mini 已部署；本轮文档同步不创建 Commit。

回归依据：[Cutover](../../tests/test_source_cutover.py)、[HTTP](../../tests/test_api_package.py)、[T02 请求](../../tests/test_t02_request_construction.py)、[图片边界](../../tests/test_t02_image_boundaries.py)、[Generation](../../tests/test_generation_package.py)、[Review](../../tests/test_review_package.py)、[Task 持久化](../../tests/test_task_state_persistence.py)、[实验 ZIP](../../tests/test_experiment_export_package.py)、[前端交互](../../tests/unified_interaction.test.cjs)。

## 6. 历史真实实验、失败与质量缺口

**Workflow Inspector V0（2026-10-22）：IMPLEMENTED / OPERATOR REVIEW PENDING。**基于本地 `dfcf6df` 开发独立只读入口 `api.inspector`，不注册到运营 App。启动必须指定 runtime 根目录及获准 Task ID，只绑定 127.0.0.1，拒绝非本机、转发头和跨站请求；仅提供 GET/HEAD，不调用模型或写业务数据。支持 Task → Image/revision/Run 选择、输入/Planning/确认/生成/Review 证据图、原图与成图预览、Prompt/Context/JSON/错误/哈希查看。原始证据、根据事件推断的关联、缺失和不适用分别显示；只定位最近相关计划 Call，不声称完整血缘或模型内部根因。匿名临时证据新增 17 项测试通过，完整离线回归 **296 项通过（17.911 秒）**；浏览器验证节点切换、缺失/失败记录、脱敏错误、大图、Pass 及刷新。真实运营 runtime 未读取、未部署；启动方法见 README。软件测试不代替真实失败归因或人工验收。

**Workflow Inspector V0.5 — Integrated Debug Sidebar（2026-10-22）：IMPLEMENTED / OPERATOR REVIEW PENDING。**

- 统一工作台新增可收起的右侧证据侧栏，窄屏为抽屉。通过主界面只读选择接口跟随实际 Task/Image/所展示的 revision/Run；复用 V0 页面、`InspectorReader`、脱敏与受限图片读取，不新增 Evidence 解析器，不修改生成/审核逻辑或数据格式。Quick 明确标为无独立 Planning；历史关联继续区分 OBSERVED / INFERRED / MISSING。
- 正式 `create_app(runtime_dir, case_dir)`、原 CLI、23 条业务路由及 WSGI 默认行为保留；默认无 Inspector API 或侧栏。只有 `create_local_debug_app()` / 下列独立命令在显式隔离 Runtime 和 Task 白名单下启用。拒绝默认运营 Runtime（含其路径别名），整个调试应用拒绝非 loopback 来源、转发头、外站 Origin 与非本机 Host；Inspector 接口只读，不接受任意文件路径。独立 V0 入口保留。
- 展开后每 5 秒串行 GET，选择变化最多约 0.5 秒同步；切换时取消旧读取并丢弃过期响应，未变化的证据不重绘。关闭卸载 iframe、停止刷新；后台标签页暂停轮询。独立调试命令显式启用 Flask 线程，查询不获取业务锁；不增加后台 Worker、不声称适用于任意生产 WSGI 并发配置。
- 修改前离线基线 **296 项通过（15.793 秒）**；最终完整离线回归 **307 项通过（17.798 秒）**，含侧栏前端 9 项交互测试包装及既有生成/编辑/Pass/批次回归。浏览器以匿名临时 Task 与固定 SDK Mock 验证商品包/Quick、选图、历史 Run、原 Pass、失败/缺失、节点与大图、390px 抽屉和收起。测试禁止外部网络及真实 runtime 读写；未调用真实模型、未部署、未 Commit。软件验证不等于真实商品变形诊断或人工验收。

现行可写本地入口如下（V0.5 原 8012 示例仅属历史，不再作为启动说明）：

```bash
./scripts/start_live_debug.sh
```

该脚本需现有 `.venv` 和 `.runtime/debug/live-debug-20261023T013447Z/runtime`，只绑定 `127.0.0.1:8013`。CLI 自动安全读取根目录 `.env` 的字面量 `OPENAI_API_KEY`，已有非空进程环境变量优先；不读取 `.env.example`，不执行 source/eval。新 Task 可在该 Runtime 内创建/保存并手动生成、修改；Inspector 只读跟随，无逐 Task 授权要求。无 Key 禁用模型操作，有 Key 不等于认证成功；启动/刷新不调用模型。
原 8012 Mock、8015 匿名只读预览属于各自历史调试实例，不能把当前 Live CLI 当作 Mock 启动器。主页面可写不改变 Inspector 只读边界；不得指向运营来源原件。正式 `create_app()` 默认不启用 Inspector，独立只读入口及静态 Task 白名单仍见 README。只读挂载、开发者身份系统、完整 Planning 血缘、生产接入与真实模型诊断未由本轮解决。

**LIVE-DEBUG-01（2026-10-23，历史检查点，权限与配置后续已调整）：LOCAL PREPARATION IMPLEMENTED / SECRET CONFIG PENDING / REAL RUN NOT EXECUTED。**

- 保留原 8012 匿名 Mock 进程；独立 8013 通过 `cli.debug_workspace` → `create_local_debug_app()` → 正式 `create_app()` 启动，不导入测试夹具或注入 MockTransport。仅绑定 127.0.0.1，正式运营工厂仍默认无 Inspector。
- 新 Runtime：`.runtime/debug/live-debug-20261023T013447Z/runtime/`；新 Quick Task：`7ef8f4fb8a72460c84e8ad5cf58b5c75`。经原资料保存 API 导入已授权本地来源 Task `bbf3f10c42ad4a329438222ac1715d39` 的 `product_001`、`reference_001` 及原有文字要求，保留方图 1024×1024；输入哈希一致，来源未改，未复制历史 Run/Pass、未运行 Planning 或生成。首轮只计划人工单张生成，不自动批量或重试。
- 环境标识由服务端显式配置 MOCK / LIVE DEBUG / UNVERIFIED，不由 `ai_configured` 推断。Live 付费操作默认锁定，需安全配置环境密钥并显式传入 `--allow-paid-actions` 才可由人工触发；本次启动进程的 Key 布尔状态为 false，泄露密钥轮换仍待用户完成，未读取或加载 `.env.example`。
- Inspector 新增只读授权状态查询；切换 Task 立即卸载旧 iframe、取消旧授权查询并丢弃过期响应，未授权时明确提示。新 Task 不自动获权，仍须服务端 `--task-id` 显式配置。旧进程未提供新配置时标为未核验，不猜测模式或继续读旧证据。
- 修改前完整离线回归 307 项通过；最终 **315 项通过（17.971 秒）**，含侧栏前端 13 项交互测试包装及既有生成/编辑/Pass 回归。匿名测试覆盖授权切换、过期响应、只读/路径保护、付费门禁及正式工厂导入。浏览器确认 8013 环境标识、真实输入和 Quick 的无 Planning 证据；生成/Review 显示缺失，未伪造结果。未调用模型、未部署或 Commit，真实模型质量与连通性尚未验证。

**FINALIZE LIVE DEBUG（2026-10-23，历史检查点）：ONE-COMMAND SETUP IMPLEMENTED / REAL RUN PENDING。**该阶段创建根目录空 Key 的 `.env`、权限 0600 并确认 Git 忽略；这不是今日文件内容或密钥轮换的核验。现行启动见上方一键命令，Task 范围以后续 FIX 为准。CLI 仅按字面量读取 `OPENAI_API_KEY`（非空进程环境优先），不执行 source/eval、不读取模板、不依赖 python-dotenv，并关闭 Flask 的二次 dotenv 加载。旧 8013 仅在同用户、同项目目录、同正式 CLI、同 Runtime 且空闲等身份核验通过后替换；不停止 8012、未知进程或运行中操作，不强杀。无 Key 禁用模型操作，有 Key 仅表示可人工触发，不表示认证或质量通过。原数据、Prompt、模型、180 秒超时及零重试不变。该阶段完整离线回归 **332 项通过**；未使用真实 Key 测试、未发送模型请求、未清理 Git 快照、未部署或提交。

**FIX LIVE DEBUG（2026-10-23）：IMPLEMENTED / OPERATOR REVIEW PENDING。**本地一键入口改为 Runtime 范围：该独立 Debug Runtime 内真实存在、state 身份匹配且路径安全的 Task 自动可手动生成/修改，Inspector 动态列出并跟随，无需逐 Task 白名单或重启。`--task-id` 只保留为可选初始链接；原 V0 静态白名单和正式运营 `create_app()` 默认关闭 Inspector 的行为不变。仍拒绝越界/符号链接、非 loopback、外站 Host/Origin 和转发头；Inspector 仅 GET/HEAD。模型调用前的明确拒绝标记 `api_call_attempted=false`，前端据此显示未发送，而连接不确定仍保留核对提示，不自动重试。模型、Prompt、版本/锁/去重及 Evidence 格式未变。本轮只读核对到新任务 `2feb571b59c44f419d479d4f992d7ffb` 无 Run，固定获准任务另有成功 Run `20261023T031644Z-0ff4c59d5d18483d8731df2553db1965`（有 request_id/usage）；后者不是本轮调用，且不代表业务质量通过。匿名临时测试覆盖连续新建两个 Task、生成/去重、带图修改、Pass 保留、Inspector 跟随与路径保护；完整离线回归 **340 项通过（17.555 秒）**，独立前端交互 **28 项通过**，`git diff --check` 通过。8013 以正式 CLI 启动，Key 配置布尔值 true，旧/新任务 Inspector 均返回 200；Key 非空不代表账户认证成功。8012 进程不变，Debug Runtime 的 24 个既有文件字节不变；本轮不触发真实模型。

**Workflow Inspector V0.6 — Context Inspector（2026-10-23）：IMPLEMENTED / OPERATOR REVIEW PENDING。**

- 首片覆盖 Quick Redesign 单次 Run：在既有 `InspectorReader` 已读取、脱敏、限域的 documents/assets 上构建纯只读 Context View Model，不引入第二套文件解析器或 AI 分析。六类卡片展示 Product Input、Reference Inputs、Task Requirements、Context Assembly、Actual Model Request、Model Output。
- 来源指向原文件、JSON pointer 和文件 SHA-256；商品资料使用所选历史快照，本次要求与辅助用途使用身份匹配的 Run Context，实际 Prompt/图片顺序/参数使用 request.json。明确区分已保存 Context 与实际请求；Quick 的 Listing/描述不因保存在快照而被声明为已发送。请求缺失只显示 Run.inputs 留存并标 UNKNOWN，不用当前代码或今日 state 重建。
- 默认摘要卡片、真实受限图片缩略图；详情按需展开。390px 侧栏可扩展同一 iframe 为大视图，支持 Prompt 全文、图片大图与原图/成图并排对照。原执行节点保留，Raw JSON 移入默认折叠的高级证据；点击字段来源可定位原文件。仅核对保存文字/清单/哈希的 MATCH / MISMATCH / UNKNOWN，不证明模型遵守约束或内部根因。
- 模型调用、Prompt、Context 组装、生成/审核规则、Task/Run/Evidence 格式均未改；本机、只读、Task/路径及跨站限制保留。验证使用临时匿名资料经正式业务代码加 SDK Mock 写出的 Quick Run，不是付费模型结果；未访问运营 runtime、未调用真实模型、未部署或提交。真实资料效果与运营接受仍待人工评审。
- 修改前基线 340 项通过；最终完整离线回归 **351 项通过（20.912 秒）**，前端交互 **31 项通过**。11 项新增匿名回归覆盖实际请求字段/角色/顺序、来源与字节只读、缺失清单/Context、历史值隔离、Prompt/哈希差异、带图编辑和失败 Run。浏览器验证默认卡片、390px 摘要、大视图、Prompt 全文、图片对照及来源跳转；截图只含匿名 Mock 样例。`git diff --check` 和新增文件空白检查通过。

**Context Flow Inspector V0.7（2026-10-23）：UI IMPLEMENTED / OFFLINE VERIFIED / HUMAN INTERACTION REVIEW PARTIAL。**

- 复用同一 `InspectorReader` 的已解析 documents/assets/context_view，纯 `inspector_graph.context_graph()` 投影构造 14 个 Artifact（包含缺失/不适用占位）、3 个 Activity 与 21 条关系；ID 绑定完整 Task/Image/revision/Run。来源带文件、JSON Pointer、原文件哈希及必要文字范围；检查结果与证据确定程度分开，不以当前 Prompt Builder 重建历史。
- 默认五阶段摘要；完整 SVG 图默认 12 节点、12 条主干关系，补充关系按需展开。实现节点/边选择、上下游高亮、缩放/平移/适应、键盘操作、三级详情、Prompt 原文定位和原图/成图对照；保留独立 Inspector、旧投影/缓存模板兼容与本机只读权限。Quick 无独立 Planning；本地尝试、SUCCEEDED、MATCH 均不声明远端执行、质量或人工通过。
- 修改前离线回归 351 项通过；新增 11 项图投影回归后完整 **362 项通过**，前端交互 **45 项通过**。匿名 HTTP 验证成功、编辑、Pass、第二张图、旧 revision、失败、缺失请求七种场景，受限图片哈希与证据字节未变；无 Run 时不虚构请求图。现有匿名 Quick Run 使用完整副本；新增分支样本明确标为 **NEW FIXTURE / SDK Mock**，不是真实付费结果。生成模型、Prompt、业务规则及 Evidence 格式未改，未访问运营 Runtime、未部署或提交。
- **人工验收边界**：上述实现检查点的浏览器工具持续返回 `Sky Computer Use native pipe startup failed`，当时未独立完成点击/布局/390px 体验与五张截图核验。用户本轮确认已有截图和部分操作体验，因此当前记 HUMAN INTERACTION REVIEW PARTIAL；不补造截图来源或逐项通过结果。完整浏览器交互清单尚未全部完成，不能由离线测试替代，也不记录整体 UI 或业务验收 PASS。

**FIX V0.7 — Writable Live Debug（2026-10-23，历史运行检查点）：IMPLEMENTED / OPERATOR REVIEW PENDING。** 8015 的 `POST /api/sessions` 405 来自匿名预览统一禁写，保存业务路由未改。新增仅显式 MOCK 白名单实例可用的 `read_only_workspace` 配置：服务端继续拒绝非 GET/HEAD，页面标明“匿名只读预览”、禁用保存/模型/确认/Pass/POST 导出，保留图片及本地历史版本查看和 Inspector。可写入口仍为 `./scripts/start_live_debug.sh` → 8013，正式 SDK、根目录 `.env` 自动加载、本地隔离 Runtime 范围及新 Task 自动授权均沿用现有实现；加载 V0.7，Inspector 本身仍只读。该阶段匿名临时测试完整离线回归 **366 项通过（20.567 秒）**，前端 **46 项通过**。当时 HTTP 核对 8013 为 LIVE DEBUG、可写、Key 配置 true（不代表账户验证），8015 只读且写入仍为 405，8012 未重启；不能当作本轮服务状态核验。未自动调用真实模型、未改历史 Evidence/Prompt/模型参数或部署。完整浏览器验收仍待完成，当前人工体验状态见上一条。

以下沿用此前已记录的核验与人工反馈；本轮本地 Live 准备仅读取上述已授权副本，不访问 Mac mini 或其他运营 Task，也不补写实验结论。

- T01：Run `20261014T052541Z-786016c60ae94a7c9168d74c55d4a36b` 保存真实首图，用户 PASS 见 [实验日志](03_EXPERIMENT_LOG.md)。不推广为其他图或普遍价值通过。
- T02：Task `7e0c5261dd6b40b9aa81f0750c626517` / Call `47321144e9e649f8bd247e03f3182f65`，reference_001 人工基准为“手持商品＋尺寸/重量信息”，模型却写入来自商品原图的“两种握法＋按钮特写”。既有核验显示身份、顺序、字节和 revision 2 应用正确；最早可观察偏差在模型返回理解。内因 UNKNOWN，结构重构没有修复语义质量。
- 新规划模型真实记录已存在：Task `43889e73c53c462da86216ed42f0a1ec` / Call `9d0a4751ae454f22b08b1f4d069ebfb1`，2026-10-16 replan，已应用 revision 4；不再描述为从未调用，也不推定新模型质量优于旧模型。
- T03：上述 case-001 Task、确认快照 3，有四张成功图片；reference_003 的 Run `20261014T063301Z-098375f4a339473c9f8168c5e8f88e5b` 为 APIConnectionError、attempted=true，无 request ID/usage。后续独立 Run 成功符合人工重试陈述，但没有点击事件的精确关联；远端执行、具体原因及重复计费 UNKNOWN。
- I01：Run `20261016T013618Z-c0952e3ddfff430189e350a8bbb27c00` 保存真实重设计图；用户仅对一个样本给出正面评价，原 review decision 仍空。首次缺资料记录未调用 API，不与真实模型失败混同。
- 真实带图编辑、连续修改、商品结构与日文保持、参考干扰、场景遗漏、批量费用及效率尚无完整评价；模型内部根因不得由现象直接推定。早期未定位的 `20261016T071710Z-94b3eab16e3c4f*` 现有准确标识记录如下，但本轮没有重新核验其原始文件。

**重要真实案例索引（文字记录，非本轮原始 Evidence 核验）**：现有 [M05 CASE-001](../../../enterprise-ai-theory/theory/M05_CASE_001_QUICK_REDESIGN_EVIDENCE_V0.1.md) 报告 Task `bbf3f10c42ad4a329438222ac1715d39` / Image `product_011` / revision 1 / Run `20261016T071710Z-94b3eab16e3c4f33a99a63332eaefdf6`，模式 Quick Redesign，未运行 T02。记录称该 Run **未证实主体替换**，主要问题是新增宣称缺少已保存商品事实支持；不能把“无依据”改写成“已经证明虚假”。该 M05 文件目前在理论仓库未跟踪，来源是既有调查报告，不等于本轮看过图片或恢复了完整请求。原始资料/本地副本可用性仍 UNKNOWN；若要调查真正的外观变形，先确认运营拒绝图片的准确 Task/Image/Run，不能用此样本预设根因。它也不与 T02 reference_001 理解偏差混为同一事件。

运营反馈保留：等待不清晰、多个商品任务管理、自然语言改图需求（2026-10-14）；两页切换成本、辅助图修正、Quick 重设计需求（2026-10-16）。对应功能已实现，能否改善质量/效率仍是待验证假设。
Product Brief 与实验日志保留其历史日期口径；其中“候选/未实现/Next Action”不代替本文件当前状态，不在本轮改写原始实验记录。

## 7. 已知限制与 UNKNOWN

- **单进程协调**：Store / 卡片锁与 active 为进程内状态，没有多进程协调、队列或后台调度；不能据此扩大 worker 数或保证多用户并发。
- **中断窗口**：快照→state、Run→指针、审核事件→指针均非跨文件事务；没有新增回滚或崩溃恢复策略。部分写入失败可能留下已完成文件。
- **调用不确定性**：SDK 零自动重试，Planning 超时 120 秒、Images 180 秒。图片链有 operation_id 与状态查询；批次未知即停、刷新不续跑。T02 没有同等持久化去重协议，人工新请求可能重复远端执行/计费。
- **数据与安全**：Task 路径隔离不构成用户权限；真实资料与 `.runtime/` 不入 Git，须单独备份。`.env` 已忽略，本轮模板及候选提交未发现真实凭据；不读取真实 `.env` 内容或将其作为测试数据。历史模板/聊天密钥与本地 `refs/codex/turn-diffs` 快照风险独立保留，撤销及曾否外泄仍 UNKNOWN；本轮不删除引用或改写历史，不把当前文件安全等同于历史风险消除。
- **诊断边界**：单文件来源哈希、缺失 HTTP/服务端内部信息、未返回 usage/账单与人工评价缺口仍存在；模型调用成功不能证明商品事实或视觉正确。
- **Inspector / Trace 边界**：图是已保存 Evidence 的只读投影；最近 Planning Call 关联可能为 INFERRED，不能补全历史 trace。SDK 请求留存不等于远端实际采用的视觉特征；Quick 的 Context 快照不是 T02 Plan。当前可视化不替代人工商品事实/外观评价，历史缺失不由当前 Builder 或 LLM 猜测补齐。
- **UNKNOWN｜当前线上状态**：本轮未核验 Mac mini 的实际版本、WSGI 导入/配置、密钥权限/额度、网络、备份现状、登录会话/整机重启及新增运营数据。历史部署或只读调查不等于今日状态；不得把本地 Cutover 或最新 HEAD 写成已部署。

## 8. Mac mini 历史记录与恢复线索（非当前核验）

本节整合原 README 的有效未提交部署记录及既有状态记录，仅表示 **2026-10-14～16 历史快照**；本轮不 SSH、不重启、不部署。
历史服务器：`andy_server@192.168.112.37`；根目录 `/Users/andy_server/commerce-image-poc-pilot/`；入口 `https://192.168.112.37:8444/`。
代码 `releases/`、业务 `data/.runtime/`、私有配置 `config/`、环境 `venv/`、备份 `backups/` 分离；旧 WSGI 为 `config/pilot_wsgi.py`，调用兼容 `prepare_plan.create_app(runtime_dir, case_dir)`。

| 历史发布 | 应用源与记录 |
|---|---|
| 2026-10-14 | T04 `7a692f3`；独立迁移 case-001 真实任务及证据，原件保留 |
| 2026-10-15 | Planning 配置 `a2e1123`；环境配置持久化，保留 4.1 回退 |
| 2026-10-16 10:36 起 | I01～I03 `a69470f`；本地副本 `.runtime/deployment/i01-i03-20261016/`，备份 `deploy-20261016T023608Z-c3c76339/` |
| 2026-10-16 13:32 起 | 逐图确认/批次 `e7094352a0bb728f28517f1b519899dafba6f9b0`；只同步 14 个应用/测试文件；记录 `.runtime/deployment/per-image-batch-20261016/` |
| 2026-10-16 14:48～14:55 | 共享交互/视觉 `cd66dad5216fddd8a365494e7652d625702dd722`；只同步 6 个前端文件和 3 个测试；记录 `.runtime/deployment/workspace-visual-20261016T064810Z-3b1cb442/` |

最后一条历史记录中，实际代码 cd66dad 更新在仍名为 `releases/e7094352a0bb728f28517f1b519899dafba6f9b0/` 的目录，未改 LaunchAgent；**目录名不能代替 `.pilot-source.json` 与文件哈希判定版本**。
当时 e709435 发布前后 788 个业务文件一致，本地/服务器各 92 项测试通过；cd66dad 发布前后 789 文件一致，各 93 项测试与 7 项访问检查通过。
最后记录的只读 HTTPS 检查为 15 个任务、98 张输入、21 张当前成图、27 个版本、4 张含 Pass 卡片；case-001 实验包 78 文件哈希匹配，最终图片包可下载。浏览器核对共享交互、草稿隔离、刷新及 Quick 入口，没有执行真实 AI 或改变历史审核。

备份路径相对服务器根目录；历史备份与校验信息保留如下，不表示本轮确认它们仍存在或可恢复：

| 批次 | 数据归档与历史 SHA-256 |
|---|---|
| I01～I03 | `backups/20261016T023530Z-f0d54881.tar.gz`；`c57004b0121ec5d2642e6d84f4a1ae11193396984285b77c4eb50ca8b3da9742` |
| e709435 | `backups/deploy-20261016T053210Z-1b6f34a6/data.tar.gz`；`a1f8fa8421426265dca7977b580a6533bf3bc675d10086efece2521c628c4d9f` |
| cd66dad | `backups/deploy-20261016T064810Z-3b1cb442/data.tar.gz`；`a235caa48ac2a8bd531f85d774bde577d406a22d454667c1c92b039e6b2bceae` |

后两批备份目录另存 `code.tar.gz`、原 LaunchAgent、数据清单与检查结果；cd66dad 另有 `source-manifest-before.json`。历史为同机备份，未验证异机/定时备份。
恢复只回退代码与必要兼容配置，不用数据归档覆盖运营新增任务；先核对空闲、备份和数据格式兼容，再停本服务、等待数据锁、恢复代码/清单并启动。
cd66dad 是原目录内更新，旧代码应从该批 `code.tar.gz` 和原清单恢复；新增 visual.css/交互测试需留档，不能直接把 e709435 目录当旧代码。逐图确认/新模式数据也不能盲目交给更旧业务逻辑改写。

历史访问/配置：HTTPS 8444，无账号密码；`config/settings.json` / `PILOT_ALLOWED_CIDRS` 为 `192.168.112.0/24`、`127.0.0.1/32`、`::1/128`。只用实际来源地址，不信任转发头，未开放公网；获准网段共享全部试用任务。
历史自签证书指纹 `86:6C:F7:D5:5A:59:D0:75:E8:B9:9D:65:20:D5:6D:A7:7F:AF:DF:BC:7E:75:26:E8:39:9E:12:85:94:18:B8:44`；应核对并建立信任，不代为绕过浏览器警告。
历史密钥位置 `config/openai_api_key`（0600）、配置目录 0700，由 `config/configure_secret.py openai` 隐藏交互录入、WSGI 加载；不复制本地 env 或把密钥放入 plist。2026-10-15/16 曾检查为已配置，不代表今日状态或已轮换。
历史服务 Label 为 `com.song36.commerce-image-pilot`，用户 LaunchAgent 在 `~/Library/LaunchAgents/com.song36.commerce-image-pilot.plist`，当时域 `gui/501`、单个 gthread worker/4 线程，需要用户登录会话。
历史密钥录入、`config/backup.py`、launchctl 启停工具均只作为恢复线索；后续须先核验实际配置和活动请求。`scripts/deploy_pilot.py` 的本地预检也会 SSH，不在本轮执行。

## 9. 下一阶段

- **P3 学习状态（2026-10-23）**：P3-01 ACTIVE，第一轮按 A 系统全貌 / B 单图调用链 / C 失败证据三个检查点快速定向。Client/Server、Flask、应用初始化已有 ORIENTED 基础，独立追踪与复述尚未确认完成。主线 A 以商品变形案例学习 Context/Multimodal/Image/Evaluation，主线 B 按需补足 Python 后端、Runtime、Persistence 与调试；Inspector 是证据辅助工具，不替代学习或语义评价。L1～L5 仅后续专题索引，P3-02～04 NOT_STARTED；见 [P3 主文档](../learning/P3_SOURCE_WALKTHROUGH_STUDY_V0.1.md)。Mac mini 核验仍 DEFER。

源码组织整理到此结束。后续按人工授权进行走读与诊断，不自动启动重构、付费实验或新业务：

1. 本地源码执行链走读：从正式入口到 Task / Planning / Generation / Review。
2. AI 业务数据通路：原始素材、图片角色、Context、请求、输出与人工接受。
3. Python 后端运行通路：应用组装、同步 HTTP、文件写入、锁与版本。
4. 失败诊断及 Evidence：区分最早可观察偏差、软件错误、模型假设与 UNKNOWN。
5. Mac mini 当前版本、WSGI、安全与备份核验：**DEFER**，需另行授权。

**HISTORICAL SNAPSHOT｜2026-10-23 三仓接续：**blueprint 已按当时共识更新既有 Vision/演进台账，检查点 `60ac4bfc3f5d803950fcdcc9c0c29a39f082a5e7`；理论仓库 HEAD 仍为 `d0ab310`，M04 实验脚本及多份学习记录未跟踪，按本轮规则停止该仓写入/提交，不把它们当作已版本化成果。近期业务学习重心为 M04/M05/M07；详细状态与最小后续任务见 P3 末尾交接。

**历史文档同步范围（2026-10-23）：**当时只同步本文件与 P3 主文档，保留既有业务及部署历史；不改源码/Prompt/测试/运行数据，不新增实验日志，不 Push、部署或操作现有服务。历史凭据撤销仍 UNKNOWN；保留本地快照引用，不将当前文件安全视为历史风险已消除。
