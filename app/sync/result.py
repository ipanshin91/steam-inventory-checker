from __future__ import annotations

from pydantic import BaseModel

from app.core.models import Account, SyncErrorCategory, SyncStatus


class SyncResult(BaseModel):
    """Outcome of syncing a single account."""

    vanity_name: str
    status: SyncStatus
    error_category: SyncErrorCategory
    error_message: str = ''
    items_fetched: int = 0
    duration_ms: int
    updated_account: Account


class SyncSummary(BaseModel):
    """Aggregate outcome of a batch sync operation."""

    total: int
    success: int
    partial_success: int
    failed: int
    skipped: int
    duration_ms: int
    errors_by_category: dict[SyncErrorCategory, int]
    failed_results: list[SyncResult] = []
