"""Publish an approved private reel using Meta's Facebook Login for Business upload flow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
import zipfile
from argparse import ArgumentParser
from collections.abc import Mapping
from contextlib import closing
from http.client import HTTPSConnection
from pathlib import Path
from typing import IO, Any
from urllib.parse import urlencode

from hawedit.v8.team_review import ReviewStore


class InstagramClient:
    def __init__(self, token: str):
        self.token = token

    def call(
        self,
        host: str,
        method: str,
        route: str,
        body: bytes | IO[bytes] | None,
        headers: Mapping[str, str],
    ) -> dict[str, Any]:
        conn = HTTPSConnection(host, timeout=120)
        try:
            conn.request(method, route, body=body, headers=dict(headers))
            result = conn.getresponse()
            payload = json.loads(result.read(256 * 1024))
            if not isinstance(payload, dict) or result.status >= 400:
                raise ValueError(
                    f"Meta returned HTTP {result.status} on {method} {route.split('?')[0]}"
                )
            return payload
        finally:
            conn.close()

    def graph(self, route: str, fields: dict[str, str] | None = None) -> dict[str, Any]:
        return self.call(
            "graph.facebook.com",
            "POST" if fields is not None else "GET",
            "/v27.0/" + route,
            urlencode(fields).encode() if fields is not None else None,
            {
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    def upload(self, container: str, movie: IO[bytes], size: int) -> None:
        result = self.call(
            "rupload.facebook.com",
            "POST",
            "/ig-api-upload/v27.0/" + container,
            movie,
            {
                "Authorization": "OAuth " + self.token,
                "offset": "0",
                "file_size": str(size),
                "Content-Length": str(size),
                "Content-Type": "application/octet-stream",
            },
        )
        if result.get("success") is not True:
            raise ValueError("Instagram did not confirm upload")


def publish_approved(store: ReviewStore, package: Path, account: str, api: InstagramClient) -> str:
    if not re.fullmatch(r"[0-9]+", account):
        raise ValueError("Supply the Instagram professional account ID")
    with package.open("rb") as stream, tempfile.TemporaryFile() as snapshot:
        digest = hashlib.sha256()
        while block := stream.read(1024 * 1024):
            snapshot.write(block)
            digest.update(block)
        bundle = digest.hexdigest()
        if not store.approved(bundle):
            raise ValueError("This exact package requires editorial approval")
        with (
            closing(sqlite3.connect(store.db, timeout=10)) as db,
            zipfile.ZipFile(snapshot) as archive,
        ):
            db.execute("""CREATE TABLE IF NOT EXISTS instagram(
                bundle TEXT, account TEXT, container TEXT, phase TEXT, receipt TEXT,
                PRIMARY KEY(bundle,account))""")
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT container,phase,receipt FROM instagram WHERE bundle=? AND account=?",
                (bundle, account),
            ).fetchone()
            if row is None:
                caption = archive.read("post.txt").decode("utf-8").strip()
                resp = api.graph(
                    account + "/media",
                    {
                        "media_type": "REELS",
                        "upload_type": "resumable",
                        "caption": caption,
                        "thumb_offset": "600",
                    },
                )
                container = str(resp["id"])
                if not container.isascii() or not container.isdecimal():
                    raise ValueError("Invalid Instagram container response")
                db.execute(
                    "INSERT INTO instagram VALUES(?,?,?,?,?)",
                    (bundle, account, container, "new", ""),
                )
                db.commit()
            else:
                container, phase, receipt = row
                db.commit()
                if phase == "published":
                    return str(receipt)
            # Serialize upload attempts. Once upload succeeds every retry reuses the container.
            db.execute("BEGIN IMMEDIATE")
            phase = db.execute(
                "SELECT phase FROM instagram WHERE bundle=? AND account=?", (bundle, account)
            ).fetchone()[0]
            if phase == "new":
                member = archive.getinfo("reel.mp4")
                with archive.open(member) as movie:
                    api.upload(container, movie, member.file_size)
                db.execute(
                    "UPDATE instagram SET phase='uploaded' WHERE bundle=? AND account=?",
                    (bundle, account),
                )
            db.commit()
            for attempt in range(6):
                status = api.graph(container + "?fields=status_code").get("status_code")
                if status == "PUBLISHED":
                    receipt = "Published container " + container
                    db.execute(
                        "UPDATE instagram SET phase='published',"
                        "receipt=CASE WHEN receipt='' THEN ? ELSE receipt END "
                        "WHERE bundle=? AND account=?",
                        (receipt, bundle, account),
                    )
                    db.commit()
                    return str(
                        db.execute(
                            "SELECT receipt FROM instagram WHERE bundle=? AND account=?",
                            (bundle, account),
                        ).fetchone()[0]
                    )
                if status == "FINISHED":
                    break
                if status != "IN_PROGRESS" or attempt == 5:
                    raise ValueError(f"Instagram container {container} has status {status!r}")
                time.sleep(10)
            db.execute("BEGIN IMMEDIATE")
            if not store.approved(bundle):
                raise ValueError("Editorial approval has been withdrawn")
            changed = db.execute(
                "UPDATE instagram SET phase='publishing' WHERE bundle=? AND account=? "
                "AND phase='uploaded'",
                (bundle, account),
            ).rowcount
            db.commit()
            if not changed:
                raise ValueError(
                    "Publish already requested; check this container again for its result"
                )
            result = api.graph(account + "/media_publish", {"creation_id": container})
            media_id = str(result["id"])
            db.execute(
                "UPDATE instagram SET phase='published',receipt=? WHERE bundle=? AND account=?",
                (media_id, bundle, account),
            )
            db.commit()
            return media_id


def instagram_cli(argv: list[str]) -> int:
    parser = ArgumentParser(prog="hawedit.v8 publish-instagram")
    parser.add_argument("package", type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--account", required=True)
    args = parser.parse_args(argv)
    token = os.environ.get("HAWEDIT_META_ACCESS_TOKEN")
    if not token:
        parser.error("Set HAWEDIT_META_ACCESS_TOKEN for the selected professional account")
    print(
        publish_approved(
            ReviewStore(args.state), args.package, args.account, InstagramClient(token)
        )
    )
    return 0
