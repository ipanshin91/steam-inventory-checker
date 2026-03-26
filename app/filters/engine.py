from __future__ import annotations

from datetime import datetime, timezone

from app.core.models import Account, SyncStatus
from app.filters.criteria import DateFilter, FilterCriteria, RangeFilter, SortSpec

_SYNC_STATUS_ORDER: dict[SyncStatus, int] = {
    SyncStatus.success: 0,
    SyncStatus.partial_success: 1,
    SyncStatus.failed: 2,
    SyncStatus.never_synced: 3,
}

_DT_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _check_range(value: int, rf: RangeFilter) -> bool:
    if rf.gte is not None and value < rf.gte:
        return False
    if rf.lte is not None and value > rf.lte:
        return False
    if rf.gt is not None and value <= rf.gt:
        return False
    if rf.lt is not None and value >= rf.lt:
        return False
    return True


def _check_date(value: datetime | None, df: DateFilter) -> bool:
    if value is None:
        return False
    if df.before is not None and value >= df.before:
        return False
    if df.after is not None and value <= df.after:
        return False
    return True


def _matches(account: Account, criteria: FilterCriteria) -> bool:
    if criteria.account_exists_status is not None:
        if account.account_exists_status != criteria.account_exists_status:
            return False
    if criteria.account_ban_status is not None:
        if account.account_ban_status != criteria.account_ban_status:
            return False
    if criteria.inventory_visibility_status is not None:
        if account.inventory_visibility_status != criteria.inventory_visibility_status:
            return False
    if criteria.sync_status is not None:
        if account.sync_status != criteria.sync_status:
            return False
    if criteria.has_items is not None:
        if criteria.has_items != (account.items_count_total > 0):
            return False
    if criteria.has_marketable_items is not None:
        if criteria.has_marketable_items != (account.marketable_items_count > 0):
            return False
    if criteria.items_count_total is not None:
        if not _check_range(account.items_count_total, criteria.items_count_total):
            return False
    if criteria.items_count_distinct is not None:
        if not _check_range(account.items_count_distinct, criteria.items_count_distinct):
            return False
    if criteria.last_successful_sync_at is not None:
        if not _check_date(account.last_successful_sync_at, criteria.last_successful_sync_at):
            return False
    if criteria.last_sync_attempt_at is not None:
        if not _check_date(account.last_sync_attempt_at, criteria.last_sync_attempt_at):
            return False
    return True


def apply_filter(accounts: list[Account], criteria: FilterCriteria) -> list[Account]:
    """Return accounts matching all non-None criteria fields. Alias fields must be expanded first."""
    return [a for a in accounts if _matches(a, criteria)]


def apply_sort(accounts: list[Account], spec: SortSpec) -> list[Account]:
    """Return a sorted copy of accounts according to spec."""
    reverse = spec.direction == 'desc'

    if spec.field == 'items_count_total':
        key = lambda a: a.items_count_total
    elif spec.field == 'items_count_distinct':
        key = lambda a: a.items_count_distinct
    elif spec.field == 'last_successful_sync_at':
        key = lambda a: a.last_successful_sync_at or _DT_MIN
    elif spec.field == 'sync_status':
        key = lambda a: _SYNC_STATUS_ORDER.get(a.sync_status, 99)
    else:
        key = lambda a: 0.0

    return sorted(accounts, key=key, reverse=reverse)


def preview_count(accounts: list[Account], criteria: FilterCriteria) -> int:
    """Return the count of accounts that would match the given filter."""
    return sum(1 for a in accounts if _matches(a, criteria))
