---
id: maintenance
title: Content approval and maintenance register
sidebar_label: Approval and maintenance
---

# Content approval and maintenance register

This is the shared handover index for
[issue #324](https://github.com/SuffolkLITLab/LITEFile/issues/324), audited against
October 13, 2026 `main` at `b4be391`. It covers changes merged September 15–October
13. **Unassigned** means an owner has not accepted the responsibility. **Pending**
means no approval is recorded here. A checkbox, merged PR, test pass or link-check
date does not supply approval or prove deployment.

Maintain four distinct facts in each record: code implemented/merged, content
approval and scope, deployed enablement, and release-test evidence. Keep private
operating details and evidence in the approved internal system; public documentation
can link to a redacted register record. This page is the initial register, not a
claim that the review work has happened.

## Review rhythm to agree

Proposed starting point, subject to owner approval:

- Daily sync freshness, worker and failed/stalled-job review.
- Weekly broken-link, notification failure and maintenance-job triage.
- Monthly resource/form-content, court/help-contact and glossary review.
- Review before every release and after court rules, fees, forms, provider codes,
  templates, translations, calendars or service scope change.

Existing code synchronization is automatic. Assigning staff, new alerts, automated
link checks or recurring review jobs is separate implementation/operations work;
this proposal has not scheduled them.

## Register

`State YAML` below means `efile_app/efile/static/config/states/<jurisdiction>.yaml`.
The last-checked column records this **documentation/code audit**, unless explicitly
labeled a content or HTTP review. Replace “unassigned” with an accepted person/team
and a review date before treating a record as maintained.

| Asset/feature | Audience | File/key | Content owner | Technical owner | Approver | Source | Last checked | Next check/event trigger | Validation evidence | Enabled/approval state | Escalation issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Screen wording/hooks | Editors/translators | State YAML `text`; `efile/utils/ui_text.py` | Unassigned: partner editor | Unassigned: UI maintainer | Unassigned: local copy/court reviewer | [Change map](./customization.md) and approved local sources to supply | 2026-10-13 code audit | Each copy/release/language change | Catalog audit; partner exercise pending | Hooks implemented; full field coverage incomplete; deployed scope unverified | [#74](https://github.com/SuffolkLITLab/LITEFile/issues/74), [#275](https://github.com/SuffolkLITLab/LITEFile/issues/275) |
| Email copy/sender | Partners/operators | State YAML `submission_notifications` | Unassigned: partner editor | Unassigned: proxy/mail operator | Unassigned: partner + service owner | [Email review](./email-review.md), technical contract | 2026-10-13 code audit | Before enablement; sender/template/transport change | Historical confirmation/HTML tests in contract; live acceptance/rejection pending | Implemented; customized mail disabled pending signoff; production delivery unverified | [#157](https://github.com/SuffolkLITLab/LITEFile/issues/157), [proxy #375](https://github.com/SuffolkLITLab/EfileProxyServer/issues/375) |
| Tracker timing/hours/calendar | Partners/filers | State YAML `filing_timing`; exact court override | Unassigned: court-contact editor | Unassigned: tracker maintainer | Unassigned: court reviewer | Per-entry `source_url` and `checked_on`; [recipe](./email-review.md#timing-office-hours-and-stale-guidance) | IL estimate/Adams hours sources checked 2026-10-12 in existing contract | Calendar/source change; each release | Timing regressions; no promised decision date | Implemented; only configured guidance displays; deployment unverified | [#157](https://github.com/SuffolkLITLab/LITEFile/issues/157) |
| Upstream code catalogs | Operators | EFSP source; `FILING_CODE_SYNC_*` | Unassigned: court code steward | Unassigned: sync operator | Unassigned: service owner | Provider catalogs; [operations](../admin/filing-code-operations.md) | 2026-10-13 code audit | Daily health; every upstream schema/source change | Freshness, changed-court count, last good index; target environment evidence pending | Sync implemented; production health unverified | [#324](https://github.com/SuffolkLITLab/LITEFile/issues/324); [#314](https://github.com/SuffolkLITLab/LITEFile/issues/314) optimization separate |
| Curated search/definitions/facets/case guidance/glossary | Editors/implementers | Five `efile/data/*.yaml` files in [inventory](./maintained-data.md) | Unassigned: terminology editor | Unassigned: search maintainer | Unassigned: local court/legal reviewer | Per-file/override source + provider metadata | 2026-10-13 code audit; substantive review unrecorded | Monthly proposed; catalog drift and translation change | Representative searches per scope required | Implemented aids; substantive local approval pending | [#296](https://github.com/SuffolkLITLab/LITEFile/issues/296) |
| Geography/docket/appellate mapping | Implementers | ZIP artifact/script, MACourts/VTCourts, `efile/services/docket_courts.py`, State YAML `court_selector` | Unassigned: jurisdiction reviewer | Unassigned: package/mapping maintainer | Unassigned: court reviewer | Census, package records, current court routes; [inventory](./maintained-data.md) | 2026-10-13 code audit | Source/dependency/route change | ZIP, ambiguity and appellate fixtures; local validation pending | Implemented hints; not eligibility decisions; deployment unverified | [#276](https://github.com/SuffolkLITLab/LITEFile/issues/276) |
| Finder/checklist scope | Partners/filers | State YAML `document_finder`, `case_types`, `case_categories`, court supplements | Unassigned: forms editor | Unassigned: resolver maintainer | Unassigned: partner/court reviewer | [Guide approval rows](./document-finder.md#approval-and-recurring-review) | 2026-10-13: seven IL guides/52 links HTTP-checked in #322; substantive approval pending | Weekly link triage/monthly content proposed; form revision | Finder/checklist resolver and sign-in tests; partner exercise pending | IL content shipped; partner review pending. MA/VT no populated finder | [#322](https://github.com/SuffolkLITLab/LITEFile/pull/322), [#323](https://github.com/SuffolkLITLab/LITEFile/pull/323) |
| Fees/surcharges/exemptions/waiver help | Partners/operators | State YAML `fee_waiver`, fee assumptions; `court_payments.py`, `waiver_documents.py` | Unassigned: jurisdiction fee reviewer | Unassigned: payment maintainer | Unassigned: court/service owner | Local official fee rules + live quote; existing [fee research](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/fee-research-2026-09-29.md) | 2026-10-13 code audit; prior research 2026-09-29 is not universal approval | Fee/rule/account-type change; each release | Runtime bank restriction and provenance regressions; live scope pending | IL explicit-provenance fallback/runtime bank checks implemented; VT statutory exemptions unresolved | [#265](https://github.com/SuffolkLITLab/LITEFile/issues/265), [#320](https://github.com/SuffolkLITLab/LITEFile/pull/320), [#321](https://github.com/SuffolkLITLab/LITEFile/pull/321) |
| Contacts/upload notices/confidentiality/local instructions | Editors/court reviewers | State YAML `jurisdiction.help_*`, court `contact`, `upload_disclaimers`, `text.organize_documents.confidentiality_help`, `filing_guidance` | Unassigned: local help editor | Unassigned: configuration maintainer | Unassigned: court/legal reviewer | Approved local rule/order/help source per statement | 2026-10-13 code audit; legal approval unrecorded | Contact/rule change; after code sync for exact-code guidance | Source/content/rendering and post-sync selection checks required | Hooks implemented; jurisdiction decisions/defaults remain open | [#235](https://github.com/SuffolkLITLab/LITEFile/issues/235), [#257](https://github.com/SuffolkLITLab/LITEFile/issues/257) |
| Jurisdiction release scope | Partners/operators | Court `filing_availability`; [scope rows](./filing-availability.md#release-scope-register) | Unassigned: jurisdiction service owner | Unassigned: availability maintainer | Unassigned: court + release owner | Actual service constraints and target court names | 2026-10-13 code audit | Every release/source/scope change | New/existing/supporting-doc/saved-draft tests required | Restriction engine implemented; Cook example inactive; scheduling not implemented | [#199](https://github.com/SuffolkLITLab/LITEFile/issues/199), [#200](https://github.com/SuffolkLITLab/LITEFile/issues/200) |
| Staff privacy and reporting | Support/analysts | `LITEFILE_ANALYTICS_*`, `LITEFILE_PRIVACY_DELETION_ENABLED`; staff roles | Unassigned: support/privacy and reporting owners | Unassigned: staff operator | Unassigned: policy/service owner | [Staff onboarding](../admin/staff-onboarding.md), [metrics](./reporting.md), existing internal runbook | 2026-10-13 code audit | Before any collection/export/deletion enablement; policy change | TOTP, scope, suppression, object/backup retry evidence required | Implemented; switches default off; production policy/enablement unverified | [#162](https://github.com/SuffolkLITLab/LITEFile/issues/162), [#315](https://github.com/SuffolkLITLab/LITEFile/issues/315) |
| Service maintenance | Operators | [Service index](../admin/service-maintenance.md) | Unassigned: service owner | Unassigned: per-service operator | Unassigned: release/privacy owner | Existing handoff/preparation/security contracts | 2026-10-13 code audit | Secret/source/worker/converter change; release | Per-service evidence record required | Implementation varies; target deployment acceptance pending | [#166](https://github.com/SuffolkLITLab/LITEFile/issues/166), [#200](https://github.com/SuffolkLITLab/LITEFile/issues/200) |
| Filer guidance/screenshots | Filers/support trainers | `docs/docs/user-guide`; [screenshot register](../admin/documentation-review.md) | Unassigned: documentation editor | Unassigned: UI maintainer | Unassigned: partner/accessibility reviewer | Current templates/workflow and redacted gist evidence | 2026-10-13 source audit | Every UI/translation/release change | Documentation checks recorded in internal handover note; partner exercise pending | Guidance updated; RC1 accessibility/release signoff not established | [#107](https://github.com/SuffolkLITLab/LITEFile/issues/107), [#202](https://github.com/SuffolkLITLab/LITEFile/issues/202), [#200](https://github.com/SuffolkLITLab/LITEFile/issues/200) |

## Local policy review and approval records

For every legal/court-policy statement, add a scoped record containing the exact
wording, official source URL/version, jurisdiction/court and new/existing case
scope, reviewer/date/decision, last content check, next date/event trigger and
what to withdraw if the source becomes stale. Do not copy Illinois rules to
Massachusetts or Vermont. Include fee/surcharge assumptions, exemptions, waiver
help, court contacts, document instructions and confidentiality guidance.

Pre-upload `upload_disclaimers` are curated snapshots and need periodic human
review. Review/submission requirements are fetched from the selected court by
`efile/services/disclaimers.py`; Review can use a ten-minute cache and submission
fetches them fresh and compares the accepted text. Automatic refresh does not
maintain the curated snapshot or approve explanatory copy.

Current payment behavior has separate boundaries: Illinois's generic waiver
filing-code fallback requires explicit waiver provenance, and court bank-payment
restrictions are checked at runtime. Neither supplies Vermont statutory fee
exemptions (#265) or future waiver reuse. Track those approvals and features
separately. Confidentiality examples/default decisions remain #235/#257.

## Record a completed review

Copy this into the asset's linked record; keep the summary current here:

```text
Asset / feature / delivered documentation page:
Audience / jurisdiction / court / case stage:
File / exact key / version:
Content owner / technical owner / approver (accepted assignments):
Authoritative source / version / retrieval date:
Last substantive review / next review date or event:
Representative checks / commands / result / evidence URL:
Code completion / content approval decision and scope:
Deployed enablement (environment, version, date):
Release tests (synthetic or live test; remaining gaps):
Escalation issue / withdrawal or rollback plan:
```

The external partner/editor exercise is still required: have someone make one
supported configuration change using only [the recipe](./customization.md#make-a-safe-wording-change),
record confusing steps and reviewer feedback, and restore the staging configuration.
An automated agent check cannot stand in for that handover exercise.

This issue does not close field-hook implementation (#74), configuration UI
(#275), email release (#157), Vermont handoff acceptance (#166), People redesign
(#197), scheduling (#199), confidentiality (#235/#257), Vermont fees (#265),
corrections (#107), or release/accessibility signoff (#200).
