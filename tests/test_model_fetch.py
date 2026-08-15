from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from getpass import getuser
from pathlib import Path
from types import ModuleType

import pytest

from hawedit import models as model_contract
from hawedit.environment import EnvironmentAuditError
from hawedit.model_fetch import (
    DOWNLOAD_CLIENT_VERSION,
    FetchItem,
    FetchPlan,
    ModelFetchError,
    _create_fresh_private_stage,
    _download_client,
    build_fetch_plan,
    fetch_checkpoint,
    main,
    validate_private_stage,
)
from hawedit.models import (
    CheckpointIntegrityReport,
    ModelStatus,
    ModelStore,
)
from hawedit.registry import REGISTRY
from hawedit.windows_security import create_private_directory

MODEL_ID = "Qwen3-VL-Embedding-2B"
REPOSITORY = "Qwen/test-embedding"
REVISION = "a" * 40


@pytest.fixture(autouse=True)
def _private_model_root_fixture(tmp_path: Path) -> None:
    """Production requires a non-writable model root; make pytest's shared temp root one."""
    if os.name != "nt":
        tmp_path.chmod(0o700)
        return
    result = subprocess.run(
        [
            "icacls",
            str(tmp_path),
            "/inheritance:r",
            "/grant:r",
            f"{getuser()}:(OI)(CI)F",
            "*S-1-5-18:(OI)(CI)F",
            "*S-1-5-32-544:(OI)(CI)F",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _item(tmp_path: Path) -> FetchItem:
    return FetchItem(
        entry=REGISTRY[MODEL_ID],
        repository=REPOSITORY,
        revision=REVISION,
        destination=tmp_path / MODEL_ID,
    )


def _report(selected: Path) -> CheckpointIntegrityReport:
    return CheckpointIntegrityReport(
        model_id=MODEL_ID,
        repository=REPOSITORY,
        revision=REVISION,
        files_verified=sum(1 for path in selected.rglob("*") if path.is_file()),
        size_bytes=sum(path.stat().st_size for path in selected.rglob("*") if path.is_file()),
    )


def test_plan_uses_registry_source_revision_and_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    entry = REGISTRY[MODEL_ID]
    monkeypatch.setattr(ModelStore, "missing_weights", lambda _self: (entry,))
    monkeypatch.setattr(ModelStore, "source_for", lambda _self, _entry: REPOSITORY)
    monkeypatch.setattr(ModelStore, "revision_for", lambda _self, _source: REVISION)
    monkeypatch.setattr(ModelStore, "assert_checkpoint_provisionable", lambda *_args: None)

    plan = build_fetch_plan(store, MODEL_ID)

    assert plan.unconfigured == ()
    assert plan.items == (_item(tmp_path),)


def test_plan_does_not_redownload_exact_validator_bytes_for_a_runtime_only_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The WSL loader and the immutable checkpoint are repaired by different commands."""
    model_id = "rzgar/qwen3-asr-sorani-kurdish-ckb-v1"
    entry = REGISTRY[model_id]
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    checkpoint = store.path_for(entry)
    checkpoint.mkdir(parents=True)
    (checkpoint / "model.safetensors").write_bytes(b"exact validator bytes")
    monkeypatch.setattr(
        ModelStore,
        "verify_checkpoint",
        lambda _self, selected_id, selected=None: CheckpointIntegrityReport(
            model_id=selected_id,
            repository=model_id,
            revision="b" * 40,
            files_verified=1,
            size_bytes=21,
        ),
    )
    monkeypatch.setattr(model_contract, "_is_importable", lambda _module: False)
    monkeypatch.setattr(ModelStore, "source_for", lambda _self, _entry: model_id)
    monkeypatch.setattr(ModelStore, "revision_for", lambda _self, _source: "b" * 40)
    monkeypatch.setattr(ModelStore, "assert_checkpoint_provisionable", lambda *_args: None)

    plan = build_fetch_plan(store, model_id)

    assert plan.items == ()
    assert plan.unconfigured == ()
    assert plan.refused == ()


def test_plan_accumulates_a_blocked_or_mismatched_manifest_before_network_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    entry = REGISTRY[MODEL_ID]
    monkeypatch.setattr(ModelStore, "missing_weights", lambda _self: (entry,))
    monkeypatch.setattr(ModelStore, "source_for", lambda _self, _entry: REPOSITORY)
    monkeypatch.setattr(ModelStore, "revision_for", lambda _self, _source: REVISION)
    monkeypatch.setattr(
        ModelStore,
        "assert_checkpoint_provisionable",
        lambda *_args: (_ for _ in ()).throw(
            model_contract.CheckpointIntegrityError("checkpoint verification is blocked")
        ),
    )

    plan = build_fetch_plan(store, MODEL_ID)

    assert plan.items == ()
    assert plan.refused == ((MODEL_ID, "checkpoint verification is blocked"),)


def test_plan_refuses_a_non_checkpoint_name(tmp_path: Path) -> None:
    with pytest.raises(ModelFetchError, match="not a downloadable checkpoint"):
        build_fetch_plan(ModelStore(root=tmp_path, metadata_root=tmp_path), "Gemini 2.5 Pro")


@pytest.mark.parametrize(
    "source",
    [
        "https://user:hf_SUPERSECRET@huggingface.co/org/repo?token=hf_SUPERSECRET",
        "org/repo.git",
        "org/../repo",
        "org//repo",
        "org/repo\naccess_token=hf_SUPERSECRET",
        ["org/repo"],
    ],
)
def test_plan_refuses_non_repo_sources_without_echoing_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: object
) -> None:
    entry = REGISTRY[MODEL_ID]
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    monkeypatch.setattr(ModelStore, "missing_weights", lambda _self: (entry,))
    monkeypatch.setattr(ModelStore, "source_for", lambda _self, _entry: source)

    with pytest.raises(ModelFetchError, match="allowlisted|repository id string") as raised:
        build_fetch_plan(store, MODEL_ID)

    assert "hf_SUPERSECRET" not in str(raised.value)
    assert "https://" not in str(raised.value)


def test_happy_download_verifies_then_publishes_without_a_partial_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    item = _item(tmp_path)
    events: list[str] = []

    def download(**kwargs: object) -> object:
        assert kwargs["repo_id"] == REPOSITORY
        assert kwargs["revision"] == REVISION
        staging = Path(str(kwargs["local_dir"]))
        assert staging.parent == tmp_path
        assert not item.destination.exists()
        (staging / "config.json").write_text("{}", encoding="utf-8")
        events.append("download")
        return staging

    def verify(
        _self: ModelStore, model_id: str, selected: Path | None = None
    ) -> CheckpointIntegrityReport:
        assert model_id == MODEL_ID and selected is not None
        events.append("verify-final" if selected == item.destination else "verify-stage")
        return _report(selected)

    monkeypatch.setattr(ModelStore, "verify_checkpoint", verify)
    report = fetch_checkpoint(item, store, download)

    assert events == ["download", "verify-stage", "verify-final"]
    assert report.files_verified == 1
    assert (item.destination / "config.json").read_text(encoding="utf-8") == "{}"


def test_preplanted_resume_hardlink_is_refused_before_downloader_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    item = _item(tmp_path)
    resume = tmp_path / f".{MODEL_ID}.resume-{REVISION}"
    if os.name == "nt":
        create_private_directory(resume)
    else:
        resume.mkdir(mode=0o700)
    victim = tmp_path / "victim"
    victim.write_bytes(b"ORIGINAL")
    os.link(victim, resume / "config.json")
    called = False

    def download(**_kwargs: object) -> object:
        nonlocal called
        called = True
        victim.write_bytes(b"CLOBBERED")
        return None

    with pytest.raises(ModelFetchError, match="hard link|another principal"):
        fetch_checkpoint(item, store, download)

    assert called is False
    assert victim.read_bytes() == b"ORIGINAL"
    assert resume.is_dir()


def test_fresh_stage_is_private_on_the_current_platform(tmp_path: Path) -> None:
    destination = tmp_path / "checkpoint"
    stage = _create_fresh_private_stage(destination, REVISION)

    if os.name != "nt":
        assert stage.stat().st_mode & 0o077 == 0
        validate_private_stage(stage)
        return

    validate_private_stage(stage)
    grant = subprocess.run(
        ["icacls", str(stage), "/grant", "*S-1-1-0:(OI)(CI)F"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert grant.returncode == 0, grant.stderr
    with pytest.raises(ModelFetchError, match="another principal"):
        validate_private_stage(stage)


def test_preplanted_publication_lock_is_a_domain_refusal_before_download(tmp_path: Path) -> None:
    item = _item(tmp_path)
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    victim = tmp_path / "lock-victim"
    victim.write_bytes(b"ORIGINAL")
    lock = tmp_path / f".{MODEL_ID}.hawedit.lock"
    os.link(victim, lock)
    called = False

    def download(**_kwargs: object) -> object:
        nonlocal called
        called = True
        return None

    with pytest.raises(ModelFetchError, match="lock must be one unlinked regular file"):
        fetch_checkpoint(item, store, download)

    assert called is False
    assert victim.read_bytes() == b"ORIGINAL"
    assert lock.stat().st_nlink == 2


def test_safe_failed_download_is_preserved_under_the_deterministic_resume_name(
    tmp_path: Path,
) -> None:
    item = _item(tmp_path)
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)

    def download(**kwargs: object) -> object:
        staging = Path(str(kwargs["local_dir"]))
        (staging / "partial.bin").write_bytes(b"partial")
        raise OSError("network lost")

    with pytest.raises(ModelFetchError, match="network lost"):
        fetch_checkpoint(item, store, download)

    resume = tmp_path / f".{MODEL_ID}.resume-{REVISION}"
    assert (resume / "partial.bin").read_bytes() == b"partial"
    assert not item.destination.exists()


@pytest.mark.parametrize("signal", [KeyboardInterrupt(), SystemExit(130)])
def test_process_control_preserves_safe_resume_then_propagates_unchanged(
    tmp_path: Path, signal: BaseException
) -> None:
    item = _item(tmp_path)
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)

    def download(**kwargs: object) -> object:
        (Path(str(kwargs["local_dir"])) / "partial.bin").write_bytes(b"partial")
        raise signal

    with pytest.raises(type(signal)) as raised:
        fetch_checkpoint(item, store, download)

    assert raised.value is signal
    resume = tmp_path / f".{MODEL_ID}.resume-{REVISION}"
    assert (resume / "partial.bin").read_bytes() == b"partial"


def test_process_death_leaves_one_discoverable_resume_for_the_next_run(tmp_path: Path) -> None:
    item = _item(tmp_path)
    script = textwrap.dedent(
        f"""
        import os
        from pathlib import Path
        from hawedit.model_fetch import FetchItem, fetch_checkpoint
        from hawedit.registry import REGISTRY

        item = FetchItem(
            entry=REGISTRY[{MODEL_ID!r}],
            repository={REPOSITORY!r},
            revision={REVISION!r},
            destination=Path({str(item.destination)!r}),
        )
        class Store:
            def verify_checkpoint(self, *_args):
                raise AssertionError("hard-exit smoke must stop before verification")
        def download(**kwargs):
            (Path(kwargs["local_dir"]) / "partial.bin").write_bytes(b"partial")
            os._exit(73)
        fetch_checkpoint(item, Store(), download)
        """
    )
    result = subprocess.run([sys.executable, "-c", script], check=False)

    assert result.returncode == 73
    resume = tmp_path / f".{MODEL_ID}.resume-{REVISION}"
    assert (resume / "partial.bin").read_bytes() == b"partial"
    assert not tuple(tmp_path.glob(f".{MODEL_ID}.download-*"))

    class Store:
        def verify_checkpoint(
            self, _model_id: str, selected: Path | None = None
        ) -> CheckpointIntegrityReport:
            assert selected in (resume, item.destination)
            assert selected is not None
            return _report(selected)

    def finish(**kwargs: object) -> object:
        assert Path(str(kwargs["local_dir"])) == resume
        (resume / "complete.bin").write_bytes(b"complete")
        return resume

    fetch_checkpoint(item, Store(), finish)  # type: ignore[arg-type]
    assert (item.destination / "partial.bin").read_bytes() == b"partial"
    assert (item.destination / "complete.bin").read_bytes() == b"complete"


def test_download_failure_diagnostic_is_bounded_printable_and_secret_free(tmp_path: Path) -> None:
    item = _item(tmp_path)
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    secret = "hf_super_secret"

    def download(**_kwargs: object) -> object:
        raise OSError(
            "GET https://cdn.invalid/file?X-Amz-Signature=signed-value\n"
            f"Authorization: Bearer {secret}\x00 token={secret} access_token={secret} "
            f"Cookie: sid={secret} https://user:{secret}@cdn.invalid/private " + "X" * 50_000
        )

    with pytest.raises(ModelFetchError) as raised:
        fetch_checkpoint(item, store, download)

    message = str(raised.value)
    assert len(message) <= 840
    assert secret not in message
    assert "signed-value" not in message
    assert "https://cdn.invalid/file?<redacted>" in message
    assert "\n" not in message and "\x00" not in message
    assert message.endswith("…")


def test_bare_hugging_face_token_is_redacted_through_api_and_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "hf_SUPERSECRET123456789"
    item = _item(tmp_path)
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)

    def leaking_download(**_kwargs: object) -> object:
        raise OSError(f"HF_TOKEN {secret}")

    with pytest.raises(ModelFetchError) as raised:
        fetch_checkpoint(item, store, leaking_download)
    assert secret not in str(raised.value)
    assert "hf_<redacted>" in str(raised.value)

    monkeypatch.setattr(
        "hawedit.model_fetch.build_fetch_plan", lambda _store, _only="": FetchPlan((item,), ())
    )
    monkeypatch.setattr("hawedit.model_fetch._download_client", lambda: leaking_download)
    monkeypatch.setattr(ModelStore, "status", lambda _self: ())
    assert main(["--models-dir", str(tmp_path), MODEL_ID]) == 1
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert "hf_<redacted>" in captured.err


def test_final_published_path_is_reverified_and_invalid_bytes_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = _item(tmp_path)
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)

    def download(**kwargs: object) -> object:
        (Path(str(kwargs["local_dir"])) / "config.json").write_text("{}", encoding="utf-8")
        return None

    def verify(
        _self: ModelStore, _model_id: str, selected: Path | None = None
    ) -> CheckpointIntegrityReport:
        assert selected is not None
        if selected == item.destination:
            raise model_contract.CheckpointIntegrityError(
                "published path changed after staging verification"
            )
        return _report(selected)

    monkeypatch.setattr(ModelStore, "verify_checkpoint", verify)
    with pytest.raises(ModelFetchError, match="published path changed"):
        fetch_checkpoint(item, store, download)

    assert item.destination.is_dir()
    assert (item.destination / "config.json").read_text(encoding="utf-8") == "{}"


def test_model_root_identity_drift_stops_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = _item(tmp_path)
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    original_lstat = os.lstat
    drifted = False

    class ChangedIdentity:
        def __init__(self, original: os.stat_result) -> None:
            self._original = original
            self.st_ino = original.st_ino + 1

        def __getattr__(self, name: str) -> object:
            return getattr(self._original, name)

    def lstat(
        path: str | os.PathLike[str], *, dir_fd: int | None = None
    ) -> os.stat_result | ChangedIdentity:
        observed = original_lstat(path, dir_fd=dir_fd)
        if drifted and Path(os.fsdecode(path)) == tmp_path:
            return ChangedIdentity(observed)
        return observed

    monkeypatch.setattr(os, "lstat", lstat)

    def download(**kwargs: object) -> object:
        nonlocal drifted
        (Path(str(kwargs["local_dir"])) / "config.json").write_text("{}", encoding="utf-8")
        drifted = True
        return None

    with pytest.raises(ModelFetchError, match="model root changed"):
        fetch_checkpoint(item, store, download)
    assert not item.destination.exists()


def test_model_root_reparse_is_refused_before_downloader_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = _item(tmp_path)
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    called = False
    module = __import__("hawedit.model_fetch", fromlist=["_path_is_reparse"])
    original = module._path_is_reparse
    monkeypatch.setattr(
        "hawedit.model_fetch._path_is_reparse",
        lambda path: Path(path) == tmp_path or original(path),
    )

    def download(**_kwargs: object) -> object:
        nonlocal called
        called = True
        return None

    with pytest.raises(ModelFetchError, match="unlinked regular directory"):
        fetch_checkpoint(item, store, download)
    assert called is False


def test_untrusted_model_root_writer_is_refused_before_download(tmp_path: Path) -> None:
    item = _item(tmp_path)
    store = ModelStore(root=tmp_path, metadata_root=tmp_path)
    if os.name == "nt":
        grant = subprocess.run(
            ["icacls", str(tmp_path), "/grant", "*S-1-1-0:(OI)(CI)F"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert grant.returncode == 0, grant.stderr
    else:
        tmp_path.chmod(0o777)
    called = False

    def download(**_kwargs: object) -> object:
        nonlocal called
        called = True
        return None

    with pytest.raises(ModelFetchError, match="mutation"):
        fetch_checkpoint(item, store, download)
    assert called is False


def test_download_client_is_exact_and_never_auto_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hawedit.model_fetch.audit_installed_profile", lambda _profile: None)
    monkeypatch.setattr("hawedit.model_fetch.importlib.metadata.version", lambda _name: "0.36.1")
    with pytest.raises(ModelFetchError, match=f"expected {DOWNLOAD_CLIENT_VERSION}"):
        _download_client()


def test_download_client_supports_the_real_lazy_hugging_face_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def expected(**_kwargs: object) -> None:
        return None

    class LazyModule(ModuleType):
        def __getattr__(self, name: str) -> object:
            if name == "snapshot_download":
                return expected
            raise AttributeError(name)

    module = LazyModule("huggingface_hub")
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    monkeypatch.setattr("hawedit.model_fetch.audit_installed_profile", lambda _profile: None)
    monkeypatch.setattr(
        "hawedit.model_fetch.importlib.metadata.version", lambda _name: DOWNLOAD_CLIENT_VERSION
    )

    assert _download_client() is expected


def test_status_and_empty_plan_do_not_require_the_download_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ModelStore, "status", lambda _self: ())
    assert main(["--models-dir", str(tmp_path), "--status"]) == 0
    assert "15/15" not in capsys.readouterr().out

    monkeypatch.setattr(
        "hawedit.model_fetch.build_fetch_plan",
        lambda _store, _only="": type(
            "Plan", (), {"items": (), "unconfigured": (), "refused": ()}
        )(),
    )
    monkeypatch.setattr(
        "hawedit.model_fetch._download_client",
        lambda: (_ for _ in ()).throw(AssertionError("download client imported for empty plan")),
    )
    assert main(["--models-dir", str(tmp_path)]) == 0


def test_status_normalizes_expected_readiness_io_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        ModelStore,
        "status",
        lambda _self: (_ for _ in ()).throw(PermissionError("metadata denied")),
    )

    assert main(["--models-dir", str(tmp_path), "--status"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "REFUSED: cannot read model readiness: PermissionError: metadata denied" in captured.err


def test_plan_metadata_failure_is_a_concise_nonzero_cli_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "hawedit.model_fetch.build_fetch_plan",
        lambda _store, _only="": (_ for _ in ()).throw(UnicodeError("bad metadata bytes")),
    )

    assert main(["--models-dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "REFUSED: bad metadata bytes\n"


def test_unconfigured_target_is_failure_without_loading_the_download_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "hawedit.model_fetch.build_fetch_plan",
        lambda _store, _only="": FetchPlan((), (MODEL_ID,)),
    )
    monkeypatch.setattr(ModelStore, "status", lambda _self: ())
    monkeypatch.setattr(
        "hawedit.model_fetch._download_client",
        lambda: (_ for _ in ()).throw(AssertionError("loaded client for an empty plan")),
    )

    assert main(["--models-dir", str(tmp_path), MODEL_ID]) == 1
    captured = capsys.readouterr()
    assert "no download source configured" in captured.err
    assert "nothing fetchable" in captured.out


def test_one_failed_target_does_not_hide_later_work_or_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = _item(tmp_path)
    second = FetchItem(first.entry, first.repository, first.revision, tmp_path / "second")
    monkeypatch.setattr(
        "hawedit.model_fetch.build_fetch_plan",
        lambda _store, _only="": FetchPlan((first, second), ()),
    )
    monkeypatch.setattr("hawedit.model_fetch._download_client", lambda: lambda **_kwargs: None)
    monkeypatch.setattr(ModelStore, "status", lambda _self: ())
    attempted: list[Path] = []

    def fetch(item: FetchItem, _store: ModelStore, _download: object) -> CheckpointIntegrityReport:
        attempted.append(item.destination)
        if item is first:
            raise ModelFetchError("first transfer failed")
        return CheckpointIntegrityReport(
            item.entry.model_id,
            item.repository,
            item.revision,
            files_verified=1,
            size_bytes=7,
        )

    monkeypatch.setattr("hawedit.model_fetch.fetch_checkpoint", fetch)

    assert main(["--models-dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert attempted == [first.destination, second.destination]
    assert f"FAILED: {MODEL_ID}: first transfer failed" in captured.err
    assert "done: 1 files, 7 bytes" in captured.out


def test_final_target_readiness_not_status_printing_drives_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    item = _item(tmp_path)
    monkeypatch.setattr(
        "hawedit.model_fetch.build_fetch_plan", lambda _store, _only="": FetchPlan((item,), ())
    )
    monkeypatch.setattr("hawedit.model_fetch._download_client", lambda: lambda **_kwargs: None)
    monkeypatch.setattr(
        "hawedit.model_fetch.fetch_checkpoint",
        lambda _item, _store, _download: CheckpointIntegrityReport(
            MODEL_ID, REPOSITORY, REVISION, files_verified=1, size_bytes=7
        ),
    )
    monkeypatch.setattr(
        ModelStore,
        "status",
        lambda _self: (
            ModelStatus(
                MODEL_ID,
                item.entry.component,
                item.entry.provisioning,
                False,
                "published bytes failed final readiness",
            ),
        ),
    )

    assert main(["--models-dir", str(tmp_path), MODEL_ID]) == 1
    captured = capsys.readouterr()
    assert "done: 1 files, 7 bytes" in captured.out
    assert f"FAILED: final checkpoint readiness refused {MODEL_ID}" in captured.err


def test_project_declares_installed_fetch_command_and_exact_optional_client() -> None:
    import tomllib

    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["scripts"]["hawedit-fetch-models"] == "hawedit.model_fetch:main"
    assert project["optional-dependencies"]["models"] == [
        f"huggingface-hub=={DOWNLOAD_CLIENT_VERSION}"
    ]


def test_checkout_wrapper_contains_no_second_downloader_transaction() -> None:
    script = Path("scripts/fetch-models.sh").read_text(encoding="utf-8")
    assert "hawedit.model_fetch" in script
    assert "snapshot_download" not in script
    assert "pip install" not in script
    assert "PYEOF" not in script


def test_download_client_refuses_a_non_callable_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hawedit.model_fetch.audit_installed_profile", lambda _profile: None)
    monkeypatch.setattr(
        "hawedit.model_fetch.importlib.metadata.version", lambda _name: DOWNLOAD_CLIENT_VERSION
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "huggingface_hub",
        type("FakeHub", (), {"snapshot_download": None})(),
    )

    with pytest.raises(ModelFetchError, match="snapshot_download is unavailable"):
        _download_client()


def test_download_client_refuses_transitive_profile_drift_before_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hawedit.model_fetch.audit_installed_profile",
        lambda _profile: (_ for _ in ()).throw(EnvironmentAuditError("urllib3 drifted")),
    )
    monkeypatch.setattr(
        "hawedit.model_fetch.importlib.metadata.version",
        lambda _name: (_ for _ in ()).throw(AssertionError("top-level check ran after refusal")),
    )

    with pytest.raises(ModelFetchError, match="environment refused: urllib3 drifted"):
        _download_client()
