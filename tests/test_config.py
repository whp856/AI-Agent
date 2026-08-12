from backend.config import get_settings


def test_default_settings():
    s = get_settings()
    assert s.llm_temperature == 0.3
    assert s.min_sample == 3
    assert s.llm_model == "deepseek-chat"
