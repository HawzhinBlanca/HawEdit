# Verified checkpoint recipe/load binding — 2026-08-09

## Reproduced gap

The Qwen visual embedder and reranker read checkpoint-controlled pooling, prompt and score-token
JSON in their constructors, before checkpoint integrity ran. An attacker could construct an object
from altered recipe files, restore the pinned bytes, then pass the later integrity check while the
object retained the malicious prompt/token ids. Separately, visual, VideoChat3 and Qwen-ASR loaders
hashed by pathname, closed verification, and reopened the mutable directory in Transformers. A
hardlink or directory replacement between those operations could make the model consume bytes that
were never verified; VideoChat3's remote model code made that executable, not just numerical.
Finally, Windows `msvcrt` locks and WSL `flock` locks do not interoperate on DrvFS: a real probe
acquired the WSL shared lock while a Windows writer held its exclusive lock.

## Current boundary

`ModelStore.verified_checkpoint_access()` acquires the checkpoint's shared lock, verifies the exact
manifest with no-follow descriptor/path identity checks, and yields the verified directory while
the lock remains held. Qwen visual loading now keeps that context across:

1. the Transformers safe-config/model-family guard;
2. pooling/prompt or score-token recipe parsing;
3. Torch/Transformers imports and CUDA refusal;
4. processor/config construction; and
5. the complete `from_pretrained` calls, loading-info check and device move.

Embedder/reranker constructors no longer read recipes. Accessing their recipe before the first
verified load is a domain refusal. Qwen-ASR uses the same integrity-first context through config,
imports, CUDA and `Qwen3ASRModel.from_pretrained`, loading from the yielded verified path.
VideoChat3 and TimeLens use the shared visual loader and therefore inherit the same boundary.
For Windows-to-WSL Qwen-ASR validation, the host producer additionally holds the Windows shared
`verified_checkpoint_access` lease across request publication, the complete WSL subprocess and
output validation. That bridge blocks the host fetcher's Windows writer even though the worker's
Linux advisory lock is a separate mechanism.

Regressions construct objects from hostile prompts/token ids, restore the trusted files before
load, and prove only the restored verified values are cached. Event-order tests prove integrity
precedes config/recipe/import, and a live context flag proves every constructor read occurs while
the binding is held. Malformed recipe JSON becomes a component-domain refusal rather than an
unhandled parser exception.

The combined Qwen/ASR/VideoChat/TimeLens/model run passed 193 tests; Ruff, formatting, targeted Mypy
and diff checks passed. A real child writer regression proves publication cannot enter until the
simulated WSL worker boundary exits. The final canonical gate passed 1,457/1,457 with zero skips
and fresh accepted JUnit evidence. This change did not reload all 37.269 GB of real visual checkpoints, so the
historical GPU measurements prove those model versions run, not that this new held-lock path has
fresh production execution evidence. That real-load recheck remains an acceptance task.
