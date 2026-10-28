# Context Flow Inspector V0.7 — 设计规格与证据验证

状态：**DESIGN REVIEW PASS / UI IMPLEMENTED / OFFLINE VERIFIED / HUMAN INTERACTION REVIEW PARTIAL**

核查日期：2026-10-23

仓库：commerce-image-poc；Branch：main；设计核查 HEAD：dfcf6df82230c6f1a7c8383ce8a1fe95091312b6。实现源码检查点：`39199acc42ec056eae87247f17b267f1adbfd05a`（C1）。

## 1. 设计目标、非目标与真实基线

**目标（设计已批准并实现）**：把单次 Quick Redesign Run 的数据、角色、请求留存与输出关系变成可点击的只读图。先回答“有什么依据、保存在哪里、哪些内容进入请求留存”，再辅助人工调查商品变形；不自动判断根因。

**非目标**：不编辑 Workflow，不编排或重新执行模型，不修改 Prompt、业务状态、审核规则或 Evidence 格式；不建设新解析器、日志平台或消息数据库；不把参考输入解释成模型采用了参考商品外观。

本规格保留设计时的 Graph Model 和匿名 Run 映射；实现及验证状态已同步至 2026-10-23。上方 HEAD 是设计时基线，**不包含**后续 Inspector 实现；本轮源码检查点见 [CURRENT_STATE](../00_PROJECT/02_CURRENT_STATE.md) 第 5 节。以下历史映射不随当前代码重建，也不声称本轮重新读取了原临时 Run。

**实现与验收检查点**：图数据及原生 JavaScript/SVG 交互代码已实现，纯投影见 [context_graph()](../../src/image_workflow/inspector_graph.py#L12)，页面见 [inspector.js](../../src/static/inspector.js#L120)。完整 Quick 图含 14 个 Artifact、3 个 Activity 和 21 条关系，默认主干 12 节点/12 边，侧栏显示五阶段摘要。V0.7 实现检查点离线回归 **362 项 / Node 45 项**；后续 Writable Live Debug 检查点为 **366 项 / Node 46 项**。Python 回归包含 Node 包装，数字不累加；本轮提交前的实际重跑结果见 CURRENT_STATE。
**人工体验边界**：用户确认已有人工截图与部分操作体验，本轮未重新读取截图或执行浏览器验收。完整点击/布局、390px、键盘/触屏与跨身份切换等清单尚未全部验收；不能写为全功能业务 PASS。匿名 Mock、MATCH 和 SUCCEEDED 均不证明真实模型质量。

### 1.1 设计检查点源码依据（历史 OBSERVED）

本表保留 V0.6 设计核查时的能力边界及行号；“尚无图”等描述只适用于该历史检查点，当前实现以上方摘要和第 8 节为准。

| 边界 | 真实位置 | 本轮结论 |
|---|---|---|
| 受限读取与字段投影 | [inspector.py](../../src/image_workflow/inspector.py#L45)：`context_view()`；`InspectorReader.inspect()` :288、`asset()` :400 | 已有 documents/assets、来源、角色、Prompt 和一致性检查；没有 Artifact/Activity 图契约 |
| Quick 输入和请求构建 | [request.py](../../src/image_workflow/generation/request.py#L64)：`initial_context()`、`select_images()` :76、`redesign_order()` :107、`build_generation_request()` :127 | Quick 保存 Context 快照，但 SDK 入参为 Prompt、图片和参数；不是发送整个 plan.json |
| 当前 Prompt 策略 | [quick_prompt.py](../../src/image_workflow/generation/quick_prompt.py#L9)：`build_prompt()`、`build_edit_prompt()` :36 | 仅用于解释当前实现，不能作为历史 Prompt 的替代证据 |
| 保存与执行 | [service.py](../../src/image_workflow/generation/service.py#L54)：`prepare_context()`、`prepare_images()` :72、`save_request()` :110、`invoke_model()` :117、`receive_image()` :133 | 持久化了 Context、清单、Prompt、请求/响应及输出；没有独立的 assembly span/event |
| 现有 UI | [inspector.html](../../src/templates/inspector.html#L25)、[inspector.js](../../src/static/inspector.js#L57)：`renderContext()`、`render()` :114；[inspector.css](../../src/static/inspector.css#L7) | 默认卡片、图片/Prompt 大视图、折叠高级证据已有；当前 edges 仅是文字，不可点击，无画布缩放平移 |
| 安全与关联 | [api/inspector.py](../../src/api/inspector.py#L48)：`local_read_only()`；[inspector.js](../../src/static/inspector.js#L136)：`load()` | 保留本机/Host/Origin/Task/路径限制、过期响应丢弃及 GET 读取 |
| 匿名夹具与测试 | [test_context_inspector.py](../../tests/test_context_inspector.py#L63)：`make_quick_evidence()`；[inspector_sidebar.test.cjs](../../tests/inspector_sidebar.test.cjs#L140) | 有正式业务代码 + SDK Mock 的匿名 Run、缺失/差异和只读测试；本轮未执行夹具生成或测试 |

### 1.2 证据状态与检查结果必须分离

| evidence_status | 准确定义 | 图示 |
|---|---|---|
| OBSERVED | 原始留存直接支持**所标注范围内**的字段、包含或归属关系 | 实线、已记录标识 |
| INFERRED | 依据已有字段、同 Run 范围和当前代码推断的处理/因果关系；没有完整历史执行证据 | 虚线、推断标识 |
| UNKNOWN | 关联是否成立无法确定，不以当前代码补全 | 点线、问号 |
| MISSING | 应查看的证据文件/事件不存在或不可读取；不等同于操作没有发生 | 缺失占位及原因 |
| N/A | 本条 Run 明确不适用，如首次生成无父版本；不能仅因文件缺失而判 N/A | 灰色标识，默认收起 |

执行状态 `SUCCEEDED/FAILED/RUNNING/UNKNOWN`、文件可读性、关系证据等级和一致性检查是不同维度。现有 `NOT_APPLICABLE` 可在新投影中映射为 N/A，原记录不变。

一致性检查只允许声明字节/字段/标签的 `MATCH / MISMATCH / UNKNOWN / N/A`，以及文字存在性 `PRESENT / ABSENT / UNKNOWN`。**MATCH 不证明语义质量、因果路径、SKU 身份或人工接受。** 某条因果边即使所有字节检查 MATCH，也可能仍为 INFERRED。

## 2. 默认数据流图

**PROPOSED**：Artifact 为方形数据节点；Activity 为圆角处理节点。以下是完整视图的默认主干，实线支持的是本地 Evidence 关系，绝不是模型内部执行图。

~~~mermaid
flowchart LR
  N01["商品原图<br/>Artifact"] -->|"E01 USED_AS · OBSERVED"| N07["图片顺序与角色清单"]
  N02["设计参考图<br/>Artifact"] -->|"E02 USED_AS · OBSERVED"| N07
  N03["保存的运营要求"] -->|"E03 INCLUDED_IN · OBSERVED"| N06["Run Context 快照<br/>plan.json ≠ Planning"]
  N04["运营商品约束"] -->|"E04 INCLUDED_IN · OBSERVED"| N06
  N03 -.->|"E06 USED_AS · INFERRED"| P01("Context / Prompt 整理<br/>逻辑活动 · INFERRED")
  N04 -.->|"E07 USED_AS · INFERRED"| P01
  N07 -.->|"E08 USED_AS · INFERRED"| P01
  P01 -.->|"E09 PRODUCED · INFERRED"| N06
  P01 -.->|"E10 ASSEMBLED_INTO · INFERRED"| N08["最终 Prompt 留存"]
  N03 -->|"E11 INCLUDED_IN · OBSERVED"| N08
  N04 -->|"E12 INCLUDED_IN · OBSERVED"| N08
  N08 -->|"E13 INCLUDED_IN · OBSERVED"| N09["Images 请求元数据<br/>不含 multipart 原始抓包"]
  N07 -->|"E14 INCLUDED_IN · OBSERVED<br/>仅图片身份清单"| N09
  N09 -.->|"E15 SUBMITTED_WITH · INFERRED"| P02("Images Edit 本地执行记录<br/>本例 SDK Mock")
  P02 -.->|"E16 PRODUCED · INFERRED"| N10["保存的响应"]
  P02 -->|"E17 PRODUCED · OBSERVED<br/>本地 Run.output 归属"| N11["成图文件"]
~~~

- 图不画 Quick Planning；快照 revision 不标“确认计划版本”。文件名 plan.json 也不改变此规则。
- **不画**“整个 Run Context → 请求”的内容传输边。request.context_sha256 是哈希引用，不是 Context 全文入参；它只作为 LEVEL 3 来源核对。
- 额外保存的 Listing/描述 N05 只与快照相连（E05），默认折叠；本例未在 Prompt 中找到它们的原文字面量，不据此断言模型从任何渠道都未获得相关信息。
- N12/P03（Review）、N13（反馈）、N14（父版本）按适用性显示或折叠，见第 6 节。没有事件时不画成已执行的人审链。
- 默认只展开本 Run 12 个主干节点。侧栏聚合为“输入依据 → 组装逻辑 → 请求留存 → 本地调用记录 → 输出”，聚合节点须保留成员证据等级计数，不能把混合组一律升级为 OBSERVED。

## 3. 节点、连线与来源数据契约

以下均为 **PROPOSED 的只读查询投影**，不是新增 Task/Run 存储格式。由现有 Reader 的 documents/assets/context_view 产生，不另读一套目录、不持久化 graph.json。

### 3.1 公共范围与身份

Graph 必须携带 `schema_version`、`selection={task_id,image_id,revision,run_id}`、`execution_environment` 及其来源。无法从 Run 本身证明执行环境时标 UNKNOWN；不能只凭模型名、Key 存在或 api_call_attempted=true 推断 LIVE。

`graph_id` 由上述四个实际身份组成；`node.id` 为 graph_id + 类型 + 稳定语义键（图片再含 slot/id），`edge.id` 为图范围内稳定边键。图片编号、V1/V2 和展示标题均不作为身份。Activity 的投影 ID 不是原始 trace/span ID；未保存的 `evidence_event_id` 必须为 null。

### 3.2 Node

| 字段 | 约束 |
|---|---|
| id / kind | kind = ARTIFACT 或 ACTIVITY；不得把文件目录伪装为已执行活动 |
| artifact_type / activity_type | 如 IMAGE、TEXT、CONTEXT_SNAPSHOT、IMAGE_MANIFEST、REQUEST_METADATA、RESPONSE、REVIEW_RECORD；CONTEXT_ASSEMBLY、IMAGES_EDIT_ATTEMPT、HUMAN_REVIEW |
| label / summary | 业务含义优先；输入事实是来源陈述，不自动标已核验 |
| evidence_status / execution_status | 独立；Artifact 不需要伪造执行状态 |
| evidence_refs / code_refs | 历史文件与当前代码分开；代码位置不得升级为历史执行证据 |
| fields / asset_keys | 复用已有字段投影和受限 asset key；禁止前端提交任意路径 |
| uncertainty_reason | UNKNOWN、INFERRED、MISSING 必填；OBSERVED 也列出其证明范围的限制 |
| details | 按第 5 节提供 LEVEL 1～3；缺失值保留 null，不套今日默认值 |

### 3.3 Edge

每条边必须有：`id、source、target、relation_type、claim、evidence_status、evidence_refs、consistency_checks、uncertainty_reason`。引用节点必须在本图；检查项有 `id/kind/result/left_ref/right_ref/expected/actual`，超大值只引用，不复制图片编码。

| relation_type | 方向与含义 | 禁止的解读 |
|---|---|---|
| USED_AS | Artifact → Activity，表示作为某种输入；也允许 Image Artifact → IMAGE_MANIFEST，明确表示登记角色和位置 | “模型采用了这张参考图的视觉特征” |
| INCLUDED_IN | 子数据/文本/清单 Artifact → 包含它的 Artifact；须说明 text、metadata 或 bytes | 把 image_order 身份元数据说成图片字节已内嵌 JSON |
| ASSEMBLED_INTO | Activity → 输出 Artifact；描述组装结果，未保存活动 trace 时为 INFERRED | “已证实当时执行了当前版本的某函数” |
| SUBMITTED_WITH | 请求元数据 Artifact → 本地调用活动；表达关联的调用尝试 | 自动等同于远端已收到、已处理或已计费 |
| PRODUCED | Activity → 输出 Artifact；必须限定本地记录归属或有证据的输出关系 | 把本地候选图、技术校验成功说成人工 Pass |

精确来源引用至少包含：

~~~json
{
  "scope": "run",
  "relative_path": "request.json",
  "document_key": "request.json",
  "pointer": "/image_order/1",
  "sha256": "原文件完整 SHA-256",
  "exists": true,
  "asset_key": "run-input-1"
}
~~~

- scope = task 或 run，配合 graph.selection 定位；文本文件以行号/字符区间代替 JSON pointer，whole-file 引用要明确。
- 来源哈希对应原文件，展示内容仍脱敏；不能把脱敏后的展示 JSON 再散列为“原文件哈希”。
- 缺失引用须保留预期受限位置、exists=false、sha256=null；MISSING 是文件可用性，不证明历史活动未执行。
- 本例没有 Review event ID，不能伪造精确事件文件名；缺失引用定位到已核验不存在的 reviews 目录，标 locator_kind=directory、event_id=null。目录引用只是来源说明，不增加目录浏览或任意路径读取接口。
- `code_refs` 只记录当前文件/函数/行号及“当前实现说明”用途，不能替代 evidence_refs。
- 边可返回 `related_checks`，但不能仅看源/目标节点均 OBSERVED 就推导此边 OBSERVED。

## 4. 交互行为（代码已实现，完整人工验收待完成）

| 场景 | 规定行为 |
|---|---|
| 390px 侧栏 | 只显示五组简化流程、缩略图/关系摘要和不确定性计数；不塞完整画布或默认 JSON；点击进入完整视图并保留 selection |
| 完整视图 | 左侧有方向的图，右侧节点/连线详情；Artifact 与 Activity 形状不同，证据等级兼用线型/文字，不只依赖颜色 |
| 点击节点 | LEVEL 1 默认展开；列出输入/输出 Artifact 和相应边的状态，不能从相邻位置编造传递关系 |
| 点击连线 | 独立选中边，高亮 source/target，显示 claim、relation_type、证据等级、精确来源、逐项检查及 uncertainty_reason；不能退回仅展示两端 JSON |
| 缩放/平移 | 完整画布提供 +/−、100%、适应画布；建议范围 25%～250%；拖动空白平移，触屏支持平移；侧栏保留普通页面滚动 |
| 滚轮/键盘 | 有焦点的完整画布内才消费修饰键+滚轮缩放；+/- 与 0/适应画布可键盘操作，不劫持整个工作台缩放/滚动 |
| 上下游 | “上游/下游/全部”在本地图上遍历，非相关节点淡化；INFERRED/UNKNOWN 边仍保持原线型，不因高亮提升证据等级 |
| 图片与 Prompt | 复用 imageTile/assetUrl、现有大图/对照与 Prompt 全文；仅通过受限 asset key GET；参考图与商品图不互换标签 |
| 原始证据 | LEVEL 3 默认折叠；来源按钮定位原文件、pointer/文本行与原文件哈希；所有文本按纯文本渲染 |
| Task/Image/revision/Run 切换 | 携带完整实际身份，立即清除上一图的图片/选中边/详情，取消旧 GET，丢弃过期响应；禁止用“最新 Run”悄悄替换用户已选 Run |
| 刷新与轮询 | 沿用侧栏关闭停止刷新、展开轻量 GET；相同图保留平移/缩放/选择，证据变化保留稳定 ID 的选择；所有操作无付费副作用 |
| 缺失与失败 | 保留缺失占位、真实错误与差异，不能用动画推测模型内部进度；没有活动阶段时间时不拆分或估算阶段耗时 |

完整视图可复用现有同一 iframe 的扩大模式和同源 postMessage 校验，不另开具有不同权限的调试后端。关闭后恢复摘要；画布变换和展开状态仅在页面内保存，不写 Task/Evidence。

安全范围不扩大：正式运营入口默认不开放；只读 GET/HEAD，本机、Host/Origin、Task 范围、符号链接及目录逃逸校验继续在服务端执行。前端不能通过点边、改 node.id 或传文件路径扩大权限。图查询不取得或创建业务锁，不改变生成、修改、去重和 Pass。

## 5. 三级信息架构

| 节点类别 | LEVEL 1：业务/关系 | LEVEL 2：实际数据与对比 | LEVEL 3：高级 Evidence |
|---|---|---|---|
| 商品图/参考图/父图/辅助图 | 缩略图、身份、角色、数组位置/slot、证据状态 | 受限原图、大图、用途原文、原图/成图对照；SKU 是否相同不自动确认 | 记录 hash/文件 hash、字节数、asset key、精确图片清单 pointer；不显示 Base64 |
| 用户要求/商品约束/反馈 | 区分整体要求、运营商品约束与本次反馈 | 保存的原文、Prompt 标签中的原文并排、PRESENT/ABSENT/MATCH 差异 | 快照/Context/Run 字段与 Prompt 来源、原文件 hash；没有浏览器输入事件就不声称可还原逐次键入历史 |
| Listing/描述等附加资料 | “已保存，未证明原样进入请求” | 历史快照/Context 留存与实际 Prompt 的字面存在性检查 | 原字段和文本备份；不从当前 state 替代历史 |
| Run Context 快照 | 输入 revision、关联 Task/Image；标明不是 Quick Planning | 可确认组成、各字段来源；明确哪些有请求证据、哪些只是背景留存 | plan.json、context_sha256 的 canonical JSON 检查；字段存在不表示整份 JSON 已发送 |
| Context Assembly 活动 | “逻辑组装，INFERRED”；不是模型阶段 | 输入/输出边与规则/字段的留存核对；活动实际执行细节 UNKNOWN | 当前代码位置与历史 Evidence 分栏，未保存 span/time 为 null |
| Prompt / Request | 模型、尺寸、输入数、关联 Run | Prompt 全文、顺序图片、参数、角色边界原文与差异 | request.json / prompt.txt、JSON pointer、request_id、operation_id；request_id 缺失不补造 |
| Images Edit 活动 | 本地尝试/成功/失败；展示已知 Mock 环境 | 保存的请求/响应/错误、Run 耗时与已有 Usage | run.json 的 api_call_attempted、时间、异常及 request_id；不把 Mock Usage 当真实计费 |
| Response / Output | 技术状态和结果缩略图；未人审不标 Pass | 对照原图与输出；错误、技术验证及响应图像字节一致性 | response.json 编码省略、image.png hash、Run.output、已有耗时/Usage |
| Review 活动/记录 | 只有明确 Run 审核事件才显示人审结论 | 事件 action、指定 Run/版本、可获取反馈；selected_run 独立显示 | reviews 中明确的 task/image/revision/run_id、current.json；无记录时活动是否发生 UNKNOWN |

连线也遵循三级：LEVEL 1 的方向/关系/状态，LEVEL 2 的真实传递片段/图片角色与比对，LEVEL 3 的精确源/目标文件字段及哈希。不能以“打开 Raw JSON”代替连线详情。

## 6. 一个既有匿名 Quick Run 的映射实证（OBSERVED）

设计验证检查点从当时已有临时匿名预览目录**只读发现** Task 与 Run，未用固定 ID 生成或替换样例，未执行 make_quick_evidence()。当时目录中仅一个 Task、一条 Run；全部文件无符号链接。本节是历史映射实证，本次文档同步不重新访问该目录，也不保证临时文件仍存在。

- 本地证据根：`/var/folders/_x/33vhm5cj6nd59yc4fd45qvbm0000gn/T/commerce-context-v06-fcsfh318/runtime`（macOS realpath 为同路径的 /private/var/folders 前缀）。
- Task：`079677a2e1b046c2bd270c1ead8dbf1c`；Image：`product_001`；输入 revision：`1`。
- Run：`20261023T053309Z-dd62bbee72ac4b1588ea63a0b992d5b6`；operation_id：`6d2e7df5a93f4cb7aa4d734b5f401624`。
- request_id：`req_anonymous_v06_mock`；mode=quick_redesign；action=generate_image；status=SUCCEEDED；api_call_attempted=true。
- 保存的模型为 `gpt-image-2.5-sunburst`；n=1、quality=low、size=1024x1536、output_format=png；SDK 记录为 2.54.0。
- 本例是**匿名 SDK Mock 证据**：夹具来源见 test_context_inspector.py 的 mock_client()/make_quick_evidence()，原既有预览创建记录也声明 1 次 Mock、0 次 Live。本轮没有重新执行它；Run 字段本身不认证 transport，因此 api_call_attempted=true 不能证明联网。
- Graph 必须分开显示“已知夹具来源声明：MOCK”和“仅凭 Run 的历史 transport：UNKNOWN”；不能从 req_anonymous_v06_mock 的命名、模型 ID 或当前测试工厂自动推出任意历史 Run 的环境。
- 共有 19 个文件：18 个位于该 Task 下，另一个是临时 Runtime 的 current.json 指针；本轮未复制它们进 Git。临时目录可能以后被清理，规格中的哈希不是资料备份。

路径缩写：`T = sessions/079677a2e1b046c2bd270c1ead8dbf1c`；`G = T/generations/000001/product_001/runs/20261023T053309Z-dd62bbee72ac4b1588ea63a0b992d5b6`。下表 Fxx 是本规格的引用索引，不是新增 Evidence ID。`#` 后为 JSON pointer；F06 的 `Lx` 为实际 prompt.txt 行号。

### 6.1 文件索引与完整哈希

| Ref | 精确相对位置 | 原文件 SHA-256 |
|---|---|---|
| F01 | `T/versions/000001.json` | `4b78aeaa400047f425a0ef9681ec0fcaecc12842f823e3d336cc442d622d724f` |
| F02 | `T/inputs/product_001.png` | `5883bf912cf61c593eb0be2a98d91e3b49e841ec1135eee6bc8b463a975407db` |
| F03 | `T/inputs/reference_001.png` | `d2c9a5e98ace0c15945ddcafda85813f3788351dbd8b22d9e0b62714b444244a` |
| F04 | `T/inputs/texts.json` | `3d7ab6c5ad203e35969480dcd61e921211e09ef798fc05f4a1fde6e64127e55d` |
| F05 | `G/plan.json` | `8f72175875858034e1a27d5e22ce1a5934053dc061080a7a260feeb71c35f441` |
| F06 | `G/prompt.txt` | `c37fc985b9191b217ef3828e4fb52147f42418c0fbc46a7a2ca8cddeeb1b5de8` |
| F07 | `G/request.json` | `450cde0a7aa81429dd3cb8b10653a03fc1d0b0ca26aa8d4216610dd8553c9f92` |
| F08 | `G/run.json` | `0bb3fca68e67446adf3a8bf8519dfbe2126b8f8705eb53bb42a5211d544e4682` |
| F09 | `G/response.json` | `8abbf42cccca984bd002a7f2e1a103388b4f227e25b6825209f586539ff174e6` |
| F10 | `G/inputs/product_001.png` | `5883bf912cf61c593eb0be2a98d91e3b49e841ec1135eee6bc8b463a975407db` |
| F11 | `G/inputs/reference_001.png` | `d2c9a5e98ace0c15945ddcafda85813f3788351dbd8b22d9e0b62714b444244a` |
| F12 | `G/image.png` | `e31b0b2477b6a0851d046110408cef23f8bac159059598f9ec9b9e53daac41ff` |
| F13 | `T/generations/000001/product_001/current.json` | `092f88c77de56fb3fd3f13fd607a69b6f9256762f2f8335dc51409ee57f52476` |
| F14 | `T/state.json` | `4b78aeaa400047f425a0ef9681ec0fcaecc12842f823e3d336cc442d622d724f` |
| F15 | `G/inputs/requirements.md` | `78a34668d3e08dfb398e7eb68c07a7524263c819286f8dc764f99dba1f56a782` |
| F16 | `G/inputs/product_facts.md` | `c6afb21f39dd3da199138083e0bc2bd4c07d4f71a363ff2c2ed80b9ee875485f` |
| F17 | `G/inputs/description.md` | `1edf540a07dce804b65430ec2d01e1b2b239b1ac4741012d5b32461523b73bc9` |
| F18 | `G/inputs/listing.md` | `c552605d86b59dcdbf7cbf7e07e9a6b106e7195421094ab3dfc77847289cba32` |

### 6.2 Node Evidence Mapping Table

以下结论只针对该 Run，角色是保存的用途登记。默认主干使用 N01～N04、N06～N11、P01/P02；其余为背景/条件项。

| Node | kind / 业务含义 | 精确 Evidence | 结果与可观察事实 | 未知边界 |
|---|---|---|---|---|
| N01 | ARTIFACT / 商品原图 | F01#/images/0；F02、F10；F07#/image_order/0；F08#/inputs/0 | OBSERVED；product_001，position=slot=1，role=original，320×420、3163 bytes；三处记录/文件 hash 一致 | 字节相同不证明真实 SKU 外观已核验 |
| N02 | ARTIFACT / 设计参考 | F01#/images/1；F03、F11；F07#/image_order/1；F08#/inputs/1；F06 L7、L15 | OBSERVED；reference_001，position=slot=2，design_reference，320×420、3008 bytes；用途边界原文存在 | 模型是否采用其构图或商品特征 UNKNOWN |
| N03 | ARTIFACT / 保存的运营要求 | F01#/inputs/requirements；F05#/original_inputs/requirements；F15；F07#/prompt；F06 L18–20 | OBSERVED；快照、Context 和请求标签值相等 | 无独立浏览器输入事件，不能还原键入过程 |
| N04 | ARTIFACT / 运营商品约束 | F01#/inputs/product_facts；F05#/original_inputs/product_facts；F16；F07#/prompt；F06 L21–23 | OBSERVED；保存值与请求标签一致 | 内容是匿名运营陈述，不等于已确认商品事实 |
| N05 | ARTIFACT / Listing 与描述留存 | F01#/inputs/listing、/inputs/description；F05#/original_inputs/listing、/original_inputs/description；F17、F18 | OBSERVED；Context 中存在，两个非空原文字面量均未在 F07#/prompt 中找到 | 未找到字面量不证明完全没有语义影响；不画已进入 Prompt 的边 |
| N06 | ARTIFACT / Run Context 快照 | F05 全文；F08#/context_sha256、/plan_sha256；F07#/context_sha256、/plan_sha256 | OBSERVED；Task/Image/input_revision 匹配；original_inputs 与所选快照相等；canonical JSON hash 一致 | 不是独立 Planning，不证明整份 Context 发送给模型 |
| N07 | ARTIFACT / 实际留存的图片顺序与角色 | F07#/image_order；F08#/inputs；F10、F11 | OBSERVED；2 项数组原序为 original、design_reference；两份清单完全相同，slot 连续且文件 hash 一致 | 这是请求留存，原始 multipart 未保存 |
| N08 | ARTIFACT / 最终 Prompt 留存 | F07#/prompt；F06 全文；F08#/prompt_sha256 | OBSERVED；请求文字=prompt.txt；UTF-8 原文件 hash 匹配 Run 记录 | 展示脱敏；不能恢复被删除的敏感值或内部系统处理 |
| N09 | ARTIFACT / Images 请求元数据 | F07 全文；F08#/model、/parameters、/confirmed_revision | OBSERVED；模型、四项参数与 revision 一致；只有 prompt/图片身份清单及来源哈希等留存 | JSON 不是含文件流的原始 HTTP/SDK 抓包 |
| N10 | ARTIFACT / 保存的响应 | F09 全文；F08#/usage | OBSERVED；有 data[0] 及 Usage，Usage 与 Run 一致；图片编码不写入规格或前端 JSON 展示 | 响应 JSON 无 request_id/Run ID 字段，不能单独证明远端返回身份 |
| N11 | ARTIFACT / 输出文件 | F12；F08#/output；F09#/data/0/b64_json | OBSERVED；response 图片本地解码 bytes=F12；output hash 匹配，validated=true；1024×1536 PNG | 技术校验不等于商品质量或人审 Pass |
| N12 | ARTIFACT / Review 记录占位 | T/generations/000001/product_001/reviews（本例目录不存在）；F13 | MISSING；没有引用此 Run 的审核事件，pointer 中无 passed_run 字段 | 是否发生未记录的人审 UNKNOWN；event_id 未知，不编造文件名 |
| N13 | ARTIFACT / 本次反馈条件项 | F08#/feedback、/parent_run_id；F05 不含 operator_feedback | N/A；反馈明确为空字符串，parent_run_id=null；首张生成不虚构修改意见 | 不是“反馈文件丢失”的结论 |
| N14 | ARTIFACT / 父成图条件项 | F08#/parent_run_id；F05 不含 parent_image | N/A；首张生成无父 Run；本次图片清单也没有 current_image | 此样本不能实证父图或辅助图分支 |
| P01 | ACTIVITY / Context 与 Prompt 整理（逻辑） | F05、F06、F07；当前 service.py prepare_context()/prepare_images()/save_request()、request.py build_generation_request() | INFERRED；构建产物存在，当前代码给出解释边界 | 没有独立活动事件、输入参数抓取或完整历史源码绑定，实际执行函数/阶段时间 UNKNOWN |
| P02 | ACTIVITY / Images Edit 本地执行记录 | F08#/api_call_attempted、/api_started_at、/finished_at、/status、/request_id、/operation_id | OBSERVED，仅指已保存 Run 尝试记录；本例已知 SDK Mock | 不能升级为 OpenAI 实际执行证明 |
| P03 | ACTIVITY / 人工审核占位 | 缺失 N12；F13#/selected_run 存在，但 /passed_run 未保存 | MISSING，execution_status=UNKNOWN | 选中版本不等于 Pass，不虚构人审活动 |

### 6.3 Edge Evidence Mapping Table

每行依次给出 source → target、relation、证据、检查和 uncertainty_reason；Fxx 的完整路径/hash 见上表。OBSERVED 只证明 claim 中限定的本地关系。

| Edge / source → target | relation / evidence_status | exact evidence references | consistency checks（本轮实际结果） | claim 与 uncertainty_reason |
|---|---|---|---|---|
| E01 N01 → N07 | USED_AS / OBSERVED | F07#/image_order/0；F08#/inputs/0；F01#/images/0；F02、F10 | id、slot=1、role=original、源/Run bytes 及记录 hash MATCH | 登记为第 1 张原商品依据；不证明模型识别正确 |
| E02 N02 → N07 | USED_AS / OBSERVED | F07#/image_order/1；F08#/inputs/1；F01#/images/1；F03、F11；F06 L7、L15 | id、slot=2、role=design_reference、bytes/hash MATCH，设计用途文字 PRESENT | 登记参考角色和边界；不证明模型实际采用或遵守 |
| E03 N03 → N06 | INCLUDED_IN / OBSERVED | F05#/original_inputs/requirements；F01#/inputs/requirements；F15 | 保存文字 MATCH | 运营要求作为字段包含于 Run Context；不是因果事件证明 |
| E04 N04 → N06 | INCLUDED_IN / OBSERVED | F05#/original_inputs/product_facts；F01#/inputs/product_facts；F16 | 保存文字 MATCH | 运营商品约束包含于快照；事实真实性未核验 |
| E05 N05 → N06 | INCLUDED_IN / OBSERVED | F05#/original_inputs/listing、/original_inputs/description；F01 对应字段；F17、F18 | 两项文字 MATCH | 仅证明留存，不能传递成 Prompt inclusion |
| E06 N03 → P01 | USED_AS / INFERRED | F05#/original_inputs/requirements；F07#/prompt；F06 L18–20 | 标签值 MATCH | 当前构建器可解释输入关系，但没有历史组装事件 |
| E07 N04 → P01 | USED_AS / INFERRED | F05#/original_inputs/product_facts；F07#/prompt；F06 L21–23 | 标签值 MATCH | 值一致不单独证明调用链或当时函数版本 |
| E08 N07 → P01 | USED_AS / INFERRED | F07#/image_order/0、/image_order/1、/prompt；F06 L6–7 | 两个 slot/role/file basename 均在顺序段 PRESENT | 顺序文字能核对，未保存格式化活动 trace |
| E09 P01 → N06 | PRODUCED / INFERRED | F05 全文；F08#/context_sha256；F07#/context_sha256 | Context canonical hash MATCH | 产物存在；未记录具体活动 ID/输入调用，不能归因为已执行当前函数 |
| E10 P01 → N08 | ASSEMBLED_INTO / INFERRED | F06 全文；F07#/prompt；F08#/prompt_sha256 | Prompt 文字/hash MATCH | 已观察输出留存，组装过程和历史源码版本仍不完整 |
| E11 N03 → N08 | INCLUDED_IN / OBSERVED | F05#/original_inputs/requirements；F07#/prompt；F06 L18–20 | 唯一 operator_design_requirements 标签值 MATCH | 证明保存请求中包含这一文字，不证明模型理解或执行要求 |
| E12 N04 → N08 | INCLUDED_IN / OBSERVED | F05#/original_inputs/product_facts；F07#/prompt；F06 L21–23 | 唯一 product_constraints_from_operator 标签值 MATCH | 证明文字包含，不把它升级为商品事实或视觉效果通过 |
| E13 N08 → N09 | INCLUDED_IN / OBSERVED | F06；F07#/prompt；F08#/prompt_sha256 | 文本和 UTF-8 hash MATCH | 留存 Prompt 包含于请求元数据；无 wire/远端接收证明 |
| E14 N07 → N09 | INCLUDED_IN / OBSERVED | F07#/image_order；F08#/inputs | 数组内容/顺序 MATCH；2 项文件 hash MATCH | inclusion 是图片身份元数据，不是 bytes 内嵌 JSON |
| E15 N09 → P02 | SUBMITTED_WITH / INFERRED | F07 全文；F08#/model、/parameters、/inputs、/confirmed_revision、/api_call_attempted、/api_started_at、/operation_id | 模型/参数/图片清单/revision MATCH，尝试标记 true | 保存的请求与本地尝试相关；原 SDK kwargs、multipart、远端收包未保存。本例为 Mock |
| E16 P02 → N10 | PRODUCED / INFERRED | F09；F08#/usage、/request_id、/status；同一 G | Usage MATCH，响应存在 | 依同 Run 路径和字段推断响应归属；F09 无 request_id，不能单独认证响应来源 |
| E17 P02 → N11 | PRODUCED / OBSERVED | F08#/output/file、/output/sha256、/output/validated；F12；F09#/data/0/b64_json | output.file=image.png；hash MATCH；响应解码 bytes MATCH | 明确的本地 Run 输出归属；不声称证明远端生成或人工 Pass |
| E18 N11 → P03 | USED_AS / UNKNOWN | 缺失 N12；F13#/selected_run；F08#/run_id | Review event linkage UNKNOWN | 没有事件证明此图被人工审核，当前选中不能替代 |
| E19 P03 → N12 | PRODUCED / UNKNOWN | 预期 reviews 下对应 Run 事件不存在 | 事件可用性 MISSING；action/run 关联 UNKNOWN | 不能将没有文件说成审核未发生或自动通过 |
| E20 N13 → P01 | USED_AS / N/A | F08#/feedback=""、/parent_run_id=null；F05 无 operator_feedback；F07#/prompt 无 revision_feedback 标签 | 首次生成条件符合；反馈适用性 N/A | 本例没有本次修改输入，不画已传反馈的边 |
| E21 N14 → N07 | USED_AS / N/A | F08#/parent_run_id=null；F07#/image_order；F05 无 parent_image | 无 current_image 条目，父图适用性 N/A | 不借用其他 Run 或假造父版本 |

### 6.4 实测摘要与证据强度

本轮只读进行了 19 项字段/字节核对：17 项一致性比较为 true；Listing、描述原文字面量是否出现于 Prompt 两项为 false，属于**预期的负向存在性结果**，不是测试失败。

- 原图 F02=F10=清单 hash；参考 F03=F11=清单 hash；文件和记录的 slot 顺序一致。当前源码只解释角色选择逻辑，不替代这些历史文件。
- F01.inputs=F05.original_inputs；F05 canonical JSON hash 与 Run/request 的 context_sha256 一致，Quick 的 plan_sha256 在本例也是同一值；它不是独立创意 Plan 的证据。
- 此处 canonical 核对采用 Python `json.dumps(ctx, ensure_ascii=False, sort_keys=True)` 的默认分隔符再以 UTF-8 编码；不是 RFC JCS，也不是 F05 原文件 SHA-256。只比较保存值，不以今日源码重建 Prompt 或原始运行。
- Prompt 原文与 request.prompt 完全相同，hash 与 Run.prompt_sha256 一致。两项标签值可从本次保存的字符串定位，不重新调用当前 Prompt builder。
- 响应 data[0] 在内存解码后与 F12 完全相同；Run.output 指向 F12，validated=true。此项只证明字节及技术记录。
- Run/response 的 Mock Usage 同为 input=12、output=18、total=30；elapsed_seconds=0.199、api_elapsed_seconds=0.190，均为匿名 Mock 记录，不能推算真实 API 费用或延迟。
- F13 选择了本 Run，card_revision=2；无 passed_run 和审核事件。不得显示人审 PASS。
- 本轮未执行任何回归或 Mock 生成；351 项离线回归、31 项前端交互是 V0.6 的既有记录，**不是本轮复跑结果**。本轮证据核对脚本只读现有文件、在内存比较，不写 Evidence 或缓存。

## 7. 无法重建的历史信息

1. **UNKNOWN**：完整 SDK 调用实参/实际 multipart/HTTP 字节与远端接收状态。request.json 是应用保存的元数据，input files 是本地快照。
2. **UNKNOWN**：独立 Context Assembly span、精确输入对象、活动级时间及确切历史执行函数。Run 时间不能分摊成未记录阶段时间。
3. **UNKNOWN**：参考图的模型注意力、权重、采用了哪些视觉特征、商品变形内部根因；即使 role/Prompt/hash 全部一致也不改变。
4. **MISSING → UNKNOWN**：本例 Review 文件缺失，无法判断是否有未记录的人审；反馈、父图明确为 N/A，不能与 Review 缺失混为一类。
5. **N/A / 未实证**：本例无编辑反馈、父图、辅助图。现有实现/匿名测试说明可保存这些字段，但当前样本不证明该分支实际发生。
6. **UNKNOWN**：完整历史源码包。source_sha256 与 quick_redesign_source_sha256 的范围仍是原入口文件，不覆盖 request.py/quick_prompt.py 全包；不改历史来源语义。
7. **UNKNOWN**：语义是否忠实、SKU 是否准确、运营是否接受、实际账单。本例为 Mock，不能用图谱代替真实模型业务验收。
8. 临时匿名目录可能清理；若未来已不存在，只能报告样本不可读取。不得按本规格 ID 重新生成并冒充原 Run，也不在本轮复制 fixture 到仓库。

## 8. 前端技术选型与实施边界

**已采用 Flask + 原生 JavaScript，完整画布使用 SVG 连线、节点及单一坐标变换。**本 Run 主干规模固定且小；前端没有新增框架构建链，复用既有来源/图片/Prompt 展示。代码实现和离线验证已完成，完整浏览器兼容与交互验收尚未完成。

- 图数据由现有只读 Inspector 投影构造，图边的 source/target/ref/checks 统一由服务端提供；前端只负责布局、选中和展示，不再次解析 Evidence 文件。
- LEVEL 2/3 复用 sourceLinks()/imageTile()/showPrompt()/showComparison()/selectDocument()；保留现有防串 Task、取消 GET 和同源 iframe 协议。
- 缩放以单一 viewBox/transform 管理；边标签与透明加宽 hit path 支持选择。固定列布局：输入资料 → 逻辑组装 → 请求 → 调用记录 → 输出；默认不支持拖动节点/编辑连线，不保存布局到业务目录。
- 只有画布局部状态，不新建 Chat Runtime、Worker、数据库或网络布局服务；不把运营资料传给第三方前端服务。
- 可选替代是继续用 HTML 卡片 + SVG overlay；成本是尺寸测量/重排同步更复杂。仅当实现验证表明纯 SVG 文本/可访问性不满足要求再选，不提前引入外部库。
- 实际实现为 InspectorReader 复用读取、独立纯 graph 投影、现有 Inspector HTML/JS/CSS、必要侧栏协调和匿名测试；Generation、Prompt、Task/Review、Evidence 写入及正式业务 API 未改变。本轮仅修正文档并建立 Git 检查点，不继续 UI 开发。

### 8.1 可实现性边界

| 能力 | 现有依据与结论 |
|---|---|
| 节点数据/图片/Prompt/Raw 详情 | 已有受限 documents/assets/context_view 支持，可复用 |
| 可点击定向连线与高亮上下游 | 已实现，图契约与前端离线交互有回归；完整浏览器体验待验 |
| 缩放/平移/适应画布 | 已实现局部坐标变换及控制；触屏、键盘及 iframe 尺寸兼容仍待完整人工验收 |
| 动态 Task/Image/revision/Run 跟随 | 已实现并有过期响应、防串数据离线回归；完整浏览器切换场景待验 |
| 完整历史因果 trace | 当前数据无法完全实现；允许 INFERRED/UNKNOWN，不以新增日志前置扩大本轮范围 |
| 参考视觉采用、模型内部推理与自动根因 | 证据不能实现，V0.7 明确不承诺 |
| 本例人审/编辑历史 | 缺失或 N/A；不能通过 UI 实现把它补成存在 |

## 9. 验收标准（离线已验证，人工交互部分完成）

下列条目仍是完整人工验收清单，不将已有截图、部分体验或 Mock 回归等同于全部逐项通过；剩余浏览器验证须据实际操作补记。

1. 390px 默认展示简化流程；展开后有两类节点和有方向的连线，默认不需要阅读 JSON。
2. 商品图、设计参考与本次输入 slot/array position 可见且可打开；图片读取仍受同一 Task/Run 和路径限制。
3. 所有五种关系均可选中查看；每条边有本规格第 3.3 节全部字段，不能只列两端节点。
4. 六类 V0.6 内容可在三级详情中找到，用户要求、最终 Prompt 和原图/成图对照保留。
5. E11/E12 可定位真实标签，E15/E16 保持 INFERRED；不得因 MATCH 或 SUCCEEDED 改成模型语义通过。
6. 组装逻辑不伪装为独立真实执行事件；Quick 没有 Planning 活动或确认计划语义。
7. 可缩放、平移、适应画布和高亮上下游；键盘可选择节点及关系列表，状态不只靠颜色。
8. 选中身份使用 Task/Image/revision/Run；切换后旧图、旧边详情和晚返回结果不能串入新图。
9. 缺 request、图片清单、快照、错误/失败、哈希不一致时，准确显示 UNKNOWN/MISSING/MISMATCH，不用当前代码重建。
10. 本例 Review 缺失、反馈与父版本 N/A 正确；另用匿名编辑夹具验证父图和辅助用途，不能冒充本例已有。
11. GET/HEAD、来源按钮、缩放、轮询及所有调试操作均不修改 Task/Run/Evidence、不调用模型；原生成、修改、锁、operation_id 去重和 Pass 回归保持。
12. UI 阶段运行必要匿名回归/完整离线测试，并在浏览器验证边选择、来源定位、缩放/平移、390px 摘要和图片对照；软件通过不代替真实商品质量验收。

## 10. 未解决问题与审核结论

- **设计审核已通过，运营理解仍待评价**：关系名与默认聚合是否易理解，INFERRED 的逻辑组装节点是否足够醒目；不能把箭头当成模型因果证明。
- **待完整 UI 实测**：已有人工截图和部分体验，但 SVG 文本、边点击、密集图、键盘/触屏、iframe 对话框与缩放焦点等尚无完整逐项验收记录。
- **数据实证范围**：匿名回归已覆盖编辑、辅助图和明确 Review 事件；第 6 节原样本仍无这些历史分支，不把新增测试嫁接成原 Run 的事实。真实业务质量待验。
- **保留 UNKNOWN**：远端处理、完整源码来源及完整组装 trace。不以开发新追踪系统作为本版前置条件。
- **当前结论**：设计已批准，图数据及交互代码 **UI IMPLEMENTED / OFFLINE VERIFIED**；人工界面验收 **HUMAN INTERACTION REVIEW PARTIAL**。原证据映射结论保留，不宣称全部浏览器场景、真实模型质量或运营业务验收 PASS。
