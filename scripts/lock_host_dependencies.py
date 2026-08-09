"""Regenerate HawEdit's exact Linux/Windows CPU host dependency locks.

This is a maintainer command, not an installer. It asks one pinned uv resolver for each
supported CPython/OS target, then reduces PEP 751 output to one exact wheel hash per package.
The committed locks are consumed by pip with ``--require-hashes --only-binary``.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast
from urllib.parse import urlsplit

ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hawedit.environment import dependency_contract_digest  # noqa: E402

UV_VERSION: Final = "0.11.26"
EXCLUDE_NEWER: Final = "2026-08-09T00:00:00Z"
ALLOWED_WHEEL_HOSTS: Final = frozenset({"files.pythonhosted.org", "download-r2.pytorch.org"})
HASH_MODULE: Final = ROOT / "src" / "hawedit" / "host_lock_hashes.py"


@dataclass(frozen=True, slots=True)
class Target:
    scope: str
    platform: str
    uv_platform: str
    python: str
    extras: tuple[str, ...]

    @property
    def destination(self) -> Path:
        version = self.python.replace(".", "")
        return ROOT / "requirements" / f"host-{self.scope}-{self.platform}-py{version}.txt"


TARGETS: Final = tuple(
    Target(scope, platform, uv_platform, python, extras)
    for scope, extras in (("base", ()), ("gate", ("dev", "media")), ("models", ("models",)))
    for platform, uv_platform in (
        ("linux", "x86_64-unknown-linux-gnu"),
        ("windows", "x86_64-pc-windows-msvc"),
    )
    for python in ("3.11", "3.12")
)


def _require_pinned_uv() -> str:
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"uv=={UV_VERSION} is required to regenerate host locks: {exc}") from exc
    version = result.stdout.strip().split()
    if len(version) < 2 or version[:2] != ["uv", UV_VERSION]:
        raise SystemExit(
            f"refusing resolver drift: expected uv {UV_VERSION}, got {result.stdout.strip()!r}"
        )
    return "uv"


def _compile(uv: str, target: Target, temporary: Path) -> Path:
    output = temporary / f"pylock.{target.scope}-{target.platform}-{target.python}.toml"
    command = [
        uv,
        "pip",
        "compile",
        "pyproject.toml",
        "requirements/release-build.txt",
        "--python-version",
        target.python,
        "--python-platform",
        target.uv_platform,
        "--torch-backend",
        "cpu",
        "--only-binary=:all:",
        "--no-emit-package",
        "hawedit",
        "--format",
        "pylock.toml",
        "--exclude-newer",
        EXCLUDE_NEWER,
        "--refresh",
        "--output-file",
        str(output),
    ]
    for extra in target.extras:
        command.extend(("--extra", extra))
    subprocess.run(command, cwd=ROOT, check=True)
    return output


def _project_version() -> str:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = document.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise SystemExit("pyproject.toml has no string project version")
    return cast(str, project["version"])


def _render(target: Target, pylock: Path) -> str:
    document = tomllib.loads(pylock.read_text(encoding="utf-8"))
    if document.get("lock-version") != "1.0" or document.get("created-by") != "uv":
        raise SystemExit(f"unexpected PEP 751 document identity in {pylock}")
    packages = document.get("packages")
    if not isinstance(packages, list) or not packages:
        raise SystemExit(f"resolver returned no packages for {target}")

    lines = [
        "# HawEdit exact host dependency lock; generated, do not hand-edit.",
        "# hawedit-lock-version: 1",
        f"# scope: {target.scope}",
        f"# target-platform: {target.platform}",
        f"# target-python: {target.python}",
        f"# extras: {','.join(target.extras) or '-'}",
        f"# project-version: {_project_version()}",
        f"# contract-sha256: {dependency_contract_digest(ROOT, target.extras)}",
        f"# resolver: uv=={UV_VERSION}",
        f"# exclude-newer: {EXCLUDE_NEWER}",
        "--extra-index-url https://download.pytorch.org/whl/cpu",
        "--only-binary=:all:",
        "",
    ]
    seen: set[str] = set()
    for item in packages:
        package = cast(dict[str, object], item)
        name = package.get("name")
        version = package.get("version")
        wheels = package.get("wheels")
        if not isinstance(name, str) or not isinstance(version, str):
            raise SystemExit(f"invalid package identity in {pylock}: {package!r}")
        if name in seen:
            raise SystemExit(f"resolver forked {name!r} for a single exact target")
        seen.add(name)
        if not isinstance(wheels, list) or not wheels:
            raise SystemExit(f"no binary wheel for {name}=={version} on {target}")
        wheel = cast(dict[str, object], wheels[0])
        url = wheel.get("url")
        hashes = wheel.get("hashes")
        if not isinstance(url, str) or urlsplit(url).scheme != "https":
            raise SystemExit(f"non-HTTPS wheel URL for {name}=={version}: {url!r}")
        if urlsplit(url).hostname not in ALLOWED_WHEEL_HOSTS:
            raise SystemExit(f"untrusted wheel host for {name}=={version}: {url!r}")
        if not isinstance(hashes, dict) or set(hashes) != {"sha256"}:
            raise SystemExit(f"wheel lacks one SHA-256 for {name}=={version}")
        digest = hashes["sha256"]
        if not isinstance(digest, str) or len(digest) != 64:
            raise SystemExit(f"invalid wheel SHA-256 for {name}=={version}")
        lines.extend((f"# selected wheel {url}", f"{name}=={version} --hash=sha256:{digest}"))
    return "\n".join(lines) + "\n"


def _render_hash_module(locks: dict[Path, str]) -> str:
    lines = [
        '"""Generated SHA-256 identities for HawEdit\'s committed and packaged host locks."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Final",
        "",
        "HOST_LOCK_SHA256: Final[dict[str, str]] = {",
    ]
    for path, rendered in sorted(locks.items(), key=lambda item: item[0].name):
        digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        lines.extend((f'    "{path.name}": (', f'        "{digest}"', "    ),"))
    lines.extend(("}", ""))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="resolve all targets and refuse any difference without rewriting locks",
    )
    args = parser.parse_args()
    uv = _require_pinned_uv()
    changed: list[Path] = []
    rendered_locks: dict[Path, str] = {}
    with tempfile.TemporaryDirectory(prefix="hawedit-host-lock-") as directory:
        temporary = Path(directory)
        for target in TARGETS:
            rendered = _render(target, _compile(uv, target, temporary))
            destination = target.destination
            rendered_locks[destination] = rendered
            current = destination.read_text(encoding="utf-8") if destination.is_file() else None
            if current == rendered:
                continue
            changed.append(destination)
            if not args.check:
                destination.write_text(rendered, encoding="utf-8", newline="\n")
    rendered_hashes = _render_hash_module(rendered_locks)
    current_hashes = HASH_MODULE.read_text(encoding="utf-8") if HASH_MODULE.is_file() else None
    if current_hashes != rendered_hashes:
        changed.append(HASH_MODULE)
        if not args.check:
            HASH_MODULE.write_text(rendered_hashes, encoding="utf-8", newline="\n")
    if args.check and changed:
        names = ", ".join(path.name for path in changed)
        raise SystemExit(f"host dependency locks are stale: {names}")
    print(f"host locks {'verified' if args.check else 'written'}: {len(TARGETS)} targets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
