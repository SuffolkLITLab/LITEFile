# Interactive Testing Guide: Partner Document Checklists & Filing Plans

This guide provides step-by-step instructions for interactively testing the changes introduced in the `100-partner-document-checklists` branch, including local S3 mock configuration, fake PDF uploads, document checklist verification, and multi-filing plan workflows.

---

## 1. Overview of Key Features in this Branch

* **Partner-Configured Document Checklists** ([`services/document_checklists.py`](file:///home/quinten/LITEFile/efile_app/efile/services/document_checklists.py)):
  * Configured in YAML ([`illinois.yaml`](file:///home/quinten/LITEFile/efile_app/efile/static/config/states/illinois.yaml), [`base-case-types.yaml`](file:///home/quinten/LITEFile/efile_app/efile/static/config/base-case-types.yaml)).
  * Resolves checklists based on human-readable names rather than brittle numeric court codes.
  * Filters checklist items conditionally depending on the lead document (e.g., Landlord Complaint vs. Tenant Appearance/Answer in eviction).
  * Applies court-specific overrides (e.g., Cook County County Division cover sheets, Early Resolution Program notices).
  * Groups documents into requirement tiers: **Always needed**, **Usually needed**, and **Sometimes needed**.
* **Filing Plans** ([`models.py`](file:///home/quinten/LITEFile/efile_app/efile/models.py), [`services/filing_plans.py`](file:///home/quinten/LITEFile/efile_app/efile/services/filing_plans.py)):
  * Long-lived `FilingPlan` model stores the matter across multiple envelopes and snapshots the checklist.
  * Checkbox state can be saved mid-flow via the **"Save my list"** button.
* **Multi-Filing Workflow** ([`confirmation.html`](file:///home/quinten/LITEFile/efile_app/efile/templates/efile/confirmation.html), [`views/draft_views.py`](file:///home/quinten/LITEFile/efile_app/efile/views/draft_views.py)):
  * On the confirmation screen, filers can click **"File something else for {title}"** to start another filing in the same matter, reusing the checklist and preserving gathered document progress.

---

## 2. Local Setup & How Fake PDF Uploads Work

### Why Fake PDF Uploads Work Seamlessly
1. **Local S3 via LocalStack**: Files uploaded in the browser are stored in LocalStack S3 on port 4566.
2. **EFSP Proxy Stand-In**: External Tyler EFSP proxies must fetch documents over HTTP/HTTPS to calculate fees and validate filings. Because the remote proxy cannot reach internal LocalStack URLs, `EFSP_TEST_DOCUMENT_URL` (in `compose.yml` / `efile_app/.env`) supplies a publicly accessible test PDF (`https://raw.githubusercontent.com/SuffolkLITLab/LITEFile/main/testing/sample_test.pdf`).
3. **Safety Guards**: This substitution only ever runs when `DEBUG=True` under development settings (`settings_dev`) and is hard-blocked from running in production.

### Starting the Local Environment

#### Option A: Docker Compose (Recommended)
```bash
docker compose up
```
* Starts LocalStack (with S3 bucket initialized automatically).
* Runs migrations and starts Django on `http://localhost:8000`.

#### Option B: Host Dev Server via `uv` + LocalStack
```bash
# 1. Start LocalStack
docker compose up -d localstack

# 2. Run migrations and start Django
cd efile_app
uv run python manage.py migrate
uv run python manage.py runserver 0.0.0.0:8000
```

---

## 3. Step-by-Step Interactive Test Scenarios

Log in at `http://localhost:8000/jurisdiction/illinois/login/` with your Tyler test credentials.
You can use `testing/sample_test.pdf` (or any local PDF) when prompted to upload a document.

---

### Test Scenario 1: Eviction Checklists (Lead Document Filtering & Court Overrides)

* **Goal**: Verify that Landlords and Tenants see different checklist items, and that Cook County-specific notices appear.
1. From the dashboard/options, click **Start a New Filing**.
2. Upload `testing/sample_test.pdf`.
3. In **Extraction / Case Information**:
   * **Court**: *Cook County - Municipal Civil Division* (`cook:cvd1`).
   * **Case Category**: *Eviction* (or *Civil*).
   * **Case Type**: *Eviction - Possession - Residential Complaint Filed - Non-Jury*.
   * **Lead Document Type**: Select `Complaint` (Landlord flow).
4. Click **Continue** to go to `/jurisdiction/illinois/document-checklist/`:
   * **Verify**: Under **Always needed**, you see *Eviction complaint* and *Early Resolution Program notice* (Cook County override).
   * **Verify**: *Answer to the complaint* and *Appearance form* are **not** present.
5. Click **Back** to Case Information and switch **Lead Document Type** to `Appearance` or `Answer` (Tenant flow).
6. Return to Document Checklist:
   * **Verify**: *Appearance form* appears under **Always needed**.
   * **Verify**: *Answer to the complaint* appears under **Usually needed**.
   * **Verify**: *Early Resolution Program notice* remains present.
   * **Verify**: *Eviction complaint* is **not** present.

---

### Test Scenario 2: Court-Specific Overrides vs. Statewide Baseline (Name Change)

* **Goal**: Verify that court-specific rules merge into or override the statewide case type configuration.
1. Start a new filing with Cook County County Division:
   * **Court**: *Cook County - County Division* (`cook:cd1`).
   * **Case Type**: *Name Change*.
2. On `/document-checklist/`:
   * **Verify**: *County Division information sheet* is listed under **Always needed**.
   * **Verify**: *Statement about your criminal history* is listed under **Usually needed**.
3. Start a new filing with an outside court (e.g., *Lake County* or *DuPage County*):
   * **Court**: *Lake County* / *DuPage County*.
   * **Case Type**: *Change of Name*.
4. On `/document-checklist/`:
   * **Verify**: Cook County's *County Division information sheet* is **absent**.
   * **Verify**: Statewide items like *Proof of newspaper notice* appear under **Usually needed**.

---

### Test Scenario 3: Case Category Fallback

* **Goal**: Verify that case types without specific checklists fall back to their broad category guidance.
1. Start a filing in *DuPage County*.
2. Select a case category with general guidance (e.g. *Small Claims*) and a case type without an explicit checklist (e.g. *Contract - Debt Collection*).
3. On `/document-checklist/`:
   * **Verify**: Category-level guidance is shown: *Papers that back up your side*, *Proof that the other side got a copy*, and *Request to waive court fees*.

---

### Test Scenario 4: Saving Progress & Multi-Filing Matter Flow

* **Goal**: Verify checklist persistence and multi-filing initiation via `FilingPlan`.
1. On the `/document-checklist/` screen, check off 1 or 2 items (e.g. check *Eviction complaint* and *Your lease*).
2. Click **Save my list**:
   * **Verify**: A success flash message appears: *"We saved your document list."*
   * **Verify**: The checkboxes remain checked upon reload.
3. Check the confirmation checkbox (*"I have added every document I want to file"*) and click **Continue**.
4. Complete Party details and Fees/Payment (fee quotes will succeed using `EFSP_TEST_DOCUMENT_URL`).
5. On the **Confirmation** page (`/confirmation/`):
   * **Verify**: The button **"File something else for [Matter Name]"** is present.
   * Click **"File something else for [Matter Name]"**.
6. You will be redirected to the upload step for a new filing attached to the same plan.
7. Upload a fake PDF and proceed to `/document-checklist/`:
   * **Verify**: The checked items from your earlier filing remain checked in the plan!

---

## 4. Automated UI Verification (Playwright)

To run the interactive browser test suite with Playwright:

```bash
cd efile_app

# Run interactive UI mode
npx playwright test --ui

# Or run in headed browser mode
npx playwright test tests/reorganized-filing-matrix.spec.js --headed
```

---

## 5. Python Unit Test Verification

To run all unit tests covering checklist resolution and filing plans:

```bash
cd efile_app
uv run pytest efile/tests/test_document_checklists.py efile/tests/test_filing_plans.py -v
```
