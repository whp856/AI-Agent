# App Store Review Analyzer 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一套可运行的评价分析网页应用：输入美国区 App Store 链接（或导入 JSON/CSV），自动执行「采集→清洗→LLM 动态分类→证据评估→PRD 生成→测试用例生成→追溯校验」8 阶段工作流，UI 实时展示进度与全部交付物。

**Architecture:** FastAPI 后端 + 原生 HTML/JS 单页前端（零构建）+ 自研 Agent 编排器（8 阶段状态机，每阶段 = 确定性工具 + LLM 决策 + 校验回环）。LLM 层用 OpenAI 兼容接口，DeepSeek 主 / Qwen 备 / Ollama 本地兜底 / 规则模式终兜底，降级全程 UI 如实标注。全部运行产出落盘为 JSON 快照，可审查可导出。

**Tech Stack:** Python 3.12, FastAPI, uvicorn, httpx, pandas, pydantic v2, openai(兼容SDK), python-dotenv, pytest

## Global Constraints

- Python >= 3.10（本机 3.12.1）
- 前端零构建步骤：原生 HTML/CSS/JS + Chart.js（CDN 引入，页面内 fallback 文字渲染，无网时也能显示表格）
- 所有 LLM 调用统一走 `LLMClient.chat_json(system, user, schema)` 返回 dict，失败按 provider 顺序降级
- 模型：主 `deepseek-chat`，备 `qwen-plus`，本地 `ollama/qwen2.5:7b`（base_url http://localhost:11434/v1）
- 确定性规则负责：采集、链接解析、清洗、去重、语言检测、统计、追溯校验、输入安全
- LLM 负责：S0 计划解析、S3 动态主题挖掘与合并、S4 推导结论、S5 需求生成、S6 用例生成
- 无任何模型可用时进入规则模式（关键词+统计兜底），产出必须标记 `degraded: rule-based`，UI 显示降级徽标
- 每轮分析产出完整 RunSnapshot JSON 到 `data/runs/{run_id}/`
- 采集限速 ≥2s/请求，最多 5 页，结果缓存 `data/cache/`
- API key 仅环境变量，`.env` 不入库（.gitignore 排除）
- 所有评论 ID 引用必须来自候选列表；S7 校验器检查孤儿引用
- 测试不依赖网络与真实 API key：LLM 用 FakeLLM（固定 JSON 响应），采集用 httpx.MockTransport

---

### Task 1: 项目骨架 + 配置 + 数据契约 + 静态前端

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `backend/models.py`
- Create: `backend/main.py`（仅静态服务 + 健康检查）
- Create: `frontend/index.html`, `frontend/style.css`, `frontend/app.js`（静态版，含完整 UI 布局）
- Test: `tests/test_config.py`, `tests/test_models.py`

**Interfaces:**
- Produces: `config.get_settings() -> Settings`（dataclass: llm_provider, deepseek_api_key, qwen_api_key, ollama_base_url, llm_model, llm_temperature=0.3, llm_max_tokens=4096, llm_timeout=60, llm_max_retries=3, collect_max_pages=5, collect_rate_limit=2.0, min_sample=3）
- Produces: `backend/models.py` 中的 Pydantic 模型：`Review, TopicCluster, Finding, Requirement, TestCase, AnalysisPlan, StageRecord, RunSnapshot, AnalyzeRequest`
- Produces: FastAPI app `backend/main.py`，静态挂载 `/` 指向 frontend

- [ ] **Step 1: 写 requirements.txt**

```
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
pandas>=2.2
pydantic>=2.6
openai>=1.30
python-dotenv>=1.0
pytest>=8.0
```

- [ ] **Step 2: 写 .env.example 与 .gitignore**

```ini
# .env.example
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OLLAMA_BASE_URL=http://localhost:11434/v1
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=4096
LLM_TIMEOUT=60
LLM_MAX_RETRIES=3
COLLECT_MAX_PAGES=5
COLLECT_RATE_LIMIT_SECONDS=2.0
MIN_SAMPLE=3
```

```gitignore
# .gitignore
.env
__pycache__/
*.pyc
.venv/
data/runs/
data/cache/*.json
```

- [ ] **Step 3: 写 backend/config.py**（读 .env，全部带默认值，key 缺失不报错）

```python
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ollama_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    llm_timeout: int = 60
    llm_max_retries: int = 3
    collect_max_pages: int = 5
    collect_rate_limit: float = 2.0
    min_sample: int = 3

def get_settings() -> Settings:
    s = Settings()
    for f in s.__dataclass_fields__:
        v = os.environ.get(f.upper())
        if v is not None and v != "":
            current = getattr(s, f)
            if isinstance(current, bool):
                setattr(s, f, v.lower() in ("1", "true", "yes"))
            elif isinstance(current, int):
                setattr(s, f, int(v))
            elif isinstance(current, float):
                setattr(s, f, float(v))
            else:
                setattr(s, f, v)
    return s
```

- [ ] **Step 4: 写 backend/models.py**（Pydantic 契约，字段与方案书 5.3 一致）

```python
from pydantic import BaseModel, Field
from typing import Optional

class Review(BaseModel):
    review_id: str
    title: str = ""
    body: str = ""
    rating: int = Field(ge=1, le=5)
    author: str = ""
    version: Optional[str] = None
    country: str = "US"
    updated: str = ""
    language: Optional[str] = None
    body_cleaned: str = ""
    dedup_key: str = ""
    is_duplicate: bool = False
    original_ids: list[str] = []
    source: str = "rss"          # rss | import

class TopicCluster(BaseModel):
    topic_id: str
    topic_name: str
    description: str = ""
    member_ids: list[str] = []
    evidence: list[str] = []
    opposing_feedback: list[str] = []
    confidence: str = "medium"   # high|medium|low
    confidence_reason: str = ""

class Finding(BaseModel):
    finding_id: str
    statement: str
    kind: str                    # statistical|model_derived|assumption
    supporting_review_ids: list[str] = []
    sample_count: int = 0
    confidence: str = "medium"
    uncertainty: str = ""
    conflicting_evidence: list[str] = []
    topic_refs: list[str] = []

class Requirement(BaseModel):
    req_id: str
    title: str
    description: str = ""
    priority: str = "P1"         # P0|P1|P2
    version: str = "v8.2"
    rationale: str = ""
    evidence_refs: list[str] = []
    acceptance_criteria: list[str] = []

class TestCase(BaseModel):
    case_id: str
    title: str
    preconditions: str = ""
    steps: list[str] = []
    expected_results: list[str] = []
    req_refs: list[str] = []
    review_refs: list[str] = []

class AnalysisPlan(BaseModel):
    focus_areas: list[str] = []
    constraints: list[dict] = []
    analysis_plan: str = ""
    degraded: bool = False

class StageRecord(BaseModel):
    name: str
    status: str = "pending"      # pending|running|validating|done|failed|degraded|skipped
    started_at: str = ""
    ended_at: str = ""
    summary: str = ""
    error: str = ""
    model_used: str = ""
    retries: int = 0

class AnalyzeRequest(BaseModel):
    url: str = ""
    goal: str = ""
    constraints: list[str] = []
    use_cache_only: bool = False

class RunSnapshot(BaseModel):
    run_id: str
    status: str = "running"      # running|done|failed|degraded
    request: AnalyzeRequest = AnalyzeRequest()
    plan: AnalysisPlan = AnalysisPlan()
    stages: list[StageRecord] = []
    reviews: list[Review] = []
    topics: list[TopicCluster] = []
    findings: list[Finding] = []
    requirements: list[Requirement] = []
    test_cases: list[TestCase] = []
    corrections: list[dict] = []
    validation_report: dict = {}
    meta: dict = {}
    created_at: str = ""
```

- [ ] **Step 5: 写测试 tests/test_config.py 与 tests/test_models.py**

```python
# tests/test_models.py
from backend.models import Review, Finding

def test_review_rating_range():
    r = Review(review_id="1", rating=3)
    assert r.country == "US"

def test_finding_defaults():
    f = Finding(finding_id="F1", statement="s", kind="statistical")
    assert f.confidence == "medium"
    assert f.conflicting_evidence == []
```

- [ ] **Step 6: 写 backend/main.py（静态服务 + 健康检查）**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI(title="App Store Review Analyzer")

@app.get("/api/health")
def health():
    return {"status": "ok"}

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
```

- [ ] **Step 7: 写 frontend/index.html + style.css + app.js 静态版**（完整 UI 布局：输入区、进度面板、交付物 Tabs；app.js 先做页面骨架渲染，API 联调在 Task 9）

- [ ] **Step 8: 运行测试**

```bash
cd app-store-review-analyzer
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
.venv/Scripts/python -m pytest tests/ -v
```

Expected: 2 test files PASS

- [ ] **Step 9: Commit**

```bash
git init
git add -A && git commit -m "feat: project skeleton, config, data models, static frontend"
```

---

### Task 2: 采集模块（链接解析 + iTunes RSS + 缓存）

**Files:**
- Create: `backend/tools/__init__.py`
- Create: `backend/tools/collector.py`
- Create: `scripts/__init__.py`
- Create: `scripts/fetch_cache.py`
- Test: `tests/test_collector.py`

**Interfaces:**
- Consumes: `Review` (models.py), `Settings` (config.py)
- Produces:
  - `parse_appstore_url(url: str) -> dict` → `{"app_id": "839285684", "country": "us"}`，非法抛 `ValueError`
  - `fetch_reviews(app_id: str, max_pages: int = 5, rate_limit: float = 2.0, client: httpx.Client | None = None) -> list[Review]`
  - `load_cache(app_id: str) -> list[Review] | None`
  - `save_cache(app_id: str, reviews: list[Review]) -> str`（返回缓存路径）
  - `cache_dir()` → 项目 `data/cache` 路径

- [ ] **Step 1: 写失败测试 tests/test_collector.py**

```python
import httpx
from backend.tools.collector import parse_appstore_url, fetch_reviews

def test_parse_valid_url():
    info = parse_appstore_url("https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684")
    assert info["app_id"] == "839285684"
    assert info["country"] == "us"

def test_parse_invalid_url():
    import pytest
    with pytest.raises(ValueError):
        parse_appstore_url("https://evil.com/not-an-app")

def test_fetch_reviews_mock():
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://itunes.apple.com/WebObjects/MZStore.woa/wa/viewContentsUserReviews?id=1&pageNumber=0&sortBying=0&type=Purple+Software</id>
        <title>Great app</title>
        <content type="text">I love it!</content>
        <im:rating xmlns:im="http://itunes.apple.com/rss">5</im:rating>
        <author><name>Alice</name></author>
        <updated>2026-08-01T10:00:00-07:00</updated>
        <im:version xmlns:im="http://itunes.apple.com/rss">8.4</im:version>
      </entry>
    </feed>"""
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=rss_xml))
    with httpx.Client(transport=transport) as client:
        reviews = fetch_reviews("839285684", max_pages=1, rate_limit=0, client=client)
    assert len(reviews) == 1
    assert reviews[0].rating == 5
    assert reviews[0].body == "I love it!"
```

- [ ] **Step 2: 运行确认失败**：`pytest tests/test_collector.py -v` → FAIL (module not found)

- [ ] **Step 3: 实现 backend/tools/collector.py**

```python
import json, re, time, uuid
from pathlib import Path
import httpx
from ..models import Review

APP_ID_RE = re.compile(r"id(\d{5,10})")
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"

def parse_appstore_url(url: str) -> dict:
    if "apps.apple.com" not in url:
        raise ValueError("仅支持 apps.apple.com 链接")
    m = APP_ID_RE.search(url)
    if not m:
        raise ValueError("链接中未找到 appId")
    country = "us"
    cm = re.search(r"apps\.apple\.com/([a-z]{2})/", url)
    if cm:
        country = cm.group(1)
    return {"app_id": m.group(1), "country": country}

def _parse_rss_entry(e: dict) -> Review:
    # entry 为 lxml/ElementTree 解析后的简化 dict 或直接由 xmltodict 风格键访问
    # 这里用标准库 xml.etree 解析，见下方 fetch 实现
    ...

def fetch_reviews(app_id, max_pages=5, rate_limit=2.0, client=None) -> list[Review]:
    import xml.etree.ElementTree as ET
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "im": "http://itunes.apple.com/rss",
    }
    own_client = client is None
    client = client or httpx.Client(timeout=15, headers={"User-Agent": "ReviewAnalyzer/1.0 (educational)"})
    reviews, seen = [], set()
    try:
        for page in range(1, max_pages + 1):
            url = f"https://itunes.apple.com/rss/customerreviews/page={page}/id={app_id}/sortBy=mostRecent/json"
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except Exception:
                break  # 网络失败/404 → 停止分页
            data = resp.json()
            entries = data.get("feed", {}).get("entry", [])
            if isinstance(entries, dict):   # 单条时是 dict
                entries = [entries]
            if not entries:
                break
            for e in entries:
                rid = e.get("id", {}).get("label", uuid.uuid4().hex)
                rid = rid.split("?")[0] or rid
                rating = int(e.get("im:rating", {}).get("label", "0") or 0)
                rev = Review(
                    review_id=rid, title=e.get("title", {}).get("label", ""),
                    body=e.get("content", {}).get("label", ""), rating=rating,
                    author=e.get("author", {}).get("name", {}).get("label", ""),
                    version=e.get("im:version", {}).get("label", ""),
                    updated=e.get("updated", {}).get("label", ""),
                    source="rss",
                )
                if rev.review_id in seen:
                    continue
                seen.add(rev.review_id)
                reviews.append(rev)
            if rate_limit > 0:
                time.sleep(rate_limit)
    finally:
        if own_client and client:
            client.close()
    return reviews

def cache_path(app_id: str) -> Path:
    return CACHE_DIR / f"{app_id}.json"

def load_cache(app_id: str) -> list[Review] | None:
    p = cache_path(app_id)
    if p.exists():
        return [Review(**r) for r in json.loads(p.read_text(encoding="utf-8"))]
    return None

def save_cache(app_id: str, reviews: list[Review]) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = cache_path(app_id)
    p.write_text(json.dumps([r.model_dump() for r in reviews], ensure_ascii=False, indent=1), encoding="utf-8")
    return str(p)
```

- [ ] **Step 4: 写 scripts/fetch_cache.py**（预取缓存脚本，支持 `python -m scripts.fetch_cache 839285684`）

```python
# scripts/fetch_cache.py
import sys
from backend.tools.collector import fetch_reviews, save_cache, parse_appstore_url

def main():
    app_id = sys.argv[1] if len(sys.argv) > 1 else "839285684"
    reviews = fetch_reviews(app_id)
    path = save_cache(app_id, reviews)
    print(f"cached {len(reviews)} reviews -> {path}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行测试**：`pytest tests/test_collector.py -v` → PASS
- [ ] **Step 6: 尝试真实采集生成缓存**（网络可用时）

```bash
.venv/Scripts/python -m scripts.fetch_cache 839285684
```

网络不可用时跳过（不影响测试，缓存由 Task 9 的 samples 兜底）。

- [ ] **Step 7: Commit**：`git add -A && git commit -m "feat: iTunes RSS collector with cache"`

---

### Task 3: 清洗模块（cleaner）

**Files:**
- Create: `backend/tools/cleaner.py`
- Test: `tests/test_cleaner.py`

**Interfaces:**
- Consumes: `Review` (models.py)
- Produces: `clean_reviews(reviews: list[Review]) -> tuple[list[Review], list[dict]]`（清洗后列表 + 清洗日志，日志项 `{"step": str, "count": int, "note": str}`）
- Produces: `detect_language(text: str) -> str | None`（"zh"/"en"/"ja"/"ko"/"ru"/"ar"/"es"/"fr"/"de"/"pt"/"it"/"unknown"）

- [ ] **Step 1: 写失败测试 tests/test_cleaner.py**

```python
from backend.models import Review
from backend.tools.cleaner import clean_reviews, detect_language

def _rev(rid, body, rating=4):
    return Review(review_id=rid, body=body, rating=rating, author="a")

def test_html_decode_and_norm():
    out, log = clean_reviews([_rev("1", "Great&amp; nice  app\n\nExtra")])
    assert "&" in out[0].body_cleaned and "  " not in out[0].body_cleaned

def test_dedup():
    out, log = clean_reviews([_rev("1", "same text"), _rev("2", "same text")])
    assert len([r for r in out if not r.is_duplicate]) == 1

def test_empty_body_filtered():
    out, log = clean_reviews([_rev("1", "   ")])
    assert len(out) == 0
    assert any(x["step"] == "empty_filter" for x in log)

def test_language_detection():
    assert detect_language("这款应用很好用") == "zh"
    assert detect_language("This app is great") == "en"
    assert detect_language("Прекрасное приложение") == "ru"
    assert detect_language("") == "unknown"
```

- [ ] **Step 2: 运行确认失败** → FAIL
- [ ] **Step 3: 实现 backend/tools/cleaner.py**

```python
import hashlib, re, html
from ..models import Review

_WS = re.compile(r"\s+")
_LANG_RANGES = [
    ("zh", [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)]),
    ("ja", [(0x3040, 0x30FF)]),
    ("ko", [(0xAC00, 0xD7AF)]),
    ("ru", [(0x0400, 0x04FF)]),
    ("ar", [(0x0600, 0x06FF)]),
    ("el", [(0x0370, 0x03FF)]),
    ("th", [(0x0E00, 0x0E7F)]),
]

def detect_language(text: str) -> str | None:
    if not text or not text.strip():
        return "unknown"
    scores = {lang: 0 for lang, _ in _LANG_RANGES}
    for ch in text:
        cp = ord(ch)
        for lang, ranges in _LANG_RANGES:
            for lo, hi in ranges:
                if lo <= cp <= hi:
                    scores[lang] += 1
    if any(v > 0 for v in scores.values()):
        top = max(scores, key=scores.get)
        return top if scores[top] >= 2 else "unknown"
    if re.search(r"[a-zA-Z]", text):
        return "en"
    return "unknown"

def clean_reviews(reviews: list[Review]) -> tuple[list[Review], list[dict]]:
    log: list[dict] = []
    out: list[Review] = []
    seen: dict[str, str] = {}   # dedup_key -> review_id
    for r in reviews:
        body = html.unescape(r.body or "")
        body = _WS.sub(" ", body).strip()
        if not body:
            log.append({"step": "empty_filter", "count": 1, "note": r.review_id})
            continue
        title = _WS.sub(" ", html.unescape(r.title or "")).strip()
        lang = detect_language(body)
        rating = int(r.rating) if 1 <= int(r.rating) <= 5 else 0
        key = hashlib.md5(f"{r.author}|{body}|{rating}".encode()).hexdigest()
        if key in seen:
            # 重复：保留先出现的，合并 original_ids
            for o in out:
                if o.dedup_key == key:
                    o.original_ids.append(r.review_id)
                    break
            log.append({"step": "dedup", "count": 1, "note": f"{r.review_id}->{seen[key]}"})
            r2 = r.model_copy(deep=True)
            r2.is_duplicate = True
            r2.dedup_key = key
            out.append(r2)
            continue
        seen[key] = r.review_id
        r.body_cleaned = body
        r.title = title
        r.language = lang
        r.dedup_key = key
        r.rating = rating if rating > 0 else 3
        out.append(r)
    return out, log
```

- [ ] **Step 4: 运行测试确认 PASS**
- [ ] **Step 5: Commit**：`git commit -am "feat: review cleaning, dedup, language detection"`

---

### Task 4: LLM 客户端 + 分级降级

**Files:**
- Create: `backend/llm/__init__.py`
- Create: `backend/llm/client.py`
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: `Settings` (config.py)
- Produces:
  - `class LLMClient`: `__init__(settings: Settings)`；`available: bool`；`mode: str`（"deepseek"/"qwen"/"ollama"/"none"）；`chat_json(system: str, user: str, example: dict) -> dict | None`（None = 全部 provider 失败）
  - `class FakeLLM(LLMClient)`: `__init__(responses: list[dict])`，按调用次数顺序返回固定响应（测试用）
- 降级顺序：deepseek → qwen → ollama（依次尝试，任一成功即返回）；全失败返回 None
- 内部：每 provider 重试 `llm_max_retries` 次，指数退避 1s/2s/4s，超时 `llm_timeout`

- [ ] **Step 1: 写失败测试 tests/test_llm_client.py**

```python
import pytest
from backend.config import Settings
from backend.llm.client import LLMClient, FakeLLM

def test_fake_llm_returns_responses():
    llm = FakeLLM([{"topics": [{"topic_id": "T1"}]}])
    out = llm.chat_json("sys", "user", {})
    assert out["topics"][0]["topic_id"] == "T1"

def test_fake_llm_exhausts_to_none():
    llm = FakeLLM([])
    assert llm.chat_json("s", "u", {}) is None

def test_no_key_means_unavailable():
    s = Settings(deepseek_api_key="", qwen_api_key="")
    llm = LLMClient(s)
    assert llm.available is False
    assert llm.mode == "none"
    assert llm.chat_json("s", "u", {}) is None
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 backend/llm/client.py**

```python
import time, json
from openai import OpenAI
from ..config import Settings

class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mode = "none"
        self._clients: list[tuple[str, OpenAI | None]] = []
        if settings.deepseek_api_key:
            self._clients.append(("deepseek", OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url, timeout=settings.llm_timeout)))
            self.mode = "deepseek"
        if settings.qwen_api_key:
            self._clients.append(("qwen", OpenAI(
                api_key=settings.qwen_api_key,
                base_url=settings.qwen_base_url, timeout=settings.llm_timeout)))
            if self.mode == "none":
                self.mode = "qwen"
        if settings.ollama_base_url:
            self._clients.append(("ollama", OpenAI(
                api_key="ollama", base_url=settings.ollama_base_url, timeout=settings.llm_timeout)))
            if self.mode == "none":
                self.mode = "ollama"
        self.available = bool(self._clients)

    def _try_call(self, provider: str, client: OpenAI, model: str, system: str, user: str) -> dict | None:
        for attempt in range(self.settings.llm_max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                text = resp.choices[0].message.content
                return json.loads(text)
            except Exception:
                if attempt < self.settings.llm_max_retries:
                    time.sleep(2 ** attempt)
        return None

    def chat_json(self, system: str, user: str, example: dict) -> dict | None:
        if not self._clients:
            return None
        last = None
        for provider, client in self._clients:
            model = self.settings.llm_model
            if provider == "qwen":
                model = "qwen-plus"
            if provider == "ollama":
                model = "qwen2.5:7b"
            last = self._try_call(provider, client, model, system, user)
            if last is not None:
                self.mode = provider
                return last
        return None

class FakeLLM(LLMClient):
    """测试用：按序返回固定响应，用完返回 None"""
    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.mode = "fake"
        self.available = True

    def chat_json(self, system, user, example):
        if not self._responses:
            return None
        return self._responses.pop(0)
```

- [ ] **Step 4: 运行测试确认 PASS**
- [ ] **Step 5: Commit**：`git commit -am "feat: LLM client with provider fallback"`

---

### Task 5: S0 计划解析 + S3 动态分类（LLM + 规则兜底）

**Files:**
- Create: `backend/workflow/__init__.py`
- Create: `backend/workflow/stage_base.py`
- Create: `backend/workflow/s0_plan.py`
- Create: `backend/workflow/s3_classify.py`
- Create: `backend/llm/prompts/s0.txt`, `backend/llm/prompts/s3_classify.txt`, `backend/llm/prompts/s3_merge.txt`
- Test: `tests/test_s3_classify.py`

**Interfaces:**
- Consumes: `AnalysisPlan, TopicCluster, Review, RunSnapshot`；`LLMClient/FakeLLM`
- Produces:
  - `class StageBase`: `name`；`run(ctx: dict) -> None`（ctx 含 `snapshot`, `llm`, `on_event`, `model_mode`）
  - `s0_plan.run(ctx)`：无 LLM → 默认计划（degraded=True）；有 LLM → 调 A1 提示词，解析 AnalysisPlan
  - `s3_classify.run(ctx)`：分批 ≤40 条 → 分类 → 主题合并 → 去重/重编号；无 LLM → 关键词+统计兜底（topic 标记 degraded）
  - `classify_with_llm(reviews, plan, llm) -> list[TopicCluster]`（可单测）
  - `keyword_fallback_topics(reviews) -> list[TopicCluster]`（兜底）
  - 事件：`on_event({"type": "stage.progress", "stage": "s3", "data": {...}})`

- [ ] **Step 1: 写测试 tests/test_s3_classify.py**（FakeLLM 返回两批主题，验证成员 ID 校验与合并）

```python
from backend.models import Review, AnalysisPlan
from backend.llm.client import FakeLLM
from backend.workflow.s3_classify import classify_with_llm, keyword_fallback_topics

def _reviews(n=5):
    return [Review(review_id=f"r{i}", body=f"评论内容 {i}", rating=1 if i % 2 else 5) for i in range(n)]

def test_classify_with_llm_merges_and_validates():
    llm = FakeLLM([
        # 批次1响应
        {"topics": [
            {"topic_id": "T1", "topic_name": "订阅问题", "member_ids": ["r0", "r1"],
             "evidence": ["评论内容 0"], "opposing_feedback": [], "confidence": "high",
             "confidence_reason": "n=2"}]},
        # 批次2响应
        {"topics": [
            {"topic_id": "T1", "topic_name": "订阅问题", "member_ids": ["r2"],
             "evidence": ["评论内容 2"], "opposing_feedback": [], "confidence": "medium",
             "confidence_reason": "n=1"}]},
        # 合并响应
        {"topics": [
            {"topic_id": "T1", "topic_name": "订阅问题", "member_ids": ["r0", "r1", "r2"],
             "evidence": ["评论内容 0"], "opposing_feedback": [], "confidence": "high",
             "confidence_reason": "n=3"}],
         "merge_log": [{"merged": ["T1", "T1"], "into": "T1", "reason": "same"}]},
    ])
    topics = classify_with_llm(_reviews(), AnalysisPlan(), llm)
    assert len(topics) == 1
    assert set(topics[0].member_ids) == {"r0", "r1", "r2"}
    # 非法 ID 被过滤
    assert all(m in {"r0", "r1", "r2"} for t in topics for m in t.member_ids)

def test_keyword_fallback():
    reviews = _reviews()
    reviews[0].body_cleaned = "subscription charged twice, refund please"
    topics = keyword_fallback_topics(reviews)
    assert any("subscri" in t.topic_name.lower() or "subscription" in t.topic_name.lower() for t in topics)
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 写提示词文件**（内容取自方案书附录 A1/A2，写入 `backend/llm/prompts/*.txt`，通过 `{placeholders}` format 填充）

- [ ] **Step 4: 实现 backend/workflow/stage_base.py**

```python
class StageBase:
    name = "stage"
    def __init__(self, ctx: dict):
        self.ctx = ctx
        self.snapshot = ctx["snapshot"]
        self.llm = ctx["llm"]
        self.on_event = ctx["on_event"]
        self.mode = ctx["model_mode"]   # "llm" | "degraded"

    def emit(self, etype, data):
        self.on_event({"type": etype, "stage": self.name, "data": data})

    def find_stage(self, name):
        for s in self.snapshot.stages:
            if s.name == name:
                return s
        return None

    def stage(self, name):
        return self.find_stage(name)
```

- [ ] **Step 5: 实现 s0_plan.py**

```python
import json
from pathlib import Path
from .stage_base import StageBase
from ..models import AnalysisPlan

PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"

class S0Plan(StageBase):
    name = "s0"
    def run(self):
        rec = self.stage("s0")
        rec.status = "running"
        try:
            if self.mode == "degraded" or not self.llm.available:
                self.snapshot.plan = AnalysisPlan(degraded=True)
                rec.status = "degraded"
                rec.summary = "无模型可用，使用默认分析计划"
                self.emit("stage.output", {"plan": self.snapshot.plan.model_dump()})
                return
            system = "你是产品分析系统的规划模块。将分析目标解析为结构化计划。只输出 JSON。"
            user = (PROMPT_DIR / "s0.txt").read_text(encoding="utf-8").format(
                analysis_goal=self.snapshot.request.goal or "(未指定，使用通用分析)",
                constraints=json.dumps(self.snapshot.request.constraints, ensure_ascii=False),
            )
            data = self.llm.chat_json(system, user, {})
            if data:
                self.snapshot.plan = AnalysisPlan(
                    focus_areas=data.get("focus_areas", []),
                    constraints=data.get("constraints", []),
                    analysis_plan=data.get("analysis_plan", ""),
                )
                rec.summary = f"计划: {self.snapshot.plan.analysis_plan}"
            else:
                self.snapshot.plan = AnalysisPlan(degraded=True)
                rec.status = "degraded"
            self.emit("stage.output", {"plan": self.snapshot.plan.model_dump()})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        rec.status = rec.status if rec.status != "running" else "done"
```

- [ ] **Step 6: 实现 s3_classify.py**（核心：分批调用、ID 校验、合并、兜底）

```python
import json
from .stage_base import StageBase
from ..models import TopicCluster, AnalysisPlan
from ..tools.cleaner import detect_language

KEYWORDS = {
    "subscription / 订阅付费": ["subscri", "订阅", "payment", "charge", "退款", "refund", "price", "价格", "free trial", "试用"],
    "bug / 故障": ["bug", "crash", "闪退", "崩溃", "freeze", "卡", "error", "failed", "not working", "无法", "白屏"],
    "usability / 易用性": ["hard to use", "confusing", "不好用", "复杂", "difficult", "easy to", "难用", "界面"],
    "update / 更新问题": ["update", "更新", "new version", "最新版", "broke", "变差"],
    "ads / 广告": ["ad", "广告", "popup", "弹窗"],
    "data loss / 数据丢失": ["lost", "丢失", "data", "进度", "progress", "disappear", "消失"],
}

def _batch(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]

def classify_with_llm(reviews, plan: AnalysisPlan, llm) -> list[TopicCluster]:
    valid_ids = {r.review_id for r in reviews}
    prompts_dir = Path(__file__).resolve().parent.parent / "llm" / "prompts"
    sys_cls = "你是资深产品分析师。从评论中自行归纳语义主题，只输出 JSON。"
    batches = list(_batch(reviews, 40))
    batch_topics: list[dict] = []
    for b in batches:
        items = json.dumps(
            [{"review_id": r.review_id, "rating": r.rating, "body": (r.body_cleaned or r.body)[:500]}
             for r in b], ensure_ascii=False)
        user = (prompts_dir / "s3_classify.txt").read_text(encoding="utf-8").format(
            app_name="(应用)", n=len(b), analysis_goal=plan.analysis_plan or "通用",
            constraints=json.dumps(plan.constraints, ensure_ascii=False), comments=items)
        data = llm.chat_json(sys_cls, user, {"topics": []})
        if data and isinstance(data.get("topics"), list):
            batch_topics.extend(data["topics"])
    if not batch_topics:
        return []
    # 合并
    sys_merge = "你是产品分析师。合并语义相似的主题，只输出 JSON。"
    user_merge = (prompts_dir / "s3_merge.txt").read_text(encoding="utf-8").format(
        topics=json.dumps(batch_topics, ensure_ascii=False))
    merged = llm.chat_json(sys_merge, user_merge, {"topics": []})
    raw = merged.get("topics", batch_topics) if merged else batch_topics
    topics: list[TopicCluster] = []
    for i, t in enumerate(raw):
        members = [m for m in t.get("member_ids", []) if m in valid_ids]
        if not members:
            continue
        topics.append(TopicCluster(
            topic_id=f"T{i+1}", topic_name=t.get("topic_name", "未命名主题"),
            description=t.get("description", ""), member_ids=members,
            evidence=t.get("evidence", [])[:3],
            opposing_feedback=t.get("opposing_feedback", [])[:3],
            confidence=t.get("confidence", "medium") if t.get("confidence") in ("high", "medium", "low") else "medium",
            confidence_reason=t.get("confidence_reason", ""),
        ))
    return topics

def keyword_fallback_topics(reviews) -> list[TopicCluster]:
    clusters: dict[str, list[Review]] = {}
    for r in reviews:
        text = (r.body_cleaned or r.body).lower()
        for label, kws in KEYWORDS.items():
            if any(k in text for k in kws):
                clusters.setdefault(label, []).append(r)
    topics = []
    for i, (label, members) in enumerate(clusters.items()):
        topics.append(TopicCluster(
            topic_id=f"T{i+1}", topic_name=label,
            member_ids=[m.review_id for m in members],
            evidence=[(m.body_cleaned or m.body)[:120] for m in members[:3]],
            confidence="low", confidence_reason="degraded: rule-based",
        ))
    return topics

class S3Classify(StageBase):
    name = "s3"
    def run(self):
        rec = self.stage("s3")
        rec.status = "running"
        active = [r for r in self.snapshot.reviews if not r.is_duplicate]
        try:
            if self.mode == "llm" and self.llm.available:
                self.snapshot.topics = classify_with_llm(active, self.snapshot.plan, self.llm)
                rec.model_used = self.llm.mode
                if not self.snapshot.topics:
                    rec.summary = "模型未产出有效主题，使用规则兜底"
                    self.snapshot.topics = keyword_fallback_topics(active)
                    rec.status = "degraded"
                else:
                    rec.summary = f"模型归纳 {len(self.snapshot.topics)} 个主题"
            else:
                self.snapshot.topics = keyword_fallback_topics(active)
                rec.status = "degraded"
                rec.summary = "降级模式：规则主题（非语义）"
            self.emit("stage.output", {"topics": [t.model_dump() for t in self.snapshot.topics]})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        rec.status = rec.status if rec.status != "running" else "done"
```

- [ ] **Step 7: 运行测试确认 PASS**
- [ ] **Step 8: Commit**：`git commit -am "feat: S0 plan + S3 LLM dynamic classification with fallback"`

---

### Task 6: S4 证据评估（stats + LLM 推导）

**Files:**
- Create: `backend/tools/stats.py`
- Create: `backend/workflow/s4_findings.py`
- Test: `tests/test_stats.py`, `tests/test_s4_findings.py`

**Interfaces:**
- Consumes: `TopicCluster, Finding, Review, AnalysisPlan`；`LLMClient`
- Produces:
  - `topic_stats(topics, reviews) -> list[dict]`（每主题：count, ratio, avg_rating, low_ratio, versions, sample_language 覆盖）
  - `rating_distribution(reviews) -> dict`
  - `version_stats(reviews) -> dict`
  - `s4_findings.run(ctx)`：统计 finding（statistical，程序生成）+ LLM 推导 finding（model_derived/assumption）+ 交叉验证标注；无 LLM → 仅统计 finding + 标注 degraded

- [ ] **Step 1: 写测试**

```python
# tests/test_stats.py
from backend.models import Review, TopicCluster
from backend.tools.stats import topic_stats, rating_distribution

def _reviews():
    return [
        Review(review_id=f"r{i}", body=f"b{i}", rating=1 if i < 3 else 5, version="8.4" if i < 4 else "8.5")
        for i in range(6)
    ]

def test_rating_distribution():
    d = rating_distribution(_reviews())
    assert d["low"] == 3 and d["high"] == 3

def test_topic_stats():
    reviews = _reviews()
    t = TopicCluster(topic_id="T1", topic_name="x", member_ids=["r0", "r1", "r2"])
    stats = topic_stats([t], reviews)
    assert stats[0]["count"] == 3
    assert stats[0]["avg_rating"] == 1.0
```

```python
# tests/test_s4_findings.py
from backend.models import Review, TopicCluster, AnalysisPlan
from backend.workflow.s4_findings import build_statistical_findings

def test_statistical_findings_have_kind():
    reviews = [Review(review_id=f"r{i}", body=f"b{i}", rating=1 if i < 3 else 5) for i in range(6)]
    t = TopicCluster(topic_id="T1", topic_name="订阅", member_ids=["r0", "r1", "r2"])
    findings = build_statistical_findings([t], reviews, min_sample=3)
    assert all(f.kind == "statistical" for f in findings)
    assert all(f.sample_count >= 3 for f in findings if f.finding_id.startswith("T"))
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 backend/tools/stats.py**

```python
from ..models import Review, TopicCluster

def rating_distribution(reviews: list[Review]) -> dict:
    n = max(len(reviews), 1)
    low = sum(1 for r in reviews if r.rating <= 2)
    mid = sum(1 for r in reviews if r.rating == 3)
    high = sum(1 for r in reviews if r.rating >= 4)
    return {"total": len(reviews), "low": low, "mid": mid, "high": high,
            "low_ratio": round(low / n, 2), "avg_rating": round(sum(r.rating for r in reviews) / n, 2)}

def version_stats(reviews: list[Review]) -> dict:
    from collections import Counter
    c = Counter((r.version or "unknown") for r in reviews)
    return dict(c.most_common(10))

def topic_stats(topics: list[TopicCluster], reviews: list[Review]) -> list[dict]:
    by_id = {r.review_id: r for r in reviews}
    out = []
    for t in topics:
        members = [by_id[m] for m in t.member_ids if m in by_id]
        if not members:
            continue
        n = len(members)
        low = sum(1 for m in members if m.rating <= 2)
        langs = {}
        for m in members:
            langs[m.language or "unknown"] = langs.get(m.language or "unknown", 0) + 1
        versions = {}
        for m in members:
            v = m.version or "unknown"
            versions[v] = versions.get(v, 0) + 1
        out.append({
            "topic_id": t.topic_id, "topic_name": t.topic_name, "count": n,
            "ratio": round(n / max(len(reviews), 1), 2),
            "avg_rating": round(sum(m.rating for m in members) / n, 2),
            "low_ratio": round(low / n, 2),
            "languages": langs, "versions": versions,
        })
    return out
```

- [ ] **Step 4: 实现 backend/workflow/s4_findings.py**

```python
import json
from pathlib import Path
from .stage_base import StageBase
from ..models import Finding
from ..tools.stats import topic_stats, rating_distribution, version_stats

def build_statistical_findings(topics, reviews, min_sample=3) -> list[Finding]:
    stats = topic_stats(topics, reviews)
    findings = []
    for s in stats:
        if s["count"] < min_sample:
            findings.append(Finding(
                finding_id=f"F-{s['topic_id']}-a", kind="assumption",
                statement=f"主题『{s['topic_name']}』样本仅 {s['count']} 条，不足以下结论（假设）",
                supporting_review_ids=s["member_ids"], sample_count=s["count"],
                confidence="low", uncertainty="样本量不足", topic_refs=[s["topic_id"]]))
            continue
        findings.append(Finding(
            finding_id=f"F-{s['topic_id']}-s", kind="statistical",
            statement=f"主题『{s['topic_name']}』共 {s['count']} 条评论，平均评分 {s['avg_rating']}，低分占比 {s['low_ratio']}",
            supporting_review_ids=s["member_ids"], sample_count=s["count"],
            confidence="high" if s["count"] >= 10 else "medium",
            uncertainty=f"数据窗口为最近评论，样本 n={s['count']}",
            topic_refs=[s["topic_id"]]))
    return findings

class S4Findings(StageBase):
    name = "s4"
    def run(self):
        rec = self.stage("s4")
        rec.status = "running"
        active = [r for r in self.snapshot.reviews if not r.is_duplicate]
        try:
            stats_f = build_statistical_findings(self.snapshot.topics, active,
                                                 self.snapshot.meta.get("min_sample", 3))
            self.snapshot.findings = stats_f
            self.emit("stage.output", {"stats": {
                "rating": rating_distribution(active),
                "versions": version_stats(active),
                "topics": topic_stats(self.snapshot.topics, active)}})
            if self.mode == "llm" and self.llm.available and self.snapshot.topics:
                derived = self._llm_derive(active)
                self.snapshot.findings.extend(derived)
                rec.model_used = self.llm.mode
                rec.summary = f"统计结论 {len(stats_f)} 条 + 模型推导 {len(derived)} 条"
            else:
                rec.status = "degraded" if self.snapshot.topics else rec.status
                rec.summary = "降级模式：仅统计结论"
            self.emit("stage.output", {"findings": [f.model_dump() for f in self.snapshot.findings]})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        rec.status = rec.status if rec.status != "running" else "done"

    def _llm_derive(self, active):
        from ..tools.stats import topic_stats, rating_distribution, version_stats
        stats = {
            "topic_stats": topic_stats(self.snapshot.topics, active),
            "rating": rating_distribution(active),
            "versions": version_stats(active),
        }
        topics = [t.model_dump() for t in self.snapshot.topics]
        prompts_dir = Path(__file__).resolve().parent.parent / "llm" / "prompts"
        user = (prompts_dir / "s4_findings.txt").read_text(encoding="utf-8").format(
            stats_json=json.dumps(stats, ensure_ascii=False),
            topics_json=json.dumps(topics, ensure_ascii=False),
            analysis_goal=self.snapshot.plan.analysis_plan or "通用",
            min_sample=self.snapshot.meta.get("min_sample", 3))
        data = self.llm.chat_json("你是严谨的产品分析师。基于证据产出结论，只输出 JSON。", user, {"findings": []})
        out = []
        if not data or not isinstance(data.get("findings"), list):
            return out
        valid = {r.review_id for r in active}
        for i, f in enumerate(data["findings"]):
            kind = f.get("kind") if f.get("kind") in ("statistical", "model_derived", "assumption") else "model_derived"
            members = [m for m in f.get("supporting_review_ids", []) if m in valid]
            conf = f.get("confidence") if f.get("confidence") in ("high", "medium", "low") else "medium"
            out.append(Finding(
                finding_id=f"F-{len(self.snapshot.findings) + i + 1}-m", kind=kind,
                statement=f.get("statement", ""), supporting_review_ids=members,
                sample_count=len(members),
                confidence=conf, uncertainty=f.get("uncertainty", ""),
                conflicting_evidence=f.get("conflicting_evidence", [])[:3],
                topic_refs=f.get("topic_refs", [])))
        return out
```

- [ ] **Step 5: 写 s4_findings.txt 提示词**（取自方案书附录 A3）
- [ ] **Step 6: 运行测试确认 PASS**
- [ ] **Step 7: Commit**：`git commit -am "feat: S4 evidence evaluation with stats + LLM derivation"`

---

### Task 7: S5 PRD 生成

**Files:**
- Create: `backend/workflow/s5_prd.py`
- Create: `backend/llm/prompts/s5_prd.txt`
- Test: `tests/test_s5_prd.py`

**Interfaces:**
- Consumes: `Finding, Requirement, RunSnapshot`；`LLMClient`
- Produces: `s5_prd.run(ctx)`；`build_requirements_with_llm(findings, llm, meta) -> list[Requirement]`（可单测）；`priority_from_stats(finding) -> str`（规则定初值）
- 硬约束：需求 evidence_refs 必须含真实 Finding ID 与 Review ID；无 LLM → 从统计 finding 生成模板需求（标记 degraded）

- [ ] **Step 1: 写测试**

```python
from backend.models import Finding
from backend.llm.client import FakeLLM
from backend.workflow.s5_prd import build_requirements_with_llm

def _findings():
    return [
        Finding(finding_id="F-T1-s", kind="statistical",
                statement="订阅主题 12 条评论均分 1.5",
                supporting_review_ids=["r0", "r1"], sample_count=12,
                confidence="high", topic_refs=["T1"]),
    ]

def test_prd_with_llm_keeps_valid_refs():
    llm = FakeLLM([{"requirements": [
        {"req_id": "PRD-1", "title": "修复订阅支付失败", "description": "d",
         "priority": "P0", "version": "v8.1", "rationale": "r",
         "evidence_refs": ["F-T1-s", "r0", "r1", "FAKE-ID"],   # 含孤儿引用
         "acceptance_criteria": ["c1"]}]}])
    reqs = build_requirements_with_llm(_findings(), llm, {"valid_review_ids": ["r0", "r1"]})
    assert len(reqs) == 1
    assert "FAKE-ID" not in reqs[0].evidence_refs
    assert reqs[0].evidence_refs == ["F-T1-s", "r0", "r1"]
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 s5_prd.py**

```python
import json
from pathlib import Path
from .stage_base import StageBase
from ..models import Requirement

def priority_from_stats(f: Finding) -> str:
    if f.sample_count >= 10 and f.kind == "statistical":
        return "P0"
    if f.sample_count >= 5:
        return "P1"
    return "P2"

def build_requirements_with_llm(findings, llm, meta) -> list[Requirement]:
    valid_f = {x.finding_id for x in findings}
    valid_r = set(meta.get("valid_review_ids", []))
    prompts_dir = Path(__file__).resolve().parent.parent / "llm" / "prompts"
    user = (prompts_dir / "s5_prd.txt").read_text(encoding="utf-8").format(
        findings_json=json.dumps([f.model_dump() for f in findings], ensure_ascii=False),
        app_name=meta.get("app_name", "(应用)"),
        version_stats=json.dumps(meta.get("version_stats", {}), ensure_ascii=False))
    data = llm.chat_json("你是资深产品经理。基于已验证结论撰写 PRD 需求，只输出 JSON。", user, {"requirements": []})
    out = []
    if not data or not isinstance(data.get("requirements"), list):
        return out
    for i, r in enumerate(data["requirements"]):
        refs = [x for x in r.get("evidence_refs", []) if x in valid_f or x in valid_r]
        if not refs or not any(x in valid_f for x in refs):
            continue   # 无有效证据引用 → 丢弃
        pri = r.get("priority") if r.get("priority") in ("P0", "P1", "P2") else "P1"
        ver = r.get("version") if r.get("version") in ("v8.1", "v8.2", "v9.0") else "v8.2"
        out.append(Requirement(
            req_id=f"PRD-{i+1}", title=r.get("title", "未命名需求"),
            description=r.get("description", ""), priority=pri, version=ver,
            rationale=r.get("rationale", ""), evidence_refs=refs,
            acceptance_criteria=r.get("acceptance_criteria", [])[:8]))
    return out

def fallback_requirements(findings) -> list[Requirement]:
    out = []
    for i, f in enumerate([x for x in findings if x.kind != "assumption"][:6]):
        out.append(Requirement(
            req_id=f"PRD-{i+1}",
            title=f"改进『{f.statement[:40]}』", description="降级模式生成，请结合人工判断",
            priority=priority_from_stats(f), version="v8.2",
            rationale="degraded: rule-based", evidence_refs=[f.finding_id] + f.supporting_review_ids[:5],
            acceptance_criteria=["验证相关评论问题得到解决"]))
    return out

class S5PRD(StageBase):
    name = "s5"
    def run(self):
        rec = self.stage("s5")
        rec.status = "running"
        try:
            if self.mode == "llm" and self.llm.available and self.snapshot.findings:
                self.snapshot.requirements = build_requirements_with_llm(
                    self.snapshot.findings, self.llm,
                    {"valid_review_ids": [r.review_id for r in self.snapshot.reviews]})
                rec.model_used = self.llm.mode
                if not self.snapshot.requirements:
                    rec.status = "degraded"
                    rec.summary = "模型需求全部未通过证据校验"
                    self.snapshot.requirements = fallback_requirements(self.snapshot.findings)
                else:
                    rec.summary = f"生成 {len(self.snapshot.requirements)} 条需求"
            else:
                self.snapshot.requirements = fallback_requirements(self.snapshot.findings)
                rec.status = "degraded"
                rec.summary = "降级模式：模板需求"
            self.emit("stage.output", {"requirements": [r.model_dump() for r in self.snapshot.requirements]})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        rec.status = rec.status if rec.status != "running" else "done"
```

- [ ] **Step 4: 写 s5_prd.txt 提示词**（取自方案书附录 A4）
- [ ] **Step 5: 运行测试确认 PASS**
- [ ] **Step 6: Commit**：`git commit -am "feat: S5 PRD generation with evidence validation"`

---

### Task 8: S6 测试用例 + S7 追溯校验

**Files:**
- Create: `backend/tools/validator.py`
- Create: `backend/workflow/s6_testcases.py`
- Create: `backend/workflow/s7_validate.py`
- Create: `backend/llm/prompts/s6_testcases.txt`
- Test: `tests/test_validator.py`, `tests/test_s6_testcases.py`

**Interfaces:**
- Consumes: `Requirement, TestCase, RunSnapshot`；`LLMClient`
- Produces:
  - `build_testcases_with_llm(requirements, llm, review_map) -> list[TestCase]`（review_refs 从需求证据链自动继承）
  - `validate_chain(snapshot) -> dict`（校验报告：passed/failed/corrected + corrections 写入 snapshot）
  - `s7_validate.run(ctx)`：执行校验 + 修正（孤儿引用 → 删除结论/需求/用例 或 标记 assumption），产出校验报告

- [ ] **Step 1: 写测试**

```python
# tests/test_s6_testcases.py
from backend.models import Requirement
from backend.llm.client import FakeLLM
from backend.workflow.s6_testcases import build_testcases_with_llm

def test_review_refs_inherited_not_fabricated():
    req = Requirement(req_id="PRD-1", title="修复订阅支付失败", priority="P0",
                      evidence_refs=["F-T1-s", "r0", "r1"], version="v8.1")
    llm = FakeLLM([{"test_cases": [
        {"case_id": "TC-1", "title": "订阅成功支付", "preconditions": "p",
         "steps": ["s1"], "expected_results": ["e1"], "req_refs": ["PRD-1"],
         "review_refs": ["FAKE-999"]}]}])   # 模型编造的 ID 应被替换为证据链 ID
    cases = build_testcases_with_llm([req], llm, {"PRD-1": ["r0", "r1"]})
    assert len(cases) == 1
    assert "FAKE-999" not in cases[0].review_refs
    assert set(cases[0].review_refs) <= {"r0", "r1"}
```

```python
# tests/test_validator.py
from backend.models import RunSnapshot, Review, TopicCluster, Finding, Requirement, TestCase
from backend.tools.validator import validate_chain

def test_orphan_reference_detected():
    snap = RunSnapshot(run_id="r1")
    snap.reviews = [Review(review_id="r0", body="b", rating=5)]
    snap.findings = [Finding(finding_id="F1", kind="model_derived", statement="s",
                             supporting_review_ids=["r0", "ghost"])]
    snap.requirements = [Requirement(req_id="PRD-1", title="t", evidence_refs=["F1", "ghost2"], version="v8.1")]
    report = validate_chain(snap)
    assert report["orphan_review_refs"]["findings"] == ["ghost"]
    assert report["orphan_review_refs"]["requirements"] == ["ghost2"]
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 backend/workflow/s6_testcases.py**

```python
import json
from pathlib import Path
from .stage_base import StageBase
from ..models import TestCase

def build_testcases_with_llm(requirements, llm, review_map) -> list[TestCase]:
    prompts_dir = Path(__file__).resolve().parent.parent / "llm" / "prompts"
    user = (prompts_dir / "s6_testcases.txt").read_text(encoding="utf-8").format(
        requirements_json=json.dumps([r.model_dump() for r in requirements], ensure_ascii=False))
    data = llm.chat_json("你是测试工程师。基于 PRD 需求生成测试用例，只输出 JSON。", user, {"test_cases": []})
    out = []
    if not data or not isinstance(data.get("test_cases"), list):
        return out
    valid_reqs = {r.req_id for r in requirements}
    for i, c in enumerate(data["test_cases"]):
        reqs = [x for x in c.get("req_refs", []) if x in valid_reqs]
        if not reqs:
            continue
        # review_refs 强制继承需求证据链，不允许模型编造
        refs: list[str] = []
        for r in reqs:
            refs.extend(review_map.get(r, []))
        refs = list(dict.fromkeys(refs))[:10]
        out.append(TestCase(
            case_id=f"TC-{i+1}", title=c.get("title", "未命名用例"),
            preconditions=c.get("preconditions", ""),
            steps=c.get("steps", [])[:12], expected_results=c.get("expected_results", [])[:8],
            req_refs=reqs, review_refs=refs))
    return out

def fallback_testcases(requirements) -> list[TestCase]:
    out = []
    for i, r in enumerate(requirements):
        out.append(TestCase(
            case_id=f"TC-{i+1}", title=f"验证『{r.title}』",
            preconditions="应用处于可测试环境",
            steps=["复现需求对应场景", "执行操作", "记录结果"],
            expected_results=["需求验收标准全部满足", "相关评论问题不再出现"],
            req_refs=[r.req_id],
            review_refs=[x for x in r.evidence_refs if not x.startswith("F-")][:5]))
    return out

class S6Testcases(StageBase):
    name = "s6"
    def run(self):
        rec = self.stage("s6")
        rec.status = "running"
        try:
            if self.mode == "llm" and self.llm.available and self.snapshot.requirements:
                review_map = {}
                for r in self.snapshot.requirements:
                    review_map[r.req_id] = [x for x in r.evidence_refs
                                            if not x.startswith("F-") and not x.startswith("PRD-")]
                self.snapshot.test_cases = build_testcases_with_llm(
                    self.snapshot.requirements, self.llm, review_map)
                rec.model_used = self.llm.mode
                if not self.snapshot.test_cases:
                    rec.status = "degraded"
                    self.snapshot.test_cases = fallback_testcases(self.snapshot.requirements)
                else:
                    rec.summary = f"生成 {len(self.snapshot.test_cases)} 条用例"
            else:
                self.snapshot.test_cases = fallback_testcases(self.snapshot.requirements)
                rec.status = "degraded"
                rec.summary = "降级模式：模板用例"
            self.emit("stage.output", {"test_cases": [c.model_dump() for c in self.snapshot.test_cases]})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        rec.status = rec.status if rec.status != "running" else "done"
```

- [ ] **Step 4: 实现 backend/tools/validator.py**

```python
from ..models import RunSnapshot

def _orphan(items, valid_ids, field):
    out = []
    for it in items:
        for ref in getattr(it, field, []) or []:
            if ref not in valid_ids:
                out.append(ref)
    return list(dict.fromkeys(out))

def validate_chain(snap: RunSnapshot) -> dict:
    valid_rids = {r.review_id for r in snap.reviews}
    valid_fids = {f.finding_id for f in snap.findings}
    valid_reqs = {r.req_id for r in snap.requirements}
    review_refs = {"findings": _orphan(snap.findings, valid_rids, "supporting_review_ids"),
                   "requirements": _orphan(snap.requirements, valid_rids, "evidence_refs")}
    req_missing_evidence = [r.req_id for r in snap.requirements
                            if not any(x in valid_fids for x in r.evidence_refs)]
    test_missing_req = [c.case_id for c in snap.test_cases if not any(x in valid_reqs for x in c.req_refs)]
    reqs_without_cases = [r.req_id for r in snap.requirements
                          if not any(r.req_id in c.req_refs for c in snap.test_cases)]
    assumptions = [f.finding_id for f in snap.findings if f.kind == "assumption"]
    orphan_review_refs = {k: v for k, v in review_refs.items() if v}
    return {
        "passed": not (orphan_review_refs or req_missing_evidence or test_missing_req or reqs_without_cases),
        "orphan_review_refs": review_refs,
        "requirements_missing_evidence": req_missing_evidence,
        "test_cases_missing_requirements": test_missing_req,
        "requirements_without_cases": reqs_without_cases,
        "assumption_findings": assumptions,
        "stats": {"findings": len(snap.findings), "requirements": len(snap.requirements),
                  "test_cases": len(snap.test_cases), "corrections": len(snap.corrections)},
    }
```

- [ ] **Step 5: 实现 backend/workflow/s7_validate.py**

```python
from .stage_base import StageBase
from ..tools.validator import validate_chain

class S7Validate(StageBase):
    name = "s7"
    def run(self):
        rec = self.stage("s7")
        rec.status = "running"
        try:
            report = validate_chain(self.snapshot)
            # 修正动作：孤儿引用的结论/需求删除或修正
            for f in list(self.snapshot.findings):
                if any(x not in {r.review_id for r in self.snapshot.reviews} for x in f.supporting_review_ids):
                    f.supporting_review_ids = [x for x in f.supporting_review_ids
                                               if x in {r.review_id for r in self.snapshot.reviews}]
                    if not f.supporting_review_ids:
                        f.kind = "assumption"
                        f.uncertainty = (f.uncertainty + "；原引用缺失已修正").strip()
                        self.snapshot.corrections.append({
                            "target": f.finding_id, "action": "标记为假设",
                            "reason": "孤儿引用被清除", "time": ""})
            for r in list(self.snapshot.requirements):
                if not any(x in {f.finding_id for f in self.snapshot.findings} for x in r.evidence_refs):
                    self.snapshot.requirements.remove(r)
                    self.snapshot.corrections.append({
                        "target": r.req_id, "action": "删除", "reason": "无有效证据引用", "time": ""})
            for c in list(self.snapshot.test_cases):
                if not any(x in {r.req_id for r in self.snapshot.requirements} for x in c.req_refs):
                    self.snapshot.test_cases.remove(c)
                    self.snapshot.corrections.append({
                        "target": c.case_id, "action": "删除", "reason": "关联需求不存在", "time": ""})
            report = validate_chain(self.snapshot)
            self.snapshot.validation_report = report
            rec.summary = f"校验{'通过' if report['passed'] else '存在未决问题'}"
            self.emit("stage.output", {"validation_report": report,
                                       "corrections": self.snapshot.corrections})
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        rec.status = rec.status if rec.status != "running" else "done"
```

- [ ] **Step 6: 写 s6_testcases.txt 提示词**（取自方案书附录 A5）
- [ ] **Step 7: 运行测试确认 PASS**
- [ ] **Step 8: Commit**：`git commit -am "feat: S6 test cases + S7 traceability validation"`

---

### Task 9: 编排器 + SSE 进度 + API + 前端联调

**Files:**
- Create: `backend/workflow/orchestrator.py`
- Create: `backend/run_manager.py`（运行快照管理：创建/读取/存盘）
- Modify: `backend/main.py`（API 路由 + SSE）
- Modify: `frontend/app.js`（联调：POST analyze → EventSource 进度 → 渲染交付物）
- Create: `scripts/demo.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: 全部 stages；`LLMClient`
- Produces:
  - `Orchestrator.execute(request: AnalyzeRequest, llm: LLMClient | None) -> RunSnapshot`（同步执行，内部调 on_event）
  - `run_manager.create_run() -> str`（run_id）；`save_snapshot(snap)`；`load_snapshot(run_id) -> RunSnapshot | None`
  - API: `POST /api/analyze`（校验 URL → 校验缓存 → 后台线程执行 → 返回 run_id）；`GET /api/status/{run_id}`（SSE）；`GET /api/results/{run_id}`；`POST /api/import`（JSON/CSV 文件）；`GET /api/samples`（内置示例）
  - 前端：输入区 → 启动 → 进度面板 SSE 渲染 → 交付物 Tabs 渲染

- [ ] **Step 1: 写测试 tests/test_orchestrator.py**（FakeLLM 全流程：导入数据 → S2 起跑，验证快照各交付物非空且链路完整）

```python
import pytest
from backend.models import AnalyzeRequest, Review
from backend.llm.client import FakeLLM
from backend.workflow.orchestrator import Orchestrator

def _imported_reviews(n=12):
    bodies = [
        "subscription charged twice and no refund", "订阅扣了两次钱",
        "the app keeps crashing on startup", "闪退",
        "hard to find the pause button", "不好用",
        "I love this app", "great workout", "nice", "ok",
        "update broke my progress", "data disappeared",
    ]
    return [Review(review_id=f"r{i}", body=bodies[i % len(bodies)],
                   rating=1 if i % 3 == 0 else 5, source="import") for i in range(n)]

def _llm_responses():
    # S0 计划
    plan = {"focus_areas": ["订阅", "易用性"], "constraints": [], "analysis_plan": "关注订阅与易用性"}
    # S3 两批（每批 40，12 条 1 批即可）→ 用 1 批 + 合并
    topics = {"topics": [
        {"topic_id": "T1", "topic_name": "订阅扣款问题", "member_ids": ["r0", "r1"],
         "evidence": ["subscription charged twice"], "opposing_feedback": [], "confidence": "high",
         "confidence_reason": "n=2"},
        {"topic_id": "T2", "topic_name": "崩溃问题", "member_ids": ["r2", "r3"],
         "evidence": ["crashing"], "opposing_feedback": [], "confidence": "medium", "confidence_reason": "n=2"}]}
    merge = {"topics": topics["topics"], "merge_log": []}
    # S4 推导
    s4 = {"findings": [
        {"kind": "model_derived", "statement": "订阅扣款问题影响严重", "supporting_review_ids": ["r0", "r1"],
         "confidence": "high", "uncertainty": "n=2", "conflicting_evidence": [], "topic_refs": ["T1"]}]}
    # S5 PRD
    s5 = {"requirements": [
        {"req_id": "PRD-1", "title": "修复订阅扣款问题", "description": "d", "priority": "P0",
         "version": "v8.1", "rationale": "r", "evidence_refs": ["F-T1-s", "r0", "r1"],
         "acceptance_criteria": ["c"]}]}
    # S6 用例
    s6 = {"test_cases": [
        {"case_id": "TC-1", "title": "订阅支付一次", "preconditions": "p", "steps": ["s"],
         "expected_results": ["e"], "req_refs": ["PRD-1"]}]}
    return [plan, topics, merge, s4, s5, s6]

def test_full_workflow_degraded_ok():
    llm = None
    orch = Orchestrator(llm)
    snap = orch.execute(AnalyzeRequest(goal="订阅转化", constraints=[]),
                        reviews=_imported_reviews())
    assert snap.status in ("done", "degraded")
    assert len(snap.reviews) >= 12
    assert snap.topics or snap.validation_report
    # 全链路引用完整
    report = snap.validation_report
    assert report.get("passed", False) or report.get("assumption_findings")

def test_full_workflow_with_llm():
    llm = FakeLLM(_llm_responses())
    orch = Orchestrator(llm)
    snap = orch.execute(AnalyzeRequest(goal="订阅转化"), reviews=_imported_reviews())
    assert snap.plan.focus_areas == ["订阅", "易用性"]
    assert len(snap.topics) >= 2
    assert any(r.req_id == "PRD-1" for r in snap.requirements)
    assert len(snap.test_cases) >= 1
    assert snap.status == "done"
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 backend/workflow/orchestrator.py**

```python
import uuid
from datetime import datetime
from ..models import RunSnapshot, StageRecord
from .s0_plan import S0Plan
from .s3_classify import S3Classify
from .s4_findings import S4Findings
from .s5_prd import S5PRD
from .s6_testcases import S6Testcases
from .s7_validate import S7Validate
from ..tools import cleaner
from ..tools.collector import fetch_reviews, load_cache, save_cache, parse_appstore_url
from ..config import get_settings

class Orchestrator:
    def __init__(self, llm=None, settings=None, on_event=None):
        self.llm = llm
        self.settings = settings or get_settings()
        self.on_event = on_event or (lambda e: None)

    def execute(self, request, reviews=None, on_event=None) -> RunSnapshot:
        if on_event:
            self.on_event = on_event
        snap = RunSnapshot(run_id=uuid.uuid4().hex[:12], request=request,
                           created_at=datetime.now().isoformat(timespec="seconds"))
        for name in ("s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7"):
            snap.stages.append(StageRecord(name=name))
        self._event(snap, "run.started")
        model_mode = "llm" if (self.llm and getattr(self.llm, "available", False)) else "degraded"
        snap.meta["model_mode"] = model_mode
        snap.meta["min_sample"] = self.settings.min_sample
        ctx = {"snapshot": snap, "llm": self.llm, "on_event": self.on_event, "model_mode": model_mode}

        try:
            S0Plan(ctx).run()
            self._collect(snap, request, reviews)
            self._clean(snap)
            S3Classify(ctx).run()
            S4Findings(ctx).run()
            S5PRD(ctx).run()
            S6Testcases(ctx).run()
            S7Validate(ctx).run()
            snap.status = "degraded" if model_mode == "degraded" else "done"
            snap.meta["collect_note"] = self._collect_note
        except Exception as e:
            snap.status = "failed"
            snap.meta["fatal_error"] = str(e)
            self._event(snap, "run.failed", {"error": str(e)})
        finally:
            self._save(snap)
        self._event(snap, "run.finished", {"status": snap.status})
        return snap

    def _collect(self, snap, request, reviews=None):
        rec = self._rec(snap, "s1")
        rec.status = "running"
        if reviews:   # 导入模式
            snap.reviews = reviews
            self._collect_note = f"使用导入数据 {len(reviews)} 条"
            rec.summary = self._collect_note
            rec.status = "done"
            return
        if request.use_cache_only:
            cached = load_cache(request.app_id)
            if cached:
                snap.reviews = cached
                self._collect_note = f"缓存数据 {len(cached)} 条（仅缓存模式）"
                rec.summary = self._collect_note
                rec.status = "done"
                return
            rec.status = "failed"
            rec.error = "use_cache_only 但无缓存"
            snap.meta["collect_note"] = "无缓存可用"
            return
        try:
            fresh = fetch_reviews(request.app_id, max_pages=self.settings.collect_max_pages,
                                  rate_limit=self.settings.collect_rate_limit)
            if fresh:
                save_cache(request.app_id, fresh)
                snap.reviews = fresh
                self._collect_note = f"实时采集 {len(fresh)} 条"
            else:
                cached = load_cache(request.app_id)
                if cached:
                    snap.reviews = cached
                    self._collect_note = f"实时采集为空，使用缓存 {len(cached)} 条"
                else:
                    self._collect_note = "采集为空且无缓存"
                    rec.status = "failed"
                    rec.error = "采集为空且无缓存"
                    snap.reviews = []
            rec.summary = self._collect_note
        except Exception as e:
            cached = load_cache(request.app_id)
            if cached:
                snap.reviews = cached
                self._collect_note = f"采集异常（{e}），使用缓存 {len(cached)} 条"
                rec.summary = self._collect_note
                rec.status = "degraded"
            else:
                self._collect_note = f"采集异常（{e}），无缓存"
                rec.summary = self._collect_note
                rec.status = "failed"
                rec.error = str(e)
        snap.meta["collect_note"] = self._collect_note
        self._event(snap, "stage.output", {"stage": "s1", "data": {"note": self._collect_note}})
        rec.status = rec.status if rec.status != "running" else "done"

    def _clean(self, snap):
        rec = self._rec(snap, "s2")
        rec.status = "running"
        snap.reviews, log = cleaner.clean_reviews(snap.reviews)
        rec.summary = f"清洗后 {len(snap.reviews)} 条（含重复标记）"
        snap.meta["clean_log"] = log
        self._event(snap, "stage.output", {"stage": "s2", "data": {"log": log, "count": len(snap.reviews)}})
        rec.status = "done"

    def _rec(self, snap, name):
        return next(s for s in snap.stages if s.name == name)

    def _event(self, snap, etype, data=None):
        self.on_event({"type": etype, "stage": etype.split(".")[0], "data": data or {},
                       "run_id": snap.run_id, "time": datetime.now().isoformat(timespec="seconds")})

    def _save(self, snap):
        from ..run_manager import save_snapshot
        save_snapshot(snap)
```

- [ ] **Step 4: 实现 backend/run_manager.py**

```python
import json, uuid
from datetime import datetime
from pathlib import Path
from .models import RunSnapshot

RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"

def save_snapshot(snap: RunSnapshot) -> str:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    p = RUNS_DIR / f"{snap.run_id}.json"
    p.write_text(json.dumps(snap.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    return str(p)

def load_snapshot(run_id: str) -> RunSnapshot | None:
    p = RUNS_DIR / f"{run_id}.json"
    if not p.exists():
        return None
    return RunSnapshot(**json.loads(p.read_text(encoding="utf-8")))
```

- [ ] **Step 5: 改造 backend/main.py**（完整 API；SSE 用 `sse_starlette` 或直接 ASGI stream）

```python
import asyncio, json, threading
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .models import AnalyzeRequest
from .config import get_settings
from .llm.client import LLMClient
from .workflow.orchestrator import Orchestrator
from .run_manager import load_snapshot, RUNS_DIR

app = FastAPI(title="App Store Review Analyzer")

_llm = None
_settings = get_settings()

def get_llm():
    global _llm
    if _llm is None:
        _llm = LLMClient(_settings)
    return _llm

_events: dict[str, list[dict]] = {}   # run_id -> 事件缓冲
_active: dict[str, dict] = {}         # run_id -> {"future": ..., "done": bool}

@app.get("/api/health")
def health():
    return {"status": "ok", "llm": get_llm().mode}

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    from .tools.collector import parse_appstore_url
    if not req.url and not req.use_cache_only:
        raise HTTPException(400, "请输入 App Store 链接")
    app_id = None
    if req.url:
        info = parse_appstore_url(req.url)
        req.app_id = info["app_id"]
    run_id = _start(req)
    return {"run_id": run_id}

def _start(req: AnalyzeRequest) -> str:
    from .models import RunSnapshot
    run_id = f"run_{len(_events) + 1}"
    _events[run_id] = []
    _active[run_id] = {"done": False}
    def worker():
        orch = Orchestrator(get_llm(), _settings, on_event=lambda e: _events[run_id].append(e))
        snap = orch.execute(req)
        _events[run_id].append({"type": "run.complete", "run_id": run_id, "data": {"status": snap.status}})
        _active[run_id]["done"] = True
    threading.Thread(target=worker, daemon=True).start()
    return run_id

@app.get("/api/status/{run_id}")
async def status(run_id: str):
    async def gen():
        idx = 0
        while True:
            evs = _events.get(run_id, [])
            while idx < len(evs):
                e = evs[idx]; idx += 1
                yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
            if _active.get(run_id, {}).get("done"):
                yield "data: {\"type\":\"sse.end\"}\n\n"
                break
            await asyncio.sleep(0.3)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/results/{run_id}")
def results(run_id: str):
    snap = load_snapshot(run_id)
    if not snap:
        raise HTTPException(404, "run not found")
    return JSONResponse(snap.model_dump())

@app.get("/api/runs")
def list_runs():
    files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
    return [{"run_id": p.stem, "mtime": p.stat().st_mtime} for p in files]

@app.post("/api/import")
async def import_data(file: UploadFile):
    from .tools.importer import import_file
    reviews, note = await import_file(file)
    return {"count": len(reviews), "note": note, "preview": [r.model_dump() for r in reviews[:5]]}

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
```

注意：`AnalyzeRequest` 需加 `app_id: str = ""` 字段（models.py 中补充）。

- [ ] **Step 6: 实现 scripts/demo.py**（无网络演示：导入内置样例 → 全流程 → 打印交付物摘要）

```python
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.models import AnalyzeRequest
from backend.workflow.orchestrator import Orchestrator
from backend.llm.client import LLMClient
from backend.config import get_settings

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "samples" / "workout-for-women.json"

def main():
    settings = get_settings()
    llm = LLMClient(settings)
    reviews = []
    if SAMPLE.exists():
        from backend.models import Review
        reviews = [Review(**r) for r in json.loads(SAMPLE.read_text(encoding="utf-8"))]
    orch = Orchestrator(llm, settings)
    snap = orch.execute(AnalyzeRequest(goal="订阅转化与训练易用性", constraints=["低分评论优先"]),
                        reviews=reviews or None)
    print(f"status={snap.status} mode={snap.meta.get('model_mode')}")
    print(f"reviews={len(snap.reviews)} topics={len(snap.topics)} findings={len(snap.findings)} "
          f"requirements={len(snap.requirements)} test_cases={len(snap.test_cases)}")
    print(json.dumps(snap.validation_report, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: 前端联调 frontend/app.js**：POST /api/analyze → EventSource(/api/status/{run_id}) → 渲染进度面板（阶段灯+摘要+中间产出）→ 全部完成后 GET /api/results/{run_id} 渲染 7 个交付物 Tab + 降级徽标 + 导出按钮

- [ ] **Step 8: 内置样例数据 data/samples/workout-for-women.json**（若 Task 2 真实采集成功则复制缓存；否则从缓存生成说明：如实标注"由 fetch_cache 脚本生成"）

- [ ] **Step 9: 运行测试 + 启动冒烟**

```bash
pytest tests/ -v          # 全部 PASS
.venv/Scripts/python -m scripts.demo   # 端到端跑通（无 key 也需可运行）
uvicorn backend.main:app --port 8000   # 浏览器冒烟
```

- [ ] **Step 10: Commit**：`git commit -am "feat: orchestrator, SSE progress, full API, frontend integration, demo script"`

---

### Task 10: 导入模块 + 文档 + 收尾

**Files:**
- Create: `backend/tools/importer.py`
- Create: `README.md`
- Create: `docs/deployment.md`, `docs/data-collection.md`, `docs/llm-design.md`, `docs/model-comparison.md`
- Create: `tests/test_importer.py`

**Interfaces:**
- Produces: `import_file(file: UploadFile) -> tuple[list[Review], str]`（支持 .json 数组 / .csv；字段映射 review_id/title/body/rating/author/version/updated；缺 review_id 生成 `generated:{md5}`）

- [ ] **Step 1: 写测试 tests/test_importer.py**

```python
import io, json
import pytest
from fastapi import UploadFile
from backend.tools.importer import parse_json_data, parse_csv_data

def test_parse_json():
    data = [{"review_id": "a", "body": "hi", "rating": 4}]
    reviews, note = parse_json_data(json.dumps(data))
    assert len(reviews) == 1 and reviews[0].rating == 4

def test_parse_json_missing_id():
    reviews, note = parse_json_data(json.dumps([{"body": "hi", "rating": 4}]))
    assert reviews[0].review_id.startswith("generated:")

def test_parse_csv():
    csv_text = "review_id,title,body,rating\n1,t,hello,3\n2,t,world,5\n"
    reviews, note = parse_csv_data(csv_text)
    assert len(reviews) == 2 and reviews[1].rating == 5
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 backend/tools/importer.py**

```python
import csv, hashlib, io, json
from ..models import Review

_FIELDS = {"review_id", "title", "body", "rating", "author", "version", "updated"}

def _norm(r: dict) -> Review:
    rating = int(r.get("rating", 3) or 3)
    rating = max(1, min(5, rating))
    rid = str(r.get("review_id", "")).strip()
    if not rid:
        rid = "generated:" + hashlib.md5(str(r).encode()).hexdigest()[:12]
    return Review(review_id=rid, title=str(r.get("title", "")), body=str(r.get("body", "")),
                  rating=rating, author=str(r.get("author", "")),
                  version=str(r.get("version", "")) or None,
                  updated=str(r.get("updated", "")), source="import")

def parse_json_data(text: str) -> tuple[list[Review], str]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("reviews", [])
    rows = [d for d in data if isinstance(d, dict) and (d.get("body") or d.get("title"))]
    return [_norm(r) for r in rows], f"JSON 导入 {len(rows)} 条"

def parse_csv_data(text: str) -> tuple[list[Review], str]:
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return [_norm(r) for r in rows], f"CSV 导入 {len(rows)} 条"

async def import_file(file) -> tuple[list[Review], str]:
    content = (await file.read()).decode("utf-8", errors="replace")
    if file.filename and file.filename.endswith(".csv"):
        return parse_csv_data(content)
    return parse_json_data(content)
```

- [ ] **Step 4: 运行测试确认 PASS**
- [ ] **Step 5: 写 README.md**（结构：简介/功能演示/快速开始/架构/方法选择矩阵/采集方案与局限/LLM 设计/降级/评审自检清单——内容引用技术方案书对应章节）
- [ ] **Step 6: 写 docs/ 四份文档**（deployment: 环境/启动/故障排查；data-collection: RSS 方案对比+局限；llm-design: 模型/提示词/参数/降级/防幻觉；model-comparison: 对比实验说明+结果模板）
- [ ] **Step 7: 全量验证**

```bash
pytest tests/ -v
python -m scripts.demo
uvicorn backend.main:app --port 8000  # 浏览器走通 分析→进度→交付物→导出
```

- [ ] **Step 8: 最终提交**：`git add -A && git commit -am "docs: deployment, data collection, LLM design, README with self-check"`

---

## Self-Review

**Spec coverage（方案书要求 → 任务）：**
- 数据采集（RSS+缓存+限速）→ Task 2
- 清洗去重语言检测 → Task 3
- LLM 客户端+降级 → Task 4
- S0 计划 / S3 动态分类 / S4 证据 / S5 PRD / S6 用例 / S7 校验 → Task 5-8
- 编排器+SSE+API+前端 → Task 9
- JSON/CSV 导入 → Task 10
- 文档（deployment/data-collection/llm-design/model-comparison/README 自检清单）→ Task 10
- 测试全部不依赖网络与真实 key（FakeLLM + MockTransport）→ 每任务内
- 密钥不入库（.gitignore 含 .env）→ Task 1

**类型一致性：** `AnalyzeRequest` 在 Task 1 定义后，Task 9 需补充 `app_id` 字段（步骤 5 已注明）；`Finding.kind` 值域与校验一致（statistical/model_derived/assumption）；`RunSnapshot` 字段在 orchestrator/validator/前端全程一致。

**无占位符：** 所有提示词文件内容引用技术方案书附录 A1-A6，实现时从方案书复制；samples 数据来源如实标注。
