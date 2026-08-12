import os

from backend.config import Settings, get_settings


def test_settings_dataclass_defaults():
    """Settings() 默认值不依赖任何环境/.env 文件。"""
    s = Settings()
    assert s.llm_temperature == 0.3
    assert s.min_sample == 3
    assert s.llm_model == "deepseek-chat"
    assert s.ollama_enabled is False


def test_get_settings_without_env(monkeypatch):
    """get_settings 在无任何环境变量时使用默认值（隔离 .env 文件）。"""
    for k in list(os.environ):
        if k in ("LLM_PROVIDER", "LLM_MODEL", "MIN_SAMPLE", "LLM_TEMPERATURE",
                 "DEEPSEEK_API_KEY", "QWEN_API_KEY", "OLLAMA_ENABLED"):
            monkeypatch.delenv(k, raising=False)
    s = get_settings()
    assert s.min_sample == 3
    assert s.llm_model == "deepseek-chat"
