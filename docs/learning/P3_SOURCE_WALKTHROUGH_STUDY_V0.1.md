# P3｜AI 产品工程源码走读与执行机制学习记录 V0.1

**项目：** commerce-image-poc
**定位：** 以真实 AIGC 业务流程为载体，理解 Python 后端工程与 AI 系统的执行机制。
**初始化日期：** 2026-10-22（Asia/Shanghai）
**当前阶段：** P3-01 — 全局 Python 与 AI 业务执行通路
**计划状态：** PLANNED；P3-01 与 L1～L5 均为 NOT_STARTED，尚未评价学习者掌握程度。
**仓库基线：** `main` / `5a3c57a8de8e3c0c07b886f9379c111cd5a79cf6`（文档检查点）。
**业务源码基线：** `78c68f9f25639d77abfdc3792a36541912f8af09`（FINAL CUTOVER）；当前 HEAD 未改变该检查点的源码。

本文既是计划，也是后续持续更新的唯一 P3 学习记录。本轮发现已有同名未跟踪草稿，直接补全，不另建等价计划或逐课文件。
源码、测试和业务状态分别以 [src/](../../src/)、[tests/](../../tests/)、[CURRENT_STATE](../02_CURRENT_STATE.md) 为准；[README](../../README.md) 是启动与导航入口。
这里的函数和行号只适用于上述基线；后续先核对版本，再更新定位，不把旧行号当作新版本事实。

## 1. 学习目标、方法与证据

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

学习顺序：只读定位 → 结合代码解释理论 → 跟踪输入/输出/状态/副作用 → 学习者无提示复述 → 记录与复习。
可以与已有 C、嵌入式或 AI 理论经验对照，但不预设学习者已经掌握；源码调查完成不等于学习完成。

| 标识 | 使用规则 |
|---|---|
| OBSERVED | 已在指定版本的源码直接读到，或在明确记录的安全实验中观察到；注明“静态源码”或“实际执行”。 |
| INFERENCE | 根据源码关系或观察作出的解释，列依据与推导；不写成作者已确认动机或模型内部事实。 |
| UNKNOWN | 当前缺证据、未执行或尚未理解；写清缺什么、怎样安全核对。 |

以下调用定位为本轮 **OBSERVED / 静态源码**，仅作为待学习的真实入口，不是本轮运行轨迹或用户已掌握知识。

## 2. 阶段路线

| 阶段 | 范围与预期产物 | 学习状态 |
|---|---|---|
| P3-01 | 全局执行通路；完成 L1～L5，能独立串联一次请求及失败边界。详见第 3 节。 | NOT_STARTED |
| P3-02 | 多模态输入、图片角色、Context 与 Planning；建立数据来源到请求/结果的简要追踪。暂不细化课次。 | NOT_STARTED |
| P3-03 | Generation、Review、并发和版本；理解执行身份、锁、父版本与 Pass。暂不细化课次。 | NOT_STARTED |
| P3-04 | Evidence 与 AI Failure Diagnosis；按阶段证据区分程序问题、语义偏差及未知原因。暂不细化课次。 | NOT_STARTED |

只有当前 P3-01 详细规划；后续阶段在人工确认当前学习进度后展开，不预设新的工程任务。

## 3. P3-01 五节学习安排

### L1 — 应用启动

**学习状态：NOT_STARTED。**

- **Python 理论**：解释器/进程、模块与 Package、import 的顶层执行、`__name__` / `__main__`、函数定义与调用、类与实例、继承、函数作为参数及 lambda。
- **后端理论**：应用工厂、依赖组装、应用对象与服务器进程的区别、配置和资源路径、WSGI 与本机开发服务。
- **AI 理论**：导入 SDK、创建适配器与实际调用模型是不同动作；配置模型/密钥不等于已经发出请求或产生费用。
- **源码入口**：[app.py:108 `create_app()`](../../src/app.py#L108)、[app.py:134 启动块](../../src/app.py#L134)、[prepare_plan.py:5 兼容导入](../../src/prepare_plan.py#L5)、[generation_runtime.py:56 配置子类](../../src/image_workflow/tasks/generation_runtime.py#L56)。
- **要亲自验证的关系**：启动块调用工厂后才调用 `.run()`；工厂创建 Store、一个 GenerationService、TaskApplication、TaskQueries、TaskImageApplication，再调用 `register_routes()`。区分“注册 handler”与“执行 handler”；追踪同一实例如何传入下游。
- **What / Why / Engineering 产物**：画一张对象关系草图；逐项列出对象创建点、共享关系和作用域。为何工厂适合隔离测试，用源码与现有测试支持解释。
- **无提示复述**：`import app`、`create_app()`、启动服务器、点击 AI 各会执行什么？为何 `prepare_plan.create_app` 不是第二套应用工厂？为什么不能从本地入口兼容推出 Mac mini 今日 WSGI 已可用？

### L2 — HTTP 请求

**学习状态：NOT_STARTED。**

- **Python 理论**：装饰器、嵌套函数/闭包、可调用对象、字典/列表、字符串与 bytes、回调参数和返回值。
- **后端理论**：Client/Server、URL/Method/endpoint、HTTP 状态码、JSON 与 multipart、请求上下文、模板/静态资源、请求解析和错误响应。
- **AI 理论**：浏览器到本地 API 与后端到模型服务是两段边界；GET/保存/确认与模型操作不能混同；识别任务、图片和版本参数。
- **源码入口**：[api/routes.py:17 `register_routes()`](../../src/api/routes.py#L17)、[routes.py:170 `save_inputs()`](../../src/api/routes.py#L170)、[routes.py:177 `action()`](../../src/api/routes.py#L177)；前端 [prepare.js:97 `runAction()`](../../src/static/prepare.js#L97) 与 [tasks.js:2 `loadTasks()`](../../src/static/tasks.js#L2)。
- **要亲自验证的关系**：`loadTasks()` 的 GET `/api/tasks` → `task_list()` → 查询；上传 POST `/api/sessions` → `save_inputs()` → `tasks.save_inputs()`；`runAction()` 的 POST `/api/sessions/<session_id>/action` → `action()` → `tasks.action()`。后者按 action 类型决定是否规划，不能将所有 action POST 都称作付费请求。
- **What / Why / Engineering 产物**：选一条请求，填写 Method、URL、输入字段/文件、handler、用例、响应和可能状态码；先以只读列表理解 HTTP，再在源码上追踪 AI 操作。
- **无提示复述**：路由装饰器何时生效？`request.get_json` 作为回调传递和立刻调用有什么差别？为何业务用例不直接导入 Flask 的 request？

### L3 — Task / Application 协调

**学习状态：NOT_STARTED。**

- **Python 理论**：对象组合与实例引用、字典可变性、拷贝和别名、异常/异常链、`try/finally`、上下文管理、线程锁及非阻塞获取。
- **后端理论**：HTTP 表示、应用用例、业务规则、查询视图和持久化职责；并发冲突、版本检查、执行顺序与锁释放。
- **AI 理论**：模型返回的是候选结果；结构/身份校验与语义正确是不同问题。Planning 返回、应用到 Task、确认用于出图也不是同一状态。
- **源码入口**：[TaskApplication.action():126](../../src/image_workflow/tasks/service.py#L126)、[rules.apply_planning_result():66](../../src/image_workflow/tasks/rules.py#L66)、[rules.confirm_plan():46](../../src/image_workflow/tasks/rules.py#L46)、[TaskImageApplication.generate_one():51](../../src/image_workflow/tasks/images.py#L51)。
- **要亲自验证的关系**：`TaskApplication.action()` 获取原 Store 锁，检查活动图片、模式、revision 和 action；确认分支不调用 planner。规划分支调用注入的 planner → 应用结果 → `store.save()` → 写 `applied.json`，最终释放锁。图片用例先取得确认快照，再交给原 Generation 协调器。
- **What / Why / Engineering 产物**：列出“业务规则 / 编排 / 查询 / 文件存取”的归属；逐步标记 Task revision、计划确认、card_revision、Run ID 的不同含义，指出哪个对象拥有锁。
- **无提示复述**：为什么模型返回后还不能直接等同 Task 更新成功？为何过期 revision 必须在调用前拒绝？为什么不能为了 Review 再新建一套独立锁？

### L4 — AI Capability 与文件 I/O

**学习状态：NOT_STARTED。**

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

**学习状态：NOT_STARTED。**

- **Python 理论**：调用栈与 traceback、`raise ... from ...`、异常被转换/被记录后返回的差异、finally、可变状态与持久化后的状态区别。
- **后端理论**：请求→用例→能力→文件→响应；错误映射、操作去重、状态查询、成功/失败与未知状态，进程内保护及崩溃窗口。
- **AI 理论**：按输入、请求、响应、Validation、状态应用及人工评价逐层定位；最早可观察偏差不等于根因；Mock 不证明视觉质量，账单与服务端内部状态可能 UNKNOWN。
- **成功链候选（待学习）**：[routes.generate_one():137](../../src/api/routes.py#L137) → TaskImageApplication → [GenerationService.generate():94](../../src/image_workflow/tasks/generation.py#L94) → Generation 执行与 Run → [routes.generation_result():128](../../src/api/routes.py#L128)。Review 另由 [Task Review.review():38](../../src/image_workflow/tasks/review.py#L38) → [apply_review():47](../../src/image_workflow/review/service.py#L47)，Pass 是独立人工动作。
- **失败链候选（待学习）**：先追踪 `TaskApplication.action()` 的过期 revision → `Problem` → [HTTP problem():28](../../src/api/routes.py#L28)，说明为何尚未触发 SDK；再追踪 Generation 执行异常 → FAILED Run/error → HTTP 错误及原结果保留，不假设所有错误都在同一 finally 范围内。
- **What / Why / Engineering 产物**：一条成功链和一条失败链，逐边界列输入、输出、状态、文件/外部副作用和错误去向；指出至少一个现有保护和一个尚未解决的窗口。
- **无提示复述**：从哪个入口调查商品变形、计划映射错误、版本冲突和不确定请求？哪些证据能区分 Planning 错误与 Generation 偏差，哪些仍然不能确定？

**测试导航（本轮未运行）**：[入口兼容](../../tests/test_source_cutover.py)、[HTTP](../../tests/test_api_package.py)、[Task 应用](../../tests/test_task_application.py)、[请求构建](../../tests/test_t02_request_construction.py)、[Generation](../../tests/test_generation_package.py)、[Review](../../tests/test_review_package.py)。先阅读相应断言；若后续需要执行，须单独确认隔离临时目录、阻断网络/真实 runtime，不因学习默认启动服务或运行生成任务。

## 4. 课次记录模板与持续记录区

每次在本节对应课次下扩展记录，复用以下模板；不得为每节另建文件。留空表示未记录，不由 Codex 代填“我的理解”或制造实验。

```text
课次：Lx — 名称
学习状态：NOT_STARTED / ACTIVE / REVIEW / UNDERSTOOD
学习日期：待记录
源码基线：Branch / Git SHA；与初始化版本的差异

A. 已核实事实
- [OBSERVED / 静态源码或实际执行] 文件、函数、行号、调用方/被调用方。
- 输入、输出、状态所有者和副作用；证据与适用版本。
B. What / Why / Engineering
- What：概念是什么；Why：为什么需要（推断须标 INFERENCE）。
- Engineering：当前实现、接口、对象、I/O、失败边界；可与既有经验对照。
C. 我的理解与复述（由学习者提供或明确确认）
- 自己解释的调用链、回答、误解和未理解点。
D. 验证
- 只读追踪/临时离线检查方法，实际是否执行；结果和证据。
- [INFERENCE] 推导及依据；[UNKNOWN] 缺失信息和安全核对方法。
E. 复习与下一步
- 待解决问题、复述反馈、是否复习、下一节入口。
更新人/确认方式：待记录；不能仅因助教读过源码就标 UNDERSTOOD。
```

### L1 学习记录

NOT_STARTED；学习日期、学习者复述、验证结果均待记录。

### L2 学习记录

NOT_STARTED；学习日期、学习者复述、验证结果均待记录。

### L3 学习记录

NOT_STARTED；学习日期、学习者复述、验证结果均待记录。

### L4 学习记录

NOT_STARTED；学习日期、学习者复述、验证结果均待记录。

### L5 学习记录

NOT_STARTED；学习日期、学习者复述、验证结果均待记录。

## 5. 状态、复述要求和完成标准

- NOT_STARTED：尚未开始该课；ACTIVE：正在学习；REVIEW：存在需复习的缺口；UNDERSTOOD：学习者无提示复述并经确认。生成计划和静态索引不推进这些状态。
- 每课结束先由学习者解释调用顺序、数据、状态与失败边界，再用源码核对。记录其实际表述和纠正点，后续短复习；不知道的部分保留 UNKNOWN。
- P3-01 仅在 L1～L5 均达到 UNDERSTOOD，并能独立追踪一条成功路径和一条失败路径、辨别源码/运行证据/推断之后标 COMPLETED。
- 完成时应能解释：模块加载与工厂、HTTP 到 Task 的边界、模型与文件 I/O、确认/版本/Pass 身份，以及错误、去重和诊断限制。
- 学习完成不等于真实模型验收、运营业务接受、部署通过或新工程范围获授权。

## 6. 更新与 Git 检查点规则

- 每节更新本文件的学习记录、实际进度与下一步；保留既有人工记录与未解决问题，不静默改写已确认结论。
- 源码变更后先核对 HEAD、工作区和实际函数，重要结论携带版本；新结论注明日期和依据，旧基线标为历史而非套用新代码。
- 学习验证默认只读；不读取密钥/真实 runtime、不发送业务资料、不调用模型、不部署、不借学习继续重构。需要运行离线检查时仅用受控临时目录与 Mock，并如实记录执行与未执行。
- 重要学习节点或阶段完成可提出独立文档 Commit；**只有用户明确授权后才暂存和提交**。显式列文件、检查 staged diff/空白与敏感信息；不自动 Push，不混入用户原有修改。
- CURRENT_STATE 仅记录阶段初始化、重要检查点与完成状态及相对链接，不复制课次计划。README 保持导航用途，本轮无需改动。
- 进入新聊天先读本文件的基线、进度、复述与 UNKNOWN，再继续；不依赖聊天记忆认定已掌握。

## 7. 当前进度及下一步

| 项目 | 当前事实 |
|---|---|
| 文档 | 既有草稿补全，初始化待人工审核；未 Commit |
| P3-01 / L1～L5 | NOT_STARTED，0/5 节有已确认学习记录 |
| P3-02～P3-04 | NOT_STARTED，仅保留阶段索引 |
| 本轮源码核对 | OBSERVED / 静态定位；没有启动服务、执行软件回归或产生运行 Evidence |
| 学习者掌握程度 | UNKNOWN，尚无本轮复述或测试记录 |
| Mac mini | UNKNOWN / UNVERIFIED，核验 DEFER；本地版本不代表线上版本 |

下一步：等待人工审核本文；随后从 **P3-01 / L1 应用启动** 开始，一次只讲一条链路，等待学习者复述和提问，再决定进入下一课。
本轮仅初始化记录，不在这里提前给出五课的学习完成结论。

## 8. Python / Flask 官方参考

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
