from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import AppConfig
from app.core.database import JsonDatabase
from app.core.filelock import FileLockManager
from app.core.indexes import AccountIndex

if TYPE_CHECKING:
    from app.proxy.manager import ProxyManager
    from app.steam.client import SteamHttpClient


@dataclass
class AppContext:
    """Shared application state threaded through all async operations."""

    config: AppConfig
    db: JsonDatabase
    index: AccountIndex
    lock_manager: FileLockManager
    http_client: SteamHttpClient
    proxy_manager: ProxyManager
