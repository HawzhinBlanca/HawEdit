"""Diagnose actual sampler leakage using existing native fixture preparation, not a study."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import tempfile
from pathlib import Path

from hawedit.editorial_acceptance import prepare_editorial_study
from hawedit.wsl_setup import package_digest


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "tests"))
    from test_editorial_acceptance import FIXTURE, _inventory

    destination = root / "specs/evidence-based-studio/T8-editorial-split-counterexample.json"
    if destination.exists():
        raise RuntimeError("Refusing to overwrite an actual diagnostic")
    with tempfile.TemporaryDirectory(prefix="hawedit-split-diagnostic-") as directory:
        root = Path(directory)
        inventory, media_root, _ = _inventory(root)
        prepared = prepare_editorial_study(
            inventory_path=inventory,
            media_root=media_root,
            output_dir=root / "study",
            sample_size=200,
        )
        manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
        training = [item for item in manifest["items"] if item["split"] == "training"]
        holdout = [item for item in manifest["items"] if item["split"] == "holdout"]
        train_media = {item["source"]["media_id"] for item in training}
        holdout_media = {item["source"]["media_id"] for item in holdout}
        result = {
            "status": "unaccepted-fixture-sampler-diagnostic",
            "source_package_sha256": package_digest(),
            "python": platform.python_version(),
            "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "test_helper": "tests.test_editorial_acceptance._inventory",
            "real_human_evaluation": False,
            "training_count": len(training),
            "holdout_count": len(holdout),
            "overlapping_media_ids": sorted(train_media & holdout_media),
            "split_policy": manifest["split_policy"],
            "manifest_sha256": prepared.manifest_sha256,
        }
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
