"""Run inside the isolated Chatterbox environment, with pre-provisioned local weights."""

from __future__ import annotations

import importlib
import json
import os
import sys
import wave
from pathlib import Path


def _offline(event: str, args: tuple[object, ...]) -> None:
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise OSError("Voice synthesis runs offline")


def main(request: Path) -> None:
    sys.addaudithook(_offline)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import numpy as np

    torch = importlib.import_module("torch")
    engine = importlib.import_module("chatterbox.mtl_tts").ChatterboxMultilingualTTS
    data = json.loads(request.read_text(encoding="utf-8"))
    if torch.cuda.is_available():
        count = torch.cuda.device_count()
        best = max(range(count), key=lambda i: torch.cuda.mem_get_info(i)[0]) if count > 1 else 0
        device = f"cuda:{best}" if count > 1 else "cuda"
    else:
        device = "cpu"
        torch.set_num_threads(min(8, os.cpu_count() or 1))
    model = engine.from_local(Path(data["weights"]), device)
    for index, phrase in enumerate(data["phrases"]):
        voice = model.generate(
            phrase, language_id=data["language"], audio_prompt_path=data["reference"]
        )
        samples = np.asarray(voice.detach().cpu().numpy()).reshape(-1)
        if not samples.size or not np.isfinite(samples).all():
            raise ValueError("Voice model returned invalid audio")
        with wave.open(str(request.parent / f"cue-{index}.wav"), "wb") as track:
            track.setparams((1, 2, model.sr, 0, "NONE", "not compressed"))
            track.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    main(Path(sys.argv[1]))
