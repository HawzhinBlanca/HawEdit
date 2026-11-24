import hashlib
import zipfile
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from hawedit.v8.instagram import InstagramClient, publish_approved
from hawedit.v8.team_review import ReviewStore


class MetaTestClient(InstagramClient):
    def __init__(self) -> None:
        self.published = 0
        self.uploaded = b""

    def graph(self, route: str, fields: dict[str, str] | None = None) -> dict[str, Any]:
        if route.endswith("/media_publish"):
            assert fields == {"creation_id": "123"}
            self.published += 1
            return {"id": "555"}
        if route.endswith("/media"):
            assert fields and fields["caption"] == "Ready"
            return {"id": "123"}
        return {"status_code": "FINISHED"}

    def upload(self, container: str, movie: BinaryIO, size: int) -> None:
        assert container == "123" and size == 5
        self.uploaded = movie.read()


def test_exact_approval_required_and_repeat_is_idempotent(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "state")
    path = tmp_path / "package.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("reel.mp4", b"video")
        bundle.writestr("post.txt", "Ready")
    api = MetaTestClient()
    with pytest.raises(ValueError, match="approval"):
        publish_approved(store, path, "15", api)
    key = hashlib.sha256(path.read_bytes()).hexdigest()
    scores = dict.fromkeys(("opening", "payoff", "meaning", "caption_accuracy", "framing"), 4)
    store.record(key, ("approver", True), {"decision": "approve", "notes": "", "scores": scores})
    assert publish_approved(store, path, "15", api) == "555"
    assert api.uploaded == b"video"
    assert publish_approved(store, path, "15", api) == "555"
    assert api.published == 1
