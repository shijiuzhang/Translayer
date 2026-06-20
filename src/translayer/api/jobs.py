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
from dataclasses import dataclass

from translayer.config import settings
from translayer.ir.models import DocumentIR

STATES = ["queued", "parsing", "enriching", "localizing", "review", "rendering", "done", "error"]


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
