# Actual Impact Map

Only existing edited code symbol: native_io.run_native. Definition/reference
map in research.md includes exact source, exports and direct capability tests.
Scoped rg additionally maps dynamic importlib/embedded-string callers in entire
tests/test_native_io.py and tests/test_native_io_memory.py. Preserve all three
complete native IO/capability modules and whole test_native_process.py.

_NativePipe read/write/transfer/completion/close and NativeJob create/wait/stop/
close mapped with actual definitions/references but are not edited. Their exact
original object/handle/arena cleanup remains the sole execution path.

A new private finite framing state is not a generic worker callback or public
producer. No current protected producer run_native caller exists. Default options
are additive and preserve existing callers. No WslOmniAsrProducer, builder,
durable queue/attempt/effect/HTTP, model, media, fixture or golden edit here.
Cover current lifetime/storage/billing/runtime/host/model-fetch acceptance callers
with complete affected modules; actual model/provider execution remains unadmitted.
