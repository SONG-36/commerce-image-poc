# Experiment Log — 真实实验简表

> 当前状态：**T01 已完成一次真实生图；本轮用户明确评价首张图片 PASS。T02 尚未执行真实规划实验。** 不预填未发生的实验或运营评价。  
> 目的：帮助判断业务问题、模型能力和改进方案，不建设独立 Evaluation 平台。

## 每次真实试验记录（一条即可）

复制以下模板追加到本文件；把大文件、完整请求/响应和实际图片保存在本地 `.runtime/`，并做好授权范围内的备份。

```md
### EXP-YYYYMMDD-01 — <简短任务名>
- 日期 / 操作人：
- 业务任务 / SKU（非敏感标识）：
- 输入文件及来源（本地 `.runtime/inputs/` 路径）：
- 要验证的命题：
- 使用模型与调用方式 / 关键指令或请求快照位置：
- 结果文件 / 原始响应或错误：
- 真实耗时 / 可得用量和成本：
- 运营人工评价：采用 / 修改 / 拒绝；具体原因；若未评价则写未评价
- 与原方式的对照（如有）：
- 结论类型：初步有效 / 初步无效 / 证据不足 / 实验失败
- 局限与下一步：
```

## 规则

- 不把“接口返回成功”写成“运营通过”；不把一次好图宣称为统计证明。
- 失败保留真实错误，不以本地 Mock、静态示例或合成日志代替。
- 这里的记录是短索引；敏感商品资料、密钥、原始图片、付费响应不得提交到 Git。
- 若没有真实实验，不新增实验记录；首次试跑之后再填写。

## 已完成实验

### EXP-20261014-01 — case-001 首张真实商品图

- 日期 / 操作人：2026-10-14；既有运行证据确认本地执行，具体终端操作者未记录；本轮补记，未重新调用模型。
- 业务任务 / SKU：case-001，验证真实商品资料能否通过成熟图像模型生成首张商品图。
- 实际输入：`.runtime/inputs/case-001/` 的三张 `product_01～03.jpg`、一张设计参考图 `ref_01.webp`、`listing.md` 与 `requirements.md`。其余三张参考图未发送。
- 模型与调用：OpenAI `gpt-image-2.5-sunburst`，官方 SDK 2.54.0，`images.edit`；`n=1`、`quality=low`、`size=1024x1536`、PNG、`max_retries=0`。
- Run ID：`20261014T052541Z-786016c60ae94a7c9168d74c55d4a36b`。
- 请求证据：`.runtime/evidence/case-001/20261014T052541Z-786016c60ae94a7c9168d74c55d4a36b/` 的 `prompt.txt`、`request.json`、`run.json`、`response.json`；实际客户端 Prompt、图片顺序及模型参数已保存。
- 结果：`.runtime/outputs/case-001/20261014T052541Z-786016c60ae94a7c9168d74c55d4a36b/image.png`；1024×1536 PNG，1,794,063 字节，SHA-256 `ea709fff0abd4853a7cbb4d5024904ed4a4b40da6588a9e52254660184f316f0`，与响应图片字节一致。
- 真实耗时与用量：API 21.164 秒，总耗时 21.327 秒；input 6042 tokens（image 4576、text 1466），output 158，total 6200。实际账单金额未记录，不推算为实付费用。
- Request ID：`req_70b0d54d84a34bdca28ea29fb0dbecf2`。
- 运营人工评价：**PASS**。依据为本轮用户明确提供“用户已对本次生成图片给出 PASS 评价”；具体接受原因未提供。原始 `run.json` 的 `NOT_REVIEWED` 是运行当时状态，保留原样，以本条追加后续人工评价。
- 资产包：`.runtime/exports/case-001-run-001.zip`，含 11 个 ACTUAL 文件及说明、清单、SHA-256 表；不含密钥或环境文件。
- 局限：服务端 `revised_prompt=null`；原始 HTTP 请求/响应字节、完整响应头、当时源码版本快照和账单金额未记录。未把源码重建信息当成原始证据。
- 结论：**T01 COMPLETE；该首张图片被用户接受。** 未证明多图一致性、单图修改稳定性或普遍业务效果；无原流程成本/效率对照。
- 下一步：T02 ACTIVE，开发 Prepare & Plan；T02 的真实多模态规划和修改效果须另行授权、执行并记录，不以本地 Mock 代替。


### EXP-20261028-E105 — Listing 两图真实 Smoke：Planning 响应校验失败

- 授权与范围：一次性新 Listing Task，最多 1 Planning / 2 Images，零自动重试；生产代码与 Prompt 不改动，不部署。
- 基线与来源：`main / ff7526ea39afecc75368ce0a23b3248aa55ba351`；历史 Task `43889e73c53c462da86216ed42f0a1ec` revision 3，分别从 reference_001 / reference_002 当时 Run 的 inputs 提取三张商品、两张参考及原始文字，未用 revision 6；原始字节与哈希一致，历史文件未改写。
- 新 Task：`6fc958c5b1b649328f24a2718d3f9954`；main / selling_point 分别绑定 reference_001 / reference_002，固定 Brief 通过现有逐图要求提供。候选输出尺寸 1024x1536，未发送 Images 请求。
- 实际调用：Planning 1 次，`gpt-5.4-mini` → 返回 `gpt-5.4-mini-2026-03-17`；reasoning low，max_output_tokens 6000，json_object，store false，timeout 120 秒，max_retries 0。Images 0 次。
- 结果：提供方返回 completed，本地事实报告校验失败并返回 HTTP 502。受影响计划字段混入 reference_101/102 图位 ID，另有一条逐图 Brief 引用被标为原始 requirements 而原文不匹配。两条均为 INSUFFICIENT_EVIDENCE，不是已证明的商品矛盾；原始结果未修正或应用。
- 确认与审核：DELEGATED_TEST_CONFIRMATION 为本次授权方式，因校验失败未执行；没有生成图片，没有 Pass，运营未评价。返回文本还描述了未经本次确认的旋转喷头，不能据此认证该机制。
- 实际用量：input 12055 / output 1408（含 reasoning 75）/ total 13463 tokens；API 12.499 秒，总过程 12.6 秒。实际计费金额 UNKNOWN。
- Evidence：`.runtime/debug/e105-listing-pack-smoke-20261028T121902Z-924883/` 的 input_manifest、planning_review、usage_summary、final_result 及 summary；原始请求/响应/错误保存在新 Task 的 `calls/79ac7dbd03df48478f4ddf04892c9881/`。
- 结论类型：实验在 Planning 应用前失败，GENERATED = 0 / BUSINESS ACCEPTANCE PENDING。未重试、切换模型、绕过确认或继续生成；不以此次失败直接推断商品图模型质量。
- 后续工程注记（2026-10-29，非新模型实验）：针对上述身份/来源契约做最小修复；Listing 模型输入不再提供内部图位 ID，逐图 Brief 使用独立且严格归属/原文匹配的 slot_requirements 来源。完整隔离 Python 451 / 独立 Node 68 项通过；原始响应仍被拒绝，34 个失败 Evidence 文件整体哈希未变。本注记不更改上述失败、Usage、评分或运营状态，没有重跑 Planning/Images。
