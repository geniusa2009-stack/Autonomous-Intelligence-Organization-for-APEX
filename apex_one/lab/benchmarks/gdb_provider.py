"""Phase 26 — GraphicDesignBench (lica-gdb) custom provider backed by the APEX ComputeBroker.

Every GDB inference goes through the $0 firewall with purpose=evaluation, so a local open-weight model (llama.cpp)
can be measured on GDB tasks without any paid route. Use with:

    gdb eval --suite v0-smoke --dataset-root <bundle> --provider custom \\
        --custom-entry apex_one.lab.benchmarks.gdb_provider:APEXBrokerModel \\
        --custom-init-kwargs '{"model_id": "gemma-multimodal"}' --custom-modality text_and_image

Honesty: the full GDB dataset lives on the Hugging Face Hub, which is unreachable from this container; runs here use
the small verification bundle shipped inside the package, so scores are a SMOKE measurement, not a leaderboard
result.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from gdb.models.base import BaseModel, Modality, ModelInput, ModelOutput
from PIL import Image


# GDB inputs are arbitrary design images (not A4 pages), so they keep their own box-bound normalisation; it is
# recorded with every GDB result (it is NOT the vision-judge input contract).
GDB_PREPROCESS = "box-bound thumbnail 768x768, Pillow default bicubic, RGB PNG"


def _png_b64(img: Any) -> str:
    if isinstance(img, (str, Path)):
        im = Image.open(img)
    elif isinstance(img, bytes):
        im = Image.open(io.BytesIO(img))
    else:
        im = img
    im = im.convert("RGB")
    im.thumbnail((768, 768))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


class APEXBrokerModel(BaseModel):
    modality = Modality.TEXT_AND_IMAGE

    def __init__(self, model_id: str, max_tokens: int = 512, timeout: float = 900.0, **_: Any):
        from apex_one.compute.broker import ComputeBroker

        self.model_id, self.max_tokens, self.timeout = model_id, max_tokens, timeout
        self.name = f"apex-broker:{model_id}"
        self.broker = ComputeBroker()

    def predict(self, inp: ModelInput) -> ModelOutput:
        from apex_one.compute.providers import ChatMessage
        from apex_one.core.schemas.compute import CapabilityRequest

        images = []
        for img in inp.images or []:
            try:
                images.append(_png_b64(img))
            except Exception:  # noqa: BLE001 — unreadable/SVG inputs are passed as text only
                continue
        req = CapabilityRequest(task="bench.gdb", vision=bool(images), purpose="evaluation", model_id=self.model_id)
        res = self.broker.complete(req, [ChatMessage("user", inp.text, images_b64_png=images)],
                                   max_tokens=self.max_tokens, temperature=0.0, timeout=self.timeout)
        # A call that did not run (server down, timeout, no route) or produced nothing is a FAILED sample, never an
        # empty prediction that GDB would score as a wrong answer (0) — raising makes GDB count it as a failure.
        if not res.executed:
            from apex_one.compute.benchmark.council import call_failure_kind

            raise RuntimeError(f"ERROR {call_failure_kind(res) or 'NOT_EXECUTED'}: model call not executed: "
                               f"{res.decision.outcome.value}: {res.decision.reasons[:2]}")
        if not (res.text or "").strip():
            raise RuntimeError("ERROR EMPTY_OUTPUT: empty model output (NOT_MEASURED)")
        return ModelOutput(text=res.text, raw={"model": res.model_id})
