# P3｜AI 产品工程源码走读与执行机制学习记录 V0.1

**项目：** commerce-image-poc
**定位：** 业务驱动学习 Context、多模态、图片与评价；通过真实案例按需补足 Python 后端和 AI 系统执行基础。
**初始化日期：** 2026-10-22（Asia/Shanghai）
**最近状态同步：** 2026-10-23；本轮起点 `main / cb8ec3944c5df5473d5e1a6b404cc1a9c6a717e8`，既有 C3 已提交；本轮只同步学习事实与跨仓接续。
**当前阶段：** P3-01 快速源码定向；主要转向真实商品变形的证据诊断，不继续线性逐行深学。
**执行状态：** P3-01 ACTIVE；采用 A/B/C 三个任务检查点。已有部分概念达到 ORIENTED，尚未完成调用链追踪与检查点复述；L1～L5 专题深学不作为第一轮前置条件。
**历史初始化基线：** `main` / `dfcf6df82230c6f1a7c8383ce8a1fe95091312b6`（P3 初始化已提交）；初始规划基线为 `5a3c57a`。
**本次源码核查基线：** `main` / `39199acc42ec056eae87247f17b267f1adbfd05a`（Inspector / Live Debug C1）；学习记录作为独立 C3 文档提交，不改变源码。
**业务源码基线：** `78c68f9f25639d77abfdc3792a36541912f8af09` 是 FINAL CUTOVER 历史检查点；后续 Inspector/Live Debug 源码检查点以 [CURRENT_STATE](../00_PROJECT/02_CURRENT_STATE.md) 第 5 节为准，不能只用旧 SHA 复现当前工作台。

本文既是计划，也是后续持续更新的唯一 P3 学习记录。初始化已提交，本次按已批准的业务/Python 双主线调整执行方式，并建立独立文档检查点；不另建学习文档。
源码、测试和业务状态分别以 [src/](../../src/)、[tests/](../../tests/)、[CURRENT_STATE](../00_PROJECT/02_CURRENT_STATE.md) 为准；[README](../../README.md) 是启动与导航入口。
以下函数和行号已按本次 Inspector/Live Debug 工作树静态核对；提交后以对应源码检查点为准。后续先核对版本，不把旧行号当作新版本事实。

## 1. 学习目标、方法与证据

采用两条互补主线，**主线 A/B 与下方 P3-01 检查点 A/B/C 是不同维度**：

| 学习主线 | 任务与边界 |
|---|---|
| A — 业务驱动的 Context / Multimodal / Image / Evaluation | 以商品主体变形案例检查商品身份、参考角色、Context/Prompt、模型图片输入、输出与人工评价；分开记录事实、推断和 UNKNOWN，不用工具图谱代替语义判断。 |
| B — 真实案例中的 Python 后端基础 | 只为当前诊断补足 HTTP/Flask、应用初始化、Runtime、Persistence、文件与异常调试；不要求先精通语言、框架内部或复杂并发。 |

Workflow Inspector 是现有证据的只读调试辅助工具，不是模型内部因果解释器；实现工具、看过截图或读过源码都不自动表示已经掌握相关理论。

建立三条相互关联的工程认知：

- **Control Flow**：入口、函数调用、回调、业务编排和异常传播。
- **Data Flow**：HTTP、JSON、图片字节、Context、模型请求和文件 I/O。
- **State Flow**：Task、确认快照、Run、操作去重、版本选择与 Pass。

每个概念均按 **What / Why / Engineering** 学习：

| 角度 | 需要回答的问题 |
|---|---|
| What | 用自己的话说明概念、输入和输出，避免只复述类名或术语。 |
| Why | 当前业务为何需要这个边界；删掉它或放错位置，会出现什么具体问题？设计动机若无直接证据须标 INFERENCE。 |
| Engineering | 在哪个文件/函数/对象上体现？谁调用、何时执行、修改什么状态、产生什么 I/O、失败由谁处理？ |

以 **Top-down** 为主：先看业务目标、组件职责与一次请求，再沿实际调用进入必要函数；不从 import、每个构造器或每行语法开始线性深挖。
仅在当前任务被语法、对象引用或 I/O 概念阻断时，短暂 **Bottom-up** 补足最小 Python 基础，随后回到原调用链。Python 按需学习，不要求先完成整套语言课程。
执行方式：选择检查点任务 → 最小源码定位 → What / Why / Engineering → **每检查点一次复述与记录** → 列出 UNKNOWN 后继续或定向补足。复述仅覆盖本检查点，不逐个专题考试。

| 学习深度 | 含义与边界 |
|---|---|
| ORIENTED | 能说明大致用途、职责和位置，已有初步概念；不代表可以独立追完整调用链或已全部 UNDERSTOOD。 |
| TRACEABLE | 能借助源码追踪本任务的输入、调用、状态、I/O 与失败去向，并指出证据位置及 UNKNOWN；这是第一轮的主要目标。 |
| DEEP DIVE | 对选定专题深入研究内部机制、边界和实现细节；只在实际问题需要时展开，不是 P3-01 第一轮必达层级。 |

执行状态（NOT_STARTED / ACTIVE / REVIEW / COMPLETED）与学习深度分开记录；未评估的深度记 UNKNOWN，不自动推定。可以与既有经验对照，但源码调查完成不等于学习完成。

| 标识 | 使用规则 |
|---|---|
| OBSERVED | 已在指定版本的源码直接读到，或在明确记录的安全实验中观察到；注明“静态源码”或“实际执行”。 |
| INFERENCE | 根据源码关系或观察作出的解释，列依据与推导；不写成作者已确认动机或模型内部事实。 |
| UNKNOWN | 当前缺证据、未执行或尚未理解；写清缺什么、怎样安全核对。 |

下列调用位置为 **OBSERVED / 静态源码**，不是本轮模型运行轨迹；学习事实来自用户确认，不因源码已提取或工程回归通过就提高掌握等级。

## 2. 阶段路线

| 阶段 | 范围与预期产物 | 学习状态 |
|---|---|---|
| P3-01 | 快速源码定向：A 系统全貌 → B 单图生成调用链 → C 失败与证据定位。以可追踪、可定位为目标。 | ACTIVE |
| P3-02 | 多模态输入、图片角色、Context 与 Planning；建立数据来源到请求/结果的简要追踪。暂不细化课次。 | NOT_STARTED |
| P3-03 | Generation、Review、并发和版本；理解执行身份、锁、父版本与 Pass。暂不细化课次。 | NOT_STARTED |
| P3-04 | Evidence 与 AI Failure Diagnosis；按阶段证据区分程序问题、语义偏差及未知原因。暂不细化课次。 | NOT_STARTED |

只有当前 P3-01 详细规划。L1～L5 保留为专题索引，不要求第一轮全部深入掌握；P3-02～P3-04 按真实需要展开，不预设新的工程任务。
当前优先用商品变形案例串联主线 A，并在阻碍追踪时补主线 B；这不自动将后续阶段或尚未独立复述的理论标为完成。

## 3. P3-01 第一轮执行检查点

### A — 系统全貌与组件职责

- **任务**：从运营创建任务到生成、修改、Pass 和导出，说明主要组件各管什么、怎样连接；先定向，不展开全部函数。
- **最小入口**：[app.create_app():108](../../src/app.py#L108)、[api.register_routes():17](../../src/api/routes.py#L17) 及 [CURRENT_STATE 模块表](../00_PROJECT/02_CURRENT_STATE.md)。
- **产物与复述**：一张简要组件关系图/职责表，一次用自己的话串联业务过程；能指出 HTTP、Task/Application、AI Capability、持久化与 Evidence 的归属即可。
- **边界**：已有基础概念先按 ORIENTED 使用；不要求理解 Flask 内核、全部依赖初始化或每个 lambda 的细节。当前 A 尚待完整复述。

### B — 单次商品图生成的真实业务调用链

- **任务**：选目标商品案例的一张图片，沿源码追踪生成请求；商品图包使用已有确认版本，Quick 不虚构 Planning。计划本身不授权新的付费执行。
- **主链**：[routes.generate_one():137](../../src/api/routes.py#L137) → [TaskImageApplication.generate_one():51](../../src/image_workflow/tasks/images.py#L51) → [GenerationService.generate():94](../../src/image_workflow/tasks/generation.py#L94) → [execute_generation():147](../../src/image_workflow/generation/service.py#L147) → Run/图片/指针与 HTTP 返回；需要时再进入 runtime 回调核对。
- **产物与复述**：一次按顺序说明 Task/Image/确认版本、Context/图片输入、SDK 边界、输出文件和状态变化；记录实际文件/函数与未知项，目标为 TRACEABLE。
- **边界**：只跟本图，不同时展开完整 Planning、所有工作模式、修改分支或复杂锁实现；不把静态链路当作已发生的真实运行。

### C — 一条典型失败路径与证据定位

- **任务**：围绕同一商品变形案例，依次定位原商品/参考身份、确认 Context（如有）、实际 Prompt 与图片顺序、模型输出及人工评价，找出第一处可观察偏差。可借 [InspectorReader.inspect()](../../src/image_workflow/inspector.py#L289) 与 [context_graph()](../../src/image_workflow/inspector_graph.py#L12) 定位保存证据，不能用当前 Builder 重建内容冒充历史请求。
- **产物与复述**：一次说明已保存什么、哪些关联可确认、哪些缺失或 UNKNOWN；区分输入/Planning/请求构建错误与输出偏差，不凭外观断言模型内部根因。补充程序失败例时，可追踪 confirmed_revision 不匹配 → Problem → [HTTP problem():28](../../src/api/routes.py#L28) 返回 409，与已尝试调用后失败对比。
- **边界**：先达到 TRACEABLE；前置拒绝不能虚构 Run，已有错误文件不能证明服务端未执行或免费。案例读取与真实调用须另有明确授权；本次仅同步计划，不新增历史调查或实验结论。

A/B/C 各保留一次复述与记录；遇到具体阻碍再查下方知识索引，不为了覆盖索引扩展检查点。

## 4. L1～L5 后续专题知识索引

以下保留原五节的源码入口、理论候选与复述题，供按需补足或后续 DEEP DIVE 使用，**不是第一轮线性必修清单**。各节列出的“产物/复述”也不要求在第一轮逐项完成。
复杂并发/锁实现、多进程、Flask/WSGI 框架内部、装饰器/闭包底层、完整导入机制与全量版本/恢复边界延后；第一轮只识别接口、作用范围和风险。延后不等于已掌握，也不自动授权深挖或重构。

### L1 — 应用启动

**索引状态**：应用初始化与对象引用已有 ORIENTED 基础；专题深学 NOT_STARTED。

- **Python 理论**：解释器/进程、模块与 Package、import 的顶层执行、`__name__` / `__main__`、函数定义与调用、类与实例、继承、函数作为参数及 lambda。
- **后端理论**：应用工厂、依赖组装、应用对象与服务器进程的区别、配置和资源路径、WSGI 与本机开发服务。
- **AI 理论**：导入 SDK、创建适配器与实际调用模型是不同动作；配置模型/密钥不等于已经发出请求或产生费用。
- **源码入口**：[app.py:108 `create_app()`](../../src/app.py#L108)、[app.py:134 本地调试工厂](../../src/app.py#L134)、[app.py:155 本地启动块](../../src/app.py#L155)、[prepare_plan.py:5 兼容导入](../../src/prepare_plan.py#L5)、[generation_runtime.py:56 配置子类](../../src/image_workflow/tasks/generation_runtime.py#L56)。
- **要亲自验证的关系**：启动块调用工厂后才调用 `.run()`；工厂创建 Store、一个 GenerationService、TaskApplication、TaskQueries、TaskImageApplication，再调用 `register_routes()`。区分“注册 handler”与“执行 handler”；追踪同一实例如何传入下游。
- **What / Why / Engineering 产物**：画一张对象关系草图；逐项列出对象创建点、共享关系和作用域。为何工厂适合隔离测试，用源码与现有测试支持解释。
- **无提示复述**：`import app`、`create_app()`、启动服务器、点击 AI 各会执行什么？为何 `prepare_plan.create_app` 不是第二套应用工厂？为什么不能从本地入口兼容推出 Mac mini 今日 WSGI 已可用？

### L2 — HTTP 请求

**索引状态**：Client/Server、HTTP、Flask 路由已有 ORIENTED 基础；专题深学 NOT_STARTED。

- **Python 理论**：装饰器、嵌套函数/闭包、可调用对象、字典/列表、字符串与 bytes、回调参数和返回值。
- **后端理论**：Client/Server、URL/Method/endpoint、HTTP 状态码、JSON 与 multipart、请求上下文、模板/静态资源、请求解析和错误响应。
- **AI 理论**：浏览器到本地 API 与后端到模型服务是两段边界；GET/保存/确认与模型操作不能混同；识别任务、图片和版本参数。
- **源码入口**：[api/routes.py:17 `register_routes()`](../../src/api/routes.py#L17)、[routes.py:170 `save_inputs()`](../../src/api/routes.py#L170)、[routes.py:177 `action()`](../../src/api/routes.py#L177)；前端 [prepare.js:98 `runAction()`](../../src/static/prepare.js#L98) 与 [tasks.js:2 `loadTasks()`](../../src/static/tasks.js#L2)。
- **要亲自验证的关系**：`loadTasks()` 的 GET `/api/tasks` → `task_list()` → 查询；上传 POST `/api/sessions` → `save_inputs()` → `tasks.save_inputs()`；`runAction()` 的 POST `/api/sessions/<session_id>/action` → `action()` → `tasks.action()`。后者按 action 类型决定是否规划，不能将所有 action POST 都称作付费请求。
- **What / Why / Engineering 产物**：选一条请求，填写 Method、URL、输入字段/文件、handler、用例、响应和可能状态码；先以只读列表理解 HTTP，再在源码上追踪 AI 操作。
- **无提示复述**：路由装饰器何时生效？`request.get_json` 作为回调传递和立刻调用有什么差别？为何业务用例不直接导入 Flask 的 request？

### L3 — Task / Application 协调

**索引状态**：Task 与持久化的基本关系已有 ORIENTED 基础；协调/版本/锁专题深学 NOT_STARTED。

- **Python 理论**：对象组合与实例引用、字典可变性、拷贝和别名、异常/异常链、`try/finally`、上下文管理、线程锁及非阻塞获取。
- **后端理论**：HTTP 表示、应用用例、业务规则、查询视图和持久化职责；并发冲突、版本检查、执行顺序与锁释放。
- **AI 理论**：模型返回的是候选结果；结构/身份校验与语义正确是不同问题。Planning 返回、应用到 Task、确认用于出图也不是同一状态。
- **源码入口**：[TaskApplication.action():126](../../src/image_workflow/tasks/service.py#L126)、[rules.apply_planning_result():66](../../src/image_workflow/tasks/rules.py#L66)、[rules.confirm_plan():46](../../src/image_workflow/tasks/rules.py#L46)、[TaskImageApplication.generate_one():51](../../src/image_workflow/tasks/images.py#L51)。
- **要亲自验证的关系**：`TaskApplication.action()` 获取原 Store 锁，检查活动图片、模式、revision 和 action；确认分支不调用 planner。规划分支调用注入的 planner → 应用结果 → `store.save()` → 写 `applied.json`，最终释放锁。图片用例先取得确认快照，再交给原 Generation 协调器。
- **What / Why / Engineering 产物**：列出“业务规则 / 编排 / 查询 / 文件存取”的归属；逐步标记 Task revision、计划确认、card_revision、Run ID 的不同含义，指出哪个对象拥有锁。
- **无提示复述**：为什么模型返回后还不能直接等同 Task 更新成功？为何过期 revision 必须在调用前拒绝？为什么不能为了 Review 再新建一套独立锁？

### L4 — AI Capability 与文件 I/O

**索引状态**：仅 Task 持久化的基本概念为 ORIENTED；AI 调用与文件 I/O 专题深学 NOT_STARTED。

- **Python 理论**：`Path`、文件 open/with、文本编码与图片字节、JSON/base64 序列化、dataclass/Callable、SDK 对象、异常传播与耗时测量。
- **后端理论**：纯函数与副作用、同步网络 I/O、超时/重试、原子替换与独占创建、文件写入顺序；单文件原子性不等于跨文件事务。
- **AI 理论**：Context/Prompt、图片身份与顺序、Responses 与 Images Edit 的不同输入、请求/响应/Usage、技术结果与人工验收、可恢复客户端请求与未知服务端内部信息。
- **Planning 入口**：[app.call_ai():97](../../src/app.py#L97) → [execute_planning():96](../../src/image_workflow/planning/service.py#L96)；纯构建 [build_planning_request():29](../../src/image_workflow/planning/request.py#L29)，执行 [invoke_model():61](../../src/image_workflow/planning/service.py#L61)。
- **Generation 入口**：[Task GenerationService._generate():149](../../src/image_workflow/tasks/generation.py#L149) → [execute_generation():147](../../src/image_workflow/generation/service.py#L147)；纯构建 [build_generation_request():127](../../src/image_workflow/generation/request.py#L127)，执行 [invoke_model():117](../../src/image_workflow/generation/service.py#L117)。
- **文件入口**：[TaskFiles.persist():43](../../src/image_workflow/tasks/storage.py#L43) → [write_snapshot_and_current():31](../../src/persistence/task_state.py#L31)；底层 [file_ops.write_json_atomic():54](../../src/file_ops.py#L54)、[write_json_exclusive():67](../../src/file_ops.py#L67)。
- **要亲自验证的关系**：builder 接收已有数据/字节并返回请求，不直接调用模型或落盘；执行层保存请求、调用 `client.responses.create` 或 `client.images.edit`、保存响应/错误。Task 快照独占写入后才替换 state；各调用方负责原有清洗策略。
- **What / Why / Engineering 产物**：各选一个 builder、SDK 调用和持久化函数，填写输入/输出/副作用表；列出本地请求与文件足以证明什么、不能证明什么。
- **无提示复述**：JSON 中的图片 data URL 与 Images 的实际图片输入有什么区别？哪里读图片、哪里构建请求、哪里实际发出？为何 source_sha256 不是整个系统源码证明？超时为何不能解释为未计费？

### L5 — 端到端调用链和失败诊断

**索引状态**：端到端追踪与失败诊断 NOT_STARTED；第一轮先完成检查点 B/C。

- **Python 理论**：调用栈与 traceback、`raise ... from ...`、异常被转换/被记录后返回的差异、finally、可变状态与持久化后的状态区别。
- **后端理论**：请求→用例→能力→文件→响应；错误映射、操作去重、状态查询、成功/失败与未知状态，进程内保护及崩溃窗口。
- **AI 理论**：按输入、请求、响应、Validation、状态应用及人工评价逐层定位；最早可观察偏差不等于根因；Mock 不证明视觉质量，账单与服务端内部状态可能 UNKNOWN。
- **成功链候选（待学习）**：[routes.generate_one():137](../../src/api/routes.py#L137) → TaskImageApplication → [GenerationService.generate():94](../../src/image_workflow/tasks/generation.py#L94) → Generation 执行与 Run → [routes.generation_result():128](../../src/api/routes.py#L128)。Review 另由 [Task Review.review():38](../../src/image_workflow/tasks/review.py#L38) → [apply_review():47](../../src/image_workflow/review/service.py#L47)，Pass 是独立人工动作。
- **失败链候选（待学习）**：先追踪 `TaskApplication.action()` 的过期 revision → `Problem` → [HTTP problem():28](../../src/api/routes.py#L28)，说明为何尚未触发 SDK；再追踪 Generation 执行异常 → FAILED Run/error → HTTP 错误及原结果保留，不假设所有错误都在同一 finally 范围内。
- **What / Why / Engineering 产物**：一条成功链和一条失败链，逐边界列输入、输出、状态、文件/外部副作用和错误去向；指出至少一个现有保护和一个尚未解决的窗口。
- **无提示复述**：从哪个入口调查商品变形、计划映射错误、版本冲突和不确定请求？哪些证据能区分 Planning 错误与 Generation 偏差，哪些仍然不能确定？

**测试导航（工程结果见 CURRENT_STATE，不自动推进学习状态）**：[入口兼容](../../tests/test_source_cutover.py)、[HTTP](../../tests/test_api_package.py)、[Task 应用](../../tests/test_task_application.py)、[请求构建](../../tests/test_t02_request_construction.py)、[Generation](../../tests/test_generation_package.py)、[Review](../../tests/test_review_package.py)。先阅读相应断言；后续学习中若需执行，仍须确认隔离临时目录、阻断网络/真实 runtime，不因学习默认启动服务或运行生成任务。

## 5. 检查点记录模板与持续记录区

每完成 A/B/C 中一个检查点，在本节补一次实际复述、反馈与记录；后续专题也在本文追加，不另建逐课文件。留空表示未记录，不由 Codex 代填“我的理解”或制造实验。

```text
检查点：A / B / C（后续专题再标 L1～L5）
任务与执行状态：NOT_STARTED / ACTIVE / REVIEW / COMPLETED
学习深度：ORIENTED / TRACEABLE / DEEP DIVE；未评估则 UNKNOWN
学习日期、源码基线：Branch / Git SHA；与记录版本的差异
1. What / Why / Engineering：本任务的用途、理由、真实组件与调用位置。
2. [OBSERVED] 静态源码或实际执行、来源、输入/输出、状态和副作用。
3. 我的单次复述：由学习者提供/确认；记录反馈与纠正，不补写不存在的原话。
4. [INFERENCE] 推导及依据；[UNKNOWN] 尚缺什么，是否阻断当前任务。
5. 验证与下一步：实际做了什么/未做什么；按需补哪个 Python 概念，何时回到主链。
确认方式：待记录。源码已摘录、计划已生成或模型返回成功均不自动提高学习深度。
```

### A 记录 — 已有定向基础

**执行状态：ACTIVE；相关概念深度：ORIENTED；检查点复述尚未完成。**
**来源：OBSERVED / 用户本轮明确提供的学习事实**，不冒充独立测验或已保存的逐字复述：

| 已有学习事实 | 深度与边界 |
|---|---|
| 初步理解 Client/Server、HTTP、Flask 路由 | ORIENTED；具体请求的完整追踪尚待 B |
| 初步理解 Task 与持久化 | ORIENTED；不代表状态/事务/恢复机制已深入掌握 |
| 初步理解 create_app 初始化和对象引用 | ORIENTED；不代表全部构造器、回调或框架内部均 UNDERSTOOD |

学习者本次检查点复述原文、反馈与 TRACEABLE 验证：待记录。不能将上述初步理解标为全部 UNDERSTOOD。

### 待复习与独立检验

以下来自已有学习记录与用户已确认的定向基础，本次没有替学习者测验或推进掌握等级：

| 主题 | 仍需自己说明/验证 |
|---|---|
| Python 后端 | 从 Client/Server、Flask、应用初始化的 ORIENTED 基础，追清一次对象引用、HTTP 调用、Runtime/文件副作用；不要求逐行精通 Python。 |
| M01 / M03 | Token Embedding 与 Sentence Embedding、训练如何形成表示；Q/K 权重与 V 汇总输出的区别。M01 已提交复盘仍为 REVIEW_REQUIRED，M03 记录未跟踪且为 ORIENTED。 |
| M04 / M05 / M07 | 商品事实与参考角色、Context 与实际 SDK 输入、生成与保持、Validation 与 Evaluation、无依据与已证伪宣称、人工 Rubric 与受控对照。已有概念记录不等于真实工程实践已验收。 |

依据：理论仓库 [M01 复盘](../../../enterprise-ai-theory/theory/M01_LEARNING_REVIEW_V0.1.md) 与第一轮知识地图；后者及 M03/M04/M05/M07 记录目前未跟踪，Git 边界见末尾交接。优先在商品变形诊断中定点复习，未独立掌握的部分保留 UNKNOWN。

### B 记录

NOT_STARTED；调用链复述、定位结果与学习深度待记录，不预填 TRACEABLE。

### C 记录

NOT_STARTED；已明确商品变形诊断方向，但独立证据定位、复述与学习深度仍待记录，不预填 TRACEABLE 或虚构已查明根因。

## 6. 第一轮完成标准

- A/B/C 各有一次学习者复述与对应记录；A 能说明全貌并找到职责归属，B/C 达到 TRACEABLE：能借助源码追踪单图生成、定位典型失败及应查证据。
- 能区分已观察事实、推断与 UNKNOWN，说明当前路径的关键输入、输出、状态和副作用；不要求背诵源码、掌握所有函数或消除所有 UNKNOWN。
- Python 基础只需足以支撑本轮追踪；不要求 L1～L5 全部 UNDERSTOOD，也不要求任何专题达到 DEEP DIVE。
- 达到以上标准后才将 P3-01 执行状态标 COMPLETED；本轮仅调整计划并记录 ORIENTED 基础，不宣称检查点已全部完成。
- 第一轮目标是**可追踪、可定位，不是源码精通**；学习完成仍不等于真实模型验收、运营接受、部署通过或新工程范围获授权。

## 7. 更新与 Git 检查点规则

- 每检查点完成一次复述与记录后更新进度和下一步；专题按需补记。保留既有人工记录与未解决问题，不静默改写已确认结论。
- 源码变更后先核对 HEAD、工作区和实际函数，重要结论携带版本；新结论注明日期和依据，旧基线标为历史而非套用新代码。
- 学习验证默认只读；不读取密钥/真实 runtime、不发送业务资料、不调用模型、不部署、不借学习继续重构。需要运行离线检查时仅用受控临时目录与 Mock，并如实记录执行与未执行。
- 重要学习节点或阶段完成可提出独立文档 Commit；**只有用户明确授权后才暂存和提交**。显式列文件、检查 staged diff/空白与敏感信息；不自动 Push，不混入用户原有修改。
- CURRENT_STATE 仅记录阶段、重要检查点与本文相对链接，不复制学习计划；本次同步其 P3-01 ACTIVE / ORIENTED 与双主线状态，保留未完成复述和 UNKNOWN。详细学习进度以本文为准。
- 进入新聊天先读本文件的基线、进度、复述与 UNKNOWN，再继续；不依赖聊天记忆认定已掌握。

## 8. 当前进度及下一步

| 项目 | 当前事实 |
|---|---|
| 文档 | 初始化 dfcf6df，双主线 C3 已提交为 cb8ec3944c5df5473d5e1a6b404cc1a9c6a717e8；本次仅同步事实与下一会话接续，不新建学习文件 |
| P3-01 / A | ACTIVE；用户提供的初步理解为 ORIENTED，系统全貌检查点复述待记录 |
| P3-01 / B、C | NOT_STARTED；单图生成与典型失败追踪尚未记录为 TRACEABLE |
| L1～L5 | 后续专题索引；不作为第一轮全部深学的门槛，已有部分 ORIENTED 不等于专题完成 |
| P3-02～P3-04 | NOT_STARTED，仅保留阶段索引 |
| 本轮验证 | 文档、静态源码定位与链接复核；工程离线回归另记 CURRENT_STATE，不当作学习者已掌握理论的证明；未启动服务、调用模型或读取真实 runtime |
| Mac mini | UNKNOWN / UNVERIFIED，核验 DEFER；本地版本不代表线上版本 |

下一步：从**真实商品变形案例**切入业务主线，借 Inspector 找到输入、Context、请求和输出的证据；按 A/B/C 检查点补足系统全貌复述、单图调用追踪和偏差定位记录，遇到阻碍才补 Python/Runtime/Persistence 基础。
不按 L1→L5 逐行深学推进，也不因已有 ORIENTED 基础跳过独立追踪、评价和复述；未独立掌握的理论继续记 UNKNOWN 或 NOT_STARTED。

## 9. Python / Flask 官方参考

以下链接于初始化时打开核对；用于解释基础原理，项目行为仍以对应 Git 版本的源码为准。Python 文档选择 3.12，Flask 选择 3.1.x 的 stable 文档；在线补丁版文档不代表本机已升级。

| 课次 | 官方资料 | 学习用途 |
|---|---|---|
| L1 | [Python Modules](https://docs.python.org/3.12/tutorial/modules.html)、[__main__](https://docs.python.org/3.12/library/__main__.html)、[Classes](https://docs.python.org/3.12/tutorial/classes.html) | 模块/Package、入口和对象；勿将 import 与调用混同 |
| L1 / L2 | [Flask Application Factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/)、[Application Lifecycle](https://flask.palletsprojects.com/en/stable/lifecycle/) | 应用组装、WSGI 与请求处理阶段 |
| L2 | [Flask Request Context](https://flask.palletsprojects.com/en/stable/reqcontext/) | 请求上下文及 request 作用域 |
| L3 / L5 | [Python Errors and Exceptions](https://docs.python.org/3.12/tutorial/errors.html)、[threading](https://docs.python.org/3.12/library/threading.html) | 异常、清理与线程锁；不据此假定项目已有跨进程保护 |
| L4 | [Python Input and Output](https://docs.python.org/3.12/tutorial/inputoutput.html)、[json](https://docs.python.org/3.12/library/json.html) | 文本/字节、文件和序列化 |
| L5 | [Testing Flask Applications](https://flask.palletsprojects.com/en/stable/testing/) | 测试客户端与隔离思路；官方示例使用 pytest，不意味着本项目需替换现有 unittest |

原草稿提及的 Docs as Code、Diátaxis、主动复述/间隔复习仅作为记录与学习组织方法，不据此新增 Charter、多层文档或工程组件。

## 10. 下一会话接续（2026-10-23）

**读取顺序**：本节 → [CURRENT_STATE](../00_PROJECT/02_CURRENT_STATE.md) → [系统愿景](../../../aigc-system-blueprint/docs/AIGC_SYSTEM_VISION_V0.1.md) / [演进台账](../../../aigc-system-blueprint/docs/SYSTEM_EVOLUTION_MAP_V0.1.md)；先核对各仓 Git，不依赖聊天记忆认定已提交、已学会或已部署。本节所在的最新文档 Commit 可用 `git log -1 -- docs/learning/P3_SOURCE_WALKTHROUGH_STUDY_V0.1.md` 确认，避免把自引用 SHA 写入正文。

| 本地仓库（均位于 /Users/andy/projects/） | 职责与 Git 检查点 |
|---|---|
| commerce-image-poc | 商品图业务、源码与运行 Evidence；源码 C1 `39199acc42ec056eae87247f17b267f1adbfd05a`，工程文档 C2 `331a13b`、学习 C3 `cb8ec39`；本轮文档起点 cb8ec39，最新交接以本文件所属 Commit 为准。 |
| enterprise-ai-theory | M00–M07 理论/实验；HEAD `d0ab310ed9ff9ee71ed6894188ec2f7bce96776c`。另有 .gitignore 修改、7 份未跟踪 Markdown 和 1 份未跟踪 M04 实验脚本；未获本轮文档提交条件，保持原样，不把本地成果冒充该 SHA 内容。 |
| aigc-system-blueprint | 长期产品方向与取舍；本轮文档检查点 `60ac4bfc3f5d803950fcdcc9c0c29a39f082a5e7`。沿用 Vision §9.1、演进 EV-002/003；不新建 ADR。 |

**已有能力**：商品/参考输入 → Planning/逐图确认（Quick 不需要）→ 生成/带图编辑 → Review/Pass → 版本/ZIP/Evidence；Inspector V0.7 和独立本地 Live Debug 已提交。最近软件实测 366 项 / Node 46 项通过，完整浏览器验收仍 PARTIAL；本轮未重跑测试或模型。
**理论状态**：本地知识地图记第一轮 M00–M07 定向结束，不能当作全模块掌握；M01 四项实验及复盘已提交且 REVIEW_REQUIRED，M02/M03/M06 仅 ORIENTED，M04/M05/M07 为 ORIENTED / ENGINEERING PRACTICE PENDING。M04 笔记报告合成分类对照 10/10 vs 10/10，非真实商品质量评价，本轮未核验原响应；M00 无独立验收，M06 无单独学习文件。相关未跟踪记录不具备 Git 可恢复性。
**两条主线**：A 以业务问题学习 Context / Multimodal / Image / Evaluation；B 通过同一案例按需补 Python 后端、Runtime、Persistence 和调试。P3-01 用 A/B/C 快速定向，不逐行深学 L1～L5；目前只有 Client/Server、Flask、Task/持久化及初始化等 ORIENTED 记录，B/C 独立复述仍待完成。
**当前问题与重要案例**：运营反馈商品主体变形。已有本地未跟踪 [M05 CASE-001](../../../enterprise-ai-theory/theory/M05_CASE_001_QUICK_REDESIGN_EVIDENCE_V0.1.md) 报告 Task `bbf3f10c42ad4a329438222ac1715d39`、Image `product_011`、revision 1、Run `20261016T071710Z-94b3eab16e3c4f33a99a63332eaefdf6`；Quick 未执行 T02，旧报告未证实主体替换，指出宣称缺少已保存事实支持。它是调查索引，不是本轮原图核验或已证明的变形根因。

**Evidence / Inspector**：已有启动为 `./scripts/start_live_debug.sh` → `http://127.0.0.1:8013/`，需既有隔离 Runtime，CLI 自动加载根目录 .env；本轮没有启动或核验运行进程/Key。只读侧栏跟随完整 Task/Image/revision/Run，按来源查看原图、清单、Context、Prompt、请求/响应与结果；Quick 图不虚构 Planning，INFERRED/MISSING 不升级为事实。历史材料可用性须在明确授权目录内核对，不自动 SSH 或扫描运营数据。

**下一步具体任务（待下一轮授权，不在本轮执行）**：

1. 先核对目标案例/运营拒绝图的准确版本，恢复商品与参考身份、实际 Prompt/顺序、输出和审核的证据表；分开评价主体保持与宣称依据。原始材料缺失时报告 UNKNOWN，不以现有 Builder 或 Mock 替代。
2. 定义最小人工 Rubric，再提出一个受控对照因素；付费生成独立授权，不自动重试/批量。近期停止扩张 UI/架构。
3. 理论仓库先独立审查未提交 M04 源码与现有修改，再建立检查点并同步总索引的 M04/M05/M07 重心；本轮因源码未提交停止该仓操作，七份 Markdown 均未纳入 Git。

**UNKNOWN / 安全**：真实外观变形的确切失败版本、案例原始文件可用性、模型内部根因、真实质量/账单与人工完整验收均未确认；Mac mini 版本/WSGI/备份 UNKNOWN，核验 DEFER。保留历史凭据风险及快照，不读取/展示密钥，不把 .env、runtime、图片或日志入 Git；资料访问、源码改动、实验/付费须分别按授权范围执行。
