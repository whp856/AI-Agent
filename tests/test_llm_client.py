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
