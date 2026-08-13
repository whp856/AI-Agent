# App Store Review Analyzer

> iOS 应用评论分析与版本规划系统 —— 输入 App Store 链接，自动完成「采集 → 清洗 → 模型动态分类 → 证据评估 → PRD 生成 → 测试用例生成 → 追溯校验」的完整产品分析工作流。

本项目为 LaienTech 技能测试交付物，完整实现"自然驱动式编程"全流程产品化，核心语义任务由大模型（DeepSeek）实时驱动，确定性任务（采集、清洗、统计、校验）由规则完成，两者分工并互验。

## 快速开始（3 步）

```bash
# 1. 安装依赖（Python 3.10+）
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. 配置模型（可选，不配置则进入降级演示模式）
cp .env.example .env               # 填入 DEEPSEEK_API_KEY 即可启用模型驱动

# 3. 启动
uvicorn backend.main:app --host 0.0.0.0 --port 8000
# 浏览器打开 http://localhost:8000
```

**无网络 / 无 key 演示**：点击页面「示例数据演示」按钮，或运行
`python -m scripts.demo`，使用内置 50 条真实评论缓存跑通全流程。

## 功能演示

1. 输入任意美国区 App Store 链接（示例：`https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684`）+ 分析目标/约束
2. 点击「开始分析」→ 实时进度面板展示 8 阶段状态与中间产出（SSE 推送）
3. 交付物 Tab 展示：原始评论 / 清洗数据 / 分类结果 / 分析结论 / PRD 草稿 / 测试用例 / 追溯校验报告
4. 支持导入 JSON/CSV 评论数据并直接启动完整分析
5. 一键导出完整运行快照（JSON）

## 架构

```
浏览器（原生 HTML/JS，零构建）
   │ REST + SSE
FastAPI 后端
   ├─ Agent 编排器：8 阶段状态机（S0 计划 → S1 采集 → S2 清洗 → S3 分类
   │                 → S4 证据 → S5 PRD → S6 用例 → S7 校验），校验失败回环重试
   ├─ 工具层：采集(RSS) / 清洗 / 统计 / 追溯校验 / 导入（全部确定性规则）
   └─ LLM 层：OpenAI 兼容接口，DeepSeek 主 → 规则模式兜底
```

## 方法选择矩阵（规则 / 统计 / LLM 分工）

| 环节 | 方法 | 理由 |
|---|---|---|
| 评论采集 | 规则 | 官方接口格式固定，合规优先，确定性 |
| 清洗/去重/语言检测 | 规则 | 纯机械转换，零误差 |
| 动态主题分类 | **LLM** | 语义泛化，适配陌生应用/语言/目标 |
| 频次/分布统计 | 统计 | 可复现的确定性事实 |
| 痛点推导/优先级 | **LLM + 统计互验** | 模型语义聚合，统计交叉验证 |
| PRD 需求生成 | **LLM + 规则校验** | 语义提炼，证据引用强制校验 |
| 测试用例生成 | **LLM** | 需求→场景转换，评论引用由规则继承 |
| 追溯校验 | 规则 | ID 完整性检查必须零误判 |

## 数据采集方案与局限性

- 数据源：**Apple 官方 iTunes RSS 评论接口**（`itunes.apple.com/rss/customerreviews/id={appId}/sortBy=mostRecent/json`），公开合规、无需登录、纯 JSON
- 合规：限速 ≥2 秒/请求、最多 5 页、失败指数退避重试、结果本地缓存（`data/cache/`）
- 局限（如实声明）：每请求最多 50 条；仅最近评论（无全量历史）；评论删除不可回溯；分析结论均标注数据窗口
- 样例数据：`data/cache/839285684.json` 含 50 条真实评论（来源见 `data/samples/SOURCE.md`），仅作演示兜底，不替代实时采集能力

## LLM 设计

- **模型与服务商**：`deepseek-chat`（DeepSeek 官方 API）
- **参数**：temperature 0.3（分析任务低温度）、max_tokens 4096、timeout 60s、重试 3 次指数退避——全部环境变量可覆盖（`.env.example`）
- **结构化输出**：全部语义阶段 `response_format=json_object` + Pydantic 强校验 + JSON Schema 提示
- **降级链**：DeepSeek → 规则模式，降级在 UI 与快照中如实标注
- **防幻觉 4 层**：① 引用强制（只能引用候选评论 ID）② ID 完整性校验（S7）③ 结论分级（统计事实/模型推导/假设）④ 置信度 + 对立反馈
- 核心提示词存于 `backend/llm/prompts/`（s0 / s3_classify / s3_merge / s4_findings / s5_prd / s6_testcases）

## 测试

```bash
pytest tests/ -v        # 52 个测试，不依赖网络与真实 API key（FakeLLM + MockTransport）
```

## 评审自检清单（对照技能测试要求）

| # | 要求 | 落地 |
|---|---|---|
| 1 | 输入链接+目标+约束，自动执行工作流 | ✅ 8 阶段编排器 |
| 2 | 采集评论 | ✅ iTunes 官方 RSS + 缓存 |
| 3 | 清洗/去重/结构化 | ✅ S2 规则清洗 |
| 4 | 动态分类（非固定关键词） | ✅ S3 LLM 主题挖掘（关键词仅作无模型降级兜底） |
| 5 | 证据充分性/矛盾/不确定性 | ✅ S4 统计+LLM 双通道 |
| 6 | 版本方案+PRD+多版本拆分 | ✅ S5（v8.1/v8.2/v9.0） |
| 7 | 用例关联需求+原始评论 | ✅ S6 三层关联 |
| 8 | 完整追溯链路校验 | ✅ S7 确定性校验 + 修正日志 |
| 9 | UI 进度/中间产出/校验/异常/修正 | ✅ SSE 进度面板 |
| 10 | 各阶段交付物展示 | ✅ 交付物 Tabs + 导出 |
| 11 | 至少一项 LLM 语义任务 | ✅ 4 项（分类/推导/需求/用例） |
| 12 | 规则/统计/LLM 理由说明 | ✅ 本 README 矩阵 + docs/ |
| 13 | 结论带 ID/样本量/置信度/对立反馈 | ✅ Finding 契约 |
| 14 | 模型结论 vs 统计结论区分 | ✅ kind 分区标注 |
| 15 | 模型/服务商/提示词/参数/降级/防幻觉文档 | ✅ docs/llm-design.md |
| 16 | 密钥环境变量禁止提交 | ✅ .env + .gitignore |
| 17 | GitHub 可运行交付 | ✅ 本仓库 |
| 18 | JSON/CSV 导入 | ✅ /api/analyze-import |
| 19 | 全新链接/新数据/新目标 | ✅ 无硬编码，动态流程 |
| 20 | 提交记录体现迭代 | ✅ git 历史完整 |
| 21 | 数据源与局限清晰 | ✅ 本文档 + docs/data-collection.md |
| 22 | 频率限制不压站 | ✅ 限速+缓存 |
| 23 | 严禁伪造数据 | ✅ 降级如实标注铁律 |

## 已知局限与未来改进

- RSS 仅最近窗口评论，长期趋势需多次采样累积
- 少数语种分类质量依赖模型能力，可用 `scripts/` 对比实验持续跟踪
- 当前为线性流水线；多轮追问式分析可升级为带人工干预点的循环架构
