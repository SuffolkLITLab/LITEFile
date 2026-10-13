---
id: service-maintenance
title: Service maintenance and escalation index
sidebar_label: Service maintenance
---

# Service maintenance and escalation index

Use the linked contracts and notes for technical procedures. This index supplies
the ownership/evidence handover for the October 13, 2026 audit without publishing
internal manuals in the public docs tree. All owner assignments below are pending;
record accepted assignments and evidence in the
[maintenance register](../partners-courts/maintenance.md).

| Service/task | Proposed owner / approver, currently unassigned | Existing reference | Required evidence and review trigger |
| --- | --- | --- | --- |
| Interview sender onboarding, secret rotation, allowed return origins | Integration operator / service-security owner | [Interview integration](../partners-courts/interview-integration.md), [security note](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/security-hardening.md) | Sender/source scope, rotation date, allowed-origin rejection tests and signed handoff replay/expiry checks; each sender/secret/origin change. Keep keys/tokens out of evidence |
| Unclaimed handoff expiry | Integration operator / privacy owner | Integration guide; `efile_app/efile/management/commands/expire_unclaimed_handoffs.py` | Approved retention, scheduler/run result, expired synthetic handoff cleanup and failure disposition; weekly job triage and retention changes |
| Live-code mapping regression | Jurisdiction implementer / partner-court reviewer | [Existing-case import note](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/existing-case-import.md), [Vermont handoff validation](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/issue-106-vermont-handoff-validation.md) | Target proxy environment, fixtures, new/existing case, party/contact and code round-trip results; after upstream schema/code changes. [#166](https://github.com/SuffolkLITLab/LITEFile/issues/166) acceptance remains separate |
| Gotenberg conversion, fonts and form corpus | Preparation operator / jurisdiction form reviewer | [Preparation validation](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/issue-113/validation.md), `testing/validate_document_preparation.py` | Converter version/health, installed font set, DOC/DOCX, field/checkmark/signature/multiline comparison, readable filing copies and error recovery; each converter/font/form revision |
| Extraction worker health/recovery | Application operator / service owner | [Deployment worker guide](./deployment.md#document-extraction-worker), [data-integrity note](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/filing-data-integrity.md) | Queue age, active/failed attempts, worker restart, manual fallback, page/text caps and temporary-file cleanup after confirmed process termination; stalled-job triage and worker change |
| Filing-code copy/search | Code-sync operator / court-code steward | [Operating checklist](./filing-code-operations.md) | Last good catalog, freshness, worker/grants/disk and representative queries; daily health review, source change |
| Bank restrictions and waiver provenance | Payment maintainer / court-service owner | [Bank payment note](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/court-bank-payments.md), local fee sources | Current live court restrictions, denied saved accounts, stale quote recovery, explicit waiver source; payment-policy/provider change |
| Email delivery and sender | Proxy/mail operator / partner + service owner | [Email review](../partners-courts/email-review.md), internal filing updates contract | Four-category copy approval, inbox/spam, actual callbacks and error/duplicate handling; before enablement and sender/transport change |
| Usage rollup/privacy retry/retention | Staff operator / policy owner | [Staff onboarding](./staff-onboarding.md), internal staff runbook | Freshness/backlog, failed-object retry, unresolved backup/provider disposition, approved retention and restore exercise; weekly failure triage, policy change |
| Safe rollout/rollback | Release operator / release-security owner | [Deployment](./deployment.md), security/data-integrity notes | Version/migration order, complete web/worker rollout, health, representative filing paths and rollback evidence; every release. Do not enable deletion during mixed versions |

An extraction failure or AI opt-out can lead to manual review; a converter failure
must not be represented as a usable filing PDF. Preserve originals and last good
catalogs while investigating. Before clearing a crashed worker's temporary files,
confirm its process has stopped and use the approved operator procedure.

For each task, link a redacted evidence record containing owner/backup, environment,
commit/service version, run date/result, synthetic versus live-test scope, open
failure, escalation contact/issue, next check and rollback/disposition. Do not
include console secrets, credentials, authenticator URIs or real filing content.
Existing tests and merge status do not establish target deployment readiness;
release/accessibility review remains [#200](https://github.com/SuffolkLITLab/LITEFile/issues/200).
