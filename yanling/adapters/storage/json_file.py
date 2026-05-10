"""JSON 文件存储适配器。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from yanling.adapters.storage.base import StorageAdapter

log = logging.getLogger("yanling.storage.json_file")


class JsonFileStorage(StorageAdapter):
    """以 JSON 文件存储数据，每个 key 对应一个文件。"""

    def __init__(self, base_path: str | Path):
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_")
        return self._base / f"{safe}.json"

    async def read(self, key: str) -> Any | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("读取 %s 失败: %s", key, e)
            return None

    async def write(self, key: str, value: Any) -> bool:
        path = self._path_for(key)
        try:
            path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            return True
        except OSError as e:
            log.error("写入 %s 失败: %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        path = self._path_for(key)
        if path.exists():
            path.unlink()
            return True
        return False

    async def list_keys(self, prefix: str = "") -> list[str]:
        return [
            p.stem for p in self._base.glob(f"{prefix}*.json")
        ]
