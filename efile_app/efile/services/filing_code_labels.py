"""Filing labels: each filing/category/case-type name combination once, with its courts.

Search groups and court lists are read from labels. Every write to the paths
table also updates the labels of the courts it wrote, so the two agree.
"""

import gzip
import hashlib
import heapq
import json
from collections import Counter
from contextlib import ExitStack
from itertools import batched, groupby
from pathlib import Path
from tempfile import TemporaryDirectory

from django.db import transaction
from django.utils import timezone

from efile.db_expressions import CourtCode
from efile.models import FilingCodeIndex, FilingCodeLabel
from efile.services.case_location import index_courts

FACETS = ("filing_type", "case_category", "case_type")
BATCH = 1000


def label_key(initial, filing, category, case_type):
    return hashlib.sha256(json.dumps([initial, filing, category, case_type]).encode()).hexdigest()[:32]


class LabelCounts:
    """Paths per label and court, gathered while paths are saved."""

    def __init__(self):
        self.courts = {}
        self.terms = {}

    def add(self, entry):
        label = (bool(entry["initial"]), *(str(entry[facet]["name"]) for facet in FACETS))
        self.courts.setdefault(label, Counter())[entry["court"]["code"]] += 1
        self.terms.setdefault(label, (entry["filing_terms"], entry["case_terms"]))

    def new_label(self, index, key, label, courts):
        filing, case = self.terms[label]
        return FilingCodeLabel(
            index=index,
            key=key,
            initial=label[0],
            filing_type_name=label[1],
            case_category_name=label[2],
            case_type_name=label[3],
            search_text=" " + " ".join(sorted(set(filing.split()) | set(case.split()))) + " ",
            filing_terms=filing,
            case_terms=case,
            courts=dict(courts),
        )

    def save(self, index):
        """Add these courts' counts to the index's labels, creating labels as needed."""
        for batch in batched(self.courts.items(), BATCH):
            keys = {label_key(*label): (label, courts) for label, courts in batch}
            existing = {row.key: row for row in FilingCodeLabel.objects.filter(index=index, key__in=list(keys))}
            for row in existing.values():
                row.courts.update(keys[row.key][1])
            FilingCodeLabel.objects.bulk_update(existing.values(), ["courts"])
            FilingCodeLabel.objects.bulk_create(
                [
                    self.new_label(index, key, label, courts)
                    for key, (label, courts) in keys.items()
                    if key not in existing
                ]
            )


class LabelSpool:
    """Labels for many courts, each written once.

    Updating a label for every court it appears in leaves a dead row version
    per court: Illinois labels average 13 to 20 courts. Each court's counts
    go to a file sorted by label instead, and the files are merged.
    """

    def __init__(self):
        self.directory = TemporaryDirectory(prefix="filing-labels-")
        self.files = []

    def add(self, labels):
        path = Path(self.directory.name) / f"{len(self.files)}.json.gz"
        rows = sorted((label_key(*label), label, courts) for label, courts in labels.courts.items())
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as spool:
            for key, label, courts in rows:
                spool.write(json.dumps([key, label, labels.terms[label], courts]) + "\n")
        self.files.append(path)

    def save(self, index):
        """Create the labels; the index must have none for these courts' labels yet."""
        with self.directory, ExitStack() as files:
            spools = [files.enter_context(gzip.open(path, "rt", encoding="utf-8")) for path in self.files]
            # Every line starts with its fixed-length key, so lines sort by label.
            rows = (json.loads(line) for line in heapq.merge(*spools))

            def merged():
                for key, group in groupby(rows, key=lambda row: row[0]):
                    labels, courts = LabelCounts(), Counter()
                    for _, label, terms, counts in group:
                        label = tuple(label)
                        labels.terms[label] = tuple(terms)
                        courts.update(counts)
                    yield labels.new_label(index, key, label, courts)

            for batch in batched(merged(), BATCH):
                FilingCodeLabel.objects.bulk_create(batch)


def forget_courts(index, codes):
    """Remove these courts from every label, and labels no other court has."""
    codes = set(codes)
    if not codes:
        return
    changed, unused = [], []
    for row in (
        FilingCodeLabel.objects.filter(index=index, courts__has_any_keys=list(codes))
        .only("courts")
        .iterator(chunk_size=BATCH)
    ):
        row.courts = {code: count for code, count in row.courts.items() if code not in codes}
        (changed if row.courts else unused).append(row)
        if len(changed) >= BATCH:
            FilingCodeLabel.objects.bulk_update(changed, ["courts"])
            changed = []
    FilingCodeLabel.objects.bulk_update(changed, ["courts"])
    for batch in batched(unused, BATCH):
        FilingCodeLabel.objects.filter(pk__in=[row.pk for row in batch]).delete()


def build_labels(index, *, progress=None):
    """Save labels for an index whose paths were saved before labels existed.

    One transaction holding the index row, so a sync waits rather than
    changing courts underneath; searches keep reading paths meanwhile.
    """
    with transaction.atomic():
        locked = FilingCodeIndex.objects.select_for_update().get(pk=index.pk)
        spool = LabelSpool()
        codes = sorted(index_courts(locked))
        for position, code in enumerate(codes, 1):
            labels = LabelCounts()
            rows = (
                locked.paths.alias(court_code=CourtCode("court"))
                .filter(court_code=code)
                .values("initial", "court", *FACETS, "filing_terms", "case_terms")
            )
            for row in rows.iterator(chunk_size=5000):
                labels.add(row)
            spool.add(labels)
            if progress:
                progress(f"Read labels for {position} of {len(codes)} courts ({code})")
        locked.labels.all().delete()
        spool.save(locked)
        locked.labels_built_at = timezone.now()
        locked.save(update_fields=["labels_built_at"])
