# Front-end JavaScript

There is no front-end framework here, and no client-side router. Each workflow
screen is a Django template that posts to its own view; the script beside it
handles only what a page reload cannot do -- showing and hiding fields, dragging
documents into order, calling a code list as the filer types. A screen with no
JavaScript is a screen that did not need any.

Every module is an IIFE that starts by looking for the element it belongs to and
returns immediately when it is not on the page, so any script can be loaded
anywhere without checking which template it landed in.

## Shared modules

| File | What it is for |
| --- | --- |
| `api-utils.js` | The only place that talks to `/api/…`: CSRF tokens, timeouts, error shaping, and a small response cache for code lists. Exposed as `window.apiUtils`. |
| `filing-payload.js` | Builds the `efile_data` blob the EFSP expects. Review and Payment must send the same one -- fees quoted against a different payload are not the fees the filer pays. |
| `checklist-status.js` | The document checklist's answer buttons, shared by the in-flow step and the filing-plans page. |

## Screen modules

`case-lookup.js`, `case-questions.js`, `document-checklist.js`,
`extraction-review.js`, `filing-plans.js`, `organize-documents.js`,
`parties.js`, `party-details.js`, `payment.js`, `review.js`,
`upload-documents.js`, and `your-information.js` each belong to the template of
the same name.

## API endpoints these call

- `/api/dropdowns/…` — court code lists (courts, case categories and types,
  filing and document types, party types, optional services)
- `/api/filer-roles/`, `/api/form-config/`, `/api/case-type-config/` — partner
  configuration for the current jurisdiction and case type
- `/api/suffolk/lookup-case/` — finding an existing court case
- `/api/payment-accounts/`, `/api/payment-account-types/`,
  `/api/payment-fees/`, `/api/auth/tyler-token/` — the fees step
- `/api/get-case-data/`, `/api/get-upload-data/`, `/api/save-case-data/` — the
  draft's own state, always read from the server rather than from localStorage:
  a stale copy could outlive a submit and leak into the next filing
- `/api/submit-final-filing/` — filing, from the review screen

## Configuration

What the forms ask for is configured in YAML, not in JavaScript. See
`../config/README.md`.

## Tests

`js-tests/` holds `node --test` unit tests for the modules worth testing on
their own (`api-utils.js`, `filing-payload.js`). Run them with
`npm run test:unit`. Whole-flow coverage lives in the Playwright specs under
`efile_app/tests/`.
