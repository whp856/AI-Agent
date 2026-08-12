import json
import time

from ..config import Settings


class LLMClient:
    """统一 LLM 客户端：OpenAI 兼容端点，按 deepseek → qwen → ollama 顺序降级。

    chat_json 返回解析后的 dict；全部 provider 失败返回 None。
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.mode = "none"
        self._clients: list[tuple[str, object]] = []
        try:
            from openai import OpenAI
        except ImportError:
            OpenAI = None
        if OpenAI is None:
            self.available = False
            return
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
        if settings.ollama_enabled and settings.ollama_base_url:
            self._clients.append(("ollama", OpenAI(
                api_key="ollama", base_url=settings.ollama_base_url, timeout=settings.llm_timeout)))
            if self.mode == "none":
                self.mode = "ollama"
        self.available = bool(self._clients)

    def _model_for(self, provider: str) -> str:
        if provider == "qwen":
            return "qwen-plus"
        if provider == "ollama":
            return "qwen2.5:7b"
        return self.settings.llm_model

    def _try_call(self, provider: str, client, model: str, system: str, user: str) -> dict | None:
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
            last = self._try_call(provider, client, self._model_for(provider), system, user)
            if last is not None:
                self.mode = provider
                return last
        return None


class FakeLLM(LLMClient):
    """测试用：按序返回固定响应，用完返回 None。"""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.mode = "fake"
        self.available = True

    def chat_json(self, system, user, example):
        if not self._responses:
            return None
        return self._responses.pop(0)
