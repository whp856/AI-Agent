"""阶段基类：所有阶段共享的上下文与事件接口。"""


class StageBase:
    name = "stage"

    def __init__(self, ctx: dict):
        self.ctx = ctx
        self.snapshot = ctx["snapshot"]
        self.llm = ctx["llm"]
        self.on_event = ctx["on_event"]
        self.mode = ctx["model_mode"]  # "llm" | "degraded"

    def emit(self, etype: str, data: dict):
        self.on_event({"type": etype, "stage": self.name, "data": data})

    def stage(self, name: str):
        for s in self.snapshot.stages:
            if s.name == name:
                return s
        raise KeyError(f"stage {name} not found")

    def active_reviews(self):
        return [r for r in self.snapshot.reviews if not r.is_duplicate]
