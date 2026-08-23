# Benchmark and form-crosswalk reconciliation

## Outcome

The review compared 30 unique synthetic documents and three taxonomy fields per
document against exact form-ID/name matches in the form crosswalk. It also checked
the proposed gold names against the current test catalog by resolving the names
within each court hierarchy.

The 90 field comparisons produced:

- 24 agreements between a reviewed benchmark name and at least one current
  crosswalk suggestion
- 15 conflicts
- 23 benchmark fields intentionally left unresolved
- 19 matched forms for which the crosswalk did not resolve the field
- 9 fields on documents with no crosswalk match

The 15 conflicts are not 15 benchmark errors. Crosswalk associations are still
unverified suggestions, and several matched forms have many unrelated or
over-broad associations. The conflict table is therefore a queue for review, not
an alternate gold set.

## Label changes

The benchmark now uses exact live Tyler names for Massachusetts divorce,
custody/support, adult name-change, and small-claims examples. The Massachusetts
small-claims case type now reflects the document's $1,275 claim amount. Vermont's
$2,250 small-claims example now uses the filing name
`Small Claims Complaint $1000 - $5000`.

For Vermont initiating forms where Tyler offers no form-specific filing name, the
printed form title remains a document-level extraction target and the taxonomy
label is separately recorded as `Initial Filing`, with lower confidence. The
Massachusetts separate-support example (MA-04) is now an abstention for all three
taxonomy levels: the live catalog and crosswalk did not establish a semantically
safe path.

Reviewed taxonomy labels replace the old LLM-assigned semantic label rather than
being appended as an alternative. This prevents broad values such as
`Probate and Family`, `Divorce`, or `Civil` from receiving credit when they are not
the exact selectable Tyler value.

## Identifier policy

Exact normalized names are the durable identities. Numeric Tyler keys now appear
only in dated, environment-specific observations or live candidate snapshots.
The live audit resolved every reviewed path by name and verified 64 names without
using stored numeric keys as identifiers.

## Limitations

- No crosswalk association is yet human-verified.
- An agreement means that at least one current suggestion matched; it does not
  validate every suggestion attached to that form.
- Several taxonomy choices remain court-practice questions, especially Vermont
  contested-versus-stipulated dissolution and generic subsequent filings.
- The test endpoint is evidence about current test configuration, not production.

See [`tables/label-reconciliation.csv`](tables/label-reconciliation.csv) for every
comparison and [`artifacts/summary.json`](artifacts/summary.json) for counts.
