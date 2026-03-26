from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class AppConfig(BaseModel):
    """Application configuration loaded from config.toml."""

    db_path: Path = Path('data/accounts.json')
    log_path: Path = Path('data/app.log')

    proxies: list[str] = Field(default_factory=list)

    global_concurrency: int = 0
    proxy_concurrency: int = 1

    @model_validator(mode='after')
    def _auto_global_concurrency(self) -> 'AppConfig':
        """Set global_concurrency to proxy count (min 1) when not explicitly configured."""
        if self.global_concurrency <= 0:
            self.global_concurrency = max(1, len(self.proxies))
        return self
    request_timeout: float = 10.0
    retry_count: int = 3
    backoff_base: float = 1.0
    backoff_jitter: float = 0.5
    request_delay: float = 5
    autosave_interval: int = 100

    stale_threshold_hours: int = 48

    pricing_enabled: bool = False
    pricing_currency: int = 1
    debug_raw_mode: bool = False
    autosave: bool = True
    loop_acceleration: bool = False


def load_config(path: Path | None = None) -> AppConfig:
    """Load AppConfig from a TOML file, falling back to defaults if absent."""
    if path is None:
        path = Path('config.toml')

    if not path.exists():
        return AppConfig()

    with path.open('rb') as fh:
        raw = tomllib.load(fh)

    db_sec = raw.get('database', {})
    prx_sec = raw.get('proxies', {})
    perf_sec = raw.get('performance', {})
    thr_sec = raw.get('thresholds', {})
    feat_sec = raw.get('features', {})

    return AppConfig(
        db_path=Path(db_sec.get('db_path', 'data/accounts.json')),
        log_path=Path(db_sec.get('log_path', 'data/app.log')),

        proxies=prx_sec.get('list', []),

        global_concurrency=perf_sec.get('global_concurrency', 0),
        proxy_concurrency=perf_sec.get('proxy_concurrency', 1),
        request_timeout=perf_sec.get('request_timeout', 10.0),
        retry_count=perf_sec.get('retry_count', 3),
        backoff_base=perf_sec.get('backoff_base', 1.0),
        backoff_jitter=perf_sec.get('backoff_jitter', 0.5),
        request_delay=perf_sec.get('request_delay', 5),
        autosave_interval=perf_sec.get('autosave_interval', 100),

        stale_threshold_hours=thr_sec.get('stale_threshold_hours', 48),

        pricing_enabled=feat_sec.get('pricing_enabled', False),
        pricing_currency=feat_sec.get('pricing_currency', 1),
        debug_raw_mode=feat_sec.get('debug_raw_mode', False),
        autosave=feat_sec.get('autosave', True),
        loop_acceleration=feat_sec.get('loop_acceleration', False),
    )
