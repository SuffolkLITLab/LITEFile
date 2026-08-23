# Form identity guard v2

## Outcome

This targeted eight-cell GPT-4o/GPT-4o-mini run verifies the strengthened form
identity rules on flattened and raster-scanned MA-01 pages. All eight cells:

- extracted `CJD 101B`
- extracted the complete descriptive title `Complaint for Divorce under G.L. c.
  208, § 1B`
- omitted form revision because the page has no actual revision

All cells passed, with a mean score of 0.883. This is the current focused form
identity checkpoint. It does not yet test a real printed revision, similar form
IDs, multi-page footer placement, or unrelated documents that should produce no
form match.

The form-ID result should be used as evidence for a normalized deterministic
registry lookup, not as a Tyler code by itself.
