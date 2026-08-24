# Official-form sentinel benchmark

This is a bounded extraction check against the refreshed court-form corpus. It
evaluated the seven-document sentinel with both extraction prompts on the two
OpenAI deployments, for 28 calls total. The cases include interactive and
flattened official forms, an official-template motion, and the raster-only
MA-01 control.

## Result

The mean field-set score was **0.301762** (3/28 passing, 0 API errors).

| Provider | Prompt | Mean score | Passing runs |
|---|---|---:|---:|
| gpt-5.4-nano | v1 production | 0.219309 | 0/7 |
| gpt-5.4-nano | v2 evidence-bound | 0.301250 | 1/7 |
| gpt-5.4 | v1 production | 0.312509 | 1/7 |
| gpt-5.4 | v2 evidence-bound | 0.373978 | 1/7 |

The prior seven-document sentinel used the synthetic facsimiles and scored
0.572228 across these same two deployment labels. This is a substantial drop,
but it is not a controlled model-only comparison: the official PDFs have much
more boilerplate, different printed form identities, native form fields, and
some fields that are genuinely absent on the current official template.

The official corpus therefore changes the extraction task materially. The
largest drop was MA-01 flattened (0.9186 to 0.1742); IL-04 remained the strongest
official-form case (0.6972). The scan control remained at 0.0 as expected for
the text-only suite.

Raw Promptfoo output is compressed in `artifacts/`; normalized tables and the
exact input snapshots are stored alongside this README. The six unselected
providers were intentionally omitted from this quick sentinel checkpoint.

## Follow-up: IL-04 deterministic lookup

The official Illinois Small Claims Complaint contains the printed identifier
`CS-C 702.1`. The extraction sentinel did not invoke taxonomy lookup, but all
four IL-04 model outputs nevertheless extracted `case category: Small Claims`.
The low case score came from other fields, especially the ambiguous `case type`
label, not from the category field.

The runtime crosswalk has two gaps to address:

1. The registry stores this statewide form as `form_id: SMC` and does not list
   `CS-C 702.1` as an identifier alias, so identifier-only matching returns no
   result.
2. Title-only matching returns 11 mappings across the statewide SMC form and a
   Cook County form with the same title. The mappings are currently advisory
   (`unverified_suggestion` / `not_current`), and the classifier never bypasses
   the model for a crosswalk match.

Suggested implementation sequence:

- Add a printed-ID alias field and have both runtime and benchmark indexes match
  it.
- Add a current Kane County mapping for the official SMC form, with `Small
  Claims` as the category; keep the contract case type unresolved until the
  court-facing subtype mapping is reviewed.
- Add a deterministic category-resolution step before model classification,
  gated by jurisdiction, court, filing phase, and reviewed mapping status.
- Add a classification sentinel case that evaluates IL-04 at the category
  level, plus unit tests for identifier-only and title-only behavior.
