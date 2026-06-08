"""
screenpipe 适配器 —— 包装现有的 Screenpipe SQLite 读取逻辑。

行为与旧 db_reader 一致：支持 config 指定 db_path，或自动发现常见路径。
区别只有一点：库中无数据时**如实返回空**（fallback_mock=False），
mock 兜底由编排层负责，避免某个空源污染多源合并结果。
"""
from typing import List, Dict

from time_audit.sources.base import SourceAdapter
from time_audit.core import db_reader


class ScreenpipeAdapter(SourceAdapter):
    name = "screenpipe"

    def _resolve_db(self, cfg: dict):
        sp = cfg.get("screenpipe", {}) or {}
        db_path = sp.get("db_path", "")
        import os
        if db_path and os.path.exists(db_path):
            return db_path
        if sp.get("auto_discover", True):
            return db_reader.discover_screenpipe_db()
        return None

    def available(self, cfg: dict) -> bool:
        return self._resolve_db(cfg) is not None

    def collect(self, cfg: dict, days: int) -> List[Dict]:
        db_path = self._resolve_db(cfg)
        if not db_path:
            return []
        return db_reader.read_screenpipe_events(db_path, days, fallback_mock=False)
