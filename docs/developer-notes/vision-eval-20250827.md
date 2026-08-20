---
id: vision-eval-20250827
title: Vision Evaluation (2025-08-27)
sidebar_label: Evaluation 2025-08-27
sidebar_position: 3
---

# Status check vs vision
Based on the current codebase, here’s where things stand relative to your MVP vision.

## What’s in place

- __EFSP integration basics__
  - Auth/tokens in `efile/api/auth_views.py` (login/logout, Tyler token, Suffolk eFile auth).
  - Filing CRUD in `efile/api/filing_views.py` (list/create/update/delete via Suffolk endpoints).
  - Case lookup, payment accounts, profiles present in `auth_views.py` and related API views.

- __Expert mode form flow__
  - Expert form with cascading dropdowns/validation: `efile/views/expert_form.py`.
  - Config-driven sections: `efile/api/config_views.py` delegates to `CaseFormAPIViews` for jurisdiction-aware JSON.

- __YAML config system and merging__
  - Loader: `efile/utils/config_loader.py`.
  - Files: `efile/static/config/` and `efile/static/config/states/`.
  - Docs: `efile/static/config/README.md`.

- __Uploads and mapping to EFSP__
  - `efile/views/upload.py` implements `create_filing()` (maps session → Suffolk payload) and `upload_documents()` (S3 → Suffolk document registration), plus mock/simple upload utilities.

## Gaps vs vision

- __Filing Flow runner (recipe-driven)__: No generalized sequence/branch/validate engine or persisted recipes for curated flows.
- __Form Blocks abstraction and UI__: No explicit Form Block schema/type library and reusable UI components.
- __Guided Interview__: No dedicated runner/UI for linear/branching flows with instructions/progress.
- __Mapping layer formalization__: Current logic in `transform_case_data_to_filing_payload()`; needs declarative, testable mapping per recipe.
- __Review & Submit__: Missing human-readable review step before submission.
- __Error surfaces__: No normalization/triage with actionable guidance/retries.
- __Configuration management UX__: No admin UI for non-technical authoring/editing of Blocks/Flows.
- __Tests__: Limited tests for flow engine, YAML court overrides, and EFSP interactions.

## Recommended next steps (MVP-targeted)

1. __Introduce a Filing Flow “recipe” format (JSON/YAML)__
   - Minimal schema: metadata (`id`, `title`, `jurisdiction`), steps (Form Blocks), branching (`next_if`, `next_else`), validation, mapping.
   - Store in `efile/static/flows/{jurisdiction}/...` (DB later).

2. __Form Blocks library__
   - Block types: `text`, `textarea`, `number`, `radio`, `dropdown`, `party_selector`, `file_upload`, `date`, `checkbox`.
   - Reuse/standardize with `efile/static/config/base-case-types.yaml` and `states/*.yaml` for both expert and guided flows.

3. __Flow runner backend__
   - Module `efile/flow/runner.py`: load recipe, evaluate conditions, session storage, validations.
   - API `efile/api/flow_views.py`:
     - `GET /api/flows/{flow_id}` (metadata + first step)
     - `POST /api/flows/{flow_id}/steps/{step_id}` (submit answers → next step)
     - `GET /api/flows/{flow_id}/review` (summary)
     - `POST /api/flows/{flow_id}/submit` (create filing + documents)

4. __Guided Interview UI__
   - Single-page shell: progress, step title, instructions, renderer, Next/Back, validations, save-to-session.
   - Reuse `efile/static/js/*` patterns and JSON from `config_views.py`; add lightweight `flow.js` if needed.

5. __Mapping layer__
   - Move to `efile/flow/mapping.py`; recipe-aware mappings.
   - `transform(flow_answers, case_context) -> filing_payload`; add unit tests (name change, eviction basic).

6. __Review & Submit__
   - `GET /api/flows/{id}/review` returns a structured summary for UI.
   - Submit reuses `create_filing()` and document uploads when referenced by answers.

7. __Error handling__
   - Central EFSP error normalizer: categorize (auth/validation/upstream), guidance, retry suggestions.
   - Integrate in `upload.py` and `filing_views.py`.

8. __Tests__
   - Flow runner branching/validation; config merging for courts (e.g., `cook:cd1` vs `cook:chd1` per `efile/static/config/README.md`); mapping integration tests.

## Concrete implementation plan

- __Backend__
  - Create `efile/flow/`: `schemas.py` (dataclasses/Pydantic for Block/Step/Recipe), `runner.py`, `mapping.py`, (optional) `models.py` for persistence.
  - API: `efile/api/flow_views.py`. Wire URLs/permissions. Store answers in session first; DB later.

- __Frontend__
  - Add `efile/static/js/flow-runner.js`: fetch recipe/step, render, post, navigate. Reuse CSS in `efile/static/css/`.

- __Leverage existing pieces__
  - Reuse dropdown endpoints and party types via `config_views.py` and Suffolk codes.
  - Reuse S3 patterns from `upload.py`.

## Open questions

- Recipes YAML (human-friendly) or JSON (browser-native)? Suggest YAML in repo + compile to JSON at runtime.
- Attachments: embed file-upload blocks in steps now or upload at review step?
- Initial guided flow: Illinois Name Change (best documented today)?

## Proposed short milestones

- __M1 (day 1-2)__: Schemas + runner skeleton (load/next/back), session storage, minimal API.
- __M2 (day 3-4)__: Mapping layer + Review & Submit, integrate with `create_filing()`.
- __M3 (day 5)__: Guided Interview UI MVP with 1 flow (Name Change).
- __M4 (day 6)__: Tests (runner, mapping, config merging) + error normalization.

## Current TODOs

- Audit existing EFSP endpoints and config system, document gaps vs vision (in progress)
- Design Form Blocks schema
- Implement Filing Flow runner backend
- Build Guided Interview UI
- Implement mapping layer
- Add Review & Submit step
- Improve error handling
- Add attachments support
- Expand tests