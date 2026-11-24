import base64
import json
import threading
import zipfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from hawedit.v8.team_review import ReviewStore, load_release_candidates, review_handler


def test_private_team_scores_approval_and_range_downloads(tmp_path: Path) -> None:
    episode = tmp_path / "episode"
    episode.mkdir()
    (episode / "episode.v8.json").write_text(
        json.dumps(
            {
                "clips": [
                    {"clip_id": "test", "grill_passed": True},
                    {"clip_id": "failed", "grill_passed": False},
                ]
            }
        )
    )
    with zipfile.ZipFile(episode / "test.v8.social.zip", "w") as archive:
        archive.writestr("reel.mp4", b"test-video")
        archive.writestr("post.txt", "A sample")
        archive.writestr("reel.en.dub.mp4", b"dub-test")
        archive.writestr(
            "captions.en.draft.srt",
            "1\r\n00:00:00,100 --> 00:00:01,001\r\nHello\r\n\r\n"
            "2\r\n00:00:01,100 --> 00:00:02,000\r\nagain\r\n",
        )
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    store = ReviewStore(tmp_path / "private")
    clips = load_release_candidates(episode, snapshots)
    (key,) = clips
    tokens = {n: store.invite(n, n == "editor") for n in ["reader", "editor"]}

    def headers(member: str) -> dict[str, str]:
        auth = base64.b64encode(f"{member}:{tokens[member]}".encode()).decode()
        return {"Authorization": "Basic " + auth, "X-HawEdit-Review": "1"}

    scores = dict.fromkeys(("opening", "payoff", "meaning", "caption_accuracy", "framing"), 4)
    body = json.dumps({"scores": scores, "notes": "native review", "decision": "approve"})
    with ThreadingHTTPServer(("127.0.0.1", 0), review_handler(store, clips)) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(
            method: str, path: str, hdr: dict[str, str], data: str | None = None
        ) -> tuple[int, bytes]:
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                conn.request(method, path, body=data, headers=hdr)
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()

        try:
            assert request("GET", "/", {})[0] == 401
            assert request("GET", "/?v=1", headers("reader"))[0] == 200
            assert request(
                "GET", "/video/" + key + "?t=1", {**headers("reader"), "Range": "bytes=0-3"}
            ) == (206, b"test")
            assert request("GET", "/dub-en/" + key, headers("reader")) == (200, b"dub-test")
            status, vtt = request("GET", "/sub-en/" + key, headers("reader"))
            assert status == 200 and b"00:00:00.100 --> 00:00:01.001" in vtt
            assert b"00:00:01.100 --> 00:00:02.000\nagain" in vtt
            assert request("GET", "/pack/" + key, headers("reader"))[0] == 403
            assert request("POST", "/ballot/" + key, headers("reader"), body)[0] == 403
            assert request("POST", "/ballot/" + key, headers("editor"), body)[0] == 200
            assert (
                request("GET", "/pack/" + key, headers("reader"))[1]
                == clips[key].package.read_bytes()
            )
            assert store.approved(key)
            assert not store.approved("changed-bundle")
            held = json.dumps({"scores": scores, "notes": "", "decision": "hold"})
            assert request("POST", "/ballot/" + key, headers("editor"), held)[0] == 200
            assert request("GET", "/pack/" + key, headers("reader"))[0] == 403
            with pytest.raises(ValueError, match="already exists"):
                store.invite("reader", False)
        finally:
            server.shutdown()
            thread.join()
