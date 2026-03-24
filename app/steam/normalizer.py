from __future__ import annotations

from app.core.models import Item
from app.steam.inventory import InventoryData


def normalize(inv: InventoryData) -> list[Item]:
    """Convert raw inventory assets and descriptions into a deduplicated list of Items."""
    desc_map: dict[str, dict] = {d['classid']: d for d in inv.raw_descriptions}

    qty_map: dict[str, int] = {}
    for asset in inv.raw_assets:
        classid = asset['classid']
        qty_map[classid] = qty_map.get(classid, 0) + int(asset.get('amount', 1))

    items: list[Item] = []
    for classid, qty in qty_map.items():
        desc = desc_map.get(classid, {})
        items.append(Item(
            display_name=desc.get('name', classid),
            market_hash_name=desc.get('market_hash_name', classid),
            quantity=qty,
            tradable=bool(desc.get('tradable', 0)),
            marketable=bool(desc.get('marketable', 0)),
            commodity=bool(desc.get('commodity', 0)),
            type=desc.get('type') or None,
            tags=_extract_tags(desc.get('tags', [])),
            icon_url=desc.get('icon_url') or None,
        ))

    return items


def count_items(items: list[Item]) -> tuple[int, int, int, int]:
    """Return (total_quantity, distinct_types, marketable_types, tradable_types)."""
    total = sum(item.quantity for item in items)
    distinct = len(items)
    marketable = sum(1 for item in items if item.marketable)
    tradable = sum(1 for item in items if item.tradable)
    return total, distinct, marketable, tradable


def _extract_tags(raw_tags: list[dict]) -> list[dict[str, str]]:
    return [
        {
            'category': t.get('category', ''),
            'name': t.get('localized_tag_name', ''),
        }
        for t in raw_tags
    ]
