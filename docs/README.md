# 文档导航 — Enterprise AI 六步开发流程

本索引按已确定的六步方法组织现有文档。六步是工程分析与决策流程，可以交错推进；不是要求逐阶段全部完成的门禁，也不因文档归档而授权开发、模型调用或部署。

## 1. 阅读入口与权威边界

- **当前业务目标与规则：**[V1 Business Baseline V0.2](02_BUSINESS_MODELING/V1_BUSINESS_BASELINE_V0.2.md)。Quick-A / Quick-B 是 Quick 的两个业务子场景，Listing 是另一模式；业务边界已明确，仍需工程符合性和实际业务验证。
- **工程实现与已记录验证：**[CURRENT_STATE](00_PROJECT/02_CURRENT_STATE.md)。这是带日期的工程记录，包含历史 SHA、测试和部署口径；不能代替当前 Git 或线上核验。各次核验与历史快照按所属日期理解，本次文档归档未重新核验运行服务或业务效果。
- **能力拆解与技术适配研究：**[商品图 AI 决策研究](04_AI_AGENT_SUITABILITY/IMAGE_AI_DECISION_STUDY_V0.1.md)。研究处于 ACTIVE，不代表 Agent、Knowledge、Skills 或新 Workflow 已获生产实施批准。
- **历史产品与实验：**[Product Brief](00_PROJECT/01_PRODUCT_BRIEF.md)、[实验日志](00_PROJECT/03_EXPERIMENT_LOG.md)。保留当时的候选方案、人工反馈和实验结论；历史 Next Action、未实施说明不作为今日状态。
- **设计与个人学习：**[Inspector V0.7 规格](design/CONTEXT_FLOW_INSPECTOR_V0.7_SPEC.md)、[P3 学习主记录](learning/P3_SOURCE_WALKTHROUGH_STUDY_V0.1.md)。分别记录设计/验证与学习状态，不替代业务基线或运营验收。

业务要求、代码已实现、离线测试通过、真实模型效果、运营接受是不同结论。发生差异时，业务目标以 V0.2 为准；代码行为以实际版本与 Evidence 为准，不通过导航文字消除差距。

## 2. 六步职责与当前状态

| 环节 | 文档职责 | 当前状态与已有入口 |
| --- | --- | --- |
| **00_PROJECT** | 跨阶段产品背景、工程状态、实验索引 | 已归档 [Product Brief](00_PROJECT/01_PRODUCT_BRIEF.md)、[CURRENT_STATE](00_PROJECT/02_CURRENT_STATE.md)、[实验日志](00_PROJECT/03_EXPERIMENT_LOG.md)。不是新的阶段或第二套业务规范。 |
| **01 Task Discovery** | 真实人工流程、角色、输入输出、痛点及未核实问题 | **PARTIAL：已有业务调查基础，部分问题尚未核实。**见 [业务场景](02_BUSINESS_MODELING/V1_BUSINESS_BASELINE_V0.2.md#3-两种模式的最小业务流程)、[运营规则与未知项](04_AI_AGENT_SUITABILITY/IMAGE_AI_DECISION_STUDY_V0.1.md#3-真实运营业务规则)及 [早期证据等级](00_PROJECT/01_PRODUCT_BRIEF.md#1-当前业务认识与证据等级)。暂无独立调查文件，不创建空目录。 |
| **02 Business Modeling** | 业务边界、SOP、规则与人工责任 | [V0.2业务基线](02_BUSINESS_MODELING/V1_BUSINESS_BASELINE_V0.2.md)仍为权威；[三场景目标 Workflow](02_BUSINESS_MODELING/IMAGE_CREATION_WORKFLOWS_V0.1.md)已整理 Quick-A / Quick-B / Listing。已确认业务规则与 **PROPOSED** 目标流程分开记录，工程符合性与真实质量待验证。 |
| **03 AI Capability Decomposition** | 决策清单、能力边界、当前机制和缺口 | [S1～S6横向能力拆解](03_AI_CAPABILITY_DECOMPOSITION/IMAGE_AI_CAPABILITY_DECOMPOSITION_V0.1.md)为 **CANDIDATE / READY FOR BUSINESS & TECHNICAL REVIEW**：区分共享能力、场景策略和事实权限，不等于六个 Agent 或新增实现。 |
| **04 AI / Agent Suitability** | 比较程序、规则、模型、Knowledge、Skills、Workflow、Agent 与人工 | [S5专业知识研究](04_AI_AGENT_SUITABILITY/S5_PROFESSIONAL_DESIGN_KNOWLEDGE_RESEARCH_V0.1.md)保留 K01～K06候选方法与 Rubric；[AI架构候选](04_AI_AGENT_SUITABILITY/IMAGE_AI_ARCHITECTURE_DECISION_V0.1.md)为 **PROPOSED / READY FOR FINAL APPROVAL**，建议一期默认 L1～L3，任务级 L4按需单独授权，不强制交付 Agent Runtime。 |
| **05 Task Contract + Evaluation** | 能力输入输出、事实边界、评价标准、基线与受控实验 | [一期实施与验收契约](05_TASK_CONTRACT_EVALUATION/V1_IMPLEMENTATION_CONTRACT_V0.1.md)为 **PROPOSED / IMPLEMENTATION NOT AUTHORIZED**，包含 P0、工程/业务评价及 E0～E5。单案例 S5方案层探索已结案，只有 AI辅助初评，不证明稳定增益或运营验收；新实验与 Coding仍需授权。 |
| **06 Engineering + Validation** | 工程实现、运行、回归、业务验证与恢复限制 | **EXISTING V1 / PILOT；新 AI 决策增强未授权 Coding。**见 [工程记录](00_PROJECT/02_CURRENT_STATE.md)、[工程设计](design/CONTEXT_FLOW_INSPECTOR_V0.7_SPEC.md)。本轮未核验运行环境、重跑测试或重新验证业务质量；无独立新专题文件，不创建空目录。 |

## 3. 当前实际目录

```text
docs/
├── README.md
├── 00_PROJECT/
│   ├── 01_PRODUCT_BRIEF.md
│   ├── 02_CURRENT_STATE.md
│   └── 03_EXPERIMENT_LOG.md
├── 02_BUSINESS_MODELING/
│   ├── V1_BUSINESS_BASELINE_V0.2.md
│   └── IMAGE_CREATION_WORKFLOWS_V0.1.md
├── 03_AI_CAPABILITY_DECOMPOSITION/
│   └── IMAGE_AI_CAPABILITY_DECOMPOSITION_V0.1.md
├── 04_AI_AGENT_SUITABILITY/
│   ├── IMAGE_AI_DECISION_STUDY_V0.1.md
│   ├── S5_PROFESSIONAL_DESIGN_KNOWLEDGE_RESEARCH_V0.1.md
│   └── IMAGE_AI_ARCHITECTURE_DECISION_V0.1.md
├── 05_TASK_CONTRACT_EVALUATION/
│   └── V1_IMPLEMENTATION_CONTRACT_V0.1.md
├── FDE_BUSINESS_FIRST_AI_ENGINEERING_METHOD_V0.2.md
├── design/
│   └── CONTEXT_FLOW_INSPECTOR_V0.7_SPEC.md
└── learning/
    └── P3_SOURCE_WALKTHROUGH_STUDY_V0.1.md
```

03和05已有独立研究与契约文档；01和06仍通过上表导航到已有资料。只有出现职责独立的真实文档时，才按需建立相应目录；不为凑齐结构拆分或复制现有记录。

## 4. 已知口径差异与个人方法论

- 研究台账已按 V0.2 对齐模式定义、S1–S6 研究维度及实验适用性；业务目标仍以 [V0.2](02_BUSINESS_MODELING/V1_BUSINESS_BASELINE_V0.2.md)为准。研究记录不另立业务规范，也不将候选能力写成已批准实现；实验适用性限制见其 [证据章节](04_AI_AGENT_SUITABILITY/IMAGE_AI_DECISION_STUDY_V0.1.md#5-已有重要实验与失败证据)。
- 研究文档保留形成时的候选样本、待讨论事项和授权边界；既有研究台账的阶段状态按原日期理解。本次 S5结案的有限结论见上表04架构候选第8节：无正式运营评价、无成图比较、未直接测试 Agent；不改写历史研究或原始 Evidence。
- V0.1 业务基线已由 V0.2替代；旧版由 Git历史保留，不恢复或复制另一份权威基线。
- [FDE 个人方法论](FDE_BUSINESS_FIRST_AI_ENGINEERING_METHOD_V0.2.md)是跨项目的个人工程方法与能力记录，不是商品图项目的专属业务规范。文件名与正文标题已统一为 V0.2，状态仍为 PROPOSED；本次归档不修改其正文、不升级批准状态，也不跨仓迁移。
- FDE 长期建议与理论仓库已有 [学习方法记录](../../enterprise-ai-theory/docs/02_LEARNING_METHODOLOGY_V0.1.md)评估整合，具体归档位置和跨仓迁移等待单独批准。

## 5. 后续文档放置与维护

1. 跨阶段项目背景、Current State、实验索引放在 `00_PROJECT/`；原始 Evidence 和运营资料不进入 docs 或 Git。
2. 独立业务调查、建模、能力拆解、技术适配、契约评价、工程专题分别归入 `01_TASK_DISCOVERY/`、`02_BUSINESS_MODELING/`、`03_AI_CAPABILITY_DECOMPOSITION/`、`04_AI_AGENT_SUITABILITY/`、`05_TASK_CONTRACT_EVALUATION/`、`06_ENGINEERING/`；创建前先检查是否可更新现有记录。
3. `design/` 与 `learning/` 保留原位和既有职责。03能力拆解、04技术适配与05实施契约各司其职，优先复用上表文档，不建立重复的研究台账或权威来源。
4. 新业务事实更新业务基线，实际工程进度更新 Current State，真实实验才追加实验记录；长期跨业务架构决策留在 Blueprint，个人方法论不升级为项目规则。
5. 保留 `OPERATOR_CONFIRMED / OBSERVED / INFERENCE / PROPOSED / DECIDED / UNKNOWN / VALIDATED` 等证据与授权边界；旧 SHA、历史结果和未验证事项不得因移动文件而升级。
6. 移动文档时同步导航与相对引用；保留原内容和版本号，提交或跨仓迁移须遵循当轮明确授权。
