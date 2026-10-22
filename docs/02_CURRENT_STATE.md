# Current State

> 核查日期：2026-10-22（Asia/Shanghai）。当前代码基线：`main` / `78c68f9f25639d77abfdc3792a36541912f8af09`。
> 该 SHA 是 FINAL CUTOVER 源码检查点；后续本轮文档提交不改变业务源码基线。线上状态 **UNKNOWN / UNVERIFIED**。

## 1. 定位与当前阶段

`commerce-image-poc` 是多工作流 AIGC 系统的第一个真实业务切入点，当前服务于跨境电商 AI 商品图制作与修改，未来系统不局限于商品图。
阶段仍为 **INTERNAL PILOT / BUSINESS VALIDATION**。源码结构整理阶段已结束，不继续目录重构或预建通用平台。
严格区分工程实现、软件测试、真实模型效果与运营验收；模型返回成功不等于业务接受。

## 2. 已实现的业务闭环

- **输入与任务**：任务中心创建/恢复独立 Task；保存商品原图、设计参考、Listing、描述、商品事实说明及整体要求。改原始输入保存为新任务，不覆盖旧任务。
- **商品图包**：一次理解请求可完成商品/参考理解与 N 张计划；支持理解修正、单张计划修改、逐图人工确认及过期保护，不强制拆分模型阶段。
- **Quick Redesign**：N 张原图各对应独立任务；整体要求、商品约束及风格参考可选，不强制 Listing、商品理解或制作计划。
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
| [app.py](../src/app.py) | 唯一正式 `create_app()`、配置与依赖组装；保留 Store 适配、Planning IO 注入和进程内活动状态 |
| [api/](../src/api/) | `register_routes()`：请求解析、HTTP 响应和错误映射；原 23 条路由身份保留 |
| [image_workflow/tasks/](../src/image_workflow/tasks/) | `rules` 状态规则，`service` Task 用例，`queries` 查询，`storage` 资料校验/存取；`images` 协调图片操作，`generation` 拥有锁/去重，`generation_runtime` 绑定依赖，`review` 适配审核 |
| [image_workflow/planning/](../src/image_workflow/planning/) | 纯请求构建、结果结构/身份校验、Responses 执行与调用 Evidence；不进行人工语义验收 |
| [image_workflow/generation/](../src/image_workflow/generation/) | 商品包/Quick 的 Context 与 Prompt、Images 执行、结果校验及 Run 保存；辅助图策略归于此处 |
| [image_workflow/review/](../src/image_workflow/review/) | 成功版本查询、选择、Pass、审核事件和最终图片 ZIP，不执行图像模型 |
| [image_workflow/experiment_export.py](../src/image_workflow/experiment_export.py) | 当前任务实验包，保留 ACTUAL / RECONSTRUCTED / MISSING 来源等级与哈希校验 |
| [infrastructure/](../src/infrastructure/) | `evidence` 通用脱敏/私密字段过滤；`openai_images` Images SDK 客户端及参数，无业务/CLI 反向依赖 |
| [persistence/](../src/persistence/) / [file_ops.py](../src/file_ops.py) | Task 当前状态/不可变快照、审核文件、路径/哈希/JSON；不替调用方推进业务状态，不提供多文件事务 |
| [cli/](../src/cli/) | T01 与 Quick 实验入口，默认免费检查；不成为正式业务的导入依赖 |
| [templates/](../src/templates/) / [static/](../src/static/) | 原生前端；prepare/workspace/generate 协同，批次由浏览器顺序执行，无后台 Worker |

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
Images 默认 `gpt-image-2.5-sunburst`，另允许 `gpt-image-2.5-flare`；`images.edit`、n=1、low、PNG。默认竖图，Quick 支持已有方图/横图尺寸。
商品资料决定事实依据，参考只借鉴设计；图片编辑先送当前选中成图，再送必要原始依据、本图参考和本次辅助图/意见，不重跑完整规划或无条件携带全部历史。
源码依据：[Planning request](../src/image_workflow/planning/request.py)、[Generation request](../src/image_workflow/generation/request.py)、[Quick Prompt](../src/image_workflow/generation/quick_prompt.py)、[Images 配置](../src/infrastructure/openai_images.py)。

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

回归依据：[Cutover](../tests/test_source_cutover.py)、[HTTP](../tests/test_api_package.py)、[T02 请求](../tests/test_t02_request_construction.py)、[图片边界](../tests/test_t02_image_boundaries.py)、[Generation](../tests/test_generation_package.py)、[Review](../tests/test_review_package.py)、[Task 持久化](../tests/test_task_state_persistence.py)、[实验 ZIP](../tests/test_experiment_export_package.py)、[前端交互](../tests/unified_interaction.test.cjs)。

## 6. 历史真实实验、失败与质量缺口

以下沿用此前已记录的核验与人工反馈；本轮仅核对源码、Git 和软件测试，不重新读取真实 runtime、执行模型或补写实验结论。

- T01：Run `20261014T052541Z-786016c60ae94a7c9168d74c55d4a36b` 保存真实首图，用户 PASS 见 [实验日志](03_EXPERIMENT_LOG.md)。不推广为其他图或普遍价值通过。
- T02：Task `7e0c5261dd6b40b9aa81f0750c626517` / Call `47321144e9e649f8bd247e03f3182f65`，reference_001 人工基准为“手持商品＋尺寸/重量信息”，模型却写入来自商品原图的“两种握法＋按钮特写”。既有核验显示身份、顺序、字节和 revision 2 应用正确；最早可观察偏差在模型返回理解。内因 UNKNOWN，结构重构没有修复语义质量。
- 新规划模型真实记录已存在：Task `43889e73c53c462da86216ed42f0a1ec` / Call `9d0a4751ae454f22b08b1f4d069ebfb1`，2026-10-16 replan，已应用 revision 4；不再描述为从未调用，也不推定新模型质量优于旧模型。
- T03：上述 case-001 Task、确认快照 3，有四张成功图片；reference_003 的 Run `20261014T063301Z-098375f4a339473c9f8168c5e8f88e5b` 为 APIConnectionError、attempted=true，无 request ID/usage。后续独立 Run 成功符合人工重试陈述，但没有点击事件的精确关联；远端执行、具体原因及重复计费 UNKNOWN。
- I01：Run `20261016T013618Z-c0952e3ddfff430189e350a8bbb27c00` 保存真实重设计图；用户仅对一个样本给出正面评价，原 review decision 仍空。首次缺资料记录未调用 API，不与真实模型失败混同。
- 真实带图编辑、连续修改、商品结构与日文保持、参考干扰、场景物体遗漏、批量费用及效率尚无完整评价；模型内部根因不得由现象直接推定。目标 Run `20261016T071710Z-94b3eab16e3c4f*` 此前本地未定位，用户称可能在 Mac mini，本轮不追加根因结论。

运营反馈保留：等待不清晰、多个商品任务管理、自然语言改图需求（2026-10-14）；两页切换成本、辅助图修正、Quick 重设计需求（2026-10-16）。对应功能已实现，能否改善质量/效率仍是待验证假设。
Product Brief 与实验日志保留其历史日期口径；其中“候选/未实现/Next Action”不代替本文件当前状态，不在本轮改写原始实验记录。

## 7. 已知限制与 UNKNOWN

- **单进程协调**：Store / 卡片锁与 active 为进程内状态，没有多进程协调、队列或后台调度；不能据此扩大 worker 数或保证多用户并发。
- **中断窗口**：快照→state、Run→指针、审核事件→指针均非跨文件事务；没有新增回滚或崩溃恢复策略。部分写入失败可能留下已完成文件。
- **调用不确定性**：SDK 零自动重试，Planning 超时 120 秒、Images 180 秒。图片链有 operation_id 与状态查询；批次未知即停、刷新不续跑。T02 没有同等持久化去重协议，人工新请求可能重复远端执行/计费。
- **数据与安全**：Task 路径隔离不构成用户权限；真实资料与 `.runtime/` 不入 Git，须单独备份。密钥不写前端/日志/Evidence；旧 `.env.example` 曾疑似含凭据，不读取或作为配置来源，轮换状态 UNKNOWN。
- **诊断边界**：单文件来源哈希、缺失 HTTP/服务端内部信息、未返回 usage/账单与人工评价缺口仍存在；模型调用成功不能证明商品事实或视觉正确。
- **线上状态**：Mac mini 实际版本、WSGI 导入/配置、密钥权限/额度、网络、备份现状、登录会话/整机重启及新增运营数据均未核验。不得把本地 Cutover 版本写成已部署。

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

源码组织整理到此结束。后续按人工授权进行走读与诊断，不自动启动重构、付费实验或新业务：

1. 本地源码执行链走读：从正式入口到 Task / Planning / Generation / Review。
2. AI 业务数据通路：原始素材、图片角色、Context、请求、输出与人工接受。
3. Python 后端运行通路：应用组装、同步 HTTP、文件写入、锁与版本。
4. 失败诊断及 Evidence：区分最早可观察偏差、软件错误、模型假设与 UNKNOWN。
5. Mac mini 当前版本、WSGI、安全与备份核验：**DEFER**，需另行授权。

本轮只更新 README 与本文件，并创建独立文档 Commit；不改源码/Prompt/测试/运行数据，不新增实验日志，不 Push 或部署。
