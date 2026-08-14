"""Content-address and verify the package-managed OmniASR runtime assets.

``omnilingual-asr`` publishes mutable HTTPS URLs in its model cards and fairseq2 keys its
cache by a truncated SHA-1 of each URL.  That cache key identifies the address, not the bytes.
This module adds HawEdit's missing content boundary: the three canonical files are downloaded
to fairseq2's expected locations only after their size and SHA-256 match, and they are hashed
again before either model pipeline is constructed.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import os
import shutil
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Final
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

__all__ = [
    "CANONICAL_CTC_CARD",
    "CANONICAL_LLM_CARD",
    "OMNI_ASSETS",
    "OmniAsset",
    "OmniAssetError",
    "OmniAssetReport",
    "OpenedOmniAsset",
    "assert_canonical_omni_cards",
    "assert_effective_omni_cards",
    "assert_omni_asset_integrity",
    "assert_omni_card_integrity",
    "fairseq2_cache_dir",
    "freeze_fairseq2_asset_overrides",
    "open_verified_omni_assets",
    "provision_omni_assets",
]

CANONICAL_LLM_CARD: Final = "omniASR_LLM_7B_v2@"
CANONICAL_CTC_CARD: Final = "omniASR_CTC_3B_v2@"
_TOKENIZER_CARD: Final = "omniASR_tokenizer_written_v2"
_CARD_RELATIVE_PATH: Final = Path("omnilingual_asr/cards/models/rc_models_v2.yaml")
_CARD_SIZE: Final = 2_725
_CARD_SHA256: Final = "af4d63febb0569831210e470b256ec70dc3a55065756c21c1f514d0001f283ed"
_CARD_POLICY_TEMP: tempfile.TemporaryDirectory[str] | None = None
_PROVISION_LOCK_TIMEOUT_S: Final = 6 * 60 * 60
_PROVISION_LOCK_RETRY_S: Final = 0.25
_WINDOWS_HOST: Final = os.name == "nt"


class OmniAssetError(RuntimeError):
    """The canonical OmniASR bytes are missing, altered, or could not be published safely."""


@dataclass(frozen=True)
class OmniAsset:
    name: str
    url: str
    filename: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("OmniASR asset name must not be empty")
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"OmniASR asset URL must be absolute HTTPS: {self.url!r}")
        if Path(self.filename).name != self.filename or not self.filename:
            raise ValueError(f"OmniASR asset filename must be one plain name: {self.filename!r}")
        if self.size <= 0:
            raise ValueError("OmniASR asset size must be positive")
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256):
            raise ValueError("OmniASR asset SHA-256 must be 64 lowercase hexadecimal characters")

    @property
    def cache_key(self) -> str:
        """The directory name fairseq2 0.6 derives from this exact URL."""
        return hashlib.sha1(self.url.encode("utf-8"), usedforsecurity=False).hexdigest()[:24]

    def path_in(self, cache_dir: Path) -> Path:
        return cache_dir / self.cache_key / self.filename


OMNI_ASSETS: Final = (
    OmniAsset(
        name="omniASR LLM-7B v2 weights",
        url="https://dl.fbaipublicfiles.com/mms/omniASR-LLM-7B-v2.pt",
        filename="omniASR-LLM-7B-v2.pt",
        size=31_220_488_063,
        sha256="1b29a4045ddfbe9125e6c9d465d5bc29063eea256ace37c129742edc07aed17a",
    ),
    OmniAsset(
        name="omniASR CTC-3B v2 weights",
        url="https://dl.fbaipublicfiles.com/mms/omniASR-CTC-3B-v2.pt",
        filename="omniASR-CTC-3B-v2.pt",
        size=12_325_920_624,
        sha256="fa7f662c326842bb80561db97631ae3c48d911aec579654a1e8414c26caf9089",
    ),
    OmniAsset(
        name="omniASR written-v2 tokenizer",
        url="https://dl.fbaipublicfiles.com/mms/omniASR_tokenizer_written_v2.model",
        filename="omniASR_tokenizer_written_v2.model",
        size=91_481,
        sha256="8aa11a1092142ef472537476ef6e76541123e2f0d789b79f3ebd119008240b1e",
    ),
)


@dataclass(frozen=True)
class OmniAssetReport:
    name: str
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class OpenedOmniAsset:
    asset: OmniAsset
    descriptor_path: Path
    file_uri: str
    report: OmniAssetReport


def fairseq2_cache_dir(
    *, environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """Resolve fairseq2 0.6's cache precedence without importing its native extension."""
    env = os.environ if environ is None else environ
    explicit = env.get("FAIRSEQ2_CACHE_DIR")
    if explicit is not None:
        if not explicit.strip():
            raise OmniAssetError(
                "FAIRSEQ2_CACHE_DIR must be unset or name an explicit cache directory; "
                "an empty value would make fairseq2 use the process working directory"
            )
        return Path(explicit).expanduser().resolve()
    xdg = env.get("XDG_CACHE_HOME")
    if xdg is not None:
        if not xdg.strip():
            raise OmniAssetError(
                "XDG_CACHE_HOME must be unset or name an explicit cache directory; "
                "an empty value would make fairseq2 use the process working directory"
            )
        return (Path(xdg).expanduser() / "fairseq2" / "assets").resolve()
    selected_home = Path.home() if home is None else home
    return (selected_home.expanduser() / ".cache" / "fairseq2" / "assets").resolve()


def assert_canonical_omni_cards(llm_card: str, ctc_card: str) -> None:
    """Refuse model-card substitutions and fairseq2's ``@user`` field overrides."""
    if llm_card != CANONICAL_LLM_CARD or ctc_card != CANONICAL_CTC_CARD:
        raise OmniAssetError(
            "canonical ASR only permits the environment-disabled cards "
            f"{CANONICAL_LLM_CARD!r} and {CANONICAL_CTC_CARD!r}; got "
            f"{llm_card!r} and {ctc_card!r}"
        )


def freeze_fairseq2_asset_overrides(*, _policy_root: Path | None = None) -> Path:
    """Point both fairseq2 override sources at private, verified-empty directories."""
    global _CARD_POLICY_TEMP
    if _policy_root is None:
        if _CARD_POLICY_TEMP is None:
            _CARD_POLICY_TEMP = tempfile.TemporaryDirectory(prefix="hawedit-omniasr-cards-")
        root = Path(_CARD_POLICY_TEMP.name)
    else:
        root = _policy_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
    locations = {
        "FAIRSEQ2_ASSET_DIR": root / "system",
        "FAIRSEQ2_USER_ASSET_DIR": root / "user",
    }
    for variable, directory in locations.items():
        if directory.is_symlink():
            raise OmniAssetError(
                f"private fairseq2 card directory must not be a symlink: {directory}"
            )
        directory.mkdir(mode=0o700, exist_ok=True)
        try:
            unexpected = tuple(directory.iterdir())
        except OSError as exc:
            raise OmniAssetError(
                f"cannot inspect private fairseq2 card directory {directory}: {exc}"
            ) from exc
        if unexpected:
            raise OmniAssetError(
                f"private fairseq2 card directory is not empty: {directory}: "
                f"{[path.name for path in unexpected]!r}"
            )
        directory.chmod(0o500)
        os.environ[variable] = str(directory)
    return root


def _open_regular_nofollow(
    path: Path, *, require_single_link: bool = False
) -> tuple[BinaryIO, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise OmniAssetError(f"cannot open canonical OmniASR asset {path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OmniAssetError(f"canonical OmniASR asset is not a regular file: {path}")
        if require_single_link and before.st_nlink != 1:
            raise OmniAssetError(
                f"canonical OmniASR asset must have exactly one hard link: {path}: "
                f"got {before.st_nlink}"
            )
        return os.fdopen(descriptor, "rb"), before
    except BaseException:
        os.close(descriptor)
        raise


def _hash_open_stream(
    stream: BinaryIO, before: os.stat_result, path: Path
) -> tuple[os.stat_result, str]:
    digest = hashlib.sha256()
    while chunk := stream.read(8 * 1024 * 1024):
        digest.update(chunk)
    after = os.fstat(stream.fileno())
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_nlink,
    )
    if identity_after != identity_before:
        raise OmniAssetError(f"canonical OmniASR asset changed while it was hashed: {path}")
    stream.seek(0)
    return before, digest.hexdigest()


def _hash_stable_file(
    path: Path, *, require_single_link: bool = False
) -> tuple[os.stat_result, str]:
    stream, before = _open_regular_nofollow(path, require_single_link=require_single_link)
    with stream:
        return _hash_open_stream(stream, before, path)


def _verify_asset(asset: OmniAsset, cache_dir: Path) -> OmniAssetReport:
    asset_dir = cache_dir / asset.cache_key
    path = asset.path_in(cache_dir)
    if asset_dir.is_symlink() or path.is_symlink():
        raise OmniAssetError(f"canonical OmniASR cache path must not be a symlink: {path}")
    try:
        members = tuple(asset_dir.iterdir())
    except OSError as exc:
        raise OmniAssetError(
            f"cannot inspect canonical OmniASR cache directory {asset_dir}: {exc}"
        ) from exc
    if len(members) != 1 or members[0].name != asset.filename:
        raise OmniAssetError(
            f"canonical OmniASR cache directory must contain only {asset.filename!r}: "
            f"{asset_dir}: {[member.name for member in members]!r}. Move that exact directory "
            "aside and rerun hawedit-asr-setup"
        )
    before, actual_hash = _hash_stable_file(path, require_single_link=True)
    if before.st_size != asset.size or actual_hash != asset.sha256:
        raise OmniAssetError(
            f"canonical OmniASR asset integrity failed for {path}: expected "
            f"{asset.size} bytes/{asset.sha256}, got {before.st_size} bytes/{actual_hash}. "
            f"Move {asset_dir} aside and rerun hawedit-asr-setup"
        )
    return OmniAssetReport(asset.name, path, before.st_size, actual_hash)


@contextmanager
def open_verified_omni_assets(
    *, cache_dir: Path | None = None, assets: Sequence[OmniAsset] = OMNI_ASSETS
) -> Iterator[tuple[OpenedOmniAsset, ...]]:
    """Keep the exact verified inodes open while fairseq2 deserializes through ``/proc``."""
    root = (cache_dir or fairseq2_cache_dir()).resolve()
    descriptor_root = next(
        (candidate for candidate in (Path("/proc/self/fd"), Path("/dev/fd")) if candidate.is_dir()),
        None,
    )
    if descriptor_root is None:
        raise OmniAssetError(
            "canonical OmniASR requires /proc/self/fd or /dev/fd to bind verified bytes to load"
        )
    streams: list[BinaryIO] = []
    opened: list[OpenedOmniAsset] = []
    alias_root = Path(tempfile.mkdtemp(prefix="hawedit-omniasr-open-"))
    try:
        for asset in assets:
            asset_dir = root / asset.cache_key
            path = asset.path_in(root)
            if asset_dir.is_symlink() or path.is_symlink():
                raise OmniAssetError(f"canonical OmniASR cache path must not be a symlink: {path}")
            try:
                members = tuple(asset_dir.iterdir())
            except OSError as exc:
                raise OmniAssetError(
                    f"cannot inspect canonical OmniASR cache directory {asset_dir}: {exc}"
                ) from exc
            if len(members) != 1 or members[0].name != asset.filename:
                raise OmniAssetError(
                    f"canonical OmniASR cache directory must contain only {asset.filename!r}: "
                    f"{asset_dir}: {[member.name for member in members]!r}"
                )
            stream, before = _open_regular_nofollow(path, require_single_link=True)
            try:
                _, actual_hash = _hash_open_stream(stream, before, path)
                if before.st_size != asset.size or actual_hash != asset.sha256:
                    raise OmniAssetError(
                        f"canonical OmniASR asset integrity failed for {path}: expected "
                        f"{asset.size} bytes/{asset.sha256}, got "
                        f"{before.st_size} bytes/{actual_hash}"
                    )
                descriptor_path = descriptor_root / str(stream.fileno())
                if not descriptor_path.exists():
                    raise OmniAssetError(
                        f"verified OmniASR descriptor is unavailable at {descriptor_path}"
                    )
                alias_path = alias_root / asset.filename
                alias_path.symlink_to(descriptor_path)
                report = OmniAssetReport(asset.name, path, before.st_size, actual_hash)
                streams.append(stream)
                opened.append(OpenedOmniAsset(asset, alias_path, alias_path.as_uri(), report))
            except BaseException:
                stream.close()
                raise
        alias_root.chmod(0o500)
        yield tuple(opened)
    finally:
        for stream in reversed(streams):
            stream.close()
        if alias_root.exists():
            alias_root.chmod(0o700)
            shutil.rmtree(alias_root)


def assert_omni_card_integrity(*, card_path: Path | None = None) -> Path:
    """Prove that the installed 0.2.0 card metadata is the reviewed official document."""
    if card_path is None:
        try:
            distribution = importlib.metadata.distribution("omnilingual-asr")
        except importlib.metadata.PackageNotFoundError as exc:
            raise OmniAssetError(
                "canonical ASR needs omnilingual-asr==0.2.0 inside its Linux runtime"
            ) from exc
        if distribution.version != "0.2.0":
            raise OmniAssetError(
                f"canonical ASR requires omnilingual-asr==0.2.0, got {distribution.version!r}"
            )
        try:
            fairseq2_version = importlib.metadata.version("fairseq2")
        except importlib.metadata.PackageNotFoundError as exc:
            raise OmniAssetError("canonical ASR requires fairseq2==0.6") from exc
        if fairseq2_version != "0.6":
            raise OmniAssetError(f"canonical ASR requires fairseq2==0.6, got {fairseq2_version!r}")
        unresolved = Path(str(distribution.locate_file(_CARD_RELATIVE_PATH)))
    else:
        unresolved = card_path
    if unresolved.is_symlink():
        raise OmniAssetError(f"canonical OmniASR model card must not be a symlink: {unresolved}")
    path = unresolved.resolve()
    before, actual_hash = _hash_stable_file(path)
    if before.st_size != _CARD_SIZE or actual_hash != _CARD_SHA256:
        raise OmniAssetError(
            f"canonical OmniASR model-card integrity failed for {path}: expected "
            f"{_CARD_SIZE} bytes/{_CARD_SHA256}, got {before.st_size} bytes/{actual_hash}"
        )
    return path


def _public_metadata(card: Any) -> dict[str, object]:
    metadata = getattr(card, "metadata", None)
    if not isinstance(metadata, Mapping):
        raise OmniAssetError("fairseq2 returned an invalid OmniASR asset card")
    return {str(key): value for key, value in metadata.items() if not str(key).startswith("__")}


def assert_effective_omni_cards(asset_store: Any) -> None:
    """Validate the metadata fairseq2 will actually use, including the bare tokenizer ref."""
    expected = {
        CANONICAL_LLM_CARD: {
            "model_family": "wav2vec2_llama",
            "model_arch": "7b_v2",
            "checkpoint": OMNI_ASSETS[0].url,
            "tokenizer_ref": _TOKENIZER_CARD,
        },
        CANONICAL_CTC_CARD: {
            "model_family": "wav2vec2_asr",
            "model_arch": "3b_v2",
            "checkpoint": OMNI_ASSETS[1].url,
            "tokenizer_ref": _TOKENIZER_CARD,
        },
        _TOKENIZER_CARD: {
            "tokenizer_family": "char_tokenizer",
            "tokenizer": OMNI_ASSETS[2].url,
        },
    }
    for name, wanted in expected.items():
        try:
            card = asset_store.retrieve_card(name)
        except Exception as exc:
            raise OmniAssetError(f"cannot resolve canonical fairseq2 card {name!r}: {exc}") from exc
        actual = _public_metadata(card)
        if actual != wanted or getattr(card, "base", None) is not None:
            raise OmniAssetError(
                f"effective fairseq2 card {name!r} drifted from HawEdit's reviewed metadata: "
                f"{actual!r}"
            )


def assert_omni_asset_integrity(
    *, cache_dir: Path | None = None, assets: Sequence[OmniAsset] = OMNI_ASSETS
) -> tuple[OmniAssetReport, ...]:
    """Hash every required file and fail before any OmniASR weight loader is called."""
    root = (cache_dir or fairseq2_cache_dir()).resolve()
    return tuple(_verify_asset(asset, root) for asset in assets)


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    """Serialize long-running provisioning without trusting the predictable lock name."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        resolved = path.parent.resolve(strict=True) / path.name
    except OSError as exc:
        raise OmniAssetError(f"cannot prepare OmniASR provision lock {path}: {exc}") from exc
    with _open_provision_lock(resolved) as stream:
        if _WINDOWS_HOST:
            # The Linux typeshed intentionally has no ``msvcrt.locking`` members even
            # though mypy still checks this runtime-only Windows branch in CI.
            msvcrt = importlib.import_module("msvcrt")
            deadline = time.monotonic() + _PROVISION_LOCK_TIMEOUT_S
            while True:
                try:
                    stream.seek(0)
                except OSError as exc:
                    raise OmniAssetError(
                        f"cannot position OmniASR provision lock {resolved}: {exc}"
                    ) from exc
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise OmniAssetError(
                            f"timed out after {_PROVISION_LOCK_TIMEOUT_S / 3600:.0f}h waiting "
                            f"for OmniASR provision lock {resolved}"
                        ) from exc
                    time.sleep(_PROVISION_LOCK_RETRY_S)
            try:
                _validate_provision_lock(stream, resolved)
                yield
            except BaseException:
                with suppress(OSError):
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                raise
            else:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError as exc:
                    raise OmniAssetError(
                        f"cannot release OmniASR provision lock {resolved}: {exc}"
                    ) from exc
        else:
            # typeshed intentionally hides POSIX fcntl members while mypy runs on the
            # Windows host; this branch executes only inside the Linux/WSL ASR runtime.
            fcntl = importlib.import_module("fcntl")
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            except OSError as exc:
                raise OmniAssetError(
                    f"cannot acquire OmniASR provision lock {resolved}: {exc}"
                ) from exc
            try:
                _validate_provision_lock(stream, resolved)
                yield
            except BaseException:
                with suppress(OSError):
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                raise
            else:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                except OSError as exc:
                    raise OmniAssetError(
                        f"cannot release OmniASR provision lock {resolved}: {exc}"
                    ) from exc


def _invalid_provision_lock(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)
    )


def _validate_provision_lock(stream: BinaryIO, path: Path) -> None:
    try:
        opened = os.fstat(stream.fileno())
        named = os.lstat(path)
    except OSError as exc:
        raise OmniAssetError(f"cannot inspect OmniASR provision lock {path}: {exc}") from exc
    if (
        _invalid_provision_lock(opened)
        or _invalid_provision_lock(named)
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        raise OmniAssetError(
            "OmniASR provision lock must be one unlinked regular file without symlinks or "
            f"reparse points and remain bound to its opened descriptor: {path}"
        )


def _open_provision_lock(path: Path) -> BinaryIO:
    """Open the final component without following or modifying an unsafe existing object."""
    try:
        checked = os.lstat(path)
    except FileNotFoundError:
        checked = None
    except OSError as exc:
        raise OmniAssetError(f"cannot inspect OmniASR provision lock {path}: {exc}") from exc
    if checked is not None and _invalid_provision_lock(checked):
        raise OmniAssetError(
            "OmniASR provision lock must be one unlinked regular file without symlinks or "
            f"reparse points: {path}"
        )

    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise OmniAssetError(f"cannot safely open OmniASR provision lock {path}: {exc}") from exc
    try:
        stream = os.fdopen(descriptor, "r+b")
        descriptor = -1
        _validate_provision_lock(stream, path)
        opened = os.fstat(stream.fileno())
        if checked is not None and (checked.st_dev, checked.st_ino) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise OmniAssetError(f"OmniASR provision lock was replaced before open: {path}")
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            stream.flush()
            os.fsync(stream.fileno())
            _validate_provision_lock(stream, path)
        stream.seek(0)
        return stream
    except BaseException as exc:
        if descriptor >= 0:
            os.close(descriptor)
        else:
            stream.close()
        if isinstance(exc, OSError):
            raise OmniAssetError(f"cannot initialize OmniASR provision lock {path}: {exc}") from exc
        raise


def _download_response(request: Request, timeout: float) -> Any:
    return urlopen(request, timeout=timeout)


def _download_one(
    asset: OmniAsset,
    cache_dir: Path,
    *,
    opener: Callable[[Request, float], Any],
    progress: bool,
) -> OmniAssetReport:
    target_dir = cache_dir / asset.cache_key
    target = asset.path_in(cache_dir)
    if target_dir.exists():
        return _verify_asset(asset, cache_dir)

    temporary = Path(tempfile.mkdtemp(prefix=f".{asset.cache_key}.hawedit-", dir=cache_dir))
    candidate = temporary / asset.filename
    try:
        request = Request(asset.url, headers={"User-Agent": "HawEdit/0.1 OmniASR integrity"})
        try:
            response_context = opener(request, 60.0)
            with response_context as response, candidate.open("xb") as output:
                final_url = str(response.geturl())
                if urlsplit(final_url).scheme != "https":
                    raise OmniAssetError(
                        f"canonical OmniASR download left HTTPS for {asset.name}: {final_url!r}"
                    )
                status_code = getattr(response, "status", None)
                if status_code != 200:
                    raise OmniAssetError(
                        f"canonical OmniASR download returned HTTP {status_code!r} for {asset.name}"
                    )
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        announced_size = int(content_length)
                    except ValueError as exc:
                        raise OmniAssetError(
                            f"canonical OmniASR download returned an invalid Content-Length for "
                            f"{asset.name}: {content_length!r}"
                        ) from exc
                    if announced_size != asset.size:
                        raise OmniAssetError(
                            f"canonical OmniASR download announced {announced_size} bytes for "
                            f"{asset.name}; expected {asset.size}"
                        )
                digest = hashlib.sha256()
                downloaded = 0
                next_report = 1 << 30
                while chunk := response.read(8 * 1024 * 1024):
                    downloaded += len(chunk)
                    if downloaded > asset.size:
                        raise OmniAssetError(
                            f"canonical OmniASR download exceeded {asset.size} bytes for "
                            f"{asset.name}"
                        )
                    output.write(chunk)
                    digest.update(chunk)
                    if progress and downloaded >= next_report:
                        print(
                            f"OmniASR: {asset.name}: {downloaded / (1 << 30):.1f} GiB",
                            file=sys.stderr,
                        )
                        next_report += 1 << 30
                output.flush()
                os.fsync(output.fileno())
        except OmniAssetError:
            raise
        except Exception as exc:
            raise OmniAssetError(
                f"canonical OmniASR download failed for {asset.name}: {exc}"
            ) from exc
        actual_hash = digest.hexdigest()
        if downloaded != asset.size or actual_hash != asset.sha256:
            raise OmniAssetError(
                f"canonical OmniASR download integrity failed for {asset.name}: expected "
                f"{asset.size} bytes/{asset.sha256}, got {downloaded} bytes/{actual_hash}"
            )
        candidate.chmod(0o444)
        try:
            temporary.rename(target_dir)
        except FileExistsError:
            _verify_asset(asset, cache_dir)
        if not target.is_file():
            raise OmniAssetError(f"canonical OmniASR asset was not published at {target}")
        return _verify_asset(asset, cache_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def provision_omni_assets(
    *,
    cache_dir: Path | None = None,
    assets: Sequence[OmniAsset] = OMNI_ASSETS,
    progress: bool = True,
    _opener: Callable[[Request, float], Any] = _download_response,
) -> tuple[OmniAssetReport, ...]:
    """Download missing canonical files, atomically publish them, then hash the complete set."""
    root = (cache_dir or fairseq2_cache_dir()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with _exclusive_file_lock(root / ".hawedit-omniasr.lock"):
        return tuple(
            _download_one(asset, root, opener=_opener, progress=progress) for asset in assets
        )
