"""Single-worker YouTube imports into Studio's existing private upload store."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from hawedit.atomic_fs import write_text_atomic
from hawedit.studio_uploads import UploadStore
from hawedit.v8.media_settings import media_setting
from hawedit.v8.youtube import resolve_youtube_source, youtube_video_id


class YouTubeImports:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active: tuple[Path, str] | None = None
        self.failure: tuple[Path, str, str] | None = None

    def request(self, store: UploadStore, url: str, *, start: bool) -> dict[str, Any]:
        video_id = youtube_video_id(url)
        key = (store.root, video_id)
        receipts = store.root / "youtube-imports"
        receipt = receipts / (video_id + ".json")
        with self.lock:
            if self.active == key:
                return {"state": "importing", "video_id": video_id}
            if receipt.is_file():
                source_id = json.loads(receipt.read_text(encoding="utf-8"))["source_id"]
                return {"state": "ready", "source": store.describe(source_id)}
            if not start:
                if self.failure and self.failure[:2] == key:
                    return {"state": "failed", "error": self.failure[2]}
                return {"state": "interrupted"}
            if self.active is not None:
                raise ValueError("Another episode import is running")
            receipts.mkdir(exist_ok=True)
            self.active = key
            self.failure = None
            worker = threading.Thread(target=self._import, args=(store, url, receipt), daemon=True)
            try:
                worker.start()
            except RuntimeError:
                self.active = None
                raise
            return {"state": "importing", "video_id": video_id}

    def _import(self, store: UploadStore, url: str, receipt: Path) -> None:
        try:
            library = Path(media_setting("youtube_library") or store.root / "youtube-media")
            movie = resolve_youtube_source(url, library)
            size = movie.stat().st_size
            ticket = store.begin(movie.name, size)
            with movie.open("rb") as stream:
                source = store.receive(ticket["upload_id"], stream, size)
            write_text_atomic(receipt, json.dumps({"source_id": source["source_id"]}))
        except Exception as exc:
            with self.lock:
                self.failure = (store.root, receipt.stem, str(exc))
        finally:
            with self.lock:
                self.active = None
