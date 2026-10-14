# Commerce Image POC

> 阶段：低成本 AI 可行性验证 / 两页式原型探索  
> 范围：跨境电商商品图包制作（当前参考 TikTok Shop、Temu 的相似制图工作）  
> 状态：**仅创建工程基础框架；尚无功能代码、真实模型调用或运营验收**。

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
├── .env.example               # 空配置样例（不含真实密钥）
├── docs/
│   ├── 01_PRODUCT_BRIEF.md    # 已讨论的产品雏形及首轮 DoD
│   ├── 02_CURRENT_STATE.md    # 唯一当前状态与下一项任务
│   └── 03_EXPERIMENT_LOG.md   # 真实调用与运营评价的最简记录
├── src/                      # 空目录：首个编码任务再添加代码
├── tests/                    # 空目录：需要时添加针对性测试
└── .runtime/                 # Git 忽略；实物素材、成图及运行证据
    ├── inputs/
    ├── outputs/
    └── evidence/
```

`src/` 与 `tests/` 初始为空；不要为了填满目录而预建文件。`.runtime/` 为本地数据，不纳入 Git；真实素材与关键证据需要自行安全备份。

## 4. 解压后的第一步

1. 在 VS Code / Codex 中打开此文件夹。可自行执行 `git init`，并在确认 `.gitignore` 后提交初始文档。
2. Codex 先读 `AGENTS.md`、`docs/01_PRODUCT_BRIEF.md` 和 `docs/02_CURRENT_STATE.md`。
3. **得到明确的 Task 01 启动指令后**，再实现一次真实的参考图生图通路；首轮暂不开发两页式界面。
4. 尚未准备真实素材、API 凭据或调用预算时，先报告缺失条件；不得伪造测试成功。

## 5. 先不做

旧工程迁移、C01～C05 强制流水线、复杂 Context Engine、Skill/Agent/RAG、评价平台、复杂权限、全量工作流和平台规则自动化。需要时必须以真实问题为依据重新决定。

参考原则：既有 `FDE_BUSINESS_FIRST_AI_ENGINEERING_METHOD_V0.1.md`；旧 `00_PRODUCT_ENGINEERING_CHARTER_V0.1.md` 仅作为历史线索，**不继承其技术方案或工程计划**。
