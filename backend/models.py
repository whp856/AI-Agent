from pydantic import BaseModel, Field
from typing import Optional


class Review(BaseModel):
    review_id: str
    title: str = ""
    body: str = ""
    rating: int = Field(default=3, ge=1, le=5)
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
    confidence: str = "medium"   # high|medium|low
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
    __test__ = False  # 防止 pytest 将其收集为测试类

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
    app_id: str = ""             # 由后端解析填充


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
