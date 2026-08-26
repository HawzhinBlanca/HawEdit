"""One window where the two credentials this project needs can be pasted, checked, and stored.

The operator here is not a programmer. `hawedit-credentials` already does the job correctly but
it is a terminal prompt that handles one of the two secrets, and it says nothing about what the
secret buys. This is the same storage path with a front door: two masked boxes, a Save that
refuses anything the provider rejects, and a line per credential naming the stages it turns on
and the numbered blocker it answers.

**Nothing about secret handling is reimplemented here.** `credentials.write_credential` opens
with `O_NOFOLLOW`, creates at mode 0600 so there is no window in which the file is readable by
anyone else, rewrites the ACL to owner-only on Windows, and refuses to write anywhere Git could
track. This module collects a string and hands it to that function. The only way a stored value
is ever rendered is `credentials.mask`.

**Tk is imported inside `_open_window`, never at module scope.** `credentials.py` sits on
`pipeline.py`'s import path, and a headless machine must still be able to import this module to
reach the terminal fallback.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from hawedit.cli import program_name, use_utf8_streams
from hawedit.credentials import (
    ENV_FILE,
    GEMINI_API_KEY,
    HF_TOKEN,
    KeyCheck,
    Transport,
    _https_get,
    credential_status,
    mask,
    read_credential,
    validate_gemini_key,
    validate_hf_token,
    write_credential,
)

__all__ = [
    "CredentialSlot",
    "NoDisplay",
    "main",
    "save",
    "slots",
    "status_line",
]


class NoDisplay(RuntimeError):
    """No graphical display is available. A known state, not a crash to show an operator."""


@dataclass(frozen=True, slots=True)
class CredentialSlot:
    """One credential, and what a person needs to know about it to decide to paste it."""

    name: str
    label: str
    unlocks: str
    blocker: int
    where: str
    validate: Callable[[str, Transport], KeyCheck]
    caveat: str = ""


# `unlocks` and `caveat` are the whole reason this exists rather than a second getpass prompt.
# A window that says "API key" tells the operator nothing about what it is for or why the run
# still fails afterwards.
_SLOTS: Final = (
    CredentialSlot(
        name=GEMINI_API_KEY,
        label="Google Gemini API key",
        unlocks="§3 Stage 3 Path A discovery and Stage 4 editorial judging",
        blocker=3,
        where="https://aistudio.google.com/apikey",
        validate=validate_gemini_key,
        # §4 pins gemini-2.5-pro and its free tier is exactly zero. A panel that said "key
        # accepted" and stopped would send the operator away believing Stage 4 works.
        caveat=(
            "A valid key is not enough on its own: §4 pins gemini-2.5-pro, whose free-tier "
            "limit is exactly zero, so the key's Google Cloud project also needs billing "
            "enabled (BLOCKED.md #3)."
        ),
    ),
    CredentialSlot(
        name=HF_TOKEN,
        label="Hugging Face token",
        unlocks="§3 Stage 0 speaker diarization (pyannote Community-1)",
        blocker=4,
        where="https://huggingface.co/settings/tokens",
        validate=validate_hf_token,
        # Holding a valid token and having accepted the licence are two different acts, and
        # nothing reachable from here can see the second one.
        caveat=(
            "The checkpoint is a gated repository. A valid token proves the credential is "
            "real; the licence must also be accepted at "
            "huggingface.co/pyannote/speaker-diarization-community-1 before the download "
            "stops returning 401 (BLOCKED.md #4)."
        ),
    ),
)


def slots() -> tuple[CredentialSlot, ...]:
    """Every credential this project stores, in the order the panel shows them."""
    return _SLOTS


def save(
    slot: CredentialSlot,
    value: str,
    env_file: Path = ENV_FILE,
    transport: Transport = _https_get,
) -> KeyCheck:
    """Verify with the provider, then store. Never the other way round.

    Storing an unverified credential turns a clear "not configured" into a failure deep inside
    the first job that needs it. `credentials.main` already refuses to do that; this must not
    become the softer door into the same store.
    """
    if not value.strip():
        return KeyCheck(False, "nothing was entered — that is a typo, not a credential")
    check = slot.validate(value.strip(), transport)
    if not check.valid:
        return check
    write_credential(slot.name, value.strip(), env_file=env_file, check_ignored=False)
    return check


def status_line(
    slot: CredentialSlot,
    env_file: Path = ENV_FILE,
    transport: Transport = _https_get,
) -> str:
    """One line describing what is stored, masked, and whether the provider still accepts it."""
    stored = read_credential(slot.name, env_file)
    if stored is None:
        return f"{slot.label}: not set"
    _, check = credential_status(slot.name, env_file, transport)
    verdict = "no answer from the provider" if check is None else check.detail
    return f"{slot.label}: {mask(stored)} — {verdict}"


def _open_window() -> int:  # pragma: no cover - requires a display
    """Build and run the Tk panel. Raises `NoDisplay` where there is no display to build on."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:
        raise NoDisplay("tkinter is not available in this interpreter") from exc

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise NoDisplay(str(exc)) from exc

    root.title("HawEdit setup")
    root.minsize(720, 260)
    frame = ttk.Frame(root, padding=16)
    frame.grid(sticky="nsew")
    root.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    ttk.Label(
        frame,
        text=(
            "Paste each token and press Save. Each one is checked with its provider before "
            "anything is stored,\nand nothing is written if the check fails."
        ),
        justify="left",
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

    for index, slot in enumerate(slots()):
        row = 1 + index * 4
        ttk.Label(frame, text=slot.label, font=("", 10, "bold")).grid(
            row=row, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Label(frame, text=f"Unlocks {slot.unlocks} · get one at {slot.where}").grid(
            row=row + 1, column=0, columnspan=3, sticky="w"
        )

        # `show="*"` is why this is a password field and not a text field: the value must not
        # survive into a screenshot or a shoulder.
        entry = ttk.Entry(frame, show="*", width=56)
        entry.grid(row=row + 2, column=0, columnspan=2, sticky="ew", pady=4)

        result = ttk.Label(frame, text=status_line(slot), wraplength=680, justify="left")
        result.grid(row=row + 3, column=0, columnspan=3, sticky="w")

        def store(
            slot: CredentialSlot = slot, entry: object = entry, result: object = result
        ) -> None:
            typed = entry.get()  # type: ignore[attr-defined]
            check = save(slot, typed)
            entry.delete(0, "end")  # type: ignore[attr-defined]
            # Only ever `status_line`, which masks. The typed value is not rendered anywhere.
            text = status_line(slot) if check.valid else f"{slot.label}: {check.detail}"
            if check.valid and slot.caveat:
                text += f"\n{slot.caveat}"
            result.configure(text=text)  # type: ignore[attr-defined]

        ttk.Button(frame, text="Verify & Save", command=store).grid(
            row=row + 2, column=2, sticky="e", padx=(8, 0)
        )

    root.mainloop()
    return 0


def _terminal_fallback() -> int:  # pragma: no cover - exercised through main()
    """The audited terminal panel, for a machine with no display."""
    from hawedit.credentials import main as credentials_main

    print("No graphical display available — falling back to the terminal panel.\n")
    for slot in slots():
        print(f"{slot.label} — unlocks {slot.unlocks} (BLOCKED.md #{slot.blocker})")
        print(f"  get one at {slot.where}")
    print()
    return credentials_main([])


def main(argv: list[str] | None = None) -> int:
    """`hawedit-setup` — the window, or the terminal panel where there is no window."""
    use_utf8_streams()
    import argparse

    parser = argparse.ArgumentParser(
        prog=program_name("hawedit.setup_panel"),
        description="Store and verify the credentials §3 needs, in one window.",
    )
    parser.add_argument(
        "--no-window", action="store_true", help="use the terminal panel even if a display exists"
    )
    args = parser.parse_args(argv)
    if args.no_window:
        return _terminal_fallback()
    try:
        return _open_window()
    except NoDisplay:
        return _terminal_fallback()


if __name__ == "__main__":  # pragma: no cover - console entry point
    raise SystemExit(main())
