# Vision brief: form submission MVP

## 1) Vision statement
To create a system that allows users to e-file online.
Integrate with EFSP REST API.
Allow non-technical users to configure workflows that make the e-file process more understandable and efficient.
  * providing custom instructions
  * form layout
  * fill order/flow
  * field labeling/naming/mapping

## 2) Core concepts
Form Blocks & Filing Flows

Form Blocks — reusable UI components (single field or grouped fields) that collect validated data; appearance is configurable. These are building blocks that don't mean much on their own but that can be pieced together.

Filing Flow — the ordered configuration of Form Blocks, including conditional steps, instructions, and mapping to EFSP fields. Form blocks are wired together to form a Filing Flow. You can think of the Filing Flow as a recipe, written in a config file.

Expert mode — a free‑form “workbench” using the full set of EFSP options; may be semi‑guided by live API responses. Think of a place where all the ingredients are available and you can mix them however you want.

The system uses Form Blocks and Filing Flows:
- Form Blocks: small, reusable components with validation and presentation. These are the building blocks of a filing flow and can be plugged together in different ways. Often these collect validated data from the user for a single field or group of related fields.
- Filing Flows: configured sequences of Form Blocks with branching, helper text, and a mapping to EFSP payloads. It can be helpful to think of these are "recipes" for guiding a pro se filer through the process of submitting a filing. A curated Filing Flow may be presented as a "Guided Interview" for a specific filing.
This enables non‑technical users to assemble court‑ready experiences from reliable pieces, while experts can use a flexible workbench mode when needed.

## 3) Problem & why now
E‑filing is often confusing: fragmented portals, jargon‑heavy flows, and brittle forms. Non‑technical staff and self‑represented litigants struggle to submit complete, correct filings on the first try. A small, focused MVP using EFSP's REST APIs to integrate with Tyler can prove that a configuration-driven flow approach reduces errors and speeds up filings. We should be able to identify any sharp edges and gaps where improvements or additional features in the MVP's dependencies could help.

## 4) Target audience
There are two target audiences for this MVP:
• Self‑represented litigants, who are the end users of the filing process.
• Non-technical personnel who author and maintain Filing Flows.

## 5) Goals & success signals
• Reduce time‑to‑submit: first filing completed within 15 minutes for a defined recipe.
• Increase first‑pass acceptance: ≥80% of guided submissions accepted without correction for IL — Adult Name Change in Cook County — measured on the MVP happy‑path constraints listed below.
• Make configuration self‑serve: a non‑technical user can create or edit a Filing Flow without code.
• Fast onboarding: new environment up and running via Docker/Compose with a few dependencies, compared to much slower roll-out and heavy dependency trees for other existing e-filing solutions.

## 6) Ideal MVP feature set
• EFSP REST API integration for authentication, options discovery, and submitting a minimal case/document package.
• Form Blocks: a small set of validated input blocks (text, select, date, address) with basic theming.
• Filing Flow runner: linear flow with optional simple branching; custom instructions and help text per step.
• Session data: allow for a flow to collect data and store it in a session. Probably semi-structured (arrays, maps, etc.). Maybe support for near and far data, where near is readily available and far is maybe stored externally, like file attachments or references.
• Mapping layer: map recipe fields to EFSP payload fields; basic validation and error surfacing.
• Review & submit step with a readable summary.
• Basic auth/session and minimal audit of actions.
• Local deploy via Docker/Compose; SQLite in dev; CI with Ruff/Ty/Pytest.
• Initial Filing Flow/jurisdiction: Illinois — Adult Name Change (Cook County).
• Proof of feasibility in filing at least 2 other case types.
• Each filing includes one or more attachments (PDFs with form fields pre‑filled by the user outside the app).
• Happy‑path constraints (MVP acceptance applies to this scope): Cook County Adult Name Change; no existing Tyler/EFSP account; no fee waiver; no impoundment.

## 7) Non‑goals
• Full visual form builder or drag‑and‑drop editor.
• Advanced RBAC, multi‑tenant billing, or complex approvals.
• Deep analytics, custom dashboards, or BI.
• Offline mode or native mobile apps.
• Support for jurisdictions other than IL.
• Handling scenarios outside the happy path for MVP (e.g., existing Tyler/EFSP accounts, fee waivers, impoundment/confidential filings). Design should be extensible to handle these cases though.
• Extracting or cross-checking data from filled PDFs.
• Advanced scripting or rules engine support in the Filing Flow.

## 8) User journey snapshot
1) User selects a Filing Flow (e.g., "Illinois — Adult Name Change").
2) Guided steps present building blocks with plain‑language labels and helper text.
3) Data is validated inline; required PDFs (pre‑filled outside the app) are attached.
4) Review screen summarizes inputs in human‑readable form.
5) Submit via EFSP API; user sees confirmation and a link/reference number.

## 9) Value proposition
Clarity and speed over complexity. Filing Flows turn specialist knowledge into repeatable, guided experiences; Form Blocks ensure consistency and validation. Teams reduce training time and filing errors while keeping flexibility to evolve flows without code changes.

## 10) Risks & assumptions
• EFSP API stability/coverage: assume required endpoints exist and are reliable.
• Mapping correctness: field mappings must be accurate to avoid rejections.
• Compliance and privacy: sensitive data must be handled and stored appropriately.
• Rate limits and quotas: submission volumes remain within EFSP constraints.
• Change management: Filing Flows remain understandable to non‑technical users.
• Jurisdiction variability: county/court‑specific fields, document requirements, and payload formatting may require flow or mapping customization; we start with Cook County to limit scope.

## 11) Guiding principles
• Clarity over control: plain language, minimal choices per step.
• Small, composable pieces: prefer building blocks with single responsibility.
• Human‑readable configuration: recipes are text‑based, diff‑able, and reviewable.
• Secure by default: least‑privilege, avoid storing sensitive data unless required.
• Observable: errors are logged with context; happy paths are measurable.

## 12) Error handling strategy
The system handles errors at multiple levels to provide clear, actionable feedback:

### Validation errors
• **Form Block validation**: Real-time validation with inline error messages for individual fields (e.g., "Phone number must be 10 digits").
• **Cross-field validation**: Step-level validation before proceeding (e.g., "End date must be after start date").
• **Document validation**: File type, size, and basic structure checks on upload.

### EFSP API errors
• **Authentication failures**: Clear messaging with retry options and contact information.
• **Submission rejections**: Parse EFSP error responses and map to user-friendly language with specific correction steps.
• **Network/timeout errors**: Automatic retry with exponential backoff; clear status messaging to user.

### Error recovery
• **Session persistence**: Form data preserved across errors and browser refreshes until successful submission or session expiry.
• **Partial progress saving**: Users can return to incomplete filings within session timeframe.
• **Error context**: Log errors with sufficient context for debugging while protecting PII.
• **Graceful degradation**: If EFSP is unavailable, show status and estimated recovery time.

### User experience
• **Progressive disclosure**: Show only relevant error details; provide "show more" for technical users.
• **Action-oriented messaging**: "Fix this field" rather than "Invalid input".
• **Error summary**: Collect and display all errors at form submission to avoid frustrating back-and-forth.

## 13) Data retention & privacy
• **Session data**: No persistent storage of user data beyond active session; all form data cleared on successful submission or session timeout.
• **File storage**: Uploaded documents stored temporarily in secure external storage with automatic expiration in <24 hours (sufficient time for Tyler import).
• **Audit logs**: Minimal logging of actions (submission attempts, errors) without PII; logs retained for debugging and metrics only.
• **No user accounts**: Stateless design eliminates need for long-term data storage or user profile management. User profiles are created instead in Tyler's system and we pull from there.

## 14) Future considerations
• **Accessibility**: Target WCAG 2.1 AA compliance in future iterations for screen readers, keyboard navigation, and color contrast.
• **Responsive design**: Mobile-optimized interface for tablet and phone usage, recognizing many users may not have desktop access.
• **Multi-language support**: Spanish translation as priority for broader accessibility.
• **Advanced error recovery**: Integration with court clerk systems for manual review of rejected filings.

## 15) Open questions
• Expert mode: fully free‑form vs. semi‑guided based on live EFSP options?
• Filing Flow format: JSON/YAML in‑repo vs. DB‑backed, and how to version changes?
• Hosting: continue Docker/Compose for dev; what's the target for prod (e.g., container platform, DB)?
• AuthN/Z: stick to basic Django auth for MVP or add SSO later?
• Data retention: where to persist drafts and submitted data; PII handling and encryption at rest.
• Error handling: how to surface EFSP rejections with actionable guidance.
• Localization: is multi‑language support required in MVP?
• Accessibility: what's the minimum acceptable level for initial release?
• Form Flow logic: how to handle advanced branching, validation, and mapping? Code references? Script snippets? Rules engine?
• Coupling between Filing Flow configs and the implementation: should we define a schema and interface standard so that users can mix and match different implementations? Be nice to have portable configs and possibly different front-end apps for UI (e.g. React, etc.)
• UI Component Libraries: the MVP will rely on vanilla Django w/ Javascript to limit the scope. However, there's a very big React ecosystem and it might make sense to leverage that in creating the reusable Form Blocks. Could also explore other UI frameworks/libraries within the Django universe like django-components (https://github.com/django-components/django-components) or djhtmx (https://github.com/iwanalabs/django-htmx-components)
• Schemas: is it helpful or just friction to define schemas for the session data? Likely not useful but might help with any tooling we build later.

### Appendix: Possible form blocks
- Person Name (first/middle/last, suffix; alias support)
- Address (street, unit, city, state, ZIP; USPS normalization optional)
- Email
- Phone (E.164 formatting)
- Date (with min/max)
- Monetary Amount (currency-aware)
- Yes/No (boolean)
- Short Text / Long Text (with length/pattern validation)
- Select (static options)
- Select (dynamic options from EFSP/jurisdiction)
- Multi‑select (tags)
- County/Court Selector (Cook‑focused for MVP)
- Party Role (e.g., Petitioner/Respondent)
- Document Upload (PDF; file type/size validation)
- Repeating Group (e.g., additional aliases)
- Acknowledgment/Attestation (checkbox with statement)
- EFSP Option Picker (opaque key/value passthrough when needed)

---

Glossary  
* Attachment — externally pre‑filled PDF(s) included with the filing.  
* Building Blocks - Metaphor drawn from the normal world to help users think about a Form Block.
* EFSP — Suffolk's RESTful API wrapper to Tyler's EFSP. This system allows for integration with Tyler's authentication, options discovery, document upload, fee calculation, envelope submission, and status polling.  
* Expert Mode - flow that presents all the options and can be used by experts. Ideally any valid EFSP payload can be created using this flow. Can still include some filtering based on previous selections, etc. to pare down the options.
* Form Block — the smallest reusable UI unit (single field or grouped fields) with validation and presentation.  
* Filing Flow — an ordered, configurable sequence of Form Blocks with branching, instructions, and EFSP mapping.
* Guided Interview - platonic ideal of a filing flow that targeted at narrow use cases. These should be curated by experts such that the user experience is as smooth as possible (i.e. no extraneous steps/fields, clear instructions, etc.)
* Jurisdiction Profile — overrides to Mapping Spec and validations for a given court/county (e.g., Cook County).
* Mapping Spec — configuration that binds Form Block outputs to EFSP (and county) payload fields.  
* Recipe - Metaphor drawn from the normal world to help users think about a Filing Flow.
* Simple Form - synonymous with Guided Interview. Used to contrast with a flow that presents all the options such as Expert Mode.
