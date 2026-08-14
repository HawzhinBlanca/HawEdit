# Confidential ZDR is held across every judge and public entry point

> Integrated 2026-08-10 from protected-main finding `3765add`; readiness test fix
> `f53b849`. Production `src/hawedit/gemini.py` was already correct and remained unchanged.

## The measured failure under mutation

§3 has two distinct governance boundaries. `Governance.assert_permits_upload` protects the Gemini
Developer API, while `Governance.assert_permits_vertex` protects the confidential Vertex route.
Protected main neutered each gate independently. The Developer API mutation reddened four tests;
removing the confidential Vertex gate reddened none.

With the Vertex check disabled, a judge configured exactly like a confidential job made two HTTP
calls—`countTokens` and `generateContent`—while all tests remained green. The recorded request
contained the confidential Kurdish transcript and real source JPEG bytes. The production gate was
right; the suite had proved only the other route.

## Why one Vertex regression is insufficient

Readiness already maintained `_concrete_judges()` as a bidirectional inventory of
`GeminiJudge` and every transitive production subclass for §7 routing. The same inventory now
accepts optional governance and a recording transport, so the confidential rule is a property of
the constructible class set rather than one hand-picked constructor.

The new matrix proves:

- every judge refuses confidential material when ZDR is absent;
- every judge refuses claimed ZDR with empty or whitespace attribution;
- the refusal occurs before transport (`api.urls == []`), not after disclosure;
- attributed approval does not substitute for actual ZDR configuration;
- `count_parts` and `generate_json` each gate independently, so a future caller cannot rely on
  today's count-before-generate ordering; and
- every judge still sends non-confidential material, preventing an always-refuse or dead-transport
  implementation from satisfying the negative cases.

There are 13 new behavioral cases. Focused acceptance is 78/78 Gemini tests with Ruff clean and
the production module clean under strict mypy. Protected main reported its corresponding mutation
set at 10/10 after the separating states were added; this branch relies on behavioral coverage and
the canonical whole-repository gate rather than restating that mutation run as local evidence.

## Confidentiality result

No production relaxation was made. A confidential transcript or source frame cannot reach either
Google route unless the selected route's own governance check accepts its exact state. Vertex
requires both configured ZDR and a nonblank attribution; the Developer API continues to refuse
confidential uploads even when flags claim ZDR, because flags cannot transform its endpoint into
Vertex.
