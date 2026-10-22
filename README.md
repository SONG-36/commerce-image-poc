# Commerce Image POC

跨境电商 AI 商品图片制作与修改工作台，是多工作流 AIGC 系统的第一个真实业务切入点；未来系统的范围不由本项目限定。

阶段：**INTERNAL PILOT / BUSINESS VALIDATION**。本地源码结构整理已完成；工程验证、模型效果和运营接受分别记录。

## 主要能力

- 任务中心与独立任务资料：商品图、Listing、描述、整体要求及设计参考图。
- 商品图包：AI 商品/参考理解与逐图规划 → 人工逐图确认 → 单图或显式顺序批量生成。
- Quick Redesign：N 张原图直接重设计，无需 Listing 或完整规划。
- 统一工作台：选图、计划/成图查看、文字加一张辅助图修改、历史版本和指定版本 Pass。
- 最终通过图片 ZIP、完整实验 ZIP，以及实际请求、响应、输入身份和失败 Evidence。

## 本地启动

在仓库根目录使用 Python 3.12。首次准备环境；已有可用 `.venv` 时跳过这两步：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

启动本机调试服务，无前端构建步骤：

```bash
.venv/bin/python -B src/app.py --port 8010
```

打开 http://127.0.0.1:8010/ 。启动、页面加载和刷新不调用模型。
原 `src/prepare_plan.py --port 8010` 及 `prepare_plan.create_app()` 仍兼容；该 Flask 调试服务不应直接开放到公网。

AI 操作需要运行人员在启动前安全配置服务端环境变量 `OPENAI_API_KEY`；程序不自动读取 `.env` 或 `.env.example`。
`OPENAI_PLANNING_MODEL`、`OPENAI_IMAGE_MODEL` 选择代码允许的模型，当前默认与调用边界见 [CURRENT_STATE](docs/02_CURRENT_STATE.md)。

## 离线测试

复用现有依赖；完整回归还需本机可执行的 Node.js，供两组前端交互测试使用：

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m pip check
```

测试使用临时目录和 Mock；不需要 API Key，不调用真实模型。279 项 Python 用例包含前端测试包装，不另行累加内部 Node 用例。
本轮核查使用额外的临时目录/网络访问保护；未重新安装依赖或启动常驻服务。

## 目录导航

| 位置 | 职责 |
|---|---|
| [src/app.py](src/app.py) | 正式工厂、配置与依赖组装 |
| [src/api/](src/api/) | Flask 请求解析、路由与错误响应 |
| [src/image_workflow/](src/image_workflow/) | Task 编排、Planning、Generation、Review 与实验导出 |
| [src/infrastructure/](src/infrastructure/) | 脱敏与 OpenAI Images 客户端配置 |
| [src/persistence/](src/persistence/) / [file_ops.py](src/file_ops.py) | 状态文件、快照、路径及 JSON 操作 |
| [src/cli/](src/cli/) | T01 与 Quick 独立实验命令；默认免费检查，只有显式 `--run-paid` 才尝试付费 |
| [src/templates/](src/templates/) / [src/static/](src/static/) | HTML、原生 JavaScript 与样式 |
| [tests/](tests/) / [requirements.txt](requirements.txt) | 离线回归与 Python 依赖 |
| `.runtime/` | Git 忽略的真实输入、任务、成图与 Evidence，须单独备份 |

Web 默认数据位于 `.runtime/prepare-plan/sessions/<task-id>/`；`create_app(runtime_dir, case_dir)` 可指定独立数据位置。
实验 CLI 原命令路径仍兼容，正式实现位于 `src/cli/`；参数可通过 `--help` 查看。

## 文档入口

- [当前工程状态](docs/02_CURRENT_STATE.md)：代码基线、模块职责、已知限制、历史部署与下一阶段。
- [Product Brief](docs/01_PRODUCT_BRIEF.md)：业务目标与历史产品决策；其中候选/未实现描述按原日期理解，当前状态以上一份为准。
- [实验日志](docs/03_EXPERIMENT_LOG.md)：真实实验与人工评价记录；旧 Next Action 不作为当前任务。
- [AGENTS.md](AGENTS.md)：协作、成本及数据保护边界。

## 验证范围与安全

- 本地 Cutover 已提交，HTTP/CLI、请求、版本、Pass、文件及 ZIP 兼容性通过离线回归；不代表真实模型质量或运营验收通过。
- Mac mini 当前在线版本、WSGI 和配置 **UNKNOWN / UNVERIFIED**；2026-10-16 的部署记录已整合到 CURRENT_STATE，不能当作今日检查结果。
- 真实资料发送到模型及付费操作须明确授权；不自动付费重试。顺序批量需用户确认，刷新不续跑；连接失败不等于未执行或未计费。
- 不将参考商品的信息自动认定为当前 SKU 事实，不保证编辑能完全保持未修改区域。
- 不将 API Key 写入 Git、前端、日志或 Evidence；不要使用旧 `.env.example` 作为密钥来源。`.runtime/`、环境文件及虚拟环境不纳入 Git。
- 任务目录隔离不等于用户权限；进程内锁、多文件中断窗口和来源哈希限制见 CURRENT_STATE。服务器核验与部署本轮均未执行。
