"""Private mobile review and approval of exact social handoff packages."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import ipaddress
import json
import re
import secrets
import shutil
import sqlite3
import ssl
import tempfile
import zipfile
from argparse import ArgumentParser
from contextlib import closing
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from hawedit.delivery import ms_to_srt_time, parse_srt_times
from hawedit.studio_artifacts import UnsatisfiableRange, byte_range
from hawedit.studio_private import PrivateDirectory
from hawedit.v8.blind_review import _CRITERIA


class ReviewStore:
    def __init__(self, state: Path):
        self.private = PrivateDirectory(state)
        self.db = self.private.path / "reviews.sqlite"
        with closing(sqlite3.connect(self.db, timeout=10)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA busy_timeout=10000")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS members(name TEXT PRIMARY KEY,
                    digest TEXT, approver INTEGER);
                CREATE TABLE IF NOT EXISTS ballots(bundle TEXT, member TEXT, payload TEXT,
                    PRIMARY KEY(bundle, member));
                CREATE TABLE IF NOT EXISTS decisions(bundle TEXT PRIMARY KEY,
                    member TEXT, decision TEXT);
            """)

    def invite(self, name: str, approver: bool) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name):
            raise ValueError("Use a short alphanumeric member name")
        token = secrets.token_urlsafe(32)
        try:
            with closing(sqlite3.connect(self.db, timeout=10)) as db, db:
                db.execute(
                    "INSERT INTO members VALUES(?,?,?)",
                    (name, hashlib.sha256(token.encode()).hexdigest(), int(approver)),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Member {name!r} already exists") from exc
        return token

    def authenticate(self, header: str) -> tuple[str, bool] | None:
        if not header.startswith("Basic "):
            return None
        try:
            name, token = base64.b64decode(header[6:], validate=True).decode().split(":", 1)
        except (ValueError, UnicodeError):
            return None
        with closing(sqlite3.connect(self.db, timeout=10)) as db:
            row = db.execute(
                "SELECT digest, approver FROM members WHERE name=?", (name,)
            ).fetchone()
        if row and hmac.compare_digest(row[0], hashlib.sha256(token.encode()).hexdigest()):
            return name, bool(row[1])
        return None

    def record(self, bundle: str, member: tuple[str, bool], data: dict[str, Any]) -> None:
        name, approver = member
        scores = data.get("scores")
        if (
            not isinstance(scores, dict)
            or set(scores) != set(_CRITERIA)
            or any(type(v) is not int or not 1 <= v <= 5 for v in scores.values())
        ):
            raise ValueError("Score each criterion from 1 to 5")
        notes = data.get("notes")
        decision = data.get("decision")
        if (
            not isinstance(notes, str)
            or len(notes) > 2000
            or decision not in ("review", "approve", "hold")
        ):
            raise ValueError("Invalid review")
        if decision != "review" and not approver:
            raise PermissionError("Only an approver can change release status")
        with closing(sqlite3.connect(self.db, timeout=10)) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO ballots VALUES(?,?,?)",
                (bundle, name, json.dumps(data, ensure_ascii=False)),
            )
            if decision != "review":
                db.execute(
                    "INSERT OR REPLACE INTO decisions VALUES(?,?,?)", (bundle, name, decision)
                )

    def approved(self, bundle: str) -> bool:
        with closing(sqlite3.connect(self.db, timeout=10)) as db:
            row = db.execute("SELECT decision FROM decisions WHERE bundle=?", (bundle,)).fetchone()
        return bool(row == ("approve",))


@dataclass(frozen=True)
class ReviewClip:
    video: Path
    package: Path
    post: str
    dubs: dict[str, Path]
    tracks: dict[str, bytes]


def load_release_candidates(episode: Path, snapshot: Path) -> dict[str, ReviewClip]:
    """Freeze only packages admitted by the episode manifest, including their actual media."""
    manifest = json.loads((episode / "episode.v8.json").read_text(encoding="utf-8"))
    candidates = list(manifest["clips"])
    secrets.SystemRandom().shuffle(candidates)
    clips = {}
    for item in candidates:
        clip_id = item["clip_id"]
        if item.get("grill_passed") is not True:
            continue
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", clip_id):
            raise ValueError("Invalid candidate identifier")
        src = episode / (clip_id + ".v8.social.zip")
        package = snapshot / (clip_id + ".zip")
        shutil.copyfile(src, package)
        with package.open("rb") as stream:
            key = hashlib.file_digest(stream, "sha256").hexdigest()
        video = snapshot / (key + ".mp4")
        with zipfile.ZipFile(package) as archive:
            with archive.open("reel.mp4") as source, video.open("wb") as dest:
                shutil.copyfileobj(source, dest)
            post = archive.read("post.txt").decode("utf-8")
            dubs = {}
            tracks = {}
            for lang in ("ar", "en"):
                dub = f"reel.{lang}.dub.mp4"
                caption = f"captions.{lang}.draft.srt"
                if dub in archive.namelist():
                    target = snapshot / f"{key}.{lang}.mp4"
                    with archive.open(dub) as source, target.open("wb") as dest:
                        shutil.copyfileobj(source, dest)
                    dubs[lang] = target
                if caption in archive.namelist():
                    raw = "\n".join(archive.read(caption).decode("utf-8-sig").splitlines()).strip()
                    blocks = re.split(r"\n[ \t]*\n+", raw)
                    cues = ["WEBVTT"]
                    for (a, b), lines in zip(parse_srt_times(raw), blocks, strict=True):
                        timing = (ms_to_srt_time(a) + " --> " + ms_to_srt_time(b)).replace(",", ".")
                        cues.append(timing + "\n" + html.escape("\n".join(lines.splitlines()[2:])))
                    tracks[lang] = ("\n\n".join(cues) + "\n").encode()
        clips[key] = ReviewClip(video, package, post, dubs, tracks)
    if not clips:
        raise ValueError("No accepted social handoff packages")
    return clips


def _review_page(store: ReviewStore, clips: dict[str, ReviewClip], approver: bool) -> bytes:
    rows = []
    scores = "".join(
        f'<label>{label} <select required name="{field}"><option value="">—</option>'
        + "".join(f"<option>{n}</option>" for n in range(1, 6))
        + "</select></label>"
        for field, label in _CRITERIA.items()
    )
    decisions = (
        (
            '<select name="decision"><option value="review">هەڵسەنگاندن</option>'
            '<option value="hold">ڕاگرتن</option><option value="approve">پەسەندکردن</option>'
            "</select>"
        )
        if approver
        else ""
    )
    for index, (key, clip) in enumerate(clips.items(), 1):
        release = (
            f'<a href="/pack/{key}">داگرتنی پاکێجی پەسەندکراو</a>' if store.approved(key) else ""
        )
        tracks = "".join(
            f'<track kind="subtitles" srclang="{lang}" label="{lang.upper()}" '
            f'src="/sub-{lang}/{key}">'
            for lang in clip.tracks
        )
        versions = (
            '<label>دەنگ <select class="voice"><option value="video">کوردی</option>'
            + "".join(f'<option value="dub-{lang}">{lang.upper()}</option>' for lang in clip.dubs)
            + "</select></label>"
            if clip.dubs
            else ""
        )
        rows.append(
            f'<form data-key="{key}"><h2>کلیپ {index}</h2>'
            '<video controls preload="metadata" playsinline '
            f'src="/video/{key}">{tracks}</video>{versions}'
            f"<p>{html.escape(clip.post)}</p>{scores}<label>تێبینی"
            f'<textarea name="notes" maxlength="2000"></textarea></label>{decisions}'
            f"<button>پاشەکەوتکردن</button> {release}<output></output></form>"
        )
    return (
        """<!doctype html><html lang="ckb" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>HawEdit</title>
<style>body{background:#111820;color:#fafafa;font:18px system-ui;margin:auto;max-width:34rem;
padding:1rem}form{border-top:1px solid #64717d;padding:1rem 0}video{width:100%;max-height:50vh}
label,output{display:block;margin:.6rem 0}button,select,textarea{font:inherit}a{color:#adcfff}
p{white-space:pre-line}</style><h1>هەڵسەنگاندنی کلیپەکان</h1>"""
        + "".join(rows)
        + """
<script>for(const select of document.querySelectorAll('.voice')){
select.onchange=()=>{const form=select.closest('form'),v=form.querySelector('video');
v.src='/'+select.value+'/'+form.dataset.key;v.load()}}
for(const f of document.forms) f.onsubmit=async e=>{
e.preventDefault();const scores={};for(const s of f.querySelectorAll('select[required]'))
scores[s.name]=Number(s.value);
try{const r=await fetch('/ballot/'+f.dataset.key,{method:'POST',
headers:{'Content-Type':'application/json','X-HawEdit-Review':'1'},body:JSON.stringify({
scores,notes:f.elements.notes.value,decision:f.elements.decision?.value||'review'})});
if(!r.ok)throw Error(await r.text());f.querySelector('output').textContent='پاشەکەوت کرا';
let a=f.querySelector('a');if((await r.json()).approved){if(!a){a=document.createElement('a');
a.textContent='داگرتنی پاکێجی پەسەندکراو';f.append(a)}
a.href='/pack/'+f.dataset.key}else if(a)a.remove()
}catch(err){f.querySelector('output').textContent=err.message}};</script></html>"""
    ).encode()


def review_handler(
    store: ReviewStore, clips: dict[str, ReviewClip]
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        timeout = 30

        def reply(self, status: int, body: bytes, mime: str = "text/plain; charset=utf-8") -> None:
            self.send_response(status)
            if status == 401:
                self.send_header("WWW-Authenticate", 'Basic realm="HawEdit team"')
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def identity(self) -> tuple[str, bool] | None:
            member = store.authenticate(self.headers.get("Authorization", ""))
            if member is None:
                self.reply(401, b"Team sign-in required")
            return member

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            member = self.identity()
            if member is None:
                return
            route = self.path.split("?", 1)[0]
            if route == "/":
                self.reply(200, _review_page(store, clips, member[1]), "text/html; charset=utf-8")
                return
            parts = route.split("/")
            if len(parts) != 3 or parts[2] not in clips:
                self.reply(404, b"Unknown candidate")
                return
            action, key = parts[1:]
            clip = clips[key]
            is_pack = action == "pack"
            if is_pack and not store.approved(key):
                self.reply(403, b"Approval required for this package")
                return
            if action.startswith("sub-") and action[4:] in clip.tracks:
                self.reply(200, clip.tracks[action[4:]], "text/vtt; charset=utf-8")
                return
            if is_pack:
                target = clip.package
            elif action == "video":
                target = clip.video
            elif action.startswith("dub-") and action[4:] in clip.dubs:
                target = clip.dubs[action[4:]]
            else:
                self.reply(404, b"Unknown review asset")
                return
            with target.open("rb") as stream:
                size = target.stat().st_size
                try:
                    span = byte_range(self.headers.get("Range"), size)
                except UnsatisfiableRange:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                start, end = span or (0, size - 1)
                self.send_response(206 if span else 200)
                self.send_header("Content-Type", "application/zip" if is_pack else "video/mp4")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if span:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                if is_pack:
                    self.send_header(
                        "Content-Disposition", 'attachment; filename="hawedit-reel.zip"'
                    )
                self.end_headers()
                if self.command == "HEAD":
                    return
                stream.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = stream.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def do_POST(self) -> None:
            member = self.identity()
            if member is None:
                return
            kind, _, key = self.path.rpartition("/")
            if kind != "/ballot" or key not in clips:
                self.reply(404, b"Unknown candidate")
                return
            if (
                self.headers.get("X-HawEdit-Review") != "1"
                or self.headers.get("Sec-Fetch-Site") == "cross-site"
            ):
                self.reply(403, b"Same-origin review required")
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    raise ValueError("Invalid review length")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Invalid ballot")
                store.record(key, member, data)
            except (ValueError, UnicodeError) as exc:
                self.reply(400, str(exc).encode())
                return
            except PermissionError as exc:
                self.reply(403, str(exc).encode())
                return
            self.reply(
                200, json.dumps({"approved": store.approved(key)}).encode(), "application/json"
            )

    return Handler


def team_cli(argv: list[str]) -> int:
    parser = ArgumentParser(prog="hawedit.v8 team")
    parser.add_argument("--state", type=Path, required=True, help="Private team data directory")
    commands = parser.add_subparsers(dest="action", required=True)
    invite = commands.add_parser("invite")
    invite.add_argument("name")
    invite.add_argument("--approver", action="store_true")
    serve = commands.add_parser("serve")
    serve.add_argument("episode", type=Path)
    serve.add_argument("--port", type=int, default=8876)
    serve.add_argument("--bind", default="127.0.0.1", help="Private interface IP")
    serve.add_argument("--tls-cert", type=Path)
    serve.add_argument("--tls-key", type=Path)
    args = parser.parse_args(argv)
    store = ReviewStore(args.state)
    if args.action == "invite":
        print(store.invite(args.name, args.approver))
        return 0
    if bool(args.tls_cert) != bool(args.tls_key):
        parser.error("Supply both TLS certificate and key")
    try:
        address = ipaddress.IPv4Address(args.bind)
    except ipaddress.AddressValueError as exc:
        parser.error(f"Invalid IPv4 bind address: {exc}")
    if not address.is_loopback and (not address.is_private or not args.tls_cert):
        parser.error("A mobile listener requires a private interface and TLS")
    tls = None
    if args.tls_cert:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version = ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(args.tls_cert, args.tls_key)
    with tempfile.TemporaryDirectory(dir=store.private.path) as tmp:
        clips = load_release_candidates(args.episode, Path(tmp))
        with ThreadingHTTPServer((str(address), args.port), review_handler(store, clips)) as server:
            if tls is not None:
                server.socket = tls.wrap_socket(server.socket, server_side=True)
            scheme = "https" if tls else "http"
            print(f"Team review listening on {scheme}://{address}:{server.server_port}", flush=True)
            server.serve_forever()
    return 0
