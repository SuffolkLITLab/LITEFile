# Importing existing court parties

Implementation and validation for [issue #291](https://github.com/SuffolkLITLab/LITEFile/issues/291#issuecomment-6069909727).

## Case-detail contract

`services/existing_cases.py` separates authenticated retrieval, normalization, preview, atomic application, and envelope reconciliation. It uses the raw detail endpoint:

```text
GET /jurisdictions/{jurisdiction}/cases/courts/{court}/cases/{tracking_id}
```

The seven authorized Illinois staging examples were queried using both the raw response and `X-API-VERSION: JSON-V1`. Raw responses remain the import source: JSON-V1 does not preserve available contacts, and its individual ID extraction does not explicitly select the `CASEPARTYID` category.

Two differences found during live validation are covered by fixtures:

- Search returns the EFM UUID needed by detail retrieval, fees, and submission. Detail responses place a local court-system ID in their top-level `caseTrackingID`. The original EFM UUID appears in `caseLineageCase`. Import verifies that identity, the selected docket number (allowing punctuation differences), and the returned court. It preserves the EFM UUID as `previous_case_id` and records the local ID separately in the snapshot.
- Marion, Kane, and Winnebago return additional parties with roles absent from the selected case type's current party-type list. Import verifies those roles against the court's full `/party_types` catalog. It does not reinterpret those parties as a plaintiff or defendant. Required-role checks still use the selected case type's requirements.

## Field mapping

| Raw detail field | Durable destination | Behavior |
| --- | --- | --- |
| Search UUID, verified against top-level ID or `caseLineageCase` | Draft `previous_case_id`; snapshot `tracking_id` | Used for both fees and submission; never replaced with the local ID |
| Top-level detail `caseTrackingID` | Snapshot `court_local_case_id` | Retained separately |
| `caseCourt.organizationIdentification.identificationID` | Snapshot `court` | Must match the selected court |
| `caseDocketID`, `caseTitleText` | Draft docket and title; snapshot | Court values replace search/browser suggestions on confirmation |
| `caseCategoryText`, Tyler augmentation `caseTypeText` | Draft category/type codes; snapshot | Court classifications drive the outgoing envelope |
| Individual `personOtherIdentification` or organization's nested `identification` with category `CASEPARTYID` | Party `external_party_id` | Category-specific selection; unrelated IDs are ignored |
| `EntityPerson` / `EntityOrganization` | Person fields / `organization_name` | Organizations serialize with `person_type: business` |
| `personGivenName`, `personMiddleName`, `personSurName`, `personNameSuffixText` | First, middle, last name, suffix | Preserved without name-based deduplication |
| `organizationName` | Organization name | Preserved as one name |
| `caseParticipantRoleCode` | Party type code and verified catalog name | Missing/unrecognized roles make the import partial |
| `ContactEmailID`, `ContactTelephoneNumber.telephoneNumberFullID` | Email and phone | First available supported value |
| `ContactMailingAddress` / `ContactAddress`, structured delivery points, city, state, postal code, country | Mailing address fields | Optional information; missing country remains unknown |
| `caseOtherEntityAttorney`, `CASEPARTYATTORNEYID` or `ATTORNEYID`, bar identification, represented-party references | Party `representation.attorneys` | Normalized attorney identities with their ID category, supported names/contacts, and associations retained |
| No returned attorney association | `representation.status: unknown` | Does not imply self-representation |

Unsupported personal attributes, historical documents, prior filing codes, payments, and service selections are not imported. The current proxy person input exposes no representation-change fields. The UI preserves and describes returned representation; it does not send guessed pro-se or attorney changes. Existing-party IDs reference the court's existing associations. `is_form_filler` retains its separate firm-filer meaning.

The bounded snapshot includes schema version, court and case identity, jurisdiction, source endpoint, retrieval time, status, problems, and normalized parties. An absent snapshot is `not_loaded`; a verified empty roster is `loaded`; missing essential fields are `partial`; retrieval/authentication/format failures are `failed`. Credentials and raw responses are not saved in the draft or logged by the import service.

## Workflow and identity rules

Confirmation previews the server-fetched roster and applies it when the filer confirms. Plan-linked cases use the same confirmation step. Active older drafts cannot proceed to People, Fees, or Review until the court import is confirmed; envelope preparation also enforces this requirement. Submitted drafts cannot be imported into or rewritten.

Imported parties have `source: court`, independently of whether their ID is present. Their ordinary edit/remove actions are unavailable and direct requests are rejected. “This is me” links the account to the existing row without renaming or deleting it. “Who are you filing for?” selects durable court rows independently of that account link. Account contact information remains separate. A separate “Add a new party” action creates `source: added`; the new party's role must be chosen from the court's current published choices. If a required role is absent from the verified roster, the UI explains the missing role and asks for an explicit addition or support; it does not fabricate a placeholder. Server required-role validation still runs.

Atomic imports serialize on the draft and reuse court rows by ID. A conditional database constraint prevents duplicate nonblank IDs within a draft and source case. Equal names with different IDs remain distinct. Case changes/rejection clear court and explicitly added case-specific parties, links, and quotes while retaining uploads and account contact details. A stale detail response cannot overwrite another selection.

Extraction suggestions cannot edit a confirmed court roster. The People screen asks the filer to compare document caption evidence with the court roster. Legacy draft writes cannot replace imported parties or verified case classifications.

The shared fee/submission preparation receives the authoritative draft. It verifies case identity, party names and roles against the snapshot, filing-party selection, unique IDs, and document references. Existing rows serialize with `tyler_id` and `is_new: false` in either party collection. Explicitly added rows are reconciled against their saved draft row and serialize with `is_new: true`, without a court ID. Internal draft-row identifiers are removed before forwarding. Each party appears once. Quote fingerprints include imported IDs, names, representation, and filing-party selections.

## Illinois staging results

Validated on October 8, 2026 (America/New_York), against `https://efile-test.suffolklitlab.org`, using authorized local test credentials. Each test used its captured court roster, a selected existing filing party, a current Motion filing code, a non-confidential document type, the required filing component, the repository's public test PDF, and an existing staging waiver payment account.

The browser payload module generated the envelopes; the shared server preparation reconciled them against persisted imported drafts before the live fee and filing requests. Every outgoing court participant had the original `CASEPARTYID` and `is_new: false`, and every document referenced the selected entry in `users`. Returned `caseId` values matched the original search UUIDs. Raw responses, payloads, and credentials stayed under `/tmp`; committed fixtures replace names, contacts, party/attorney IDs, and bar numbers with synthetic values.

| Court | Supplied case number | Imported parties | Motion code | Fee response | Submission response | Staging envelope |
| --- | --- | ---: | --- | --- | --- | --- |
| Marion | `2025SC5` | 3 | `143177` | 200 | 200 | `324947` |
| Kane | `2024EV001752` | 4 | `77747` | 200 | 200 | `324948` |
| Kane | `2005SC000985` | 4 | `6344` | 200 | 200 | `324949` |
| Winnebago | `2019-D-0000655` | 5 | `6344` | 200 | 200 | `324950` |
| Winnebago | `2019-SC-0001642` | 2 | `196589` | 200 | 200 | `324951` |
| Lake | `2024SC00003388` | 2 | `53156` | 200 after timeout/retry | 200 | `324952` |
| Lake | `2024DC00000572` | 2 | `53159` | 200 | 200 | `324953` |

All seven submissions returned an envelope ID and one filing ID. This verifies staging envelope acceptance, not a later clerk disposition. No production filing was made.

## Regression checks

`efile/tests/test_existing_cases.py` covers the seven sanitized detail responses and full role catalogs, category-specific ID selection, organizations and equal names, import idempotency, uniqueness, required roles, immutable details, account linking, explicit new parties, lifecycle changes, stale results, resume, failures, and substituted payload identities.

Its browser test runs the actual Django views with sanitized court responses: lookup, confirmation, read-only roster, native keyboard filing-party selection, account linking, and Review. The JavaScript suite checks both party collections and document references. Existing routing tests now provide a trusted detail response rather than assuming confirmation can bypass import.

From `efile_app/`:

```bash
uv run pytest -q efile/tests/test_existing_cases.py
uv run pytest -q efile/tests/test_existing_cases.py efile/tests/test_fee_quotes.py efile/tests/test_handoff.py efile/tests/test_people_flow.py efile/tests/test_review_submit_flow.py
uv run pytest -q efile/tests --ignore=efile/tests/test_integration.py --ignore=efile/tests/tests.py -m 'not integration'
npm run test:unit
uv run ruff check .
uv run ty check
uv run python manage.py makemigrations --check --dry-run
```

The repeatable backend suite passed with **1,675 passed and three integration tests deselected**. The final affected regression suite passed with **167 tests**, including the real-view browser flow and attorney-association mapping. JavaScript unit tests passed with **88 tests**. Ruff, Ty, changed-file ESLint, template formatting, migration consistency, and `git diff --check` passed. The repository-wide JavaScript lint command also scans an unrelated local broken virtual environment; ESLint was therefore run against every changed JavaScript file.

The browser test requires the repository's npm dependencies and installed Playwright Chromium. The live seven-case matrix was performed separately from the repeatable fixture/browser suite. Migration `0038_existing_case_identity` must be applied before deploying the application changes.
