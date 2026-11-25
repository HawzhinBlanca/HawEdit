# Owner-Bound Local HTTP Research

2026-10-03 local / 2026-10-02 UTC. Research only while the source-frozen storage gate
runs. Current package 6bde42cba644a4510bbdb1bdd28596dba7cece5c328612c6dcbcb0e3d7f0b2cb;
uncommitted baseline HEAD 372a16645d7a8558bc6cedcff34a9fbfa13f712f. No session authority,
bootstrap secret, provider call or production configuration is created by this note.

## Actual Boundary

web.HawEditWebHandler._local_write checks loopback Host, matching Origin and Fetch-Site;
GET/HEAD routes reuse the local guard. This is cross-site refusal, not identification of
the requesting OS user. run_web_server now creates a private upload leaf; JobManager's
legacy import/read namespace and all protected worker/DBOS/checkpoint/trust/session
adoption remain incomplete. Actual handler/startup definitions and callers are preserved
in serena-T3-storage-final-map.json; local-guard source is separately inspected, not
claimed as a new dedicated symbol/caller map. No existing source is edited here.

## Primary Technical Constraints

HTTP cookies do not isolate ports. Another local service on the same host can receive or
overwrite matching cookies; a signed port claim does not prevent token disclosure before
server-side verification. Therefore loopback-only, SameSite or HttpOnly labels alone do
not establish an owner-private local session against mutually untrusted local services.
[RFC 6265 sections 1 and 8.5](https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5).

Loopback origins can be potentially trustworthy for browser APIs, but this classification
does not authenticate an OS user or certify browser implementations. A future service-
worker transport may be feasible; registration, origin/client scope, activation, updates,
worker termination and actual browser recovery all require independent verification.
[W3C Secure Contexts](https://www.w3.org/TR/secure-contexts/#is-origin-trustworthy),
[Service Worker specification](https://w3c.github.io/ServiceWorker/).

An Authorization-header session would need authenticated media requests too. Rewriting
fetch/XHR alone leaves video src, HEAD/ranges, seeks and direct downloads unresolved.
Query-string capabilities are not an acceptable workaround: bootstrap/session authority
must stay out of URLs, logs, job/options records and review payloads. Private bootstrap
delivery, replay/expiry/revocation, refresh/server restart, multiple tabs and token redaction
must be part of the same tested contract, not assumed from a credential constructor.

## Required Next Evidence

Complete actual dedicated session/guard/response/preview symbol and caller mapping before
design or source edits. Compare native owner-bootstrap mechanisms and browser media
transport without introducing a second producer graph. A protected OS-private launch
artifact with one-time body exchange is a research option, not an approved or verified
scheme; it must handle file origins, replay, browser history, focus/accessibility and loss.
No secrets should be exposed to an automated audit transcript. No browser automation or
owner identity proof has been performed for these options.

Require real native HTTP and selected-browser tests for missing/foreign/expired/revoked
credentials, cross-port services, origin spoofing, stale cookies/workers, token non-leakage,
range playback, download and reconnect. OS private files are a prerequisite, not sufficient
evidence of these outcomes. Keep protected generation disabled until both identity and
persisted supervisor/runtime/governance/billing authority have genuine adoption evidence.
