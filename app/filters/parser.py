from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.core.models import (
    AccountBanStatus,
    AccountExistsStatus,
    InventoryVisibilityStatus,
    SyncStatus,
)
from app.filters.criteria import DateFilter, FilterCriteria, RangeFilter

_TOKEN_RE = re.compile(r'(\w+)\s*(>=|<=|>|<|=)\s*(.+)')
_DURATION_RE = re.compile(r'^(\d+)([hd])$')

_ENUM_FIELDS: dict[str, type] = {
    'account_exists_status': AccountExistsStatus,
    'account_ban_status': AccountBanStatus,
    'inventory_visibility_status': InventoryVisibilityStatus,
    'sync_status': SyncStatus,
}

_BOOL_FIELDS: frozenset[str] = frozenset({
    'has_items',
    'has_marketable_items',
    'has_tradable_items',
    'inventory_empty',
    'inventory_non_empty',
    'stale',
    'failed_last_sync',
})

_RANGE_FIELDS: frozenset[str] = frozenset({'items_count_total', 'items_count_distinct'})

_DATE_FIELDS: frozenset[str] = frozenset({'last_successful_sync_at', 'last_sync_attempt_at'})


class FilterParseError(ValueError):
    """Raised when a filter expression string cannot be parsed."""


def _parse_range(field: str, op: str, value: str) -> RangeFilter:
    try:
        n = int(value)
    except ValueError:
        raise FilterParseError(f'Expected integer for field {field!r}, got {value!r}')
    match op:
        case '=':
            return RangeFilter(gte=n, lte=n)
        case '>=':
            return RangeFilter(gte=n)
        case '<=':
            return RangeFilter(lte=n)
        case '>':
            return RangeFilter(gt=n)
        case '<':
            return RangeFilter(lt=n)
    raise FilterParseError(f'Unsupported operator {op!r} for field {field!r}')


def _parse_date(field: str, op: str, value: str) -> DateFilter:
    m = _DURATION_RE.match(value)
    if not m:
        raise FilterParseError(f'Expected duration like 48h or 7d for field {field!r}, got {value!r}')
    n = int(m.group(1))
    unit = m.group(2)
    delta = timedelta(hours=n) if unit == 'h' else timedelta(days=n)
    threshold = datetime.now(timezone.utc) - delta
    match op:
        case '<':
            return DateFilter(before=threshold)
        case '>':
            return DateFilter(after=threshold)
        case _:
            raise FilterParseError(
                f'Operator {op!r} not supported for duration values on field {field!r}. Use < or >'
            )


def parse_filter(expr: str) -> FilterCriteria:
    """
    Parse a filter expression string into FilterCriteria.

    Raises FilterParseError on invalid syntax.
    """
    tokens = [t.strip() for t in expr.split(',') if t.strip()]
    if not tokens:
        raise FilterParseError('Empty filter expression')

    kwargs: dict = {}
    for token in tokens:
        m = _TOKEN_RE.match(token)
        if not m:
            raise FilterParseError(f'Invalid filter token: {token!r}')

        field, op, value = m.group(1), m.group(2), m.group(3).strip()

        if field in _ENUM_FIELDS:
            if op != '=':
                raise FilterParseError(f'Only = is supported for field {field!r}')
            try:
                kwargs[field] = _ENUM_FIELDS[field](value)
            except ValueError:
                valid = [e.value for e in _ENUM_FIELDS[field]]
                raise FilterParseError(
                    f'Invalid value {value!r} for field {field!r}. Valid: {valid}'
                )
        elif field in _BOOL_FIELDS:
            if op != '=':
                raise FilterParseError(f'Only = is supported for field {field!r}')
            if value.lower() not in ('true', 'false'):
                raise FilterParseError(f'Expected true or false for field {field!r}, got {value!r}')
            kwargs[field] = value.lower() == 'true'
        elif field in _RANGE_FIELDS:
            kwargs[field] = _parse_range(field, op, value)
        elif field in _DATE_FIELDS:
            kwargs[field] = _parse_date(field, op, value)
        else:
            all_fields = sorted(
                list(_ENUM_FIELDS) + list(_BOOL_FIELDS) + list(_RANGE_FIELDS) + list(_DATE_FIELDS)
            )
            raise FilterParseError(f'Unknown filter field: {field!r}. Available: {all_fields}')

    return FilterCriteria(**kwargs)
