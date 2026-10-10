# D-326: Explicit Private Kernel Entropy Endpoint

Status: owner-approved architecture, explicit Wareen reply2026-10-10;
accepted decision in DECISIONS.md D-326, implementation/verification WIP.
Do not treat this as current independent security review.

The actual retained Python build cannot bootstrap in the copied readonly root
without its device-based entropy path. Kernel getrandom succeeds there; its
absence from the compiled interpreter, not the existing fence, explains the
failure. Retain the pinned runtime and all irreversible protections.

Propose explicit rooted-only admission of genuine /dev/urandom, original
read-only noninheritable descriptor/anchor custody, character major1/minor9,
reserved private path and a single private readonly/nosuid/noexec endpoint
mount. All regular image files remain independently copied/read-only, root
nodev remains, and no host directory/device inventory is exposed. No fabricated
random file, fixed hash seed, kernel policy bypass or arbitrary caller path.

The endpoint is kernel state, not a hashable immutable regular model file.
Keep its identity/custody proof distinct from copied-byte hashes. Required
actual positive/damaged tests and independent security re-review remain. This
proposal does not admit GPU devices, grant cloud scope or make a reel verified.

Actual readonly-mount negative calibration still permits character-device
write opens. The opt-in's existing seccomp fence must also refuse writable
open/openat/creat and pointer-carried openat2; readonly reads/default behavior
stay intact. Do not chmod the host device or loosen the contract for SDK imports.
