class EngineError(Exception):
    """A safe, stable error code. Never include paths, tokens or source text."""

    def __init__(self, code: str, *, status: int = 400, retriable: bool = False):
        self.code = code
        self.status = status
        self.retriable = retriable
        super().__init__(code)
