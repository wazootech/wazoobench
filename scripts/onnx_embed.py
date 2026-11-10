#!/usr/bin/env python3
"""Batch-embed texts with a sentence-transformers ONNX model.

Reads JSON {model: <onnx path>, tokenizer: <dir>, texts: [...]} on stdin,
writes {"embeddings": [[...], ...]} on stdout. Mean-pools the token
outputs (sentence-transformers pooling) and L2-normalizes.
"""
import json
import sys
import numpy as np
from tokenizers import Tokenizer
import onnxruntime as ort


def main() -> int:
    req = json.load(sys.stdin)
    tok = Tokenizer.from_file(f"{req['tokenizer']}/tokenizer.json")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    sess = ort.InferenceSession(req["model"], opts, providers=["CPUExecutionProvider"])
    inputs = {i.name for i in sess.get_inputs()}

    def embed(texts):
        encs = [tok.encode(t) for t in texts]
        maxlen = max(len(e.ids) for e in encs)
        ids = np.zeros((len(encs), maxlen), dtype=np.int64)
        mask = np.zeros((len(encs), maxlen), dtype=np.int64)
        for i, e in enumerate(encs):
            ids[i, : len(e.ids)] = e.ids
            mask[i, : len(e.ids)] = 1
        feed = {}
        if "input_ids" in inputs:
            feed["input_ids"] = ids
        if "attention_mask" in inputs:
            feed["attention_mask"] = mask
        if "token_type_ids" in inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        out = sess.run(None, feed)[0]
        m = mask[:, :, None].astype(np.float32)
        vecs = (out * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
        return vecs / np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9, None)

    out = []
    batch = 64
    texts = req["texts"]
    for i in range(0, len(texts), batch):
        vecs = embed(texts[i : i + batch])
        out.extend(vecs.tolist())
    json.dump({"embeddings": out}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
