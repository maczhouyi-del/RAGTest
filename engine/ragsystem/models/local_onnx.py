import hashlib
import json
from pathlib import Path

from ragsystem.domain.errors import EngineError


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            result.update(data)
    return result.hexdigest()


class LocalE5:
    """The explicitly approved E5 ONNX candidate, CPU only, no Hub client calls."""

    def __init__(self, directory: Path):
        import numpy as np
        import onnxruntime as ort
        import tokenizers
        from tokenizers import Tokenizer

        directory = Path(directory)
        manifest = json.loads((directory / "manifest.json").read_text())
        if (
            manifest["repository"] != "intfloat/multilingual-e5-small"
            or manifest["revision"] != "614241f622f53c4eeff9890bdc4f31cfecc418b3"
        ):
            raise EngineError("MODEL_UNSUPPORTED")
        hashes = {row["path"]: row["sha256"] for row in manifest["files"]}
        if (
            hashes.get("onnx/model.onnx")
            != "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665"
            or hashes.get("tokenizer.json")
            != "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"
        ):
            raise EngineError("MODEL_HASH_MISMATCH")
        # Do not allow a manifest to escape its resource directory.
        for name in ("onnx/model.onnx", "tokenizer.json", "config.json"):
            path = directory / name
            if not path.is_file() or path.is_symlink() or file_hash(path) != hashes.get(name):
                raise EngineError("MODEL_HASH_MISMATCH")
        config = json.loads((directory / "config.json").read_text())
        self.dimension = config["hidden_size"]
        if self.dimension != 384:
            raise EngineError("MODEL_DIMENSION_INVALID")
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding(pad_id=config["pad_token_id"], pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        ort.disable_telemetry_events()
        self.session = ort.InferenceSession(
            str(directory / "onnx/model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.fingerprint = {
            "model": manifest["repository"],
            "revision": manifest["revision"],
            "weight_sha256": hashes["onnx/model.onnx"],
            "tokenizer_sha256": hashes["tokenizer.json"],
            "config_sha256": hashes["config.json"],
            "dimension": self.dimension,
            "metric": "cosine",
            "normalization": "l2",
            "preprocessing": {
                "algorithm": "e5_masked_mean_l2_v1",
                "max_length": 512,
                "query_prefix": "query: ",
                "document_prefix": "passage: ",
                "runtime": "onnxruntime-" + ort.__version__,
                "provider": "CPUExecutionProvider",
                "tokenizers_version": tokenizers.__version__,
                "numpy_version": np.__version__,
                "padding_id": config["pad_token_id"],
            },
        }
        self.calls = 0
        self.encoded_texts = 0
        self.truncated_texts = 0

    def encode(self, texts: list[str], *, query=False):
        import numpy as np

        if not 1 <= len(texts) <= 16 or any(
            not isinstance(t, str) or len(t) > 20000 for t in texts
        ):
            raise EngineError("EMBEDDING_INPUT_INVALID")
        prefix = "query: " if query else "passage: "
        encoded = self.tokenizer.encode_batch([prefix + text for text in texts])
        values = {
            "input_ids": np.array([e.ids for e in encoded], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encoded], dtype=np.int64),
            "token_type_ids": np.array([e.type_ids for e in encoded], dtype=np.int64),
        }
        inputs = {}
        for entry in self.session.get_inputs():
            if entry.name not in values:
                raise EngineError("MODEL_INPUT_UNSUPPORTED")
            inputs[entry.name] = values[entry.name].astype(
                np.int32 if entry.type == "tensor(int32)" else np.int64
            )
        hidden = self.session.run(None, inputs)[0]
        if hidden.ndim != 3 or hidden.shape[-1] != self.dimension:
            raise EngineError("MODEL_OUTPUT_INVALID")
        mask = values["attention_mask"][..., None].astype(np.float32)
        vectors = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
        norm = np.linalg.norm(vectors, axis=1, keepdims=True)
        if (norm <= 0).any() or not np.isfinite(vectors).all():
            raise EngineError("MODEL_OUTPUT_INVALID")
        vectors = (vectors / norm).astype(np.float32)
        self.calls += 1
        self.encoded_texts += len(texts)
        self.truncated_texts += sum(bool(e.overflowing) for e in encoded)
        return vectors.tolist()
