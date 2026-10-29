"""Small per-run stage diagnostics; no prompts, keys or document text in this trace."""

import time


class PipelineTrace:
    def __init__(self):
        self.started = time.perf_counter()
        self.current = None
        self.current_started = self.started
        self.data = {
            "version": "answer-pipeline-v1",
            "stages": [],
            "elapsed_ms": 0,
            "model_attempts": {"answer": 0, "support": 0, "relevance": 0},
        }

    def start(self, stage, input_count=None):
        self.finish()
        self.current = {"stage": stage, "status": "running"}
        if input_count is not None:
            self.current["input_count"] = input_count
        self.data["stages"].append(self.current)
        self.current_started = time.perf_counter()

    def finish(self, status="completed", output_count=None):
        now = time.perf_counter()
        if self.current and (self.current["status"] == "running" or status == "failed"):
            self.current.update(status=status, elapsed_ms=(now - self.current_started) * 1000)
            if output_count is not None:
                self.current["output_count"] = output_count
        self.data["elapsed_ms"] = (now - self.started) * 1000

    def model_attempt(self, task):
        self.data["model_attempts"][task] += 1
