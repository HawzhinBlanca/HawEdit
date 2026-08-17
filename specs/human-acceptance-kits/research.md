# Research — human acceptance kits

## Scope

This feature implements the autonomous preparation required by AC-7 through AC-11 before Hawa
supplies licensed media, expert labels, gated-model access, a paid Vertex project, or release
approval. It does not manufacture those inputs and it does not promote a model or release.

The governing sources are `BLUEPRINT.md` §§3, 7, 8.1, and 8.2; `BLOCKED.md` #1, #4, #9, #13,
#14, #15, #18, and #21; and the approved `specs/true-10-10-acceptance/` acceptance contract.

## Existing surfaces

### Sorani ASR

- `hawedit.corpus.Corpus` represents raw human references, dialects, the seven §8.1 conditions,
  durations, optional word timings, and a licensed provenance record.
- `Corpus.assert_section_8_1_coverage()` refuses missing dialect/condition cells and less than the
  D-009 three-hour floor.
- `hawedit.corpus_import` pessimistically imports Common Voice and human-confirmed Cortex records.
  It does not guess dialect, conditions, duration, or human confirmation.
- `hawedit.bench` produces per-dialect and per-condition accuracy, alignment, throughput, and
  hardware evidence and refuses model promotion from an interim corpus.

Missing handoff controls: the manifest does not bind the audio bytes or raw reference bytes, does
not record consent/authorization separately from a licence label, does not constrain paths to one
dataset root, and does not detect duplicate audio, duplicated item identity, or overlap with a
declared training/exclusion set. A human can therefore provide a syntactically valid corpus that
changes after review or leaks training material into evaluation without the benchmark noticing.

### Editorial study

- `hawedit.editorial_bench.EditorialRegressionSet` verifies exact candidate/span pairing, at least
  two named reviewers, real media, dialect coverage, and the 20-item judge-promotion floor.
- `hawedit.repurposing` implements Recall@K by path, temporal IoU, sentence completeness,
  misleading-edit rate, pairwise preference, cost, and wall-clock metrics.

The 20-item regression set is intentionally not AC-8. There is no deterministic 200–500 candidate
sampling artifact, concealed A/B identity, independent reviewer records, disagreement/adjudication
record, immutable training/holdout split, leakage check, or one command that produces the §8.2
promotion report.

Caller mapping for Task 2 found no production caller that can safely be broadened in place.
`EditorialRegressionSet.load/evaluate` is the 20-item judge-promotion surface used only by its CLI
and tests. `decide_judge` consumes aggregate incumbent/shadow/tie counts, while the complete §8.2
metrics live separately in `repurposing.py`. The acceptance kit should therefore be a new coordinator
boundary which consumes strict candidate inventory, calls the existing verdict and metric types, and
emits a compatibility regression set only after signed human labels are complete. This preserves the
20-item model-regression meaning rather than quietly redefining it as the 200–500-item threshold set.

The deterministic design is content-derived rather than operator-seeded: the exact inventory bytes,
study id, and fixed namespaces rank candidates within each dialect, assign a near-equal stratified
sample, freeze a per-dialect 80/20 training/holdout split, and choose A/B order. The coordinator-only
manifest carries the answer key and split; the reviewer packet carries only opaque options. Two
distinct signed reviewer documents cover the exact sampled item set. A third, distinct signed
adjudicator resolves exactly the fields on which reviewers disagree. Every signature names the same
manifest and reviewer-packet digests, so labels cannot be moved between studies.

Adversarial implementation review sharpened those boundaries. Evaluation must reopen the exact
inventory and recompute the sample, opaque ids, A/B order, holdout and manifest; trusting only an
`inventory_sha256` field would allow a balanced but hand-picked set. Candidate files must be
probeable video, match their declared duration, and keep the same digest across ffprobe. The source
hour denominator must equal the unique media identities. Signature independence is four distinct
OpenSSH key fingerprints, not merely four role-name strings, and the one allowed-signers snapshot is
captured before all verification. Coordinator approval precedes both reviews; adjudication follows
both and preserves each disagreement, both signed positions and the reason.

The final report shall keep training and holdout slices separate and shall expose pairwise preference,
Recall@20 by discovery path, path-unique wins, temporal IoU to the adjudicated gold span, sentence
completeness, misleading-edit rate, reviewer disagreement, and cost/wall-clock per source hour. It
does not invent thresholds or claim that the absent humans have tuned them; it produces immutable
training and holdout inputs for that later human-enabled step.

### Diarization and speaker-aware reframing

- `hawedit.diarization` implements exclusive-turn validation, exact DER speaker mapping, and word-
  boundary reconciliation.
- `hawedit.reframe` distinguishes ordinary face tracking from speaker-labelled face evidence and
  refuses points that contradict the active exclusive turn.
- `hawedit.ingest` records diarization absence explicitly; it does not claim a production diarizer.

There is no real-data manifest binding footage, reference turns, word timings, consent, and the
gated pyannote model identity; no benchmark command combines DER, boundary quality, speaker-face
association, and crop stability; and no acceptance record distinguishes a measured speaker-tracked
result from the explicit fallback.

Task 3 caller research confirms that the core measurements and production composition seams already
exist and should not be broadened. `attach_diarization` is the least-trusted exclusive-turn boundary;
`diarization_error_rate` performs the exact optimal speaker mapping and preserves missed speech,
false alarm and confusion; `boundary_reconciliation` measures turn edges against aligned words;
`validate_speaker_focus_points` proves a claimed focus point names the speaker active in the same
system's measured turn. The missing artifact is a coordinator that binds all four to one authorised
real-media study and compares them with human reference turns and face centres.

The acceptance schema must keep two identities separate: the production Community-1 model pinned at
revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` and the non-routable 3.1 benchmark control. It
must require a human gated-access/licence assertion and verified checkpoint receipt rather than
converting the public metadata pin into access. Each media item must be probeable video with at
least two reference speakers, strict exclusive turns, aligned reference words, and reference
speaker-face points on exact timestamps. Each system run must be content-bound to the same media and
model receipt. Community-1 and every production consumer remain strictly exclusive. The 3.1
benchmark control may emit ordinary overlapping diarization, so its benchmark-only DER uses speaker
time and counts extra simultaneous speakers as false alarm instead of either rejecting the required
control or weakening production's exclusive-turn boundary. A run may say `speaker_tracked` only
when attributed focus points validate against exclusive turns; ambiguous/overlapping visual
association is an explicit fallback.

No accuracy threshold is specified in the frozen blueprint, so the autonomous report must expose
raw per-system/per-item facts instead of inventing a pass line: DER and its components, boundary
mean absolute error and within-the-recorded-tolerance rate, mapped active-speaker association error,
horizontal centre MAE/normalised MAE, crop step/jitter statistics, speaker-tracked versus fallback
counts, and the exact attribution/model/media/signature evidence. Human reference creation, gated
licence acceptance, qualified pyannote runtime/model execution and the final crop-quality judgment
remain external. The packet removes schema, recomputation and reporting discovery; it does not
pretend the absent production adapter or dependency lock exists.

### Confidential Vertex

Gemini/Vertex adapters, governance routing, bounded errors, no-redirect transport, and no-retry
billing controls exist. The missing item is an operator-safe acceptance packet: project/location,
ADC and billing preflight, approved retention record, exact media/transcript binding, bounded-cost
confirmation, one live request, and a redacted non-secret evidence artifact.

Task 4 caller research keeps the acceptance boundary separate from the ordinary pipeline. The
existing `VertexGeminiJudge` is the authority for the regional URL, ADC bearer header,
confidential-governance check, real `countTokens`, lower-tier ceiling, schema validation and the
single non-retried `generateContent` call. `extract_judge_frames` is the authority for sourcing at
most twenty real JPEG frames from the exact candidate span. `NormalizedTranscript` remains the
only model-input transcript type. The coordinator must compose those surfaces rather than create a
second Vertex client, frame sampler, token estimator or verdict parser.

The live acceptance has two distinct boundaries. A local preparation phase binds one authorised
video, its measured duration, one exact normalised transcript, the candidate slice, project,
location, model, cost limits, billing assertion and retained ZDR-policy digest, then emits an
unsigned approval template without transport. Execution reopens and re-hashes every private input,
requires the owner-signed approval, refreshes ADC and checks its project plus the live Cloud Billing
state before client content leaves the machine, extracts the exact frames, and reserves a
content-derived attempt identity before the first model request. The reservation is retained even
when counting or generation fails: an ambiguous crash cannot turn a rerun into a second paid call.

The model boundary should expose one counted judgment operation. Calling `countTokens` in the
coordinator and then ordinary `judge()` would count the same content twice, and worse, the count
used for the human-approved limit would not necessarily be the count that authorises generation.
`GeminiJudge.judge_with_count` therefore owns count, the project ceiling, the stricter approved
ceiling and exactly one generation attempt as one operation; ordinary `judge` delegates to it.

The public evidence contains only hashes and non-content operational facts: media/transcript/frame
digests, clip bounds, model/project/location, ADC credential class and project, a hash of the billing
account reference and ZDR policy, token count, estimated input price, numeric verdict fields,
signature identity and timestamps. It excludes access tokens, account names, the full transcript,
source frame bytes, generated Kurdish title/description/hashtags and any retained policy text.
Billing enablement and ADC can be mechanically checked. Contractual ZDR configuration, media
rights and the permitted spend remain signed human assertions; the kit binds them but cannot make
them true.

### Decisions and release

The repository already records the facts behind the unresolved semantic choices and implements
exact-SHA reproducible building, installed-wheel smoke, OIDC attestation, and immutable release
publication. Humans still need concise decision forms for #13/#14/#15/#18/#9/#21 and an explicit
version/tag approval. The final release kit must verify rather than recreate these controls.

Task 5 release caller research separates four authorities. `hawedit.release` authenticates one
successful official main-branch gate, exports the immutable Git object twice, and creates the exact
wheel/SBOM/provenance/checksum bundle. `.github/workflows/release.yml` owns the unprivileged build,
two-version installed-wheel smoke, fresh privileged attestation, strict pre-existing tag check,
draft byte comparison and immutable publication. `evidence/versioned-immutable-release.md` owns the
forward-only rollback rule. The new approval coordinator must consume and independently verify those
facts; calling the builder, creating/moving a tag, pushing Git, uploading an asset or publishing a
release would duplicate or bypass the existing authority.

The human handoff therefore has two phases. Preparation takes one downloaded four-file release
artifact plus the exact successful release-workflow run id. It reopens every member through a
stable no-follow/single-link read, requires the exact file set, validates strict SHA256SUMS grammar,
binds wheel/SBOM/provenance bytes, requires schema-5 provenance for one strict SemVer HawEdit version
and official successful main gate, then queries the official GitHub release run and independently
runs the same signer-workflow/source-ref/source-digest/signer-digest/hosted-runner attestation policy
for all four payloads. The candidate tag is derived as `v<version>`; it is never supplied or guessed.

The packet also binds `BLOCKED.md`, `PROGRESS.md` and the immutable-release policy from the exact
clean candidate checkout. It emits all residual blocker text by hash, the payload hashes, run/job
facts, exact attestation commands, forward-only rollback text and an approval template with no owner,
timestamp, decision, rationale or risk acknowledgements selected. Verification reopens the packet,
bundle and exact hosted evidence, requires an OpenSSH signature over the completed approval, and
returns a tag-authorization record containing pasteable commands. It still makes no repository
mutation: the human act is creating and pushing the exact annotated tag, after which the existing
workflow alone can publish.

Installed-operator research found that `hawedit.decision_packets` already has a prepare-only,
machine-readable `main`, while `hawedit.vertex_acceptance` exposes the settled prepare/run library
boundary but no parser. The integrated handoff therefore adds thin launchers only: owner decisions
map directly to the existing transport-free prepare call; Vertex maps `prepare` to the offline
packet function and `run` to the signed one-attempt function. The CLI must not introduce a second
Google transport, hidden confirmation flag, credential value, retry, or alternate evidence writer.

Search found no production decision-packet type or writer. The authoritative inputs are the six
open `BLOCKED.md` sections named by HK-8 and wave D5, plus the frozen `BLUEPRINT.md` and the
measurement records each blocker already cites. The generator therefore must not restate those
facts without a byte binding: it should extract each exact blocker section, authenticate each named
evidence file, bind the complete frozen blueprint, and emit both a machine-readable manifest and a
human-readable page.

The six decisions share one trust contract but have different consequences:

- #13 asks whether Latin-script Kurdish is in the current `ckb_Arab` product scope and explicitly
  forbids folding phonemically distinct `ř/ł` to guessed ASCII forms.
- #14 chooses a VAD/alignment relationship for sentence boundaries; any choice changes §5 anchors,
  so a conservative recommendation remains only a recommendation until labelled audio measures it.
- #15 chooses whether and how TimeLens may extend a clip. Evidence-only operation is the safest
  production recommendation until labelled footage supplies a relevance threshold.
- #18 resolves the conflict between §3's full-transcript Gemini call and M2's BM25 arrow. The least
  lossy recommendation keeps full-transcript Path A and gives BM25 an explicit brief/operator query
  consumer rather than silently filtering model context.
- #9 is a two-gate decision: real footage must first show face-centred cropping is insufficient,
  then every added model must pass the §7 commercial-licence boundary. Deferral is the only option
  currently supported by evidence.
- #21 is an owner licence assertion for locally trained weights. The generator can recommend
  internal-only use until the owner selects terms; it cannot infer copyright or training-data rights.

An unset template is part of the output, not a failure to finish it. Accepted values must be
enumerated option identifiers, with owner identity, rationale and UTC timestamp left JSON `null`.
Preparation performs no model, cloud or GitHub call. Publication is a write-once exact file set so
two operators cannot silently overwrite the questions or their evidence bindings.

## Design conclusion

Each kit must have three layers:

1. a canonical, strict, versioned input manifest with content hashes and path containment;
2. a deterministic verifier/report generator that refuses missing or contradictory evidence; and
3. a short human guide containing only the fields or decisions an operator must supply.

The confidential workspaces also inherit the repository's existing Win32 trust boundary rather
than relying on `tempfile` permissions: `hawedit.windows_security.create_private_directory` creates
an owner/SYSTEM/Administrators-only protected DACL, and `assert_private_windows_path` verifies it.
On POSIX, the corresponding workspace is owner-created mode 0700. This matters for both extracted
client pixels and the staged evidence directory; a random name under a readable parent is not a
privacy boundary.

Human names, licences, consent, cloud approvals, model-gate acceptance, expert judgments, and
release approval remain assertions by the responsible human. HawEdit binds those assertions to
exact bytes and refuses incomplete evidence; it cannot authenticate their real-world truth by
itself. Where an organization has a signing key, the canonical manifest digest is the object to
sign, and detached signature verification belongs in the final acceptance record.

The Sorani ASR kit is the first implementation unit because its runtime and metrics already exist,
its human input is the earliest broad acceptance dependency, and content/leakage binding can be
implemented without changing the canonical transcript or benchmark algorithms.
