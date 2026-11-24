import hashlib
import zipfile
from pathlib import Path
from typing import IO, Any

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

    def upload(self, container: str, movie: IO[bytes], size: int) -> None:
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


def test_ambiguous_publish_recovery_and_withdrawn_approval(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "state")
    path = tmp_path / "package.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("reel.mp4", b"video")
        bundle.writestr("post.txt", "Ready")
    key = hashlib.sha256(path.read_bytes()).hexdigest()
    scores = dict.fromkeys(("opening", "payoff", "meaning", "caption_accuracy", "framing"), 5)
    store.record(key, ("approver", True), {"decision": "approve", "notes": "", "scores": scores})

    class AmbiguousClient(MetaTestClient):
        def __init__(self) -> None:
            super().__init__()
            self.status = "FINISHED"
            self.fail_publish = True

        def graph(self, route: str, fields: dict[str, str] | None = None) -> dict[str, Any]:
            if route.endswith("/media_publish"):
                self.published += 1
                if self.fail_publish:
                    raise TimeoutError("ambiguous gateway timeout")
                return {"id": "777"}
            if route.endswith("/media"):
                return {"id": "123"}
            return {"status_code": self.status}

    api = AmbiguousClient()
    with pytest.raises(TimeoutError):
        publish_approved(store, path, "15", api)
    assert api.published == 1
    # Retry while still FINISHED refuses to send a duplicate /media_publish.
    with pytest.raises(ValueError, match="already requested"):
        publish_approved(store, path, "15", api)
    assert api.published == 1
    # Once Meta reports PUBLISHED, retry records and returns the receipt without republishing.
    api.status = "PUBLISHED"
    assert publish_approved(store, path, "15", api) == "Published container 123"
    assert api.published == 1

    # Withdrawing approval after upload blocks /media_publish atomically.
    path2 = tmp_path / "package2.zip"
    with zipfile.ZipFile(path2, "w") as bundle:
        bundle.writestr("reel.mp4", b"video2")
        bundle.writestr("post.txt", "Ready")
    key2 = hashlib.sha256(path2.read_bytes()).hexdigest()
    store.record(key2, ("approver", True), {"decision": "approve", "notes": "", "scores": scores})

    class RevokeDuringUploadClient(MetaTestClient):
        def upload(self, container: str, movie: IO[bytes], size: int) -> None:
            movie.read()
            store.record(
                key2, ("approver", True), {"decision": "hold", "notes": "stop", "scores": scores}
            )

    revoked_api = RevokeDuringUploadClient()
    with pytest.raises(ValueError, match="withdrawn"):
        publish_approved(store, path2, "15", revoked_api)
    assert revoked_api.published == 0
