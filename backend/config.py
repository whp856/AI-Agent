import os
from dataclasses import dataclass
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
    ollama_enabled: bool = False
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
