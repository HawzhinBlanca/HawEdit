# OpenChatCut applicability assessment

Date: 2026-10-08 (Asia/Baghdad). Scope: owner-requested research, no implementation.
HawEdit inspected at `65bb556cdd87523278fa2437ba304b01f58742fa`; working tree initially clean.
OpenChatCut source pinned to `2e6f4a29b784200cfb32b859b16f2561592bc3e8`, package version
`0.2.16`. Tools: web browsing, GitHub tree API, PowerShell source reads, rg, Git.
No installation, application execution, export round-trip, quality benchmark, source edit,
feature ledger change, gate or CI run. Source inspection is not runtime acceptance.
Serena symbol/reference mapping has not been performed; any implementation needs the
repository's research/impact/approval workflow before changing symbols.

## Judgment

Useful as an editing-experience reference and potential separate finishing application.
Prioritize transcript-linked review, inspectable draft changes, and reversible timeline
interactions. Keep HawEdit's Kurdish speech, alignment, boundary, caption and delivery
authority. Direct adoption of the entire editor is a substantial architecture and licensing
choice, not a Python dependency addition.

## Existing HawEdit capability and possible contribution

| Area | HawEdit source inspected | OpenChatCut contribution | Assessment |
|---|---|---|---|
| Agent editing | `src/hawedit/editor_agent.py:43`, `proposals.py`, `policy.py` | Isolated draft sessions with base-revision checks | Improve human review of a grouped proposal; preserve D-A6's human-only commit authority |
| Transcript/timeline | `edit_plan.py`, `condenser.py:951`, `transcripts.py` | Word deletions project into retained source segments and retimed words | Adopt interaction ideas; edit a derived plan, never canonical ASR or CTC timestamps |
| Caption safety | `caption_layout.py:140`, `shot_composition.py`, `captions.py` | Face collision warnings and alternate layout suggestions | Compare UX/QA; HawEdit already protects visual regions |
| Editorial handoff | `delivery.py:297`, `timeline.py:141`, `edit_plan.py` | CMX EDL/FCPXML import, FCPXML export | Plausible separate-app experiment; no demonstrated automatic compatibility |
| Resources | HawEdit's existing render/brand pipeline | Separately licensed LUTs, sounds, motion templates | Individual MIT assets may be reusable; template runtime compatibility is separate |

Grounding: BLUEPRINT Stage 6 / §4.1–4.3 / §5 / §8.3; DECISIONS D-A6, D-A7,
D-A12 and D-307. Canon read: HawEdit Propose Commit Split and HawEdit Kurdish Invariants.

## Concrete source findings

1. OpenChatCut's [external edit sessions](https://github.com/0xsline/OpenChatCut/blob/2e6f4a29b784200cfb32b859b16f2561592bc3e8/src/agent/external-edit-session.ts)
   bind a draft to a base revision and detect stale state. Manual and automatic modes both
   exist. Its automatic apply path conflicts with HawEdit's model-can-propose/cannot-commit
   canon. A future HawEdit MCP surface should expose reads/proposals and retain a distinct
   authenticated human commit route. Adding MCP also needs a policy decision and ADR.
2. [Transcript edit projection](https://github.com/0xsline/OpenChatCut/blob/2e6f4a29b784200cfb32b859b16f2561592bc3e8/src/transcript/edit.ts)
   shares retained-segment/timing calculations between consumers. This is a useful consistency
   pattern. HawEdit already has `SourceTimeMapping` and `VisualEditPlan`; extend their UI
   rather than introduce competing clocks. Arbitrary deletion must not bypass sentence
   boundaries or change a speaker's meaning.
3. [Caption collision detection](https://github.com/0xsline/OpenChatCut/blob/2e6f4a29b784200cfb32b859b16f2561592bc3e8/src/geometry/caption-collision.ts)
   approximates caption footprint using a fixed band, scaled/rotated for layout. Useful for
   advisory placement, insufficient as actual Sorani glyph-ink evidence. D-307 requires
   decoded widths; preserve ASS/libass/HarfBuzz/FriBidi and §8.3 regression checks.
4. [Timeline import schema](https://github.com/0xsline/OpenChatCut/blob/2e6f4a29b784200cfb32b859b16f2561592bc3e8/src/agent/tools/schemas/timeline-import-tools.ts)
   accepts EDL/FCPXML, requires resolvable existing media, accepts an explicit EDL frame
   rate/origin, rounds when rates differ and reports omitted elements. Captions/effects/
   transitions do not arrive through this import. HawEdit `build_edl` emits generic `AX`
   reels without source filename comments; media binding needs verification or a deliberate
   adapter. OTIO is not listed in this import schema.
5. [FCPXML export](https://github.com/0xsline/OpenChatCut/blob/2e6f4a29b784200cfb32b859b16f2561592bc3e8/src/export/fcpxml.ts)
   uses explicit time/media mapping. Unrendered motion graphics can become placeholders;
   an editable-project export is not automatically a visually faithful round-trip.
6. [SRT parsing](https://github.com/0xsline/OpenChatCut/blob/2e6f4a29b784200cfb32b859b16f2561592bc3e8/src/captions/srt.ts)
   produces cue-level entries. SRT does not preserve HawEdit's individual CTC word timings,
   karaoke animation or ASS styling. Keep aligned-word artifacts separately.

## Licensing and stack

OpenChatCut's [package](https://github.com/0xsline/OpenChatCut/blob/2e6f4a29b784200cfb32b859b16f2561592bc3e8/package.json)
declares `AGPL-3.0-or-later`. Its [license](https://github.com/0xsline/OpenChatCut/blob/2e6f4a29b784200cfb32b859b16f2561592bc3e8/LICENSE)
permits commercial use but places source/licensing conditions on covered distributed works
and modified network-accessible versions (§§5–6,13). Do not treat copying or porting code
as permissive reuse. The exact combined-work boundary of a proposed integration needs
review; communicating over MCP is not a blanket exemption. This assessment makes no
claim about HawEdit's current distribution license.

The [repository architecture](https://github.com/0xsline/OpenChatCut#architecture) uses
React/TypeScript, Electron, Remotion and FFmpeg. Embedding it adds a second application
stack. [Remotion](https://www.remotion.dev/docs/license/pricing) has separate license terms
and company-size-dependent paid licensing. It does not establish compliance with HawEdit's
complex-script render contract.

The [resource catalog](https://openchatcut.com/resources) labels several official resources
MIT, including titles, sounds and LUTs; the agent skill itself is labeled AGPL. Inspect the
actual selected package/license and dependencies before reuse. Sound files/LUTs are more
portable than runtime-specific motion graphics. Website labels are not a completed asset
license audit. [Pro documentation](https://openchatcut.com/docs) says purchases/downloads
are not open; no recommendation depends on unreleased Pro functionality.

## Suggested next experiment (not executed or approved implementation)

Take one owner-selected Sorani interview candidate already reviewed in HawEdit. Preserve
the canonical artifacts. First try the accepted rendered clip in a separate OpenChatCut
project for finishing. Then test source-media plus CMX EDL handoff with explicitly matched
frame rate, record origin and media identity. Keep existing burned Kurdish captions or
test a separate cue import without assuming word-level fidelity. Exercise one manual draft,
reject/approve/undo, and compare source cuts, audio sync and decoded Kurdish captions.
Use the result to choose a handoff adapter or independently implemented HawEdit review UI.
Imported/exported results must return through HawEdit's review and delivery checks before
being treated as accepted HawEdit outputs.

Approval is needed only if proceeding to an implementation plan under AGENTS.md. This
research does not propose a canon change or declare an implementation done.
