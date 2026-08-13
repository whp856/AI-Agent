from .stage_base import StageBase
from ..tools.validator import validate_chain


class S7Validate(StageBase):
    name = "s7"

    def run(self):
        rec = self.stage("s7")
        rec.status = "running"
        self.emit("stage.started", {})
        try:
            valid_rids = {r.review_id for r in self.snapshot.reviews}
            valid_fids = {f.finding_id for f in self.snapshot.findings}
            valid_reqs = {r.req_id for r in self.snapshot.requirements}

            # 修正动作 1：孤儿引用从结论中清除；全部无效 → 标记 assumption
            for f in list(self.snapshot.findings):
                clean = [x for x in f.supporting_review_ids if x in valid_rids]
                if clean != f.supporting_review_ids:
                    f.supporting_review_ids = clean
                    self.snapshot.corrections.append({
                        "target": f.finding_id, "action": "清除孤儿引用",
                        "reason": f"移除 {len(f.supporting_review_ids) - len(clean)} 条无效评论引用",
                    })
                    if not clean:
                        f.kind = "assumption"
                        f.uncertainty = (f.uncertainty + "；原引用缺失已修正").strip()

            # 修正动作 2：无有效证据引用的需求 → 删除
            for r in list(self.snapshot.requirements):
                if not any(x in valid_fids for x in r.evidence_refs):
                    self.snapshot.requirements.remove(r)
                    self.snapshot.corrections.append({
                        "target": r.req_id, "action": "删除",
                        "reason": "无有效证据引用（孤儿或被清除）",
                    })

            # 修正动作 3：关联需求不存在的用例 → 删除
            for c in list(self.snapshot.test_cases):
                if not any(x in valid_reqs for x in c.req_refs):
                    self.snapshot.test_cases.remove(c)
                    self.snapshot.corrections.append({
                        "target": c.case_id, "action": "删除",
                        "reason": "关联需求不存在",
                    })

            report = validate_chain(self.snapshot)
            self.snapshot.validation_report = report
            rec.summary = f"校验{'通过' if report['passed'] else '存在未决问题'}；修正 {len(self.snapshot.corrections)} 项"
            self.emit("stage.output", {
                "validation_report": report,
                "corrections": self.snapshot.corrections,
            })
        except Exception as e:
            rec.status = "failed"
            rec.error = str(e)
        if rec.status == "running":
            rec.status = "done"
