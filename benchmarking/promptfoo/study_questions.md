# Follow-up extraction questions

## Current classification finding

The 2026-08-22 stratified study supports a three-stage production direction:
extract document/form evidence, retrieve exact-form and live hierarchy candidates,
then have the model choose a short run-local candidate reference. Application code
should resolve that reference to the exact canonical name and current route key.
This reached 36/36 on the small two-model sentinel and avoids asking the model to
reproduce punctuation-sensitive Tyler strings. See the
[`stratified classification study`](lab-notebook/studies/2026-08-22-stratified-classification/).

This is a promising sentinel result, not a production accuracy estimate. The next
study needs predicted-parent propagation, iterative candidate retrieval, more
ambiguous forms, and court-facing label review.

The current production prompt asks for useful document facts, but those facts do
not by themselves complete a Tyler filing. The first benchmark should report the
11 current fields without making the model responsible for every downstream API
decision.

## Candidate document-level fields

- Whether the displayed date is a signature, issue, service, or filing date.
- Whether the PDF is the lead filing, a supporting document, a proposed order,
  or a confidential attachment.
- The moving or filing party and that person's role, especially when the caption
  alone does not say who submitted a motion.
- An amount in controversy or claim amount when it is expressly shown and Tyler
  uses amount bands to select a case type.
- Checked form choices that distinguish emergency, stipulated, with-children,
  jury, possession-only, or similar filing variants.
- Strong evidence about whether the document starts a case or belongs to an
  existing case. A docket number is evidence, but should not be the only rule.

## Tyler lookup outputs

These should normally be resolved after extraction against the selected court's
live code lists, with the filer confirming ambiguous matches:

- exact court code
- initial or subsequent filing timing
- exact case category and code
- exact case type and code
- exact filing type and code for each uploaded document
- filer role and Tyler party types
- confidential or security/document type
- amount-in-controversy band and filing-specific case questions
- optional services and service contacts

The benchmark should eventually score this as a staged pipeline: document fact
extraction, live-catalog candidate retrieval, and final candidate ranking. A
single unconstrained LLM prompt cannot reliably emit codes that vary by court and
change over time.

## Labeling work still needed

- Review Massachusetts targets against courts that are actually present in the
  test catalog. Several synthetic forms name courts not exposed by the current
  endpoint, so their semantic labels remain provisional.
- Decide whether accepted values should reward both a natural document title and
  Tyler's generic filing label (for example, “Eviction Complaint” and
  “Complaint”) or score them as separate fields.
- Add at least two independent reviewers for ambiguous category/type labels and
  measure their agreement before treating those items as high-confidence gold.
- Expand the raster-only sentinel beyond one form: multi-page, rotated,
  low-contrast, handwriting, and checkbox-heavy examples remain untested.
- Decide how to label opaque AcroForm field names and checkbox export values.
  The current synthetic names are unusually descriptive.
- Add prompt-injection cases inside PDF text and form values before sending
  machine-extracted context to production models.
- Compare the hybrid rendered-page context with the provider-native Files API;
  the current vision path does not prove that PDF ingestion behaves identically.
