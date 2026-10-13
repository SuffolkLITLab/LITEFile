# Issue #324 documentation handover

Audit source: October 13, 2026 `main`, `b4be391ab8837851a63363a6cae0750b5b32c7ce`;
merged window September 15–October 13. Spec:
[LITEFile #324](https://github.com/SuffolkLITLab/LITEFile/issues/324).
This note stays outside the public Docusaurus source tree.

## Delivered pages and review status

Paths below are relative to `docs/docs/`. Every external reviewer/owner assignment
is **unassigned**, substantive approval is **pending**, and deployed enablement
is **unverified** unless the shared register explicitly records otherwise. The
agent's source and automated checks do not count as partner/court approval.

| Spec section | Delivered pages | Documentation validation | Reviewer and next review |
| --- | --- | --- | --- |
| A1 change map | `partners-courts/customization.md`; jurisdiction reference link | All 26 UI catalog keys/defaults/link flags extracted from current source; 30 public YAML examples parse; safe override renders for IL/MA/VT using copied config, source fallback preserved | Partner/editor + UI maintainer unassigned; human recipe exercise pending; recheck on copy/hook/language changes |
| A2 email/tracker | `partners-courts/email-review.md` | Four-category/eight-field set, two substitution stages, source timing and disabled flags checked against service/config/internal contract; notification/timing tests pass | Partner/mail operator unassigned; #157 sender/copy and live callback/delivery signoff pending; review before enablement and source changes |
| B1 maintained discovery/geography | `partners-courts/maintained-data.md` | File/cache/reindex locations checked; search/case-guidance regressions pass | Local terminology/mapping reviewers unassigned; substantive review and representative target-environment searches pending; monthly/post-sync/source changes proposed |
| B2 resources | Extended finder/checklists | Finder search/resolver/sign-in/start behavior tests pass; 52 IL links checked in this run, zero failures; seven separate approval rows pending | Partner forms reviewer unassigned; destination/form content review still pending; weekly reachability/monthly content proposed |
| B3 local policy/scope | `partners-courts/maintenance.md`; availability scope register | Availability, court-payment and explicit waiver-provenance regressions pass; current inactive Cook example and unresolved jurisdiction decisions recorded | Court/legal/service owners unassigned; local statement approval, live scope and removal criteria pending; rules/fees/codes/service changes |
| C1 code operations | `admin/filing-code-operations.md`; deployment entry point | Commands/settings, least-privilege grants, poll/retry timing and storage prerequisites checked against current source/reference | Sync/proxy operator unassigned; production freshness/capacity not measured in this run; daily health proposed |
| C2 support/reporting/services | `admin/staff-onboarding.md`, `admin/service-maintenance.md`, `partners-courts/reporting.md` | Roles, TOTP/recovery, metrics, suppression and deletion/backup boundaries checked against current internal runbook/code; no production policy switches changed | Support/privacy/reporting/service owners unassigned; collection/export/deletion approval and supervised onboarding pending; policy/service changes and release |
| D filer/publication/evidence | Updated five user guides; `admin/documentation-review.md`; overview/sidebar links | Current workflow/templates reconciled; existing #319 gist provenance recorded; six fresh finder browser captures at 1280/390px; production build and rendered-site results below | Partner/docs/accessibility reviewer unassigned; human handover and #200 release/accessibility review pending; every UI/translation/release change |

The shared owner/source/approval/enablement register is
`docs/docs/partners-courts/maintenance.md`. Its initial rows state missing
assignments openly. The proposed daily/weekly/monthly rhythm has not been
accepted by owners or newly scheduled by this work.

## Automated validation

Run from `efile_app/` using `uv` (cache under `/tmp/litefile-docs-uv-cache`):

- `uv run python manage.py check --fail-level WARNING`: passed, no issues.
- `uv run python manage.py extract_config_text --check`: passed; stub current.
- Relevant existing regressions: **524 passed, 4 skipped**, 56.24 seconds.
  Files: `test_ui_text.py`, `test_filing_guidance.py`, `test_document_finder.py`,
  `test_filing_code_search.py`, `test_case_type_guidance.py`,
  `test_filing_availability.py`, `test_submission_notifications.py`,
  `test_filing_timing.py`, `test_court_payments.py`, `test_waiver_documents.py`,
  `test_workflow.py`. Four skips are opt-in court-payment browser scenarios requiring
  `COURT_PAYMENT_BROWSER_TESTS`; the backend run uses SQLite and does not establish
  PostgreSQL or live-provider behavior.
- `uv run python manage.py check_document_finder_links --jurisdiction illinois`:
  **52 links, zero failures** on October 13. No substantive approval inferred;
  destinations were HTTP-checked, not legally reviewed.
- Temporary validation parsed all **30** YAML examples in public docs and rendered
  the safe `text.organize_documents.confidentiality_help` override with copied
  IL/MA/VT configurations. Source files/fallback were not changed.
- Fresh anonymous finder capture: **1 temporary browser validation passed**,
  six screens at 1280px and 390px, expected headings/HTTP 200/no horizontal overflow.
  A temporary pytest file needed `-o filterwarnings=` because the outside-repository
  path inherited a removed-Django-warning filter; no repository test settings changed.
- Production documentation build: passed after formatting literal catalog
  placeholders as inline code for MDX. Final rendered-site checks recorded below.
- Chromium production-site preview: **28 rendered-page checks passed** across
  nine new pages and five updated user guides at 1280px/390px. No page errors,
  horizontal page overflow or broken same-page anchors. Wide reference tables
  scroll within the content area.
- `git diff --check`: passed.

No Python, YAML configuration, application template or translation catalog is
changed by this task. The outdated historical “PR remains unmerged” sentence in
the internal email contract now states the audit's merged-but-disabled state.

## Screenshot evidence and limits

Fresh finder evidence:
[gallery, manifest and results](https://gist.github.com/nonprofittechy/e88c3fce4148bc53c4a425d0fa3f67cc).
Captured against `b4be391` on October 13, 2026. Anonymous local Django/Chromium;
configured IL search/adult guide and MA no-guide state; no actual filing,
payment, email, recipient data or external resource visit. Six PNGs are embedded
in a downloadable HTML gallery with alt text and SHA-256 hashes. Raw files are
under `/tmp/litefile-docs-screens`, not committed.

Reused current workflow evidence:
[PR #319 gallery](https://gist.github.com/nonprofittechy/b855c1c8c3a69e8cd694f8ee3909b5a3),
`719cfed`, captured October 13 UTC. Its source README records synthetic
Massachusetts/Vermont existing-case journeys, IL fees/Review, People fixtures
and tracker status tests. Sources, scenario limitations and older #113 images
are listed in `admin/documentation-review.md`. Old fixed-step walkthrough images
are no longer referenced as the current interface. No release or court-policy
approval is claimed from browser rendering.

## Remaining human and deployment work

- Assign content/technical owners and approvers, and accept or revise the proposed
  review rhythm. Record authoritative local sources and substantive decisions.
- Have a partner/editor complete one supported change from the documentation
  without reading Python; record feedback, validation and rollback. The automated
  example check is preparation, not a replacement for that exercise.
- Complete scoped legal/form/fee/confidentiality reviews, email sender/copy/live
  callback checks, policy gates and target-environment operating evidence.
- Keep implementation/decision issues #74, #275, #157, #166, #197, #199, #235,
  #257, #265, #107 and #200 separate. Full third-party history #202 is not declared
  complete. This documentation work does not declare RC1 ready.


## Claude review and validated corrections

Claude Code reviewed the complete working tree against the issue and source at
`b4be391`, using read-only Read/Glob/Grep tools. The successful initial review
reported model `claude-opus-5-5`; it did not run commands or independently attest
to the automated results. All 14 verified findings were independently checked
and implemented. The three optional suggestions were also addressed. The raw
review is retained locally at `/tmp/litefile-324-claude-review.md`; this record
preserves its findings and disposition without committing tool transcripts.

| Finding | Source validation | Implemented improvement |
| --- | --- | --- |
| H1 outdated Fly example | `fly.toml` and `refresh_filing_code_index.py` | Example env/processes now match current source exactly; require `--daily` for scheduled sync and staff jobs |
| M1 incorrect/incomplete statuses | `services/filings.py` status and tracker definitions | Real status labels, separate Received/Served, separate no-update/unknown-update explanations |
| M2 missing navigation label | `components/profile_header.html`, `view_statuses.html` | Use **My cases** |
| M3 unnamed waiver/exemption controls | `payment.html` and configured exemption notes | Name both conditional payment options and eligibility help; selection is not approval |
| M4 incomplete customization map | `payment.html`, IL finder YAML and disclaimer renderer/reference | Add waiver eligibility/document guidance, exemption note, finder path/resolver/side keys and sanitized-notice markup |
| M5 unusable screenshot delivery | Gist raw PNG responses and final rendered walkthrough | Three selected unchanged synthetic PNGs embedded with alt text, captions and fallback source links; gist hosting preserves AGENTS.md requirements |
| M6 remaining fixed-screen promises | `workflow.py` and homepage/admin copy | Remove fixed 14-step/linear claims from homepage, architecture and development; clarify supported hooks and optional checklist guidance |
| L1 waiver-line detection | `waiver_documents.py` / `submission_notifications.py` | Distinguish recognizable waiver filing names from generic fallback types requiring explicit provenance |
| L2 shallow timing override | `filing_timing.py` | Explain whole-block court replacement and required fields; verify stale-estimate withdrawal |
| L3 operation/recovery details | Command startup/job/backfill/retry implementation | Explain configured 900-second versus default 60-second retry, interrupted jobs, automatic missing-label backfill and coordinated commands |
| L4 preparation defaults/failures | `document_preparation.py` | Default flattening in all three states; signed-PDF and missing-answer recovery messages in FAQ |
| L5 recipe deployment/stub | `config_loader.py`, locale README | Commit generated extraction stub; restart after shared-base changes; retain state-file reload distinction |
| L6 invalid-guidance scope | `filing_guidance.py` | One invalid rule omits all jurisdiction guidance without blocking filings |
| L7 conditional side/add-file actions | Confirm/checklist templates | Explain side question placement, adding documents and existing-case filing-type search |
| Suggestion: recipient/provider identifiers | Existing email contract evidence | Redact designated test recipient address and provider IDs while preserving sender, dates, outcomes and remaining gates |
| Suggestion: retired static images | Repository reference audit | Remove 14 unreferenced old PNGs from published static assets; retain Git history |
| Suggestion: example court review | Existing Illinois override and recipe | Explicitly state that the example replaces prior wording and needs court/legal review before public use |

The suggestion to put validation images under `docs/static/img/` was not followed:
AGENTS.md requires screenshot storage in a gist. Direct PNGs were added through
the gist's Git repository and verified to load in the published-page preview.
The source manifest records original capture dates/commits and SHA-256 hashes.

An optional focused Claude follow-up returned a session-limit error and did not
complete. It is not counted as a successful second review. All corrections were
independently validated against implementation; no partner/court/policy approval
is inferred from either the initial review or automated checks.

## Final PR validation

- Full backend suite: **2,011 passed, 14 skipped**, 252.75 seconds. An initial run
  failed the filing-tracker browser check because `@axe-core/playwright` was
  missing locally. `npm ci` restored locked browser dependencies; the isolated
  tracker rerun passed, then the full suite passed. No test/application code changed.
- JavaScript unit checks: **90 passed**, no failures/skips.
- Configuration and translation-extraction checks passed after review fixes.
- All 30 YAML examples parse. The Fly example's complete env/process mappings
  match `fly.toml`; documented status labels match the service catalog. Default
  flattening, timing-block replacement/withdrawal and waiver-named/generic
  provenance cases were exercised with copied/synthetic inputs.
- Production docs build passed. Reviewed pages passed **32** desktop/mobile
  render checks, including all three remote screenshots at both widths,
  descriptive alt text, no page errors/overflow or broken same-page anchors.
  Two additional homepage checks passed at both widths for conditional paths,
  PDF/Word and AI opt-out, optional checklists and no page overflow (**34** final
  rendered-page checks in total).
- `git diff --check` passed. Human review/approval and deployed-state gaps above
  remain pending; this PR addresses documentation without closing those gates.
