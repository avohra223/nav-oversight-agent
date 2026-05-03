"""Prompt versioning: hash the system prompt + defect checklist so each
agent run records which prompt version produced it.

A change to any prompt file rolls the hash, making it trivial to diff
behavior across prompt revisions without re-reading source.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path


_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=1)
def system_prompt_text() -> str:
    return (_PROMPTS_DIR / "system_prompt.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def defect_checklist_text() -> str:
    return (_PROMPTS_DIR / "defect_checklist.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def prompt_version() -> str:
    """Short hash combining system prompt + defect checklist."""
    h = hashlib.sha256()
    h.update(system_prompt_text().encode("utf-8"))
    h.update(b"\x00")
    h.update(defect_checklist_text().encode("utf-8"))
    return h.hexdigest()[:12]


def reload() -> None:
    """Bust the cache; tests use this after editing prompts on disk."""
    system_prompt_text.cache_clear()
    defect_checklist_text.cache_clear()
    prompt_version.cache_clear()
