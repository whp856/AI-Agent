# LLM 层设计文档

## 1. 模型与服务商

| 角色 | 服务商 | 模型 | 启用条件 | 用途 |
|---|---|---|---|---|
| 主模型 | DeepSeek（国内直连） | `deepseek-chat`（V3） | `DEEPSEEK_API_KEY` 非空 | 全部核心语义任务 |
| 备选模型 | 阿里云百炼 DashScope | `qwen-plus` | `QWEN_API_KEY` 非空 | 主模型故障/限流自动切换 |
| 本地兜底 | Ollama | `qwen2.5:7b` | `OLLAMA_ENABLED=true` | 完全离线演示，质量较低但流程可跑通 |
| 规则模式 | 无 | 关键词+统计 | 以上均不可用 | 降级演示，结论如实标注 degraded |

统一 **OpenAI 兼容端点**（`backend/llm/client.py`）：

```
DeepSeek:  https://api.deepseek.com
Qwen:      https://dashscope.aliyuncs.com/compatible-mode/v1
Ollama:    http://localhost:11434/v1
```

## 2. 模型参数配置（.env.example 全量可覆盖）

| 参数 | 默认 | 说明 |
|---|---|---|
| LLM_TEMPERATURE | 0.3 | 分析类任务低温度，输出稳定 |
| LLM_MAX_TOKENS | 4096 | 单次响应上限 |
| LLM_TIMEOUT | 60s | 请求超时 |
| LLM_MAX_RETRIES | 3 | 每 provider 重试次数，指数退避 1s/2s/4s |

## 3. 工具定义（JSON Schema 结构化输出）

所有语义阶段使用 `response_format={"type": "json_object"}` + Pydantic 强校验。
核心工具（各阶段 LLM 调用）定义：

| 阶段 | 工具 | 输入 | 输出 schema 要点 |
|---|---|---|---|
| S0 | 计划解析 | 目标+约束 | `{focus_areas[], constraints[], analysis_plan, data_requirements[]}` |
| S3 | 主题挖掘 | 评论批次(≤40) | `{topics[{topic_name, description, member_ids[], evidence[], opposing_feedback[], confidence}]}` |
| S3 | 主题合并 | 各批主题 | `{topics[], merge_log[]}` |
| S4 | 结论推导 | 统计+主题 | `{findings[{statement, kind, supporting_review_ids[], confidence, uncertainty, conflicting_evidence[]}]}` |
| S5 | 需求生成 | 结论 | `{requirements[{title, priority, version, rationale, evidence_refs[], acceptance_criteria[]}]}` |
| S6 | 用例生成 | 需求 | `{test_cases[{title, preconditions, steps[], expected_results[], req_refs[]}]}` |

**引用强制约束**：S3/S4/S5 提示词硬性要求"评论 ID 只能引用候选列表中的值"，从源头杜绝无依据推论；程序侧 S7 校验器再复查一遍。

## 4. 异常降级策略（分级降级，UI 如实标注）

| 故障场景 | 行为 | UI 标注 |
|---|---|---|
| 主模型超时/限流 | 自动切 Qwen 重跑当前阶段 | 「已切换 qwen-plus」 |
| 云端均不可用 | 切 Ollama 本地模型（若启用） | 「本地模型模式（质量较低）」 |
| 无任何模型 | 规则模式：关键词+统计兜底 | 「降级模式：置信度受限」 |
| 采集失败 | 缓存数据兜底（如有） | 「已使用缓存数据（N 条）」 |
| 单阶段多次失败 | 跳过并标注依赖缺失 | 「阶段 X 失败」 |

**铁律**：任何降级都必须如实告知，严禁伪装成模型产出，严禁伪造数据。

## 5. 减少幻觉与无依据推论的保障方案

1. **引用强制**：结论/需求/主题成员只能引用给定候选评论 ID；
2. **ID 完整性校验**：S7 确定性校验，孤儿引用 → 清除/删除/标记假设（修正日志可查）；
3. **结论分级**：`statistical`（统计事实，程序生成）/ `model_derived`（模型推导）/ `assumption`（假设）——UI 与快照明确分区；
4. **置信度与不确定性**：每条结论必须带 confidence + uncertainty（样本量、代表性说明）；
5. **对立反馈**：主题与结论强制展示 opposing_feedback / conflicting_evidence；
6. **样本量阈值**：`MIN_SAMPLE=3`，不足的观察自动降级为 assumption，不进 PRD；
7. **双通道交叉验证**：模型语义结论 vs 统计指标（频次/评分/版本分布）矛盾时，结论中明确标注「统计与模型结论存在分歧」；
8. **模型对比实验**：规则基线 vs LLM 的结果对比报告框架见 `docs/model-comparison.md`。

## 6. 提示词工程要点

- 系统提示词固定（角色+质量标准），数据放用户消息（结构化 JSON 而非原文拼接，省 token、防注入）；
- 评论正文截断 500 字符，过滤 URL 与敏感标记；
- 提示词版本化（存于 `backend/llm/prompts/`，文件即版本）；
- 每次调用记录模型/温度/token/耗时/重试 → 写入运行快照（可审计）。

## 7. 安全

- API key 仅环境变量读取，`.env` + `.gitignore` 双重排除；
- 本仓库未包含、也不允许提交任何真实密钥。
