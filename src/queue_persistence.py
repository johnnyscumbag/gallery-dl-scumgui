from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable


class QueuePersistence:
    """Persist unfinished ScumGUI queue items between application runs."""

    def __init__(self) -> None:
        appdata = os.environ.get("APPDATA")
        if appdata:
            root = Path(appdata)
        else:
            root = Path.home() / "AppData" / "Roaming"
        self.path = root / "ScumGUI" / "queue.json"

    def load(self) -> list[dict[str, str]]:
        if not self.path.is_file():
            return []

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(data, list):
            return []

        restored: list[dict[str, str]] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue

            url = entry.get("url")
            destination = entry.get("destination")
            if not isinstance(url, str) or not url.strip():
                continue
            if not isinstance(destination, str) or not destination.strip():
                continue

            restored.append({
                "url": url.strip(),
                "destination": destination.strip(),
            })

        return restored

    def save(self, queue_items: Iterable[object]) -> None:
        pending = []
        for item in queue_items:
            if getattr(item, "status", None) not in {"Waiting", "Downloading"}:
                continue

            url = getattr(item, "url", "")
            destination = getattr(item, "destination", "")
            if not isinstance(url, str) or not url.strip():
                continue
            if not isinstance(destination, str) or not destination.strip():
                continue

            pending.append({
                "url": url,
                "destination": destination,
            })

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(pending, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            pass
