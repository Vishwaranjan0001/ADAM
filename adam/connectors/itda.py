"""Connector for ITDA-curated official sample sets and departmental batch folders."""

import hashlib
import json
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Iterator, Optional, Dict, Any

from adam.connectors.base import BaseConnector, DiscoveredItem, FetchResult
from adam.db.models import Source
from adam.vocabularies import DocType, DepartmentId, AuthorityLevel, Classification


class ITDASampleBatchConnector(BaseConnector):
    """Loads curated batches of real representative Government Orders provided by ITDA/departments.

    Strictly enforces boundary: processes authentic departmental files with provenance,
    never fabricating data or pulling from unverified mirrors.
    """

    def __init__(self, batch_dir: Path | str):
        self.batch_dir = Path(batch_dir)

    def discover(self, source: Source) -> Iterator[DiscoveredItem]:
        """Scan authorized batch directory for genuine PDF files and optional sidecar metadata."""
        if not self.batch_dir.exists():
            return

        for path in sorted(self.batch_dir.glob("**/*")):
            if path.is_file() and path.suffix.lower() == ".pdf":
                sidecar_meta = self._load_sidecar_meta(path)
                file_url = f"file://{path.resolve()}"

                title = sidecar_meta.get("title") or path.stem.replace("_", " ").replace("-", " ")
                doc_type = sidecar_meta.get("doc_type") or DocType.GO.value
                dept_id = sidecar_meta.get("department_id") or source.department_id
                auth_level = sidecar_meta.get("authority_level") or AuthorityLevel.DEPARTMENTAL_SECRETARY.value
                go_num = sidecar_meta.get("go_number")

                displayed_date = None
                if sidecar_meta.get("date"):
                    try:
                        displayed_date = date.fromisoformat(sidecar_meta["date"])
                    except Exception:
                        pass

                yield DiscoveredItem(
                    source_url=file_url,
                    title=title,
                    doc_type=doc_type,
                    department_id=dept_id,
                    displayed_date=displayed_date,
                    go_number=go_num,
                    authority_level=auth_level,
                    classification=source.access_classification or Classification.PUBLIC.value,
                    metadata={
                        "is_itda_curated_sample": True,
                        "batch_path": str(path),
                        "sidecar_metadata": sidecar_meta,
                    },
                )

    def fetch(self, item: DiscoveredItem) -> FetchResult:
        """Read original immutable bytes from local curated batch file."""
        if item.source_url.startswith("file://"):
            local_path = Path(item.source_url[7:])
        else:
            local_path = Path(item.source_url)

        data = local_path.read_bytes()
        return FetchResult(
            source_url=item.source_url,
            data=data,
            http_status=200,
            http_headers={"content-type": "application/pdf"},
            retrieved_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _load_sidecar_meta(pdf_path: Path) -> Dict[str, Any]:
        """Look for optional sidecar json (e.g. order-1.json next to order-1.pdf)."""
        json_path = pdf_path.with_suffix(".json")
        if json_path.exists():
            try:
                return json.loads(json_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
