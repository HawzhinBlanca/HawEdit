# Research

2026-10-08, source 529dd23b935ed7d7eccd87888881cd5458ecbdf8; actual
seven-pair Serena definitions/references before editing, unchanged source.
Map: C:/Users/Wareen/AppData/Local/HawEditEvidence/validator-startup-map-529dd23-20261008/serena-map.json,
SHA256 5108d2127521aadb8552c1e6ff4412107cf9aa768c92c6df568e736a6b5b1877.

Frozen primary c163511 real ZAR worker completed 158 nonempty draft operations.
Unchanged escalation selects 76 validation operations, not a speech-accuracy
measurement. Read-only py-spy 0.4.1 observed Qwen's string input entering
librosa/core/audio.py optional lazy imports, inspect.stack and module realpath
resolution on Windows-mounted WSL storage. This is a captured startup path, not
a measured whole-run bottleneck proportion. Installed qwen-asr 0.0.6 utils.py
accepts (numpy.ndarray, sample_rate), leaves mono 16000 Hz unchanged before its
float32 range normalization. No neural policy change is required.

Soundfile is locked in the WSL environment but absent from the standard native
gate environment. Do not add a dependency: use the existing standard-library
wave plus NumPy PCM16 conversion already used by ingest.detect_speech. Restrict
optimization to complete, bounded mono 16 kHz PCM16 WAV; preserve the string
input for other formats, empty/truncated/oversized files or unreadable headers.

Actual fresh-file msvcrt probe: native C: acquires; WSL UNC returns errno 22,
EINVAL. Current setup retries every OSError for six hours. The owned alternate
setup alone was stopped; no successful native-Linux runtime was established.
Probe source SHA256 06236aa36072f6f937f26f1881354ce3511aa5b6cfb28dcf4cb12cef7dfc1086;
stdout b21948e8094b39a9c308a0a80d6d93f854001dc23ba30d92276a0f4d47b3aaeb.
Microsoft's _locking contract documents EACCES as locking violation, EBADF and
EINVAL as permanent failures, and EDEADLOCK for the blocking retry mode:
https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking?view=msvc-170
Preserve historical EDEADLK contention compatibility and EACCES retry/deadline;
normalize every other errno immediately. Do not bypass locking or claim UNC
support. BLUEPRINT section3 Stage1 and section8.1; D-278; blockers1/3/4/24/25
remain separate from this repair; closed champion licence blocker21 stays closed.
