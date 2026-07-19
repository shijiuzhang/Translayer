"""Job model and in-memory store with a simple state machine.

States: queued -> parsing -> enriching -> localizing -> review -> rendering -> done
(or error). For the MVP jobs live in memory with assets in a per-job temp dir;
swap for SQLite/Redis in a later phase.
"""

from __future__ import annotations

import os
import tempfile
import threading
import uuid
from dataclasses import dataclass, field

from translayer.config import settings
from translayer.ir.models import DocumentIR

STATES = [
    "queued",
    "parsing",
    "screening",
    "localizing_text",
    "image_review",
    "localizing_images",
    "review",
    "rendering",
    "done",
    "error",
]


@dataclass
class ImageDecision:
    suggested_action: str
    action: str | None
    source: str = "suggested"

    def public(self) -> dict:
        return {
            "suggested_action": self.suggested_action,
            "action": self.action,
            "source": self.source,
        }


@dataclass
class Job:
    id: str
    input_path: str
    source_lang: str
    target_lang: str
    translation_engine: str
    ocr_engine: str
    inpaint_engine: str
    images: bool = True
    state: str = "queued"
    error: str | None = None
    ir: DocumentIR | None = None
    output_path: str | None = None
    work_dir: str = ""
    image_decisions: dict[str, ImageDecision] = field(default_factory=dict)
    image_plan_locked: bool = False
    image_budget_usd: float = 0.0
    estimated_image_cost_usd: float = 0.077
    paid_image_calls: int = 0
    slide_preview_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def initialize_image_decisions(self) -> None:
        if self.ir is None:
            return
        route_actions = {
            "whole_image": "whole_image",
            "region": "region",
            "skip": "preserve",
            "reuse": "reuse",
            "review": None,
        }
        self.image_decisions = {}
        for image in self.ir.resources.images:
            route = image.selection.route if image.selection else "review"
            action = route_actions[route]
            self.image_decisions[image.id] = ImageDecision(
                suggested_action=action or "preserve",
                action=action,
            )

    def unresolved_images(self) -> int:
        return sum(decision.action is None for decision in self.image_decisions.values())

    def planned_paid_calls(self) -> int:
        if self.ir is None:
            return 0
        return sum(
            decision.action == "whole_image"
            and (
                (image := self.ir.image_by_id(image_id)) is None
                or image.localization_validation.status != "passed"
            )
            for image_id, decision in self.image_decisions.items()
        )

    def estimated_image_spend(self) -> float:
        return round(self.planned_paid_calls() * self.estimated_image_cost_usd, 4)

    def public(self) -> dict:
        return {
            "id": self.id,
            "state": self.state,
            "error": self.error,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "blocks": len(self.ir.blocks) if self.ir else 0,
            "images": len(self.ir.resources.images) if self.ir else 0,
            "has_output": bool(self.output_path and os.path.exists(self.output_path)),
            "image_unresolved": self.unresolved_images(),
            "image_plan_locked": self.image_plan_locked,
            "planned_paid_calls": self.planned_paid_calls(),
            "estimated_image_spend_usd": self.estimated_image_spend(),
        }


class JobStore:
    def __init__(self, root: str | None = None):
        self.root = root or settings.jobs_dir
        os.makedirs(self.root, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, upload_bytes: bytes, filename: str, source_lang: str,
               target_lang: str, **engines: str) -> Job:
        job_id = uuid.uuid4().hex[:12]
        work_dir = tempfile.mkdtemp(prefix=f"job_{job_id}_", dir=self.root)
        ext = os.path.splitext(filename)[1] or ".pptx"
        input_path = os.path.join(work_dir, f"input{ext}")
        with open(input_path, "wb") as fh:
            fh.write(upload_bytes)
        job = Job(
            id=job_id,
            input_path=input_path,
            source_lang=source_lang,
            target_lang=target_lang,
            translation_engine=engines.get("translation_engine") or settings.translation_engine,
            ocr_engine=engines.get("ocr_engine") or settings.ocr_engine,
            inpaint_engine=engines.get("inpaint_engine") or settings.inpaint_engine,
            images=engines.get("images", True),
            work_dir=work_dir,
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        return list(self._jobs.values())
