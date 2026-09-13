"""Hardware environment profiles, resource budgets, and storage cache governance.

Per Phase 04 specification:
- 'Resource budgets:
   - 8GB MacBook Air: one Q4 1.7–4B model, 2k–4k context, single request; local embedding model;
     queued OCR; reserve >=2GB macOS headroom; do not run OCR/indexing while chatting.
   - Team/dev server: same model service, CPU benchmark; 8–16GB RAM preferred; model cache may be 10–20GB.
   - Government production: approved GPU/CPU nodes after measured load test; independent workers;
     30–40GB disk cache ceiling for approved models, OCR and embeddings; size RAM/VRAM from tests.'
- '“30–40GB” is a storage budget, not evidence that an 8GB laptop can run it all. Suggested pilot cache:
   generator 3–4GB, embeddings <1GB, reranker <1GB, OCR assets 1–3GB, originals/index determined by corpus;
   cap cache and use one active heavy worker.'
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from adam.config import STORAGE_DIR
from adam.vocabularies import EnvironmentProfileType


@dataclass
class EnvironmentProfile:
    """Hardware profile configuration enforcing strict RAM, context, and storage constraints."""
    profile_type: EnvironmentProfileType
    description: str
    ram_total_gb: float
    macos_headroom_gb: float
    max_active_requests: int
    max_context_window: int
    disk_cache_ceiling_gb: float
    generator_budget_gb: float
    embeddings_budget_gb: float
    reranker_budget_gb: float
    ocr_assets_budget_gb: float
    enforce_heavy_worker_mutual_exclusion: bool

    @property
    def usable_ram_gb(self) -> float:
        return max(1.0, self.ram_total_gb - self.macos_headroom_gb)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_type": str(self.profile_type),
            "description": self.description,
            "ram_total_gb": self.ram_total_gb,
            "macos_headroom_gb": self.macos_headroom_gb,
            "usable_ram_gb": self.usable_ram_gb,
            "max_active_requests": self.max_active_requests,
            "max_context_window": self.max_context_window,
            "disk_cache_ceiling_gb": self.disk_cache_ceiling_gb,
            "generator_budget_gb": self.generator_budget_gb,
            "embeddings_budget_gb": self.embeddings_budget_gb,
            "reranker_budget_gb": self.reranker_budget_gb,
            "ocr_assets_budget_gb": self.ocr_assets_budget_gb,
            "enforce_heavy_worker_mutual_exclusion": self.enforce_heavy_worker_mutual_exclusion,
        }


# Canonical Environment Profiles
MACBOOK_AIR_8GB_PROFILE = EnvironmentProfile(
    profile_type=EnvironmentProfileType.MACBOOK_AIR_8GB,
    description="MacBook Air 8GB Unified Memory pilot profile",
    ram_total_gb=8.0,
    macos_headroom_gb=2.0,  # reserve >=2GB macOS headroom
    max_active_requests=1,   # single request concurrency
    max_context_window=4096, # 2k-4k context window
    disk_cache_ceiling_gb=10.0,
    generator_budget_gb=3.5,
    embeddings_budget_gb=0.8,
    reranker_budget_gb=0.8,
    ocr_assets_budget_gb=2.5,
    enforce_heavy_worker_mutual_exclusion=True,  # do not run OCR/indexing while chatting
)

DEV_SERVER_PROFILE = EnvironmentProfile(
    profile_type=EnvironmentProfileType.DEV_SERVER,
    description="Team/Dev Server 8-16GB RAM benchmark profile",
    ram_total_gb=16.0,
    macos_headroom_gb=2.0,
    max_active_requests=4,
    max_context_window=8192,
    disk_cache_ceiling_gb=20.0,  # 10-20GB model cache
    generator_budget_gb=6.0,
    embeddings_budget_gb=1.5,
    reranker_budget_gb=1.5,
    ocr_assets_budget_gb=4.0,
    enforce_heavy_worker_mutual_exclusion=False,
)

GOV_PRODUCTION_PROFILE = EnvironmentProfile(
    profile_type=EnvironmentProfileType.GOV_PRODUCTION,
    description="Government Production GPU/CPU nodes with independent workers",
    ram_total_gb=64.0,
    macos_headroom_gb=4.0,
    max_active_requests=16,
    max_context_window=16384,
    disk_cache_ceiling_gb=40.0,  # 30-40GB disk cache ceiling
    generator_budget_gb=12.0,
    embeddings_budget_gb=3.0,
    reranker_budget_gb=3.0,
    ocr_assets_budget_gb=10.0,
    enforce_heavy_worker_mutual_exclusion=False,
)


class ResourceBudgetManager:
    """Monitors and enforces system memory headroom and disk cache storage ceilings."""

    def __init__(self, profile: Optional[EnvironmentProfile] = None, storage_dir: Optional[Path] = None):
        self.profile = profile or MACBOOK_AIR_8GB_PROFILE
        self.storage_dir = storage_dir or STORAGE_DIR

    def set_profile(self, profile: EnvironmentProfile) -> None:
        self.profile = profile

    def get_cache_size_bytes(self) -> int:
        """Calculate current disk cache footprint in bytes across cache, models, and embeddings directories."""
        subdirs = ["cache", "models", "embeddings", "ocr"]
        total_size = 0
        for sub in subdirs:
            target = self.storage_dir / sub
            if target.exists():
                for dirpath, _, filenames in os.walk(target):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        try:
                            total_size += os.path.getsize(fp)
                        except OSError:
                            pass
        return total_size

    def check_cache_ceiling(self) -> Tuple[bool, float, float]:
        """Verify that disk cache is strictly under the profile ceiling.

        Returns: (is_within_ceiling, current_gb, ceiling_gb)
        """
        current_bytes = self.get_cache_size_bytes()
        current_gb = current_bytes / (1024 ** 3)
        ceiling_gb = self.profile.disk_cache_ceiling_gb
        is_ok = current_gb <= ceiling_gb
        return is_ok, current_gb, ceiling_gb

    def check_mac_headroom(self) -> Dict[str, Any]:
        """Verify memory headroom constraint for pilot deployment."""
        usable_ram = self.profile.usable_ram_gb
        headroom_reserved = self.profile.macos_headroom_gb
        system_physical_ram_gb = None
        try:
            pagesize = os.sysconf("SC_PAGE_SIZE")
            phys_pages = os.sysconf("SC_PHYS_PAGES")
            system_physical_ram_gb = round((pagesize * phys_pages) / (1024 ** 3), 1)
        except (ValueError, AttributeError, OSError):
            pass

        return {
            "profile": str(self.profile.profile_type),
            "ram_total_gb": self.profile.ram_total_gb,
            "system_physical_ram_gb": system_physical_ram_gb,
            "headroom_reserved_gb": headroom_reserved,
            "usable_ram_gb": usable_ram,
            "headroom_satisfied": headroom_reserved >= 2.0,
        }

    def get_budget_report(self) -> Dict[str, Any]:
        """Produce complete diagnostic report of resource budgets."""
        cache_ok, cache_gb, ceiling_gb = self.check_cache_ceiling()
        headroom = self.check_mac_headroom()
        return {
            "profile": self.profile.to_dict(),
            "disk_cache": {
                "current_gb": round(cache_gb, 3),
                "ceiling_gb": ceiling_gb,
                "is_within_ceiling": cache_ok,
            },
            "memory_headroom": headroom,
        }
