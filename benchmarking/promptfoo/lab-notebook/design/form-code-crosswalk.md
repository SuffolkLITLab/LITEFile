# Official form-to-code crosswalk plan

## Goal

Recognize an official court form with high precision, then resolve its valid
Tyler category, case type, and filing type without asking a model to search the
full taxonomy. Use fuzzy taxonomy classification only when the form is unknown
or its reviewed mappings remain ambiguous after applying court and case context.

The crosswalk must be one-to-many. A form can be available in several courts,
used in several case categories, or map to different filing types depending on
whether a filing is initial or subsequent. The registry should never assume that
a form number is a globally unique Tyler filing code.

## Proposed records

Keep form identity separate from court-specific code mappings:

```yaml
form:
  jurisdiction: massachusetts
  form_id: CJD 101B
  canonical_name: Complaint for divorce under G.L. c. 208, § 1B
  aliases:
    - Complaint for Divorce
  revision: null
  official: true
  source_url: https://www.mass.gov/example
  source_sha256: "..."
  identity_signals:
    acroform_field_signature: "..."
    first_page_text_signature: "..."

mappings:
  - court_scope:
      department: Probate and Family Court
      court_names: [Essex Probate and Family Court]
      observed_route_keys: ["352"] # staging provenance only
    filing_phase: initial
    category: Domestic Relations
    case_type: Divorce 1B
    filing_type: Complaint for Divorce - Irretrievable Breakdown 1B
    discriminators: []
    confidence: 0.98
    catalog_status: current
    catalog_checked_at: 2026-08-23
    association_status: human_verified
    human_verification:
      verified: true
      verified_by: reviewer@example.org
      verified_at: 2026-08-23
```

Tyler's numeric taxonomy keys are environment-specific surrogate keys. They
can change and differ between staging and production. The canonical category,
case-type, filing-type, and court names are the durable identifiers. A live
audit may use today's numeric keys transiently to walk parent-child endpoints,
but runtime code must resolve the saved names again in the selected environment.

Use a stable internal form key rather than making the printed ID the database
primary key. Printed IDs can be absent, reused, or changed by revision.

## Phase 1: Seed the registry

Start with the forms already represented in the synthetic corpus. Those source
records contain a form name, printed identifier, official source URL, state, and
paired interactive and flattened PDFs.

For each form:

1. Confirm the name, identifier, revision, and official source URL.
2. Record the source PDF checksum and retrieval date.
3. Generate normalized title and identifier aliases.
4. Record stable AcroForm field-name and first-page text signatures where useful.
5. Mark synthetic facsimiles and generic pleadings as non-official so they can
   test false-positive rejection but cannot trigger deterministic code selection.

Expand later by indexing official court form directories. Preserve source URLs
and retrieval metadata so the approximately 1,000-form inventory can be updated
without silently changing reviewed records.

## Phase 2: Identify forms deterministically

Use a precision-first cascade:

1. Exact normalized form ID plus compatible jurisdiction
2. Form ID plus revision and normalized title
3. Unique AcroForm field-name signature
4. Exact normalized official title plus court department
5. Strong first-page structural or text signature
6. Vision or language-model form identification only as a fallback

Binary PDF hashes are useful for pristine source copies but not sufficient for
filled, flattened, optimized, or scanned documents. A match should combine at
least two independent signals when an identifier is short or reused.

Return the internal form key, matched revision, evidence, and confidence. Do not
return a Tyler code at this stage.

## Phase 3: Discover possible mappings

For every recognized form, enumerate possible paths from the live endpoint:

1. Determine the court scopes where the official source says the form is valid.
2. Retrieve categories for representative courts in each scope.
3. Retrieve child case types for plausible categories.
4. Retrieve initial and subsequent filing types under each plausible path.
5. Rank filing-type names against the form's printed name, aliases, instructions,
   and purpose.
6. Store the candidate paths as unverified suggestions, including paths with no
   good match.

This discovery step may use fuzzy text or a model, but it must never publish a
mapping automatically. It creates a review queue rather than ground truth.

## Phase 4: Review one-to-many mappings

A reviewer should confirm each complete category/type/filing path and record why
more than one path is valid. Useful discriminators include:

- selected court or department
- initial versus subsequent filing
- selected case category and case type
- checked choices on the form
- amount thresholds
- contested, uncontested, emergency, stipulated, or fee-required variants
- whether the form is a lead document or an attachment

If those inputs reduce the mapping to one live path, deterministic lookup can
recommend it. If multiple paths remain, pass only those reviewed alternatives to
the taxonomy classifier or ask the filer a targeted question.

## Phase 5: Validate against Tyler continuously

Every mapping should retain the exact canonical names, court scope, hierarchy
parents, review date, and label confidence. Environment-specific numeric values
may be kept in dated observation notes, but never as the crosswalk identity. A
scheduled audit should resolve each name to today's environment key and check
that:

- each category still exists for an in-scope court
- each case type remains a child of the recorded category
- each filing type remains valid under the recorded category, case type, and
  filing phase
- each stored canonical name still resolves uniquely enough for the workflow

Catalog drift should mark a mapping stale and return it to review; it should not
silently substitute a similar name or retain a stale numeric key.

## Runtime decision policy

Use the following order:

1. Extract form name, form ID, revision, court, and document facts.
2. Identify a registry form using deterministic signals.
3. Filter its reviewed mappings with court, filing phase, category, case type,
   and selected form options.
4. Revalidate the surviving paths against cached or live Tyler tables.
5. Auto-suggest a unique high-confidence path.
6. If several reviewed paths survive, classify only among those paths or ask a
   targeted question.
7. If no mapping survives, use hierarchical fuzzy taxonomy retrieval.

Initially, show even unique matches for user confirmation. Automatic application
can be considered after measuring false-positive form identification and mapping
drift in realistic filings.

## Evaluation plan

Test form recognition outside Promptfoo as deterministic code, then use
Promptfoo for the vision and fuzzy fallbacks.

Measure:

- exact form-key precision and recall
- identification coverage by interactive, flattened, and scanned input
- revision accuracy
- percentage resolved to zero, one, or several reviewed code paths
- live hierarchy validity
- end-to-end exact path accuracy
- false matches on generic motions and unofficial facsimiles
- token and latency savings relative to full-table prompting

The first checkpoint should cover 10–20 forms across Massachusetts, Illinois,
and Vermont, including at least one reused or ambiguous form, one revised form,
one scan, and several negative controls.
