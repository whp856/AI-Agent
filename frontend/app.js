// App Store Review Analyzer 前端
// Task 1 骨架：健康检查、约束 chips、Tab 切换、阶段节点渲染
// Task 9 联调：分析启动、SSE 进度、交付物渲染

"use strict";

const $ = (id) => document.getElementById(id);

const STAGE_NAMES = {
  s0: "S0 范围确定", s1: "S1 数据采集", s2: "S2 清洗去重", s3: "S3 动态分类",
  s4: "S4 证据评估", s5: "S5 PRD 生成", s6: "S6 测试用例", s7: "S7 追溯校验",
};

const CONSTRAINT_CHIPS = ["低分评论优先", "订阅转化", "训练易用性", "指定版本", "功能缺陷", "设计体验"];

let currentSnapshot = null;

// ---------- 初始化 ----------
async function init() {
  renderChips();
  bindTabs();
  bindButtons();
  try {
    const r = await fetch("/api/health").then((x) => x.json());
    setModeBadge(r.llm);
  } catch {
    setModeBadge("offline");
  }
}

function renderChips() {
  const box = $("constraintChips");
  CONSTRAINT_CHIPS.forEach((label) => {
    const el = document.createElement("span");
    el.className = "chip";
    el.textContent = label;
    el.onclick = () => el.classList.toggle("active");
    box.appendChild(el);
  });
}

function setModeBadge(mode) {
  const badge = $("modeBadge");
  const map = {
    deepseek: ["ok", "模型：DeepSeek"],
    qwen: ["ok", "模型：Qwen"],
    ollama: ["warn", "模型：Ollama 本地"],
    fake: ["warn", "测试模式"],
    none: ["warn", "无模型配置（降级模式）"],
    offline: ["err", "后端未连接"],
  };
  const [cls, text] = map[mode] || ["warn", `模式：${mode}`];
  badge.className = `mode-badge ${cls}`;
  badge.textContent = text;
}

// ---------- Tab ----------
function bindTabs() {
  $("tabs").addEventListener("click", (e) => {
    const tab = e.target.closest(".tab");
    if (!tab) return;
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    renderTab(tab.dataset.tab);
  });
}

function renderTab(name) {
  const box = $("tabContent");
  if (!currentSnapshot) { box.innerHTML = '<div class="empty">暂无数据</div>'; return; }
  const s = currentSnapshot;
  if (name === "reviews") box.innerHTML = renderReviews(s.reviews);
  else if (name === "cleaned") box.innerHTML = renderCleaned(s.reviews, s.meta.clean_log);
  else if (name === "topics") box.innerHTML = renderTopics(s.topics);
  else if (name === "findings") box.innerHTML = renderFindings(s.findings);
  else if (name === "prd") box.innerHTML = renderPRD(s.requirements);
  else if (name === "cases") box.innerHTML = renderCases(s.test_cases);
  else if (name === "validation") box.innerHTML = renderValidation(s);
  else if (name === "meta") box.innerHTML = renderMeta(s);
}

// ---------- 渲染辅助（交付物渲染在 Task 9 完善，先提供结构） ----------
function esc(t) {
  return String(t ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function confBadge(c) {
  return `<span class="badge ${esc(c)}">${esc(c)}</span>`;
}

function kindBadge(k) {
  const label = { statistical: "统计事实", model_derived: "模型推导", assumption: "假设" }[k] || k;
  return `<span class="badge ${esc(k)}">${esc(label)}</span>`;
}

function renderReviews(reviews) {
  if (!reviews.length) return '<div class="empty">无数据</div>';
  const rows = reviews.slice(0, 200).map((r) => `
    <tr><td>${esc(r.review_id)}</td><td>${esc(r.rating)}</td><td>${esc(r.version || "-")}</td>
    <td>${esc(r.body)}</td><td>${esc(r.language || "-")}</td></tr>`).join("");
  return `<table><tr><th>ID</th><th>评分</th><th>版本</th><th>正文</th><th>语言</th></tr>${rows}</table>
          <p class="muted">共 ${reviews.length} 条（显示前 200 条）</p>`;
}

function renderCleaned(reviews, log) {
  const logHtml = (log || []).map((l) => `<li>[${esc(l.step)}] ${l.count} 条 — ${esc(l.note || "")}</li>`).join("");
  return `<h3>清洗日志</h3><ul>${logHtml || "<li>无</li>"}</ul>
          <h3>有效评论 ${reviews.filter((r) => !r.is_duplicate).length} 条 / 重复 ${reviews.filter((r) => r.is_duplicate).length} 条</h3>`;
}

function renderTopics(topics) {
  if (!topics.length) return '<div class="empty">无主题</div>';
  return topics.map((t) => `
    <div class="section-block">
      <div class="title">${esc(t.topic_id)} ${esc(t.topic_name)} ${confBadge(t.confidence)}</div>
      <div class="kv"><span>评论 <b>${t.member_ids.length}</b> 条</span></div>
      <p>${esc(t.description)}</p>
      <p class="muted">代表性摘录：${esc((t.evidence || []).join(" / "))}</p>
      ${t.opposing_feedback?.length ? `<p class="muted">对立反馈：${esc(t.opposing_feedback.join(" / "))}</p>` : ""}
    </div>`).join("");
}

function renderFindings(findings) {
  if (!findings.length) return '<div class="empty">无结论</div>';
  return findings.map((f) => `
    <div class="section-block">
      <div class="title">${esc(f.finding_id)} ${kindBadge(f.kind)} ${confBadge(f.confidence)}
        <span class="muted">样本 ${f.sample_count}</span></div>
      <p>${esc(f.statement)}</p>
      <p class="muted">不确定性：${esc(f.uncertainty)}</p>
      ${f.conflicting_evidence?.length ? `<p class="muted">对立证据：${esc(f.conflicting_evidence.join(" / "))}</p>` : ""}
    </div>`).join("");
}

function renderPRD(reqs) {
  if (!reqs.length) return '<div class="empty">无需求</div>';
  return reqs.map((r) => `
    <div class="section-block">
      <div class="title"><span class="badge ${esc(r.priority)}">${esc(r.priority)}</span>
        ${esc(r.req_id)} ${esc(r.title)} <span class="muted">→ ${esc(r.version)}</span></div>
      <p>${esc(r.description)}</p>
      <p class="muted">依据：${r.evidence_refs.map(esc).join(", ")}</p>
      ${r.acceptance_criteria?.length ? `<p class="muted">验收：${r.acceptance_criteria.map(esc).join("；")}</p>` : ""}
    </div>`).join("");
}

function renderCases(cases) {
  if (!cases.length) return '<div class="empty">无用例</div>';
  return cases.map((c) => `
    <div class="section-block">
      <div class="title">${esc(c.case_id)} ${esc(c.title)} <span class="muted">关联 ${c.req_refs.map(esc).join(",")}</span></div>
      <p class="muted">前置：${esc(c.preconditions)}</p>
      <ol>${c.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
      <p class="muted">期望：${(c.expected_results || []).map(esc).join("；")}</p>
      <p class="muted">评论来源：${(c.review_refs || []).map(esc).join(", ")}</p>
    </div>`).join("");
}

function renderValidation(s) {
  const v = s.validation_report || {};
  const rows = [
    ["校验通过", v.passed === true ? "是" : "否"],
    ["结论数", v.stats?.findings ?? "-"], ["需求数", v.stats?.requirements ?? "-"],
    ["用例数", v.stats?.test_cases ?? "-"], ["修正记录", v.stats?.corrections ?? "-"],
    ["孤儿引用（结论）", (v.orphan_review_refs?.findings || []).join(", ") || "无"],
    ["孤儿引用（需求）", (v.orphan_review_refs?.requirements || []).join(", ") || "无"],
    ["缺证据需求", (v.requirements_missing_evidence || []).join(", ") || "无"],
    ["假设项", (v.assumption_findings || []).join(", ") || "无"],
  ];
  return `<table>${rows.map(([k, val]) => `<tr><th>${esc(k)}</th><td>${esc(val)}</td></tr>`).join("")}</table>
    <h3>修正记录</h3><ul>${(s.corrections || []).map((c) => `<li>${esc(c.target)} — ${esc(c.action)}：${esc(c.reason)}</li>`).join("") || "<li>无</li>"}</ul>`;
}

function renderMeta(s) {
  const m = s.meta || {};
  return `<div class="section-block">
    <div class="title">数据来源</div>
    <p>${esc(m.collect_note || "导入数据")}</p>
    <p class="muted">运行模式：${esc(m.model_mode || "unknown")}</p>
    <p class="muted">分析目标：${esc(s.request?.goal || "-")}</p>
    <p class="muted">约束：${(s.request?.constraints || []).map(esc).join(", ") || "-"}</p>
    <h3>数据局限声明</h3>
    <ul><li>采集窗口为最近评论（iTunes RSS 官方接口，每请求约 50 条）</li>
        <li>样本量与语言覆盖范围已在前述交付物中标注</li>
        <li>降级模式下结论置信度受限，已如实标注</li></ul>
  </div>`;
}

// ---------- 按钮 ----------
function bindButtons() {
  $("exampleBtn").onclick = () => {
    $("urlInput").value = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684";
  };
  $("importBtn").onclick = () => $("fileInput").click();
  $("fileInput").onchange = handleImport;
  $("exportBtn").onclick = exportSnapshot;
  $("analyzeBtn").onclick = startAnalysis;
  $("demoBtn").onclick = startDemo;
}

async function handleImport(e) {
  const file = e.target.files[0];
  if (!file) return;
  const goal = $("goalInput").value.trim();
  const constraints = Array.from(document.querySelectorAll(".chip.active"))
    .map((c) => c.textContent);
  const fd = new FormData();
  fd.append("file", file);
  fd.append("goal", goal);
  fd.append("constraints", constraints.join(","));
  $("importNote").textContent = "导入并启动分析…";
  try {
    const r = await fetch("/api/analyze-import", { method: "POST", body: fd })
      .then((x) => x.json());
    if (r.detail) throw new Error(r.detail);
    $("importNote").textContent = `已导入 ${r.count} 条，开始分析…`;
    subscribe(r.run_id);
  } catch (err) {
    $("importNote").textContent = `导入失败：${err.message}`;
  }
  e.target.value = "";
}

function exportSnapshot() {
  if (!currentSnapshot) return;
  const blob = new Blob([JSON.stringify(currentSnapshot, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${currentSnapshot.run_id || "snapshot"}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ---------- 分析流程 ----------
let currentRunId = null;

async function startAnalysis() {
  const url = $("urlInput").value.trim();
  const goal = $("goalInput").value.trim();
  const constraints = Array.from(document.querySelectorAll(".chip.active"))
    .map((c) => c.textContent);
  if (!url) {
    $("urlInput").focus();
    return;
  }
  $("analyzeBtn").disabled = true;
  $("analyzeBtn").textContent = "分析中…";
  $("resultsCard").hidden = true;
  try {
    const r = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, goal, constraints }),
    }).then((x) => x.json());
    if (r.detail) throw new Error(r.detail);
    subscribe(r.run_id);
  } catch (err) {
    showFatal(err.message);
  } finally {
    $("analyzeBtn").disabled = false;
    $("analyzeBtn").textContent = "开始分析";
  }
}

async function startDemo() {
  $("analyzeBtn").disabled = true;
  $("resultsCard").hidden = true;
  try {
    const r = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ use_cache_only: true, app_id: "839285684",
                             goal: "重点关注订阅转化与训练易用性",
                             constraints: ["低分评论优先"] }),
    }).then((x) => x.json());
    if (r.detail) throw new Error(r.detail);
    subscribe(r.run_id);
  } catch (err) {
    showFatal(err.message);
  } finally {
    $("analyzeBtn").disabled = false;
  }
}

// ---------- SSE 进度 ----------
function subscribe(runId) {
  currentRunId = runId;
  $("progressCard").hidden = false;
  $("errorBanner").hidden = true;
  renderStages([
    { name: "s0", status: "pending" }, { name: "s1", status: "pending" },
    { name: "s2", status: "pending" }, { name: "s3", status: "pending" },
    { name: "s4", status: "pending" }, { name: "s5", status: "pending" },
    { name: "s6", status: "pending" }, { name: "s7", status: "pending" },
  ]);
  const es = new EventSource(`/api/status/${runId}`);
  const stageEls = {};
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "sse.end") { es.close(); return; }
    if (ev.type === "run.failed") { showFatal(ev.data?.error || "运行失败"); return; }
    if (ev.type === "run.complete") {
      es.close();
      loadResults(ev.data.run_id || runId);
      return;
    }
    const st = ev.stage;
    if (st && STAGE_NAMES[st]) {
      let state = stageEls[st] || { status: "pending", summary: "" };
      if (ev.type === "stage.started") state = { status: "running", summary: state.summary || "" };
      if (ev.type === "stage.output") state = { status: "done", summary: summarize(ev) };
      stageEls[st] = state;
      renderStages(Object.keys(STAGE_NAMES).map((n) => ({
        name: n,
        status: stageEls[n]?.status || "pending",
        summary: stageEls[n]?.summary || "",
      })));
    }
    if (ev.data?.error) showFatal(ev.data.error);
  };
  es.onerror = () => { /* 重连由浏览器自动处理 */ };
}

function summarize(ev) {
  const d = ev.data || {};
  if (ev.stage === "s1") return d.note || `采集 ${d.count || 0} 条`;
  if (ev.stage === "s2") return `有效 ${d.active || 0} / 重复 ${d.duplicates || 0}`;
  if (ev.stage === "s3") return `主题 ${(d.topics || []).length} 个`;
  if (ev.stage === "s4") return `结论 ${(d.findings || []).length} 条`;
  if (ev.stage === "s5") return `需求 ${(d.requirements || []).length} 条`;
  if (ev.stage === "s6") return `用例 ${(d.test_cases || []).length} 条`;
  if (ev.stage === "s7") {
    const v = d.validation_report || {};
    return `校验${v.passed ? "通过" : "未通过"} 修正 ${(d.corrections || []).length} 项`;
  }
  return "";
}

function showFatal(msg) {
  const b = $("errorBanner");
  b.hidden = false;
  b.textContent = `错误：${msg}`;
}

// ---------- 结果加载 ----------
async function loadResults(runId) {
  try {
    const snap = await fetch(`/api/results/${runId}`).then((x) => x.json());
    currentSnapshot = snap;
    $("resultsCard").hidden = false;
    // 模式徽标按运行结果更新
    const mode = snap.meta?.model_mode || "unknown";
    setModeBadge(mode === "degraded" ? "none" : "deepseek");
    if (snap.meta?.model_mode === "degraded") {
      $("modeBadge").textContent = "降级模式（无模型配置）";
      $("modeBadge").className = "mode-badge warn";
    } else {
      $("modeBadge").textContent = "模型驱动";
      $("modeBadge").className = "mode-badge ok";
    }
    // 修正记录
    if (snap.corrections?.length) {
      $("correctionsBox").hidden = false;
      $("correctionsList").innerHTML = snap.corrections
        .map((c) => `<li>${esc(c.target)} — ${esc(c.action)}：${esc(c.reason)}</li>`).join("");
    }
    renderTab(document.querySelector(".tab.active").dataset.tab);
    window.scrollTo({ top: $("progressCard").offsetTop - 10, behavior: "smooth" });
  } catch (err) {
    showFatal(`加载结果失败：${err.message}`);
  }
}

// ---------- 阶段节点渲染 ----------
function renderStages(stages) {
  $("stageTimeline").innerHTML = stages.map((st) => {
    const statusText = { pending: "等待", running: "执行中", validating: "校验中", done: "完成",
      failed: "失败", degraded: "降级", skipped: "跳过" }[st.status] || st.status;
    return `<div class="stage-node ${esc(st.status)}">
      <div><span class="dot"></span><span class="name">${STAGE_NAMES[st.name] || esc(st.name)}</span></div>
      <div class="status-text">${statusText}</div>
      ${st.summary ? `<div class="summary">${esc(st.summary)}</div>` : ""}
    </div>`;
  }).join("");
}

init();
