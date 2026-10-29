# Current State

## V1 Overall Project Status

**总览更新：2026-10-29（Asia/Shanghai）。当前阶段：V1 工程基础已建立，Knowledge 可选接入处于离线验证阶段；BUSINESS ACCEPTANCE PENDING。** `commerce-image-poc` 是长期 AIGC / 多模态系统的首个商品图业务切片；当前核心问题仍是商品主体、接口、喷头及附件保真，以及有依据的营销信息能否正确进入最终图片。

**当前决定：暂停新增开发，进入 LOCAL RUNTIME / USABILITY INSPECTION。** 保留此前 PAUSED FOR REVIEW / BUSINESS REALITY CHECK 的业务核对方向；本轮新增授权仅为 B-02 与本文分别提交、离线回归、本地启动和免费 UI 检查。仍不授权新功能、Agent Runtime、架构重构、付费模型实验或部署；下表 Next Action 均是恢复后候选，不是执行授权。工作节奏调整不代表已关闭服务或修改部署。

**本轮核验基线（OBSERVED）：**起始为 `main / 815e4db10f790d7194e9e836379efa4316df75f3`（B-01），暂存区为空，5 Modified + 2 Untracked。复核并重跑隔离回归后，B-02 六个文件已独立提交为 **`53013f80c7123a34dd8d23b643c3e5fd721a7d98`**，`feat: integrate listing knowledge into planning`；这是本文提交前最新工程基线。既有总览内容保留，本文单独归档；本轮不 Push、不部署、不调用真实模型。

**证据时效：**Git、B-02 Diff 与源码接入点已核对，本轮实际隔离回归 **Python 539 PASS / 独立 Node 73 PASS**，`pip check` 通过；测试禁止真实网络、读取真实密钥/Runtime 及写入仓库。下文旧浏览器记录、真实模型结果仍为 **PREVIOUSLY REPORTED**，不因本次回归升级为新版真实业务验收；本地启动/UI 结果另按本轮实际交付记录，不在文档提交前预填成功。

业务规则以 [Business Baseline V0.3](../02_BUSINESS_MODELING/V1_BUSINESS_BASELINE_V0.3.md)为准；[能力拆解](../03_AI_CAPABILITY_DECOMPOSITION/IMAGE_AI_CAPABILITY_DECOMPOSITION_V0.1.md)、[架构候选](../04_AI_AGENT_SUITABILITY/IMAGE_AI_ARCHITECTURE_DECISION_V0.1.md)和[实施契约](../05_TASK_CONTRACT_EVALUATION/V1_IMPLEMENTATION_CONTRACT_V0.1.md)保留各自的研究 / PROPOSED 状态。它们的历史“待实施”描述不是当前代码状态；已授权增量的完成情况以下表及 Git 检查点为准，文档归档也不等于后续 Coding 授权。

**状态口径：**`IMPLEMENTED` 表示代码存在；`ENGINEERING VERIFIED` 表示指定离线工程范围通过；`BROWSER VERIFIED WITH MOCK` 表示真实浏览器中的匿名 Mock 操作通过；`REAL MODEL VERIFIED` 仅适用于有真实调用证据且明确写出的验证范围，不自动包含语义或图片质量。`BUSINESS ACCEPTED` 必须有对应案例的运营接受证据。`RESEARCH ONLY`、`NOT IMPLEMENTED`、`UNKNOWN` 分别表示研究资产、尚无对应实现、证据不足；同一模块可以同时有多个状态。

| Module | Implementation Status | Verification Status / Evidence | Known Limitations | Next Action（恢复后候选） |
| --- | --- | --- | --- | --- |
| Quick-A 同款快速改版 | IMPLEMENTED（入口、持久化、场景请求策略） | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK；E1-01、E1-03 及既有模式记录 | `quick_redesign` 子场景；无强制 Planning；保留适用信息的真实效果未验收 | 用运营确认同款、同外观的样本验收 |
| Quick-B 换主体快速改版 | IMPLEMENTED（入口、持久化、主体替换请求策略） | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK；[场景请求测试](../../tests/test_quick_scenario_policy.py)及既有模式记录 | 仍复用 Quick 后端；全域替换是否成功、适用卖点是否正确 UNKNOWN | 用运营确认外观不同且卖点适用的样本验收 |
| Listing / Planning | IMPLEMENTED（`product_pack`，资料理解、逐图计划及人工确认） | ENGINEERING VERIFIED / 模式 BROWSER VERIFIED WITH MOCK / REAL MODEL VERIFIED（Planning 调用及结构校验）；E1-04、`8bb1c6c`、真实 Task `63c1448453ac48c6aeb03bafa82ef8ea` | 真实计划通过 ID/来源校验后仍因删除授权 15° 的语义错误停止；不是完整 Listing 业务通过 | 人工修订并确认后验证正式 Listing 生图 |
| 商品与参考素材输入 | IMPLEMENTED | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK；共享上传、角色、绑定及[Quick V1 测试](../../tests/test_quick_v1.py) | 多张商品图属于同 SKU 是业务约定，不是自动 SKU/真伪识别；商品素材张数不决定输出数 | 核对真实样本角色、来源及完整性 |
| 五类输出 / 动态 N 图位 | IMPLEMENTED | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK；E1-02、[动态图位测试](../../tests/test_dynamic_slots.py)、超过 8 项及删除/另存记录 | 卖点/场景动态 N，主图/尺寸/对比各 max1；无固定业务总数不等于 Planning 容量无限 | 验收实际业务数量与制作成本 |
| Manual Plan Edit | IMPLEMENTED | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK；`a6222db`、[可用性测试](../../tests/test_v1_usability.py)、TEST-01～10 | 免费编辑，不重新 Planning；只撤销本图确认，保留事实争议及版本校验；编辑后真实生图未验证 | 完成人工编辑→正式确认→真实生成闭环 |
| Low / Medium / High | IMPLEMENTED（Task 默认与逐图覆盖） | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK；`a6222db`、SDK Mock 参数断言 | 新 Web Task 默认 Medium，历史/API/CLI 缺省 Low；High 不保证保真，Medium/High 真实效果与费用未测 | 有独立预算后核对参数、效果与成本 |
| Generation / Revision | IMPLEMENTED | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK；父 Run、锁、operation_id、失败保留回归；真实 Images 见本页实验索引 | 新 Run 不覆盖旧版本，零自动重试；Direct Smoke 两图不等于正式 Listing 端到端，真实修改保真未验收 | 验收确认计划到成图、修改及失败停止 |
| Reject / Feedback | IMPLEMENTED | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK；`a6222db`、选定 Run 原因/备注及显式复用测试 | 不自动修改/重试，不覆盖旧 Pass；未 Pass 不等于 Reject；真实运营评价尚未完成 | 收集真实拒绝原因与返工意见 |
| Select / Pass / ZIP | IMPLEMENTED | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK；选定版本、旧版本保留及 ZIP 字节核对；[审核实现](../../src/image_workflow/review/service.py) | Pass 绑定指定版本；V1 三场景无完整运营接受链，历史 T01 单图 PASS 不能外推 | 由运营审核并导出接受版本 |
| 尺寸专项素材 | IMPLEMENTED | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK（既有交互范围）；E1-04、[业务保护测试](../../tests/test_business_guards.py) | 必须绑定本 Task product、声明并保持素材一致；声明不是尺寸认证，真实尺寸成图未验收 | 用有效专项素材及缺失反例验收 |
| Listing 事实冲突处理 | IMPLEMENTED | ENGINEERING VERIFIED；完整浏览器/真实识别效果 UNKNOWN；E1-04、[契约测试](../../tests/test_listing_planning_contract.py) | 明显冲突与证据不足分流，处理绑定版本；未报告冲突不等于事实认证 | 核对正反例、处理后重新确认的完整交互 |
| 单图 Context / 历史 Prompt 兼容 | IMPLEMENTED | ENGINEERING VERIFIED；`3008891`、[Context 测试](../../tests/test_context_contract.py) | Listing 各图独立传递类型、要求及 reference 身份；Inspector 兼容新旧标题，无法确认时 UNKNOWN；新版真实链路未验收 | 用同一实际 Run 对照 Context、Prompt 与输入 |
| Workflow Inspector V0.7 | IMPLEMENTED（只读） | ENGINEERING VERIFIED / BROWSER VERIFIED WITH MOCK（已操作范围）；[Graph](../../src/image_workflow/inspector_graph.py)及工作台记录 | 显式本地启用；历史 Planning 关联可能 INFERRED，缺失不补造；完整交互清单未全量验收 | 复用现有工具调查，不继续扩张 UI |
| Business Rules | IMPLEMENTED（部分） | ENGINEERING VERIFIED；图位/角色/来源/版本/尺寸/争议等校验及 Quick 场景请求测试 | 商品事实、主体保持与营销语义部分仍是 Prompt 约束，测试不证明模型服从 | 区分确定性保护、模型责任与运营确认 |
| Knowledge K01～K06 / Registry | IMPLEMENTED（B-01 已提交）；内容仍为 RESEARCH_CANDIDATE | ENGINEERING VERIFIED（既有报告）；本轮核对[资产](../../src/image_workflow/knowledge/cards_v0_1.json)、[Registry](../../src/image_workflow/knowledge/registry.py)及 Commit | 版本、来源和哈希已保存；来源仍待核查，研究资产不等于业务有效知识；未默认注入生产请求 | 恢复后先审核适用条件与实际业务需要 |
| Method Candidate Selection | IMPLEMENTED（B-01 已提交） | ENGINEERING VERIFIED（既有报告）；[选择器](../../src/image_workflow/knowledge/selection.py)、[测试](../../tests/test_knowledge_methods.py) | 按显式条件保留选择/未选/缺失依据；不自动理解图片，不证明模型采用或专业收益 | 按实际案例核对候选选择及条件来源 |
| Listing Knowledge Runtime | IMPLEMENTED（B-02 已提交；默认关闭） | ENGINEERING VERIFIED：本轮 Python 539、Node 73；[接入](../../src/image_workflow/planning/knowledge.py)、[测试](../../tests/test_listing_knowledge.py) | ENGINEERING INTEGRATED / NOT OPERATOR-ACCESSIBLE BY DEFAULT；无前端开关，不能视为生产已启用；未真实模型验证，MODEL_ADOPTION_UNKNOWN | 先检查实际工作台；Knowledge 受控真实验证须另行授权 |
| Skills | NOT IMPLEMENTED（正式运行时）；RESEARCH ONLY | 无正式 Skills 调度或业务收益验证记录 | 普通函数、Prompt 和知识卡不是已验证专业 Skill | 只有明确重复任务与收益证据后再研究 |
| AI Decision | IMPLEMENTED（L1～L3 基础） | 确定性 Rules、真实模型判断与条件分支已有记录；业务效果仍 PENDING | LLM 判断不是自主 Agent；04/05 文档保留 PROPOSED 边界 | 先核对现有决策对业务的实际帮助 |
| Bounded Agent | NOT IMPLEMENTED（L4 Runtime）；RESEARCH ONLY | 无正式任务级动态工具选择/执行反馈 Runtime 的验证记录 | 保留按需扩展边界，不是当前开发任务或一期前置 | 仅在独立业务证据及授权下另行决定 |
| 商品视觉保真 | IMPLEMENTED（素材依据与 Prompt 约束） | Direct Smoke 两图已有初评；稳定保真 UNKNOWN | 喷头、接口、泡沫附件/瓶体有偏差；模型内部根因及通用解决方法未证实 | 结合原图、实际请求及运营评价定位问题 |
| 真实业务验收 | 主链已实现；当前 V1 尚未 BUSINESS ACCEPTED | BUSINESS ACCEPTANCE PENDING；历史 T01 仅单张用户 PASS | 正式 Listing、Quick-A/B 真实闭环未验收；运营正式 Pass、接受率、返工时间/成本基线仍缺 | 优先完成一个明确范围的真实运营闭环 |

### 当前工程、运行与证据边界

- **源码与闭环：**[app.py](../../src/app.py) / [API](../../src/api/) → [Task](../../src/image_workflow/tasks/) → [Planning](../../src/image_workflow/planning/) / [Generation](../../src/image_workflow/generation/) / [Review](../../src/image_workflow/review/) → [Persistence](../../src/persistence/) / [Infrastructure](../../src/infrastructure/)；前端与 CLI 复用这些能力，未新建 Agent 引擎。已实现输入→规划/直接生成→人工确认（Listing）→生成/修改→版本→审核→导出及 Evidence 留存；“实现闭环”不表示真实业务已全部通过。
- **本地入口：**项目根目录执行 `./scripts/start_live_debug.sh`，沿用现有 `.venv`、`src/cli/debug_workspace.py`，监听 `http://127.0.0.1:8013/`，Runtime 固定为 `.runtime/debug/live-debug-20261023T013447Z/runtime`。只按字面量加载根目录 `.env` 的 `OPENAI_API_KEY`，已有非空进程环境优先，不读 `.env.example`；Key 非空不代表认证成功。脚本启用手动付费操作，启动本身不调用模型，不能当作离线 Mock 启动器。
- **开发与运营隔离：**Live Debug 使用正式客户端、独立 Runtime，Inspector 在其安全范围内跟随合法 Task；普通 `create_app()` 默认不开放完整 Inspector。本轮启动前观察到 8012 已监听、8013 空闲，保留 8012；最新版本实际启动/HTTP/UI 结果以后续检查为准，不能从源码提交推定运行成功。远端版本、本地/远端同步及 Mac mini 实际部署/WSGI/数据/备份状态未核验，继续 **UNKNOWN / DEFER**；本轮不部署或改动 Pilot。
- **Evidence / Trace：**保存输入与哈希、Context、Prompt、请求参数、响应/错误、Run、父版本、审核指针；Inspector 是只读投影。SDK 请求记录不证明提供方内部有效 Prompt、图片权重或模型遵守约束；Usage/request_id/费用以实际返回为准。源码哈希仍非完整包追踪；进程内锁/active 非跨进程协调，多文件写入非事务。Runtime 必须独立备份；历史凭据与快照引用风险未由本次核验消除。

### 工程检查点与验证范围

`a6222dbc1ae1ae6d5426bb03190183e1749bae6a` 已提交 Manual Plan Edit、Low/Medium/High、Task 默认及逐图质量覆盖、Reject/Feedback，以及相应版本和历史兼容保护。质量偏好独立持久化，不重写历史 Run 或确认快照；人工计划修改保留原始 AI 响应及 HUMAN_EDIT 差异；Reject 保留被评价的 Run 和旧 Pass。

| 检查点 / 验证项 | 结果与核验时效 | 范围与限制 |
| --- | --- | --- |
| V1 Usability Closure / Python | **466 PASS，0 失败/错误/跳过**，24.476 秒 | `a6222db` 当时的匿名临时素材、假 Key、SDK Mock 回归；包含 Node 包装，不与 Node 数量相加，不是当前 HEAD 的新测结果 |
| V1 Usability Closure / 独立 Node | **73 PASS，0 失败/跳过** | 前端状态/DOM 测试不等于浏览器验收 |
| V1 Usability Closure / Edge Chromium + CDP | **TEST-01～10 最终 PASS；BROWSER VERIFIED WITH MOCK** | 3 次 Planning / 6 次 Images 均为 SDK Mock；390px 无横向溢出；初次 TEST-09 驱动失败及修正后重测记录保留，不外推为 B-02 浏览器验收 |
| Context / Inspector 修复、B-01 | 已有离线通过报告；本轮确认 `3008891`、`815e4db` 的提交范围 | 单图 Context、Prompt 解析、Registry 与候选选择；没有由此证明真实模型效果 |
| B-02 最新离线回归 | **本轮实际：Python 539 PASS，0 失败/错误/跳过，26.639 秒；独立 Node 73 PASS，0 失败/跳过；pip check 通过** | 假 Key / SDK Mock；外层保护禁止网络、真实密钥/Runtime 读取及仓库写入。日志位于 `/private/tmp/v1-local-usability-20261029-zr9hofvd/python-regression.log`、`node-regression.log`；临时日志不属于永久 Git Evidence |
| V1 可用性、B-01/B-02 开发及本轮状态整理的真实模型 | **各自记录为 0 次；本轮 0 次** | 不覆盖既有 Direct Smoke 的两张真实产物；没有 Medium/High、Knowledge 接入或新版完整 Listing 的真实验收 |
| 运营与运行环境 | **BUSINESS ACCEPTANCE PENDING；运行版本 UNKNOWN** | 当前 V1 无正式运营 Pass；远端/部署及本地服务代码版本本轮未核实 |

既有浏览器报告引用仓库外临时目录 `/private/tmp/v1-usability-browser-llzs50yq/`，包括 `engineering-checkpoint.json`、`browser-report.json`、`python-final.log`、`node-final.log`、`sdk_mock_calls.json`、`download_integrity.json`。**本轮未复查该临时目录是否仍存在**；临时文件不是永久 Git 归档，失效后不可补造截图或操作记录。

### Knowledge 检查点：B-01 / B-02 均已提交

- **B-01（COMMITTED）：**`815e4db10f790d7194e9e836379efa4316df75f3` 包含 K01～K06 运行时资产、Knowledge Registry 与 Method Candidate Selection，以及版本、来源、内容哈希、适用性与选择依据。资产仍标记 `RESEARCH_CANDIDATE`，来源为 `SOURCE_LEAD_VERIFY`；存在可加载代码不等于来源已独立核验或成图有效。
- **B-02（COMMITTED / ENGINEERING VERIFIED）：**`53013f80c7123a34dd8d23b643c3e5fd721a7d98`，复用正式 Listing Planning 路径；`knowledge_enabled` 是严格布尔、调用级 opt-in，**默认关闭、没有前端开关**，不把开关写成 Task 永久配置。只有符合来源归属和原文匹配要求的显式结构化条件才参与选择；来源验证不认证条件语义或商品事实，无条件时保持 UNKNOWN / `NO_METHOD_SELECTED`，不自动理解图片或推测适用性。
- **请求与 Evidence：**选中的方法作为独立 `PROFESSIONAL DESIGN METHODS` Context 加入实际请求，保留 reference 适用范围、字符预算及未选原因；新调用保存 `knowledge.json`、有效 Prompt、版本/哈希及选择依据。持续记录 `MODEL_ADOPTION_UNKNOWN`，知识进入请求不证明模型采用，更不证明图片质量改善；不是所有历史调用都已有 `knowledge.json`。
- **本次六文件提交范围：**修改 `src/app.py`、`src/image_workflow/planning/request.py`、`src/image_workflow/planning/service.py`、`src/image_workflow/tasks/service.py`；新增 `src/image_workflow/planning/knowledge.py`、`tests/test_listing_knowledge.py`。未包含本文、历史 Evidence 或 Runtime；本文为独立文档提交。不 Push、不部署，不得将本地归档描述为生产 Knowledge 已启用。
- **验证限制：**B-02 本轮实际 Python 539 / Node 73 通过。尚无该接入通路的真实模型验证，尚未证明 Knowledge 提高方案或成图质量；原 S5 独立 A/B 不等于 B-02 Runtime 验收。

### 开发历史与可核实 Git 检查点

以下仅作进度索引；详细过程保留在本文历史正文。E1 子任务编号是实际增量检查点，不表示 05 候选契约的全部阶段已验收。

| 阶段 | 完成范围 / 验证边界 | 已核实 Git Commit |
| --- | --- | --- |
| E0 | 工程差距调查与业务增量冻结；调查本身没有独立代码提交 | 审查基线 `e322d97d68a5cad4f0171263e0d350e4f6cb2f71`；共享输入/动态 N 文档 `4b19fd7c97800549bbf0a0fcefb8bf3752fc6593` |
| E1-01 | 三入口、共享输入、Listing reference 计划身份；当时场景策略尚待实施 | `c93bd900eb5aa530436b3bc2ea61a07fdb67cdc8` |
| E1-02 | 卖点/场景动态 N、稳定身份、保存/恢复/另存 | `4e42f17d76cef156826edfaae8324621a3d0caab` |
| E1-03 | Quick-A/B 信息权限及主体替换请求策略；非真实质量通过 | `d1999bc4de76a1042ee584f5e8e698bcdc9c97e1` |
| E1-04 | 尺寸专项、Listing 事实冲突、确认/版本与历史分类另存保护 | `ff7526ea39afecc75368ce0a23b3248aa55ba351`；当时浏览器 NOT TESTED，后续只按已验证操作补充 |
| E1-05 | 隔离浏览器与真实模型探索；失败、语义阻断、Direct Smoke 分开保留 | Listing 契约修复 `8bb1c6cff8b558b9310ec763171a4946902a1057`；Runtime 实验不属于已提交源码，也不是业务通过 Commit |
| V1 Usability Closure | 免费人工 Plan Edit、质量选择/覆盖、Reject/Feedback、历史兼容；466 Python / 73 Node / 10 浏览器 Mock 项通过 | `a6222dbc1ae1ae6d5426bb03190183e1749bae6a` |
| A — Context Contract Fix | Listing 逐图 Context 独立传递、Inspector 新旧 Quick Prompt 兼容；离线验证不代表模型遵从 | `3008891cbe41e7615362fe8165b0f5fa54f0ff2f` |
| B-01 — Knowledge Assets + Method Selection | K01～K06 运行时资产、Registry、候选选择、版本/来源/哈希和选择依据；非默认生产注入 | `815e4db10f790d7194e9e836379efa4316df75f3` |
| B-02 — Listing Knowledge Runtime | 默认关闭的调用级 Knowledge 接入与 Evidence；本轮 539 Python / 73 Node 通过，未真实调用 | **最新工程提交：`53013f80c7123a34dd8d23b643c3e5fd721a7d98`** |

## AI Capability Implementation Status

S1～S6 是业务能力分类，不是六个服务、六个 Agent 或固定六次调用。以下为当前落地状态；真实调用只证明所列调用/产物存在，不能替代业务验收。

| 能力 | Implementation Status / 当前代码 | Verification Status / Evidence | Known Limitations | Next Action（恢复后候选） |
| --- | --- | --- | --- | --- |
| S1 商品理解 | IMPLEMENTED：Listing [Planning 请求/校验](../../src/image_workflow/planning/request.py)、[事实争议](../../src/image_workflow/planning/conflicts.py)；Quick 由图像模型隐含完成 | Listing REAL MODEL VERIFIED（调用与结构范围）；工程回归见上表 | BUSINESS ACCEPTANCE PENDING；主要依据运营资料和图片；B-02 方法不是事实来源或独立认证，冲突识别可靠性未证明 | 核对资料声明、图片可见事实及运营确认 |
| S2 参考图理解 | IMPLEMENTED：同次 Listing Planning 的 references；Quick 无独立理解产物，使用[场景 Prompt](../../src/image_workflow/generation/quick_v1.py)及图像模型 | Listing 与 S5 独立实验有真实记录；不是 B-02 真实验证 | 已记录第五栏误读、UP/15° 混淆；结构校验不证明理解正确；独立 K01/K05/K06 实验不代表生产支持 | 对照参考图原件核查理解，不以历史 Plan 作答案 |
| S3 参考适配与事实权限 | IMPLEMENTED：Quick 场景策略、Listing 资料/逐图要求/确认计划及[生成 Context](../../src/image_workflow/generation/request.py) | ENGINEERING VERIFIED；Listing 有真实候选计划；新 A/B 完整真实验收 UNKNOWN | BUSINESS ACCEPTANCE PENDING；B-02 不增加事实权限，信息适用性仍依赖运营与模型；主体替换效果未证实 | 核查适用卖点、不可继承信息与真实主体替换 |
| S4 平台 / 地区规则 | IMPLEMENTED（运营文字要求、Prompt）；专用有来源/版本/适用范围的规则加载校验 NOT IMPLEMENTED | 日语/乐天风格真实请求已有记录；正式合规验证 UNKNOWN | 没有正式平台知识源；K01～K06 是制作方法，不是平台硬规则或认证 | 有具体要求时再核对可追溯规则来源 |
| S5 专业制作决策 | IMPLEMENTED：Listing plans、[人工编辑规则](../../src/image_workflow/tasks/rules.py)、Quick 指令及模型隐含决策；B-01 方法资产/选择器、B-02 可选注入均已提交 | 真实 Planning、探索性 A/B、Direct Smoke 已有记录；B-02 本轮离线验证；Skills NOT IMPLEMENTED | BUSINESS ACCEPTANCE PENDING；Knowledge 默认关闭、未真实验证接入；评分差主要在 S2，专业方法稳定收益与保真未证明 | 围绕实际不合格图片确认方法缺口，再决定最小验证 |
| S6 Context Engineering | IMPLEMENTED：[Planning](../../src/image_workflow/planning/request.py)、[Generation request](../../src/image_workflow/generation/request.py) / [service](../../src/image_workflow/generation/service.py)、快照与 Inspector；`3008891` 修复单图传递/解析，B-02 增加可选 Knowledge Context/Evidence | ENGINEERING VERIFIED；真实请求/输入顺序/响应/产物有既有记录；B-02 539/73 本轮复核通过 | 客户端快照不证明提供方内部执行或模型采用；历史缺失、来源追踪仍有限制；Direct Smoke 不是正式 Listing Context 链验收 | 用当前案例原始 Context、实际请求与人工评价核对传递 |

**Rules / Knowledge / Skills / Agent 的落地边界：**图位数量与归属、合法 reference ID、来源原文匹配、尺寸声明、计划/Run 版本、冲突处理、去重及审核指针部分由确定性程序保证；卖点适用、主体替换、文字/布局及外观保持部分仍由模型执行 Prompt。Knowledge 由“研究”推进到 **B-01 运行时资产/候选选择 + B-02 默认关闭接入，均已提交**，尚无该接入的真实模型或生产启用证据，也不直接注入 Generation。正式专业 Skills 运行时、L4 Bounded Agent Runtime 均未实现；L1 规则、L2 模型判断、L3 条件流程基础已经存在。04/05 文档仍为 PROPOSED，已授权增量不等于全部候选已实施，更不构成继续开发的批准。

## 真实实验结果与当前业务缺口

| 记录 | 实际结果 | 结论与证据边界 |
| --- | --- | --- |
| S5 Knowledge A/B | `CLOSED_EXPLORATORY_PILOT`；Plan-X / Knowledge 13/15、Plan-Y / Model-only 11/15 | AI-assisted preliminary review，非运营验收；主要差在 Q4 / S2：Plan-Y 将参考第五栏误述为泡沫洗净，其他四项同分；单案例、每组一次成功调用，无成图比较，不能证明 S5 稳定增益、技术胜出或 Agent 必要性。见 [04 结案摘要](../04_AI_AGENT_SUITABILITY/IMAGE_AI_ARCHITECTURE_DECISION_V0.1.md#8-现有实验如何影响架构)及 `experiments/s5/washer_reference_002_ab_v0.1/attempts/attempt_002/unblinded_analysis_v0.1.md` |
| 首次真实 Listing Planning | Task `6fc958c5b1b649328f24a2718d3f9954`；Call `79ac7dbd03df48478f4ddf04892c9881`；1 Planning / 0 Images | 混入内部图位 ID、逐图 Brief 冒充 requirements 原文，本地拒绝，原响应保留；`8bb1c6c` 修复请求契约且仍严格拒绝非法来源/ID。见 [实验日志 EXP-20261028-E105](03_EXPERIMENT_LOG.md#exp-20261028-e105--listing-两图真实-smokeplanning-响应校验失败) |
| 修复后 Listing 重跑 | Task `63c1448453ac48c6aeb03bafa82ef8ea` revision 2；Call `4e189711d5d0493989b8c8b18da021c2`；1 Planning / 0 Images | HTTP 200，结构/ID/来源校验通过并应用，但 reference_002 将参考 UP 不明误用为“不写 15°”，未完整保留授权五种模式；停于语义审核，未确认/生成/Pass。证据：`.runtime/debug/e105-listing-pack-rerun02-20261029T011556Z-e9f998/summary.md`、`planning_review.json`及 Task calls |
| Direct Image Smoke | **DIRECT IMAGE SMOKE / GENERATED = 2**；2 Images / 0 Planning / 0 重试；`gpt-image-2.5-sunburst`、low、1024x1536 | 两张真实 PNG 已有保存记录；不是 Listing Task、计划确认或端到端验收。PRELIMINARY REVIEW 记录喷头/接口、泡沫附件装配及瓶体纹理偏差，以及未经本次确认的营销效果文案；不是已证明的模型内部根因。证据：`.runtime/debug/e105-direct-two-image-smoke-20261029T013054Z-951197/summary.md`、`preliminary_review.json`、`image_01/image.png`、`image_02/image.png` |

用户快照另述 Direct Smoke 已完整表达五种模式、基本布局和日语文字初步可用；此处按**用户提供的初步评价**保留，本轮未重新查看图片或独立审校日语，不能据此声称全部文字/功能表达正确。已生成两图只证明真实生图通路成立；商品结构与外观保真、宣称准确性仍未达到可确认的业务交付标准，High 能解决失真或 Knowledge 改善成图均未得到证明。

本轮只核对文档与源码，不新增实验或重读 Runtime。真实调用的 Usage 继续以各目录 `usage_summary.json` 为准，实际账单金额 UNKNOWN。**正式 Listing：计划→人工编辑/确认→真实生成→运营审核/Pass→导出尚未通过；Quick-A/B 真实业务验收、当前 V1 运营正式 Pass 均未完成。** 历史 T01 首图的用户 PASS 保留在 [实验日志](03_EXPERIMENT_LOG.md)，仅限该旧样本，不覆盖当前三场景及新可用性能力；该日志开头的 T02 待执行是旧状态，不代表后来没有真实 Planning。Direct Smoke 和 S5 的后续详情沿用本页既有索引，不把日志尚未同步的部分写成已补记。

## 当前暂停点与恢复入口

**暂停新增开发，进行实际运行与业务检查。** B-01、B-02 已建立工程 Git 检查点，B-02 本轮离线回归通过；V1 真实业务验收未完成。本轮仅执行已授权的本地启动和免费 UI 检查；之后仍先理解现有功能与 Evidence，再决定下一项最小工作，不自动继续开发或付费实验。

1. **先恢复事实基线。**重新核对 HEAD、工作区与本文，保留独立的 B-02 与文档检查点；实际运行版本以进程/HTTP 核对为准，不把提交成功当作启动成功。本轮本地启动之外的 Push、部署及功能开发仍须单独授权。
2. **以真实运营使用与业务效果决定优先项。**候选入口是已有洗车机 Plan 的人工修订/正式确认后 Listing 闭环，或经运营确认关系的 Quick-A/B 样本。先明确哪些功能满足需求、哪些保真/宣称问题阻碍交付，记录接受/拒绝理由、人工投入、耗时和可得成本；任何真实生成/修改须另有预算及授权，不重写旧证据。
3. **增强能力须有实际缺口依据。**优先判断现有 Rules、Knowledge 与 AI Decision 是否有业务价值；必要的只读架构 Review、方法评价、保真研究是候选方向，不是本轮 Coding 或付费实验任务。不把继续建设 Skills、Agent Runtime 或新架构自动设为下一步；目标是在可接受的时间、人工投入与模型成本下稳定获得运营认可的商品图，而非代码/测试/Agent 数量。

## Historical Development Records（历史正文原样保留）

以下是各阶段当时的详细记录；其中“本轮”、旧测试数量、未提交/未实施/浏览器未测、下一步及部署描述仅适用于原日期与范围，不覆盖上方当前总览，也不构成当前任务授权。后续优先更新本页总览，历史记录用于追溯，不再以逐任务记录代替项目总体状态。

**V1 可用性收口｜2026-10-29：ENGINEERING VERIFIED；BROWSER VERIFIED（匿名 SDK Mock）；BUSINESS ACCEPTANCE PENDING。** 本轮提交前基线 `main / 8bb1c6cff8b558b9310ec763171a4946902a1057`，独立工程提交 SHA 以包含本条的 Commit 为准；未 Push、部署或调用真实模型。下方记录按原日期理解，不代表本轮仍未实现。

- Listing 新增免费 `manual_plan` 操作，保留五项计划 Schema、reference ID、原 AI Call 和前后差异；事件标记 `HUMAN_EDIT`。只递增本图计划版本，撤销本图确认，仍须正式重确认。明显矛盾保留，已处理争议随方案版本失效；人工编辑不认证商品事实、不调用 Planning。AI 重新规划在界面独立标明付费。Quick-A/B 仍无强制 Planning。
- 质量支持 `low / medium / high`（低｜草稿、中｜标准、高｜精细）。新 Web Task 显式默认 Medium；历史 Task/旧 API 与 CLI 缺字段保持原 Low。Task 默认与逐图覆盖保存、恢复和另存重映射；工作台通过免费 `set_quality` 保存设置，`generation_settings.json` 单独记录设置版本，不改变确认计划或旧 Run 目录。新生成/修改记录实际 quality，过期设置及不同质量复用 operation_id 被拒绝，零自动重试不变；历史 Run/Pass 不被覆盖。
- 当前模型仍为既有 Images 模型。核对官方 [Image generation / Size and quality options](https://developers.openai.com/api/docs/guides/image-generation#size-and-quality-options) 与本地 SDK 的 Images Edit 参数均支持上述三个值；本轮只用 SDK Mock 验证传参，没有进行真实 Medium/High 质量或费用试验，High 不保证商品保真。
- Review 新增绑定 Task/图位/确认版本/Run 的 `reject` 事件，六类原因和可选说明写入现有 reviews，保留图片、旧 Pass、历史选择及 ZIP。拒绝不删除、不自动修改、不自动调用模型；说明可由用户主动填入下一次修改意见。未 Pass 不自动解释为已拒绝。
- 最终完整安全离线回归：Python **466 PASS**；独立 Node **73 PASS**，零失败/错误/跳过（Python 包含 Node 包装，不累加）。新增 15 项 Python 和 5 项 Node 可用性回归；原有黄金指纹、关键断言和 23 条普通应用路由保持，未刷新历史指纹。
- 实际 Microsoft Edge Chromium + CDP 验证 TEST-01～10：人工保存且 Planning 增量 0、重确认、三档质量保存/刷新/另存、逐图覆盖进入 SDK Mock、Reject/反馈、Select/Pass/历史 ZIP、Quick-A/B 闭环、10 个动态图位删除/新增/另存、尺寸专项正反例、Listing 矛盾处理与证据不足正例均通过；390px 无横向溢出。浏览器最初 TEST-09 因脚本等待旧 Task 卡片超时，按完整 Task 身份等待后重测通过，原失败记录保留。
- 临时匿名浏览器 Evidence：`/private/tmp/v1-usability-browser-llzs50yq/browser-report.json`、`sdk_mock_calls.json`、`download_integrity.json`、`screenshots/`（临时目录可能清理）；3 次 Planning / 6 次 Images 均为 SDK Mock，真实模型调用 **0**。已核对下载 ZIP 字节对应明确 Pass 的旧 Run。没有读取真实 `.env`、运营 Runtime 或改写历史 Evidence；Pilot 与用户原本的本地服务未改动。
- 边界：本次通过的是可用性工程与匿名浏览器操作，不代表商品外观、宣称、日语、专业设计或实际模型质量验收通过。真实模型与运营验收仍需独立执行；Mac mini 当前部署版本继续 UNKNOWN / DEFER。下一轮架构审核只需关注本次人工修订/确认、质量设置/Run 参数、Review 反馈及锁/持久化边界，不以此授权 Agent、Knowledge 或 Skills 扩展。

**E1-05 Listing Planning 契约修复｜2026-10-29：OFFLINE ENGINEERING VERIFIED；REAL RERUN NOT PERFORMED。** 保留下方真实失败及既有未提交记录；本轮只改 Planning 请求投影、来源校验与离线测试，不修改 Generation、Review、业务基线或历史 Evidence。

- 明确合法 reference/计划 ID，并在模型输入中去除内部图位 ID；保留参考绑定、类型、逐图要求和尺寸，任务存储身份不变。原始 listing/description/requirements 继续逐字匹配；新增仅限本次提供且启用的具体参考图的 `slot_requirements` 来源，必须带 reference_id、关联受影响计划并逐字匹配该 Brief。模型推断不作为原始来源，运行时约束不等于商品事实认证；无效 ID/来源仍拒绝，不做模糊匹配或自动重映射。
- 新来源的人工处理摘要额外绑定对应 Brief，改动后失效；旧来源摘要算法不变。未处理明显矛盾、逐图确认及版本保护保持，证据不足不自动升级为明显矛盾。未把本次洗车机实验的禁用参数写成通用规则。
- 新增 17 项匿名回归，结构来自失败 Call `79ac7dbd03df48478f4ddf04892c9881`，不复制运营图片或完整响应为测试夹具。定向回归 60 项通过；最终完整隔离 Python **451 项通过（23.659 秒）**，独立 Node **68 项通过**，零失败/错误/跳过，Python 含 Node 包装不累加。测试禁止联网与项目真实 `.env`/`.runtime` 访问。
- 单独只读核对真实失败 Evidence：原响应仍拒绝，仅明确标记的内存假设结构通过校验；34 个文件整体哈希未变。下一次真实 Planning 尚未执行、需独立付费授权；模型语义、商品事实与成图质量仍待验收。未 Commit/Push、部署或调用模型。

**E1-05 Listing 两图真实 Smoke｜2026-10-28：PLANNING RESPONSE VALIDATION FAILED；GENERATED = 0；BUSINESS ACCEPTANCE PENDING。** 在独立 `.runtime/debug/e105-listing-pack-smoke-20261028T121902Z-924883/runtime` 新建 Task `6fc958c5b1b649328f24a2718d3f9954`，只从洗车机历史 revision 3 的两个 Run 提取原始输入，图片/文字字节和来源哈希核对通过；固定两图 Brief 通过现有逐图要求提供，生产代码和 Prompt 未修改。

- 实际仅调用 Planning 1 次：`gpt-5.4-mini`，返回 `gpt-5.4-mini-2026-03-17`，API 返回 completed；因事实报告混入图位 ID `reference_101/102`，且一条来源引用不属于其声明的原始 requirements，正式本地校验返回 HTTP 502，计划未应用。两条报告均为 INSUFFICIENT_EVIDENCE，不据此宣布商品事实矛盾。原始请求/响应、输入顺序、错误及 Usage 已保留。
- Usage：输入 12055、输出 1408、合计 13463 tokens，API 耗时 12.499 秒，实际金额 UNKNOWN。Images 调用 0、重试 0。`DELEGATED_TEST_CONFIRMATION` 为本次已授权但未执行的确认方式；未确认计划、未生成或 Pass。来源文件哈希未变。详见实验日志新增记录及独立 Runtime Evidence；未追加实验、修复代码、部署或提交 Git。

**E1-04 最终工程检查点｜2026-10-28：ENGINEERING VERIFIED（离线范围）；BROWSER ACCEPTANCE: NOT TESTED；REAL MODEL NOT TESTED；BUSINESS ACCEPTANCE PENDING。** 提交前基线为 `main / d1999bc4de76a1042ee584f5e8e698bcdc9c97e1`，30 Modified + 2 Untracked 全部属于已审核 E1-04 范围。本条随独立 E1-04 Commit 归档，SHA 以包含本条记录的 Git 提交为准；不 Push、不部署。

- 本轮重新完整隔离回归：Python **434 项通过（22.797 秒）**，独立 Node **68 项通过**，零失败/错误/跳过；Python 包含 Node 包装，不重复累加。使用匿名临时数据、假 Key 与 SDK Mock，禁止测试联网和访问项目真实 `.env` / `.runtime`。尺寸绑定、声明、直接生成/修改前置保护，争议版本与旧确认保护，历史 Listing 分类另存及尺寸保留，动态 N、版本、Pass、ZIP 与 CLI 回归通过；没有新增功能或改变保护性断言。
- 本轮用户明确允许浏览器工具不可用时独立建立工程检查点，取代下方上次的提交阻断。**BROWSER ACCEPTANCE: NOT TESTED** 保持不变：此前 Codex 浏览器 native pipe 启动失败，内置浏览器不可用，并非已证实业务功能失败；Node DOM 测试不能替代浏览器交互，也没有截图或操作记录。
- 浏览器交接可复用 `cli.debug_workspace --runtime-dir <全新临时目录> --port <空闲本机端口>`，使用显式离线假 Key，**不传 `--allow-paid-actions`**，不读取真实 Key，不使用既有历史 Runtime；可手工检查三个入口、动态 N、尺寸声明和保存/恢复/另存。现有 CLI 没有交互式 SDK Mock 开关；Planning/冲突、历史版本及审核导出的浏览器验收仍需隔离 Fixture/Mock 环境，不将 unittest 夹具当作已可浏览的服务。`start_live_debug.sh` 使用既有 Runtime 并启用付费门禁，不用于本次无付费交接。
- 本轮未启动服务、读取运营数据、调用真实模型或部署。E1-05 仍须先完成未测浏览器项目、冻结有效业务样本与人工验收标准，并独立授权模型种类、单次预算和失败处理；不自动重试或追加调用。尺寸声明不是独立测量认证，模型冲突识别和真实成图质量仍待验证。

**E1-04 上次检查点复核 / UI 验收记录｜2026-10-28：当时 UNIT / INTEGRATION TESTED；BROWSER NOT TESTED；按当时门禁提交 BLOCKED。** 当时基线为 `main / d1999bc4de76a1042ee584f5e8e698bcdc9c97e1`，预期 30 Modified + 2 Untracked 与现场一致。代码复核发现并修复一项范围内阻断：有旧 `image_sizes` 的无分类 Listing 在分类另存时，前端混交旧尺寸映射和新 `listing_slots`，服务端的旧尺寸保留校验又拒绝只提交新图位。现将绑定参考的旧尺寸带入新图位、仅提交新尺寸表示，服务端允许显式新图位表示取代旧映射；普通旧任务另存仍不得遗漏尺寸。新增前后端回归验证来源任务和素材不变；另新增测试证实新争议可阻止未改变计划的旧确认及缓存状态继续生成。

- 本轮相关 Python **88 项通过**，另有新增旧确认保护单项 **1 项通过**；最终完整隔离回归 **434 项通过（22.619 秒）**，独立 Node **68 项通过**，零失败/跳过，Python 包含 Node 包装，不累加。新增兼容用例先复现失败，局部修复后通过；未刷新历史金样或放宽安全断言。
- 实际浏览器通道返回 native pipe 启动失败、无可用浏览器，内置浏览器亦不可用。三个模式、动态 N、尺寸声明、冲突处理及审核导出的真实浏览器交互均 **NOT TESTED**；Node DOM 模拟不是浏览器验收，未补造截图。按本轮提交门禁，没有暂存、Commit 或 Push，全部工作树改动保留；未部署、未启动服务、未读取生产凭据，真实模型调用为 0。
- E1-05 仅核对两个已知本地历史候选的快照及 Run 文件：测温 Task `963cd0348c824948a6f02b988091dd69` / revision 1 / `reference_102` / Run `20261026T022139Z-388e488b64a2446cb01f672f149b5467` 位于既有 Live Debug Runtime，其 `quick_scenario` 缺失，不能赋予 A/B 身份；洗车机 Listing Task `43889e73c53c462da86216ed42f0a1ec` / revision 3 / `reference_002` / Run `20261014T084656Z-5b6ba1bfd6864f76b7c8fcf87a9f01e5` 位于原 `.runtime/prepare-plan`，可作为分类另存候选，不能用当前新计划解释旧 Run。原始文件只读，未复制或改写。实际 A/B 业务关系、尺寸专项真实性声明及事实冲突正反例仍需人工冻结；后续调用预算仅能提出建议，本轮未授权付费执行。**REAL MODEL NOT TESTED / BUSINESS ACCEPTANCE PENDING**。

**E1-04 初始实现历史记录｜2026-10-28：ENGINEERING VERIFIED（明确分类图位的离线范围）/ BROWSER NOT TESTED / BUSINESS ACCEPTANCE PENDING。** 当时 `main` / `d1999bc4de76a1042ee584f5e8e698bcdc9c97e1` 为阶段 A 已提交的 E1-03 检查点（13 文件；重新完整回归 420 项通过，21.963 秒）。以下 E1-04 改动当时未暂存、未提交，最终检查点以上方为准；未 Push、部署、启动服务、读取 `.env` 或真实 Runtime，真实模型调用为 0。

- **尺寸专项：**在原 Quick/Listing 图位内保存 `dimension_source_product_id`、`dimension_source_confirmed`。运营从本任务 `product` 选择已标注目标商品真实尺寸的白底素材并明确声明，不要求另填数字；不做 OCR、测量或真实性认证。界面刷新/另存保留并重映射商品身份，改选或删除所选素材清除声明。服务端拒绝非法角色、跨范围引用和非布尔声明；Task 协调在创建 Run 前检查关联/声明/文件存在，请求构建再检查专项素材实际进入商品输入，原图片哈希校验仍在 SDK 前执行。Quick-A/B 与 Listing 的明确 `dimensions` 图位仅在满足条件后解除临时阻断，直接生成、批量及修改使用同一保护。
- **Listing 争议：**仅为有明确 `listing_slots` 的新规划补充 `fact_issues`，要求文字来源原文、商品图片 ID、可见依据、受影响 reference/计划 ID，并区分 `VISIBLE_CONTRADICTION` 与 `INSUFFICIENT_EVIDENCE`。来源与归属校验失败不应用结果；缺少拍摄角度不是确定性矛盾。旧未处理争议不会因下一次模型返回空数组而消失。没有报告争议不表示商品资料已经独立核验；识别正确性和影响范围仍依赖模型报告，未经真实模型验证。
- **人工处理与版本：**复用原 `/action`、Task 锁/活动检查和逐图计划确认。运营可以明确保留、修正或移除争议宣称；修正/移除须提交受影响图位的修订计划，原始来源不改写。处理记录绑定输入、商品/参考理解、计划内容及版本；计划/理解变化后旧处理过期。未处理/过期的可见矛盾阻止受影响计划确认和有效生成；处理后仍需原有逐图确认。当前人工决定与修订计划进入 Generation Context/Prompt，保留人工来源而非认证标签；Pass 不反向证明商品事实。人工处理本身不调用模型，Live Debug 付费门禁不再将它误判为付费操作，原本机/Host/Origin/只读限制保留。
- **历史边界：**历史 Task/Run/Pass/Evidence 不迁移、不补声明。历史 Quick V1 中已有明确尺寸类型但无声明者阻断新生成/修改；无图位类型的历史 Quick 保留原单图重设计及 CLI 行为，不从标题或 Prompt 自动推断尺寸类型，也不能声称其具备新版尺寸专项校验。无分类历史 Listing 可读取、选择历史版本、Pass、导出，但新增生成/修改保守阻断；界面允许明确分类、绑定已有参考后另存新任务并重新规划/确认，不修改原计划。动态 N、reference 计划身份、父 Run、锁、去重、旧 Pass、失败保留与零自动重试保持。
- **验证：**新增 12 项 Python / 5 项 Node 测试。最终完整隔离回归 **432 项通过（23.005 秒）**；独立 Node **67 项通过**，零失败/跳过，Python 包含 Node 包装，不累加。匿名 SDK Mock 核对三模式尺寸请求的实际图片字节/顺序、专项商品角色、父 Run、旧 Pass、去重与错误；验证争议来源、按图位阻断、人工处理、计划重确认、过期保护、另存不沿用旧事实决定及免费处理。既有 Generation/CLI 历史指纹未刷新；Task 历史指纹先精确断言并归一化本轮有意新增的“未分类 Listing 执行阻断”查询差异，其余 HTTP、文件和写入顺序仍对照原金样。
- **未验证与下一步：**真实浏览器交互、实际尺寸素材内容、模型冲突识别可靠性及成图质量未测试；仅有运营声明与 SDK Mock，不能报告 BUSINESS ACCEPTED。源码追踪仍为单文件哈希；未核验 Mac mini。E1-05 前应先人工审阅本轮 Diff，确认历史未分类任务的执行边界并体验尺寸/争议交互；真实模型验证仍须单独授权，不据本轮离线通过自动追加调用或其他功能。

**E1-03｜2026-10-28：场景请求策略 ENGINEERING VERIFIED / BUSINESS ACCEPTANCE PENDING；尺寸专项能力 ENGINEERING PARTIAL。** 本节保留 E1-03 当时记录：其起点为 E1-02 检查点 `4e42f17d76cef156826edfaae8324621a3d0caab`（8 文件，当时阶段 A 回归 410 项通过）；E1-03 后于本轮阶段 A 独立提交为 `d1999bc4de76a1042ee584f5e8e698bcdc9c97e1`。以下临时尺寸阻断和未实现项属于 E1-03 历史状态，以顶部 E1-04 记录为准。未 Push、部署、读取 `.env`、访问真实 Runtime 或调用真实模型。

- 仅显式 `quick_scenario=quick_a|quick_b` 启用新策略，Context 与保存的请求均记录场景。Quick-A 以实际商品素材决定外观，允许沿用适用的同款参考营销信息，保留差异化再设计及必保留卖点约束；Quick-B 要求替换主视觉、局部特写、结构及场景中的全部相关参考商品主体，禁止混合两款外观/结构，并按目标商品形态调整布局。关系声明与营销信息均不等于独立检测认证，明显矛盾/不可读/不适用内容不得猜补，候选结果仍需运营审核。
- 生成与修改复用同一场景策略，不强制独立 Planning。商品素材、当前绑定主参考、整体/逐图要求、父 Run 候选图及本次辅助素材的权限在实际 Prompt 中区分；`design_reference` 文件同时携带适用营销信息与设计表达，不再对新 A/B 使用旧的“一律不可继承参考参数/功能”规则。历史未分类 Quick、旧 Quick V1 和 Listing 继续走原请求策略，不改写历史 Evidence 或既有确认、版本、Pass。
- 先在全局阻断仍保留时通过 4 项 SDK Mock 请求策略测试，再开放 A/B 的非尺寸图位。dimensions 继续在 Task 协调入口（创建 Run 前）和纯请求构建边界（SDK 前）阻断生成/修改；页面禁用对应动作并显示 E1-04 原因，普通文字声明不能绕过。这里只按明确图位类型保护，未实施尺寸专项素材识别/绑定/校验，也没有自动商品事实裁决或 Listing 冲突处理。
- 本轮完整隔离 Python 回归 **420 项通过（21.685 秒）**；独立 Node **62 项通过**，零失败/跳过，Python 含 Node 包装，不累加。新增 10 项 Python 测试核对实际 SDK Mock 序列化、图片字节/顺序、场景一致性、父 Run/旧 Pass/去重、错误不伪装成功及 dimensions 双重门控；动态 N、Listing Planning、旧 Prompt/请求/Evidence 指纹和 CLI 回归通过。保护性断言仅按本轮授权将“全场景阻断”收窄为“dimensions 阻断”，未放宽身份、参考、锁、版本或重试保护。
- 测试使用匿名临时目录、假 Key、SDK Mock 并禁止网络及项目 `.env` / `.runtime` 访问。浏览器交互 **NOT TESTED**；`REAL IMAGE GENERATED = 0`，商品真实性、视觉质量、Quick-B 完整主体替换效果及运营接受 **PENDING**。Prompt 约束不是已验证的模型行为；未实施 E1-04、Agent、Knowledge/Skills 或新的模型调用。Mac mini 当前状态继续 **UNKNOWN / DEFER**。

**E1-02 历史检查点｜2026-10-28：动态 N ENGINEERING VERIFIED / BUSINESS ACCEPTANCE PENDING。** 实施基线为 E1-01 `c93bd900eb5aa530436b3bc2ea61a07fdb67cdc8`，已于 `4e42f17d76cef156826edfaae8324621a3d0caab` 归档；下述 A/B 全局阻断为该阶段当时范围，已由上方 E1-03 待审改动收窄为 dimensions 专项阻断。未 Push、部署、读取 `.env`、访问真实 Runtime 或调用真实模型。

- 三个入口共用的卖点、场景图位支持持续增删，不再使用 3/2/8 业务上限；主图、尺寸、对比各 max1。前端分别定义可多项与数量上限，类型分组及组内顺序用于展示和保存；删除中间项不重编号其他身份，恢复/另存保留参考、要求和尺寸。服务端创建与读取共用原校验，保留 ID 唯一性、参考归属、启用状态、绑定唯一性、尺寸及文本校验，不迁移历史数据。
- Listing 仍通过 `listing_slots` 关联 reference ID，沿用原 Planning、逐图确认和生成快照。匿名 SDK Mock 验证 4 卖点＋3 场景＋3 单项共 10 个启用图位，以及更大的 24 项配置；不完整或缺项 Planning 显式失败，保留请求/响应/错误，不覆盖原计划或确认，不自动重试。10 图按各自尺寸生成，修改保留父 Run 和旧 Pass，最终 ZIP 顺序/数量/文件名及实验 ZIP 完整性通过。
- 保留现有技术保护：HTTP 请求总量 80 MB、表单内存 2 MB、单图 20 MB；Planning 输出预算为全量 6000 / 单项 2500 tokens、超时 120 秒，Images 超时 180 秒，零自动重试。现有附加辅助图编辑路径的 16 张输入保护未变；它不是已验证的所有输入路径统一上限。无固定业务数量上限不代表任意 N 一次 Planning 或批次均能成功，未自动分批或追加调用。
- 完整隔离 Python 回归 **410 项通过（21.087 秒）**；独立 Node **61 项通过**，零失败/跳过，Python 含 Node 包装，不累加。测试禁止网络及项目 `.env` / `.runtime` 访问，使用匿名临时目录、假 Key 和 SDK Mock。浏览器交互 **NOT TESTED**，`REAL IMAGE GENERATED = 0`，真实质量与运营接受 **PENDING**。Quick-A/B 仍在 Run / SDK 创建前阻断未完成场景策略；未实施 E1-03、后续尺寸专项素材或 Listing 事实冲突处理。Mac mini 状态继续 **UNKNOWN / DEFER**。

**E1-01 历史检查点｜2026-10-28：输入基础 ENGINEERING VERIFIED；Quick-A/B 制作策略 ENGINEERING PARTIAL。** 实施基线 `main / 4b19fd7c97800549bbf0a0fcefb8bf3752fc6593`，已于 `c93bd900eb5aa530436b3bc2ea61a07fdb67cdc8` 归档；下述旧数量限制是 E1-01 当时范围，已由上方 E1-02 待审改动替代。未访问 Pilot 或真实 Runtime、未读取 `.env`、未调用真实模型。

- 三个入口 Quick-A / Quick-B / Listing 保留 `quick_redesign` / `product_pack` 两类后端；新增显式 `quick_scenario=quick_a|quick_b`，缺失字段的历史任务不自动归类。复用商品/参考上传与现有五类图位，仍保留本阶段 1/1/1/3/2、总计 8 的限制；动态 N 待 E1-02。
- 新 Listing 保存 `listing_slots` 分类、启用状态、参考绑定、补充要求和尺寸；图位表单 ID 不替代 reference ID。分类信息进入既有 Planning 请求，仍需逐图人工确认；生成及确认沿用 reference ID 和原快照。逐图尺寸保存在该关联中，历史 Listing 仍沿用原 `image_sizes` / 默认规则。创建、读取、刷新恢复与另存参考重映射通过离线验证，不迁移历史文件。
- 新 Quick-A/B 暂仅保存输入；页面明确提示策略未完成，服务端在创建 Run / SDK 调用前拒绝生成与修改。事实权限、Quick-B 主体替换策略待 E1-03；历史 Quick 和既有未分类 Quick V1 保持原执行行为。此检查点不代表 Quick-A/B 可运营使用或 BUSINESS ACCEPTED。
- 本轮基线回归 **393 项通过（18.680 秒）**；修改后完整隔离 Python 回归 **403 项通过（19.388 秒）**，独立 Node **59 项通过**，零失败/跳过，Python 含 Node 包装，不累加。测试使用匿名临时目录、假 Key 和 SDK Mock，并禁止网络及项目 `.env` / `.runtime` 访问；macOS 临时路径统一为真实路径后执行，未修改旧断言或历史指纹。真实浏览器交互本轮 **NOT RUN**；`REAL IMAGE GENERATED = 0`，`BUSINESS ACCEPTED = PENDING`。Mac mini 当前版本与运行状态仍 **UNKNOWN / DEFER**。

以下为历史工程状态，旧 SHA、测试与待审工作树描述保留其所属日期，不代表本轮工作区状态。

> 语义同步：2026-10-27（Asia/Shanghai）。本轮仅核对本地 Git、现有文档和引用；未访问 Pilot Runtime、启动服务、读取密钥、运行模型或重跑工程测试。

**HISTORICAL VERIFIED STATE｜2026-10-27 本地核验**

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
