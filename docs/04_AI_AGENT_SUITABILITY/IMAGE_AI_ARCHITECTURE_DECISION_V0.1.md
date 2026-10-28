# 商品图 AI 子系统架构决策 V0.1

**项目：** `commerce-image-poc`\
**阶段：** 04 AI / Agent Suitability\
**日期：** 2026-10-28\
**状态：** `PROPOSED / READY FOR FINAL APPROVAL`\
**性质：** 目标架构候选，不代表已经正式批准、实施或通过业务验收。

建议路径：`docs/04_AI_AGENT_SUITABILITY/IMAGE_AI_ARCHITECTURE_DECISION_V0.1.md`

业务规则以 [Business Baseline V0.2](../02_BUSINESS_MODELING/V1_BUSINESS_BASELINE_V0.2.md)为权威依据，目标流程参照[三场景 Workflow](../02_BUSINESS_MODELING/IMAGE_CREATION_WORKFLOWS_V0.1.md)。本次只澄清 AI Decision 与 Agent 的定位，不新增事实权限或实施授权。

## 1. 架构目标

在现有商品图片制作系统上，支持三个业务工作入口：

- Quick-A：同款快速改版
- Quick-B：换主体快速改版
- Listing：商品资料制图

内部业务分类仍为 Quick 与 Listing 两种模式，Quick 包含 A/B 两个子场景；不据此创建三套独立生成系统。入口由运营选择，AI/Agent 不自行重新决定业务模式。

一期优先解决实际商品外观保真、商品事实权限、参考图适配、制作决策、图片生成和人工审核问题。

本项目是长期统一 AIGC / 多模态工作台的第一个真实业务切入点，但一期不提前建设通用 Agent、跨媒体 Workflow 或企业级知识平台。

## 2. 架构方案选择

比较以下三种方案：

| 方案 | 优势 | 风险 | 结论 |
|---|---|---|---|
| A：场景化 Workflow + Model-first AI Decision | 可控、复用现有工程、易于调试 | 专业能力需要逐步增强 | 一期默认采用 L1～L3 |
| B：统一自主 Agent | 动态任务处理能力较强 | 事实权限复杂、成本和失败路径难以控制 | 一期不采用 |
| C：固定业务流程 + 按需知识及工具 | 兼顾控制与未来扩展 | 需要证明动态能力的真实收益 | 演进方向；必要的任务级 L4 须单独授权 |

**架构建议：**

一期默认采用 A：确定性 Business Rules、Model-first AI Decision 与场景化 Conditional Workflow（L1～L3），保留向 C 演进的能力边界。具体任务若已证明需要动态工具选择、执行、观察与调整，可以按下文条件单独授权 L4 Bounded Agent，不是一律禁止任务级动态能力。

不建立独立的通用 AI Decision 服务，不因为存在 S1～S6 就创建六个 Agent 或六个模型调用。

## 3. 目标逻辑架构

整体逻辑链：

**Business Workflow → Business Rules → AI Decision Capability → Context Engineering → Generation / Review / Evidence**

各环节的职责：

| 层次 | 主要职责 |
|---|---|
| Business Workflow | 承接运营选择的工作模式，管理输入、任务状态和人工确认条件 |
| Business Rules | 管理信息来源、尺寸图前置条件、必须替换或保留的内容 |
| AI Decision Capability | 理解商品和参考图，按场景事实权限选择卖点与制作方法 |
| Context Engineering | 将商品资料、参考素材、制作要求和已确认决策准确组织给模型 |
| Generation | 使用现有图片生成能力产生候选图 |
| Human Review | 运营确认制作方案或成图，修改、Pass、导出 |
| Evidence | 记录有效输入、模型请求、响应、版本及人工决策 |

以上为逻辑职责，不要求建立对应数量的代码模块、服务或 API。

AI Decision Capability 是逻辑责任，可以采用普通确定性规则、单次或少量 LLM Decision、条件式 Workflow，或按需且单独授权的任务级 Bounded Agent。普通语义判断不自动等于 Agent；固定 Workflow 中同样可以具有 AI 决策能力。

## AI Autonomy Levels

以下为本项目采用的工程分类，不是统一行业标准。层级描述自主决策与行动范围，不等于 AI 智能水平高低，也不是必须依次升级的实施路线。

### L1｜Deterministic Rules

根据明确条件执行规则。例如：没有运营提供的、已标注目标商品真实尺寸的专项白底素材，不允许生成尺寸图。规则执行不等于独立认证尺寸测量真实性。

### L2｜LLM Decision

模型根据商品资料、参考图和业务目标进行语义判断，例如选择卖点、参考适配、推荐构图和专业制作方法。不要求动态工具调用，不因判断由模型完成就创建 Agent。

### L3｜Conditional Workflow

系统依据模型或规则结果进入预先定义的处理分支。例如：发现明显事实冲突时交运营确认；资料正常且满足既有业务条件时继续制作。正常 Quick 不因此增加独立 Planning 或逐项审批。

### L4｜Bounded Agent

在明确目标、工具权限与预算范围内，模型可以根据任务状态：

- 选择下一步行动；
- 按需调用获准工具；
- 观察工具返回结果；
- 调整后续行动；
- 满足条件时终止，或请求人工确认。

候选例子：Quick-B 缺少商品局部视角时，在授权范围内检查已有素材，判断能否改用其他构图；必要时请求运营补充素材。不得凭空创造商品结构，不得自行扩大资料访问或付费权限。这个例子不是已实施能力或本轮开发授权。

### L5｜Autonomous Agent

在更大范围内自主规划、执行多种任务与工具协作。一期不涉及通用自主任务平台或此类自主度。

## 4. 三个业务场景的执行策略

### 4.1 Quick-A

运营选择同款快速改版。

- 商品原图决定目标商品外观。
- 同款参考图中的适用参数、功能和卖点可以沿用。
- 允许选择部分卖点重点展示，但不能删除运营明确指定的必保留内容。
- AI 负责差异化构图、布局、信息层级和视觉设计。
- 不增加强制独立 Planning。
- 运营最终审核成图。

### 4.2 Quick-B

运营选择换主体快速改版。

- 选择该模式表示运营声明参考图中的相关规格、功能和卖点适用于目标商品。
- 商品原图决定全部实际商品主体的外观。
- 参考商品的主体、相关特写和场景商品必须正确替换。
- 可以沿用经确认适用的营销信息，但不自动继承参考品牌、包装、配件及专属结构。
- 允许重新设计构图和卖点排版，不强制复制参考版式。
- 不增加强制独立 Planning。
- 运营重点审核主体替换完整性。

### 4.3 Listing

运营提供商品图、参考营销图及 Listing、描述、卖点等文字资料。

- 当前商品文字资料是商品宣称的主要依据。
- 实际商品图片是商品可见外观的主要依据。
- 参考图主要提供营销表达与视觉设计方法。
- 参考图额外参数与卖点不能未经核对自动继承。
- 图片与文字出现明显矛盾时必须提示运营，不得自行选择一个版本作为事实。
- 保留已有商品理解、参考理解、逐图 Planning 和运营确认流程。
- 根据确认后的制作计划生成并审核图片。

## 5. AI Capability 的职责分配

| 能力 | 默认执行方式 | 任务级 Agent 候选边界 |
|---|---|---|
| S1 商品理解 | 原生多模态模型 + 商品事实来源约束 | 不因商品理解包含判断就创建 Agent |
| S2 参考图理解 | 原生多模态模型，重点提高参考内容准确性 | 不因参考理解包含判断就创建 Agent |
| S3 参考图适配 | 模型判断 + 场景专属 Business Rules | 需要动态查证资料、检查多个素材来源并据结果调整处理方法时，可研究 L4 |
| S4 平台/地区规则 | 已知平台与图位优先进行有来源、适用范围明确的确定性规则查询 | 只有实际需要多来源动态查证、比较和工具协调时才研究 L4 |
| S5 专业制作决策 | Model-first，可按需提供经过审核的专业 Knowledge，不强制 Skills | 需要动态检索专业方法、选择实际设计工具、检查中间结果并调整方案时，可研究 L4 |
| S6 Context Engineering | 可追溯的确定性输入组装，保持素材角色、来源与版本一致 | 未来可增加按需知识选择；不要求所有 Context 都由 Agent 生成 |

S1～S6 是能力分类，不是六个 Agent，不等于固定执行顺序或独立运行组件。候选条件不代表已经证明有收益，也不授权实施。

## 6. Rules、Knowledge、Skills、Agent 选择

### Rules

一期必须落实已确认的业务约束：

- 商品外观依据；
- Quick-A/B/Listing 信息权限；
- Quick-B 完整主体替换要求；
- 尺寸图专项素材条件；
- 必保留营销信息；
- Listing 显著事实冲突的人工处理；
- 已确认计划与有效输入版本的一致性。

可由程序确定的条件应优先采用确定性检查。需要理解图片语义时，可使用模型辅助识别，但不能宣称模型已独立验证商品真实性。

### Knowledge

保留已经研究的专业制图知识卡 K01～K06。

当前定位为研究资产和可选增强能力，不默认注入全部生产请求。

只有真实业务评价或实验显示增益时，才逐步纳入对应图位的有效 Context。

### Skills

一期不建设正式专业制图 Skill 库。

先验证专业方法有效，再比较固定 Context、按需加载和 Skill 封装的实际收益。

### Agent

一期默认采用 L1～L3，以低自主度 AI Decision + 场景化 Workflow 为核心；不以通用 Agent Runtime、多 Agent 协作或自主任务平台作为基础设施前置条件。明确保留 L4 任务级 Bounded Agent 边界，L5 不属于一期范围。

S3、S5、素材处理等实际任务出现动态工具选择与反馈处理需求时，可以进行任务级研究。只有同时满足以下条件，才建议单独授权具体 Agent 实施：

1. 有明确业务问题；
2. 简单方法存在可观察不足；
3. 存在必要的实际工具操作；
4. 工具结果会影响下一步处理；
5. 工具权限与执行预算可控制；
6. 有人工确认和停止条件；
7. 能保存完整的实际执行 Evidence；
8. 有合理的评价方法。

这些条件用于判断是否提出授权建议，不构成自动批准。Bounded Agent 不加入所有商品图任务，也不是一期完成的强制条件。

### Agent 与业务 Workflow 的边界

Quick-A、Quick-B、Listing 入口由运营选择；商品事实权限由 Business Rules 决定。AI/Agent 只在获准任务内决定处理方法和下一步行动，不得：

1. 擅自改变商品 SKU 或身份；
2. 将未确认的参考卖点升级为商品事实；
3. 自行批准有冲突的商品宣称；
4. 绕过 Listing 的人工方案确认；
5. 自动把生成结果标记为运营 Pass；
6. 未经授权调用付费工具或 API；
7. 异常时无限重试。

既有 Quick-A/B 适用信息沿用权限和尺寸专项前提保持不变；L4 不新增事实裁决权，也不改变人工责任。

### Bounded Agent 的最小任务契约

未来任何任务级 Bounded Agent 至少先明确：

| 契约项 | 必须明确的范围 |
|---|---|
| Task Goal | 具体业务目标与完成结果 |
| Allowed Tools | 获准工具、资料访问、读写及付费操作范围 |
| Input / Output Contract | 有效输入、输出及可检查结果 |
| Business Rules | 不可绕过的场景规则与人工责任 |
| Fact Permissions | 商品外观、可用宣称与争议信息的来源权限 |
| Execution Budget | 调用次数、费用及其他执行资源边界 |
| Maximum Steps / Retries | 最大步骤、重试上限及禁止自动重试的操作 |
| Human Approval Conditions | 何时交运营处理或另行取得操作授权 |
| Stop Conditions | 完成、预算耗尽、资料不足或无获准下一步时的停止条件 |
| Failure Handling | 错误与执行不确定性处理，不伪装成功或盲目重发 |
| Evidence / Observability | 实际输入、行动、工具返回、版本、异常与人工操作记录 |
| Evaluation Criteria | 对照简单方法的业务效果、风险和成本评价 |

这是候选任务的授权前提，不是 Agent Runtime、接口 Schema 或新架构层的实施要求。一期不必立即建设这套 Runtime；具体调用范围与成本仍须单独批准。

## 7. Human Gates

| 场景 | 制作前确认 | 成图确认 |
|---|---|---|
| Quick-A | 正常情况不强制 | 必须 |
| Quick-B | 正常情况不强制 | 必须 |
| Listing | 必须确认制作计划 | 必须 |

所有模式遇到关键商品事实争议时，需将相关问题交由运营处理。

生成成功、结构校验成功、模型自评成功，都不能替代人工 Pass。

## 8. 现有实验如何影响架构

S5 首次 Listing 对照实验已经结案：

- Experiment：`washer_reference_002_ab_v0.1`；Attempt：`attempt_002`。
- Model + Knowledge：13/15
- Model-only：11/15
- 评价性质：`AI-assisted preliminary review`；Operator Review：`NOT_COMPLETED`；Generated Image Review：`NOT_PERFORMED`。
- 差异来自 Q4 参考理解；其他四项同分，两份专业制作方案总体接近。
- Model-only 将参考图第五栏误述为泡沫洗净；这是已记录的参考内容偏差，不能直接当作专业布局能力差异。
- 单案例、每组一次成功 Planning 调用，不能证明 Knowledge 稳定改善 S5 专业制作决策。
- 没有正式运营评价、没有实际成图比较，也没有直接测试 Agent。
- 状态：`CLOSED_EXPLORATORY_PILOT`。历史实验 Evidence 保持原样，本文件只引用结论。

因此，保留 Knowledge 作为研究候选；本实验不能证明 Agent 必须开发，也不能证明 Agent 没有价值。不能用它授权 Knowledge / Skills / Agent 生产实施。本次不重评、不解释为新实验，也不改变原评分和结案记录。

## 9. 明确不在一期范围内

- 通用自主 Agent 平台；
- 多 Agent 协作框架；
- 全面 RAG / 向量数据库；
- 专业 Skills 自动调度；
- 自动替代运营 Pass 的质量审查系统；
- 全自动修图循环；
- 视频、音频业务 Workflow；
- 自动采集市场与社媒信息；
- 重新开发整套 Task、Planning、Generation 和 Review 基础设施。

上述通用平台与自动化不在一期范围，不代表长期禁止；也不排除符合第 6 节条件、单独授权的任务级 L4。保留该边界不表示一期必须交付 Agent Runtime。

## 10. 架构决策结论

建议采用：

**Business Workflow + Business Rules + AI Decision Capability + Context Engineering + 现有 Generation / Review / Evidence。**

一期以现有工程为基础，默认采用 L1～L3；任务级 L4 依业务证据、完整契约和单独授权按需引入，不建设通用自主 Agent 或多 Agent 平台。

避免两个极端：不让所有 AI 任务都通过 Agent 执行，以免增加成本、复杂度和事实权限风险；也不永久限制为固定 Workflow、排除模型动态选择工具。当前任务采用最简单且可靠的方式，根据实际业务收益决定是否扩展，不按技术流行程度决定。

这是架构候选结论；进入生产开发前仍需根据现有源码完成最小变更设计并获得实施授权。
