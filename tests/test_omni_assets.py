from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request

import pytest

from hawedit.omni_assets import (
    CANONICAL_CTC_CARD,
    CANONICAL_LLM_CARD,
    OMNI_ASSETS,
    OmniAsset,
    OmniAssetError,
    assert_canonical_omni_cards,
    assert_effective_omni_cards,
    assert_omni_asset_integrity,
    assert_omni_card_integrity,
    fairseq2_cache_dir,
    freeze_fairseq2_asset_overrides,
    provision_omni_assets,
)


def _asset(payload: bytes = b"canonical-weights") -> OmniAsset:
    return OmniAsset(
        name="fixture",
        url="https://weights.example/fixture.pt",
        filename="fixture.pt",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _write_cached(cache: Path, asset: OmniAsset, payload: bytes) -> Path:
    path = asset.path_in(cache)
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    return path


class _Response(io.BytesIO):
    status = 200

    def __init__(
        self,
        payload: bytes,
        *,
        url: str,
        content_length: str | None = None,
    ) -> None:
        super().__init__(payload)
        self._url = url
        self.headers = {} if content_length is None else {"Content-Length": content_length}

    def geturl(self) -> str:
        return self._url


def test_canonical_manifest_matches_the_fairseq2_url_cache_layout() -> None:
    assert [asset.cache_key for asset in OMNI_ASSETS] == [
        "116c2dd9dc4cf95c0aac590e",
        "0a31b71a234e317bd6f84e33",
        "e7be1a6acb8f76fdbca19dce",
    ]
    assert sum(asset.size for asset in OMNI_ASSETS) == 43_546_500_168


def test_cache_resolution_matches_fairseq2_precedence(tmp_path: Path) -> None:
    assert (
        fairseq2_cache_dir(
            environ={"FAIRSEQ2_CACHE_DIR": str(tmp_path / "explicit")}, home=tmp_path / "home"
        )
        == (tmp_path / "explicit").resolve()
    )
    assert (
        fairseq2_cache_dir(
            environ={"XDG_CACHE_HOME": str(tmp_path / "xdg")}, home=tmp_path / "home"
        )
        == (tmp_path / "xdg" / "fairseq2" / "assets").resolve()
    )
    assert (
        fairseq2_cache_dir(environ={}, home=tmp_path / "home")
        == (tmp_path / "home" / ".cache" / "fairseq2" / "assets").resolve()
    )


@pytest.mark.parametrize("variable", ["FAIRSEQ2_CACHE_DIR", "XDG_CACHE_HOME"])
def test_empty_cache_environment_values_are_refused(variable: str, tmp_path: Path) -> None:
    with pytest.raises(OmniAssetError, match="working directory"):
        fairseq2_cache_dir(environ={variable: "  "}, home=tmp_path)


def test_only_environment_disabled_official_cards_are_canonical() -> None:
    assert_canonical_omni_cards(CANONICAL_LLM_CARD, CANONICAL_CTC_CARD)
    with pytest.raises(OmniAssetError, match="environment-disabled"):
        assert_canonical_omni_cards("omniASR_LLM_7B_v2", CANONICAL_CTC_CARD)
    with pytest.raises(OmniAssetError, match="only permits"):
        assert_canonical_omni_cards(CANONICAL_LLM_CARD, "custom")


def test_cached_asset_requires_exact_size_and_sha256(tmp_path: Path) -> None:
    payload = b"canonical-weights"
    asset = _asset(payload)
    path = _write_cached(tmp_path, asset, payload)
    report = assert_omni_asset_integrity(cache_dir=tmp_path, assets=(asset,))
    assert report[0].path == path
    assert report[0].size == len(payload)
    assert report[0].sha256 == hashlib.sha256(payload).hexdigest()

    path.write_bytes(b"canonical-weightz")
    with pytest.raises(OmniAssetError, match="integrity failed"):
        assert_omni_asset_integrity(cache_dir=tmp_path, assets=(asset,))


def test_hardlinked_asset_is_refused_before_hash_or_load(tmp_path: Path) -> None:
    payload = b"canonical-weights"
    asset = _asset(payload)
    path = _write_cached(tmp_path, asset, payload)
    os.link(path, tmp_path / "second-name.pt")
    with pytest.raises(OmniAssetError, match="exactly one hard link"):
        assert_omni_asset_integrity(cache_dir=tmp_path, assets=(asset,))


def test_existing_corruption_is_refused_without_network_replacement(tmp_path: Path) -> None:
    payload = b"canonical-weights"
    asset = _asset(payload)
    _write_cached(tmp_path, asset, b"tampered-bytes!!!")
    calls = 0

    def forbidden(_request: Request, _timeout: float) -> _Response:
        nonlocal calls
        calls += 1
        raise AssertionError("corrupt cache attempted a network replacement")

    with pytest.raises(OmniAssetError, match="integrity failed"):
        provision_omni_assets(
            cache_dir=tmp_path, assets=(asset,), progress=False, _opener=forbidden
        )
    assert calls == 0


def test_missing_asset_is_published_only_after_download_integrity(tmp_path: Path) -> None:
    payload = b"canonical-weights"
    asset = _asset(payload)
    requests: list[tuple[str, float]] = []

    def opener(request: Request, timeout: float) -> _Response:
        requests.append((request.full_url, timeout))
        return _Response(payload, url=asset.url, content_length=str(len(payload)))

    report = provision_omni_assets(
        cache_dir=tmp_path, assets=(asset,), progress=False, _opener=opener
    )
    assert requests == [(asset.url, 60.0)]
    assert report[0].path.read_bytes() == payload


def test_bad_download_leaves_no_fairseq2_cache_entry(tmp_path: Path) -> None:
    payload = b"canonical-weights"
    asset = _asset(payload)

    def opener(_request: Request, _timeout: float) -> _Response:
        tampered = b"canonical-weightz"
        return _Response(tampered, url=asset.url, content_length=str(len(tampered)))

    with pytest.raises(OmniAssetError, match="download integrity failed"):
        provision_omni_assets(cache_dir=tmp_path, assets=(asset,), progress=False, _opener=opener)
    assert not (tmp_path / asset.cache_key).exists()
    assert not tuple(tmp_path.glob(f".{asset.cache_key}.hawedit-*"))


def test_download_refuses_a_non_https_final_location(tmp_path: Path) -> None:
    payload = b"canonical-weights"
    asset = _asset(payload)

    def opener(_request: Request, _timeout: float) -> _Response:
        return _Response(payload, url="http://mirror.example/fixture.pt")

    with pytest.raises(OmniAssetError, match="left HTTPS"):
        provision_omni_assets(cache_dir=tmp_path, assets=(asset,), progress=False, _opener=opener)
    assert not (tmp_path / asset.cache_key).exists()


def test_download_refuses_an_upstream_size_change_before_reading(tmp_path: Path) -> None:
    payload = b"canonical-weights"
    asset = _asset(payload)

    def opener(_request: Request, _timeout: float) -> _Response:
        return _Response(payload, url=asset.url, content_length=str(len(payload) + 1))

    with pytest.raises(OmniAssetError, match="announced"):
        provision_omni_assets(cache_dir=tmp_path, assets=(asset,), progress=False, _opener=opener)


def test_cache_directory_refuses_any_unverified_extra_member(tmp_path: Path) -> None:
    payload = b"canonical-weights"
    asset = _asset(payload)
    path = _write_cached(tmp_path, asset, payload)
    (path.parent / "unreviewed.yaml").write_text("checkpoint: elsewhere\n", encoding="utf-8")
    with pytest.raises(OmniAssetError, match="must contain only"):
        assert_omni_asset_integrity(cache_dir=tmp_path, assets=(asset,))


def test_private_card_sources_replace_ambient_fairseq_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FAIRSEQ2_ASSET_DIR", str(tmp_path / "attacker-system"))
    monkeypatch.setenv("FAIRSEQ2_USER_ASSET_DIR", str(tmp_path / "attacker-user"))
    root = freeze_fairseq2_asset_overrides(_policy_root=tmp_path / "policy")
    system = Path(os.environ["FAIRSEQ2_ASSET_DIR"])
    user = Path(os.environ["FAIRSEQ2_USER_ASSET_DIR"])
    assert root == (tmp_path / "policy").resolve()
    assert system != user
    assert system.parent == root == user.parent
    assert not tuple(system.iterdir())
    assert not tuple(user.iterdir())


def test_installed_card_document_requires_exact_reviewed_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    card = tmp_path / "rc_models_v2.yaml"
    payload = b"reviewed-card"
    card.write_bytes(payload)
    monkeypatch.setattr("hawedit.omni_assets._CARD_SIZE", len(payload))
    monkeypatch.setattr("hawedit.omni_assets._CARD_SHA256", hashlib.sha256(payload).hexdigest())
    assert assert_omni_card_integrity(card_path=card) == card.resolve()
    card.write_bytes(b"reviewed-carf")
    with pytest.raises(OmniAssetError, match="model-card integrity failed"):
        assert_omni_card_integrity(card_path=card)


def test_installed_card_allows_package_manager_hardlinks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_copy = tmp_path / "wheel-cache-card.yaml"
    card = tmp_path / "rc_models_v2.yaml"
    payload = b"reviewed-card"
    cache_copy.write_bytes(payload)
    os.link(cache_copy, card)
    monkeypatch.setattr("hawedit.omni_assets._CARD_SIZE", len(payload))
    monkeypatch.setattr("hawedit.omni_assets._CARD_SHA256", hashlib.sha256(payload).hexdigest())

    assert assert_omni_card_integrity(card_path=card) == card.resolve()


def test_runtime_refuses_same_name_wrong_omnilingual_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hawedit.omni_assets.importlib.metadata.distribution",
        lambda _name: SimpleNamespace(version="0.2.1"),
    )
    with pytest.raises(OmniAssetError, match="requires omnilingual-asr==0.2.0"):
        assert_omni_card_integrity()


class _Card:
    def __init__(self, metadata: dict[str, object]) -> None:
        self.metadata = metadata
        self.base = None


class _Store:
    def __init__(self) -> None:
        self.cards = {
            CANONICAL_LLM_CARD: _Card(
                {
                    "model_family": "wav2vec2_llama",
                    "model_arch": "7b_v2",
                    "checkpoint": OMNI_ASSETS[0].url,
                    "tokenizer_ref": "omniASR_tokenizer_written_v2",
                    "__source__": "package:omnilingual_asr.cards",
                }
            ),
            CANONICAL_CTC_CARD: _Card(
                {
                    "model_family": "wav2vec2_asr",
                    "model_arch": "3b_v2",
                    "checkpoint": OMNI_ASSETS[1].url,
                    "tokenizer_ref": "omniASR_tokenizer_written_v2",
                    "__source__": "package:omnilingual_asr.cards",
                }
            ),
            "omniASR_tokenizer_written_v2": _Card(
                {
                    "tokenizer_family": "char_tokenizer",
                    "tokenizer": OMNI_ASSETS[2].url,
                    "__source__": "package:omnilingual_asr.cards",
                }
            ),
        }

    def retrieve_card(self, name: str) -> _Card:
        return self.cards[name]


def test_effective_cards_match_every_loader_relevant_field() -> None:
    store = _Store()
    assert_effective_omni_cards(store)

    store.cards[CANONICAL_LLM_CARD].metadata["checkpoint"] = "https://evil.example/model.pt"
    with pytest.raises(OmniAssetError, match="drifted"):
        assert_effective_omni_cards(store)


def test_bare_tokenizer_reference_cannot_honor_a_user_override() -> None:
    store = _Store()
    store.cards["omniASR_tokenizer_written_v2"].metadata["tokenizer"] = (
        "https://evil.example/tokenizer.model"
    )
    with pytest.raises(OmniAssetError, match="drifted"):
        assert_effective_omni_cards(store)


def test_effective_card_cannot_disable_restricted_checkpoint_loading() -> None:
    store = _Store()
    store.cards[CANONICAL_CTC_CARD].metadata["restrict"] = False
    with pytest.raises(OmniAssetError, match="drifted"):
        assert_effective_omni_cards(store)
