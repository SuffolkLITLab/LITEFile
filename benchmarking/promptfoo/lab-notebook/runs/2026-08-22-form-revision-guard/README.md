# Form revision guard

## Outcome

This targeted eight-cell GPT-4o/GPT-4o-mini run tested the first attempt to stop
copy-status notices from being extracted as form revisions. All cells passed the
overall threshold and extracted `CJD 101B`, but GPT-4o mini v2 still returned
`TEST COPY` as the revision on both flattened and scanned inputs.

The result showed that a negative example alone was insufficient. The successor
prompt uses a positive emission rule: output a revision only when it contains a
date or version number or is explicitly labeled Rev, Revision, or Version.
