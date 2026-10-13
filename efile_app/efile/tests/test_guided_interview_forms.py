"""Keep the source inventory complete without equating it with filing coverage."""

from copy import deepcopy

from efile.services.guided_interview_forms import inventory_errors, load_inventory


def minimal_inventory():
    repo = "LSVermont/example"
    inventory = {"repositories": [{"repo": repo, "state": "vermont"}]}
    manifest = {
        "state": "vermont",
        "repositories": [
            {
                "repo": repo,
                "commit": "abc123",
                "source_url": "https://github.com/LSVermont/example",
                "reason": "Inspected source outputs.",
                "entrypoints": [],
            }
        ],
        "documents": [
            {
                "id": "example-instructions",
                "repo": repo,
                "entrypoint": "questions/example.yml",
                "title": "Instructions",
                "template_paths": ["templates/instructions.docx"],
                "source_urls": ["https://github.com/LSVermont/example/blob/abc123/templates/instructions.docx"],
                "publication_status": "uncertain",
                "stage": "unknown",
                "filing_status": "noncourt",
                "exclusion_reason": "Instructions explain how to file; they are not submitted to court.",
                "filing_type_labels": [],
                "mapping_status": "unmapped",
            }
        ],
    }
    return inventory, manifest


def test_missing_repository_cannot_be_counted_as_reviewed():
    inventory, manifest = minimal_inventory()
    assert inventory_errors(inventory, [manifest]) == []
    assert "missing repository review" in inventory_errors(inventory, [dict(manifest, repositories=[])])[-1]


def test_instructions_cannot_inherit_interview_filing_type():
    inventory, manifest = minimal_inventory()
    manifest["documents"][0]["filing_type_labels"] = ["Initial Filing"]
    assert any(
        "excluded document still suggests filing codes" in error for error in inventory_errors(inventory, [manifest])
    )


def test_repeated_repository_cannot_inflate_inventory_coverage():
    inventory, manifest = minimal_inventory()
    duplicate = deepcopy(manifest)
    assert any("duplicate repository" in error for error in inventory_errors(inventory, [manifest, duplicate]))
    assert any("duplicate output" in error for error in inventory_errors(inventory, [manifest, duplicate]))


def test_all_issue_repositories_and_output_sources_have_a_disposition():
    inventory, manifests = load_inventory()
    assert len(inventory["repositories"]) == 117
    assert inventory_errors(inventory, manifests) == []


def test_explicit_inline_output_does_not_need_a_static_template():
    inventory, manifest = minimal_inventory()
    document = manifest["documents"][0]
    document["template_paths"] = []
    document["attachment_variable"] = "generated_pdf"
    document["source_urls"] = ["https://github.com/LSVermont/example/blob/abc123/questions.yml"]
    assert inventory_errors(inventory, [manifest]) == []


def test_output_without_static_template_or_attachment_source_is_rejected():
    inventory, manifest = minimal_inventory()
    document = manifest["documents"][0]
    document["template_paths"] = []
    document["attachment_variable"] = None
    assert any("no entrypoint/source evidence" in error for error in inventory_errors(inventory, [manifest]))


def test_report_separates_bundles_attachments_and_distinct_printed_forms(monkeypatch):
    import efile.services.guided_interview_forms as service

    inventory = {
        "checked_at": "2026-10-13",
        "source_issue": "test",
        "repositories": [
            {"repo": "LSVermont/example", "state": "vermont"},
        ],
    }
    docs = [
        {
            "id": "one",
            "repo": "LSVermont/example",
            "title": "Download form",
            "printed_title": "Petition for Relief",
            "form_id": "VT-001",
            "filing_status": "court_filing",
            "publication_status": "public",
            "mapping_status": "candidate",
            "stage": "unknown",
        },
        {
            "id": "two",
            "repo": "LSVermont/example",
            "title": "Another link",
            "printed_title": "Petition for Relief",
            "form_id": "VT-001",
            "filing_status": "court_filing",
            "publication_status": "public",
            "mapping_status": "candidate",
            "stage": "unknown",
        },
        {
            "id": "bundle",
            "repo": "LSVermont/example",
            "title": "Download all forms",
            "form_id": None,
            "filing_status": "uncertain",
            "publication_status": "public",
            "mapping_status": "unmapped",
            "stage": "unknown",
            "output_kind": "bundle",
            "output_filename": "packet.pdf",
        },
        {
            "id": "one-attachment",
            "repo": "LSVermont/example",
            "title": "Petition",
            "printed_title": "Petition for Relief",
            "form_id": "VT-001",
            "filing_status": "court_filing",
            "publication_status": "public",
            "mapping_status": "candidate",
            "stage": "unknown",
            "output_filename": "petition.pdf",
        },
        {
            "id": "fragment",
            "repo": "LSVermont/example",
            "title": "Petition page 2",
            "printed_title": "Continuation",
            "form_id": "VT-001",
            "filing_status": "court_filing",
            "publication_status": "public",
            "mapping_status": "candidate",
            "stage": "unknown",
            "output_kind": "fragment",
        },
    ]
    manifest = {
        "state": "vermont",
        "repositories": [
            {
                "repo": "LSVermont/example",
                "entrypoints": [],
            }
        ],
        "documents": docs,
    }
    monkeypatch.setattr(service, "inventory_errors", lambda *_: [])
    monkeypatch.setattr(
        service,
        "deterministic_form_identity",
        lambda _state, evidence: {
            "status": "matched",
            "matches": [],
        },
    )
    monkeypatch.setattr(service, "exact_form_crosswalk_matches", lambda *_: [])

    counts = service.inventory_report(inventory, [manifest])["states"]["vermont"]

    assert counts["attachment_outputs"] == 4
    assert counts["document_outputs"] == 3
    assert counts["fragment_outputs"] == 1
    assert counts["bundle_outputs"] == 1
    assert counts["court_filing_fragments"] == 1
    assert counts["distinct_court_filing_forms"] == 1
