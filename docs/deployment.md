# 部署与运行文档

## 环境要求

- Python 3.10+（开发环境 3.12）
- 可访问外网（可选，无外网时进入缓存/规则降级演示模式）
- 可选：Ollama（本地模型模式，需下载 qwen2.5:7b）
- 可选：DeepSeek / 阿里云百炼 API key（模型驱动模式）

## 安装

```bash
git clone <repo-url>
cd app-store-review-analyzer
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # 国内网络可加 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 配置

```bash
cp .env.example .env
```

| 变量 | 说明 | 默认 |
|---|---|---|
| DEEPSEEK_API_KEY | DeepSeek 官方 API key | 空（未配置则跳过） |
| QWEN_API_KEY | 阿里云百炼 API key（备选模型） | 空 |
| OLLAMA_ENABLED | 是否启用本地 Ollama 兜底 | false |
| LLM_TEMPERATURE | 分析温度（低=稳定） | 0.3 |
| COLLECT_MAX_PAGES | 采集最大页数（每页约 50 条） | 5 |
| COLLECT_RATE_LIMIT_SECONDS | 采集限速（秒/请求） | 2.0 |

**安全说明**：`.env` 已被 `.gitignore` 排除，严禁提交任何密钥到代码仓库。

## 启动

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

浏览器访问 `http://localhost:8000`。

## 使用方式

| 入口 | 说明 |
|---|---|
| 链接分析 | 输入美国区 App Store 链接 + 目标/约束 → 开始分析 |
| 示例数据演示 | 无网/无 key 时使用内置 50 条真实评论缓存跑通全流程 |
| 导入分析 | 上传 JSON/CSV 评论文件，直接启动完整工作流 |
| 导出 | 交付物页「导出 JSON」下载完整运行快照 |

## 无模型/无外网演示（面试场景兜底）

1. **无 API key**：系统自动进入降级模式（规则关键词分类 + 统计结论 + 模板 PRD/用例），UI 顶部徽标显示「降级模式」，所有结论如实标注 `degraded`；
2. **无外网**：实时采集失败自动回退 `data/cache/` 缓存（如 839285684 的 50 条真实评论），快照 `collect_note` 如实标注「实时采集为空，使用缓存」；
3. **命令行演示**：`python -m scripts.demo` 输出全流程摘要。

## 故障排查

| 现象 | 原因与处理 |
|---|---|
| 页面无响应 | 确认 uvicorn 已启动、端口未被占用 |
| 采集 0 条 | 网络无法访问 itunes.apple.com，自动回退缓存并如实标注 |
| 降级模式 | 未配置任何 API key；配置 `.env` 后重启 |
| 导入失败 | 确认文件为规范 JSON（数组或 {reviews:[...]}）或 CSV（review_id,title,body,rating,author,version,updated） |

## 测试

```bash
pytest tests/ -v
```

全部 52 个测试不依赖网络与真实 API key。
