from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.models import InventoryVisibilityStatus, SyncStatus
from app.filters.criteria import DateFilter, FilterCriteria, RangeFilter


def expand_aliases(criteria: FilterCriteria, stale_threshold_hours: int) -> FilterCriteria:
    """Expand alias filter fields into their concrete equivalents. Clears alias fields after expansion."""
    updates: dict = {}

    if criteria.inventory_empty is True:
        updates['inventory_visibility_status'] = InventoryVisibilityStatus.public
        updates['items_count_total'] = RangeFilter(lte=0)
        updates['inventory_empty'] = None

    if criteria.inventory_non_empty is True:
        updates['items_count_total'] = RangeFilter(gte=1)
        updates['inventory_non_empty'] = None

    if criteria.stale is True:
        threshold = datetime.now(timezone.utc) - timedelta(hours=stale_threshold_hours)
        updates['last_successful_sync_at'] = DateFilter(before=threshold)
        updates['stale'] = None

    if criteria.failed_last_sync is True:
        updates['sync_status'] = SyncStatus.failed
        updates['failed_last_sync'] = None

    if not updates:
        return criteria

    return criteria.model_copy(update=updates)
