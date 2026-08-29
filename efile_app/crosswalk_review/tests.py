import csv
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from crosswalk_review.local_forms import LocalFormIdVerification
from crosswalk_review.models import CrosswalkForm, CrosswalkMapping, FormReview, MappingVerdict


class CrosswalkModelTests(TestCase):
    def setUp(self):
        self.form = CrosswalkForm.objects.create(
            canonical_id="TEST-01",
            jurisdiction="massachusetts",
            form_id="CJD 101B",
            canonical_name="Complaint for Divorce",
            department="Probate and Family Court",
            description="Test form description",
            is_efileable=True,
            is_form=True,
            source_urls=["https://example.com/form.pdf", "https://example.com/info"],
            registry_index=0,
        )
        self.mapping_high = CrosswalkMapping.objects.create(
            form=self.form,
            mapping_index=0,
            category="Domestic Relations",
            case_type="Divorce 1B",
            filing_type="Complaint for Divorce",
            filing_phase="initial",
            court_names=["Middlesex Probate and Family Court"],
            confidence=0.92,
            association_status="unverified_suggestion",
            catalog_status="current",
            notes="Filing type matched. [Staging observation: code=123, cat=456]",
        )
        self.mapping_med = CrosswalkMapping.objects.create(
            form=self.form,
            mapping_index=1,
            category="Domestic Relations",
            case_type="Divorce 1B",
            filing_type="Joint Petition",
            filing_phase="initial",
            court_names=["Norfolk Probate and Family Court"],
            confidence=0.75,
            notes="No staging observations",
        )
        self.mapping_low = CrosswalkMapping.objects.create(
            form=self.form,
            mapping_index=2,
            category="Domestic Relations",
            case_type="Divorce 1B",
            filing_type="Other",
            confidence=0.40,
        )
        self.mapping_none = CrosswalkMapping.objects.create(
            form=self.form,
            mapping_index=3,
            category="Domestic Relations",
            case_type="Divorce 1B",
            filing_type="Unknown",
            confidence=None,
        )

    def test_form_properties(self):
        self.assertEqual(str(self.form), "TEST-01 – Complaint for Divorce")
        self.assertEqual(self.form.primary_source_url, "https://example.com/form.pdf")

    def test_form_primary_source_url_empty(self):
        empty_form = CrosswalkForm.objects.create(
            canonical_id="TEST-EMPTY",
            canonical_name="Empty Form",
            source_urls=[],
            registry_index=1,
        )
        self.assertIsNone(empty_form.primary_source_url)

    def test_form_source_urls_exclude_unsafe_schemes(self):
        self.form.source_urls = [
            "javascript:alert(1)",
            "http://[invalid",
            "https://example.com/safe.pdf",
        ]
        self.assertEqual(self.form.safe_source_urls, ["https://example.com/safe.pdf"])
        self.assertEqual(self.form.primary_source_url, "https://example.com/safe.pdf")

    def test_mapping_clean_notes(self):
        self.assertEqual(self.mapping_high.notes_clean, "Filing type matched.")
        self.assertEqual(self.mapping_med.notes_clean, "No staging observations")

    def test_mapping_confidence_labels(self):
        self.assertEqual(self.mapping_high.confidence_label, "high")
        self.assertEqual(self.mapping_med.confidence_label, "medium")
        self.assertEqual(self.mapping_low.confidence_label, "low")
        self.assertEqual(self.mapping_none.confidence_label, "unknown")
        self.assertEqual(self.mapping_high.confidence_percent, 92)
        self.assertIsNone(self.mapping_none.confidence_percent)


class CrosswalkViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.form1 = CrosswalkForm.objects.create(
            canonical_id="MA-01",
            jurisdiction="massachusetts",
            canonical_name="Form One",
            registry_index=0,
        )
        self.form2 = CrosswalkForm.objects.create(
            canonical_id="MA-02",
            jurisdiction="massachusetts",
            canonical_name="Form Two",
            registry_index=1,
        )
        self.m1 = CrosswalkMapping.objects.create(
            form=self.form1,
            mapping_index=0,
            category="Family",
            case_type="Divorce",
            filing_type="Complaint",
            confidence=0.90,
        )
        self.m2 = CrosswalkMapping.objects.create(
            form=self.form2,
            mapping_index=0,
            category="Civil",
            case_type="Contract",
            filing_type="Complaint",
            confidence=0.80,
        )

    def test_index_get(self):
        response = self.client.get(reverse("crosswalk_review:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crosswalk review")
        self.assertContains(response, "Total forms")

    def test_index_post_sets_reviewer(self):
        response = self.client.post(
            reverse("crosswalk_review:index"),
            {"reviewer_name": "Alice"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("Alice", response.url)
        self.assertEqual(self.client.session.get("reviewer_name"), "Alice")

    def test_index_encodes_reviewer_in_redirect(self):
        response = self.client.post(
            reverse("crosswalk_review:index"),
            {"reviewer_name": "Alice & Bob+QA"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("reviewer=Alice+%26+Bob%2BQA", response.url)

    def test_index_rejects_overlong_reviewer_name(self):
        response = self.client.post(
            reverse("crosswalk_review:index"),
            {"reviewer_name": "A" * 101},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "must be 100 characters or fewer")
        self.assertIsNone(self.client.session.get("reviewer_name"))

    def test_index_only_counts_forms_with_every_mapping_reviewed(self):
        second_mapping = CrosswalkMapping.objects.create(
            form=self.form1,
            mapping_index=1,
            filing_type="Answer",
        )
        MappingVerdict.objects.create(mapping=self.m1, reviewer_name="Alice", verdict="correct")
        MappingVerdict.objects.create(mapping=self.m1, reviewer_name="Bob", verdict="correct")

        response = self.client.get(reverse("crosswalk_review:index"))
        self.assertEqual(response.context["forms_fully_reviewed"], 0)

        MappingVerdict.objects.create(mapping=second_mapping, reviewer_name="Alice", verdict="correct")
        response = self.client.get(reverse("crosswalk_review:index"))
        self.assertEqual(response.context["forms_fully_reviewed"], 1)

    def test_review_form_requires_reviewer(self):
        response = self.client.get(reverse("crosswalk_review:review_form", args=["MA-01"]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("crosswalk_review:index"))

    def test_review_form_get_with_reviewer(self):
        response = self.client.get(reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Form One")
        self.assertContains(response, "Alice")
        self.assertContains(response, "Browse filing codes on LITEFile")

    def test_review_form_displays_confidence_as_percentage(self):
        response = self.client.get(reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice")
        self.assertContains(response, "90%")

    def test_review_form_preloaded_court_uses_the_route_key_expected_by_javascript(self):
        self.m1.court_names = ["Middlesex Probate and Family Court"]
        self.m1.raw_data = {
            "court_scope": {
                "court_names": ["Middlesex Probate and Family Court"],
                "observed_route_keys": ["352"],
            }
        }
        self.m1.save(update_fields=["court_names", "raw_data"])

        response = self.client.get(reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice")

        self.assertContains(response, 'value="Middlesex Probate and Family Court"')
        self.assertContains(response, 'data-code="352"')

    def test_review_form_uses_valid_lookup_phase_for_paper_only_mapping(self):
        self.m1.filing_phase = "paper_only"
        self.m1.save(update_fields=["filing_phase"])

        response = self.client.get(reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice")

        self.assertContains(response, 'data-assigned-filing-phase="paper_only"')
        self.assertContains(response, '<option value="initial" selected>Initial</option>', html=True)
        self.assertContains(response, "staging lookup starts with Initial")
        self.assertNotContains(response, 'data-filing-phase="paper_only"')

    def test_review_form_uses_local_pdf_from_working_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            forms_root = Path(temp_dir)
            pdf_path = forms_root / "MA" / "MA_Form_One.pdf"
            pdf_path.parent.mkdir()
            pdf_bytes = b"%PDF-local-form-one"
            pdf_path.write_bytes(pdf_bytes)
            (forms_root / "form_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "form_id": "",
                            "canonical_title": "Form One",
                            "jurisdiction": "ma",
                            "relative_path": "MA/MA_Form_One.pdf",
                            "source_url": "https://example.com/form-one.pdf",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            verified = LocalFormIdVerification(status="verified", form_id="CJD 101B", page=1)
            with (
                override_settings(CROSSWALK_REVIEW_FORMS_ROOT=forms_root),
                patch("crosswalk_review.views.verify_local_form_id", return_value=verified),
            ):
                response = self.client.get(reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice")

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "appears on page 1")
                self.assertContains(response, "MA/MA_Form_One.pdf")
                self.assertContains(response, reverse("crosswalk_review:local_form_pdf", args=["MA-01"]))

                pdf_response = self.client.get(reverse("crosswalk_review:local_form_pdf", args=["MA-01"]))

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertIn('inline; filename="MA_Form_One.pdf"', pdf_response["Content-Disposition"])
        self.assertEqual(pdf_response["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(b"".join(pdf_response.streaming_content), pdf_bytes)

    def test_review_form_blocks_local_pdf_when_assigned_id_is_not_in_candidate(self):
        self.form1.form_id = "CJD 200"
        self.form1.save(update_fields=["form_id"])
        with tempfile.TemporaryDirectory() as temp_dir:
            forms_root = Path(temp_dir)
            pdf_path = forms_root / "MA" / "MA_Form_One.pdf"
            pdf_path.parent.mkdir()
            pdf_path.write_bytes(b"%PDF-local-form-one")
            (forms_root / "form_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "canonical_title": "Form One",
                            "jurisdiction": "ma",
                            "relative_path": "MA/MA_Form_One.pdf",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            missing = LocalFormIdVerification(status="missing", form_id="CJD 200")
            with (
                override_settings(CROSSWALK_REVIEW_FORMS_ROOT=forms_root),
                patch("crosswalk_review.views.verify_local_form_id", return_value=missing),
            ):
                response = self.client.get(reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice")
                pdf_response = self.client.get(reverse("crosswalk_review:local_form_pdf", args=["MA-01"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not appear in the extracted text")
        self.assertNotContains(response, '<iframe class="source-frame"')
        self.assertEqual(pdf_response.status_code, 404)

    def test_review_form_does_not_embed_remote_pdf_when_local_copy_is_missing(self):
        self.form1.source_urls = ["https://example.com/form-one.pdf"]
        self.form1.save(update_fields=["source_urls"])
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(CROSSWALK_REVIEW_FORMS_ROOT=Path(temp_dir)):
                response = self.client.get(reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No local PDF has been deterministically associated")
        self.assertNotContains(response, '<iframe class="source-frame"')
        self.assertContains(response, "Open official source in new tab")

    def test_review_form_post_saves_verdicts(self):
        response = self.client.post(
            reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice",
            {
                "reviewer_name": "Alice",
                f"verdict_{self.m1.pk}": "correct",
                f"notes_{self.m1.pk}": "Verified against docket rule",
            },
        )
        self.assertEqual(response.status_code, 302)
        verdict = MappingVerdict.objects.get(mapping=self.m1, reviewer_name="Alice")
        self.assertEqual(verdict.verdict, "correct")
        self.assertEqual(verdict.reviewer_notes, "Verified against docket rule")

    def test_review_form_post_updates_existing_verdict(self):
        MappingVerdict.objects.create(
            mapping=self.m1,
            reviewer_name="Alice",
            verdict="unsure",
            reviewer_notes="Old note",
        )
        response = self.client.post(
            reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice",
            {
                "reviewer_name": "Alice",
                f"verdict_{self.m1.pk}": "incorrect",
                f"notes_{self.m1.pk}": "Wrong category",
            },
        )
        self.assertEqual(response.status_code, 302)
        verdict = MappingVerdict.objects.get(mapping=self.m1, reviewer_name="Alice")
        self.assertEqual(verdict.verdict, "incorrect")
        self.assertEqual(verdict.reviewer_notes, "Wrong category")

    def test_review_form_post_requires_every_mapping(self):
        second_mapping = CrosswalkMapping.objects.create(
            form=self.form1,
            mapping_index=1,
            filing_type="Answer",
        )
        response = self.client.post(
            reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice",
            {
                "reviewer_name": "Alice",
                f"verdict_{self.m1.pk}": "correct",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a verdict for every mapping")
        self.assertEqual(MappingVerdict.objects.count(), 0)
        self.assertContains(response, f'name="verdict_{second_mapping.pk}"')

    def test_field_review_save_persists_partial_identity_and_mapping_answers(self):
        response = self.client.post(
            reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice",
            {
                "action": "save",
                "reviewed_title": "Corrected form title",
                "title_verdict": "incorrect",
                "reviewed_form_id": "CJD 101B",
                "form_id_verdict": "correct",
                "form_notes": "Title corrected from the source PDF.",
                f"category_{self.m1.pk}": "Family",
                f"case_type_{self.m1.pk}": "Divorce",
                f"filing_type_{self.m1.pk}": "Complaint",
                f"category_verdict_{self.m1.pk}": "correct",
                f"case_type_verdict_{self.m1.pk}": "",
                f"filing_type_verdict_{self.m1.pk}": "",
                f"notes_{self.m1.pk}": "Need to confirm the lower levels.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=1", response.url)
        form_review = FormReview.objects.get(form=self.form1, reviewer_name="Alice")
        self.assertEqual(form_review.reviewed_title, "Corrected form title")
        self.assertEqual(form_review.title_verdict, "incorrect")
        mapping_review = MappingVerdict.objects.get(mapping=self.m1, reviewer_name="Alice")
        self.assertEqual(mapping_review.reviewed_category, "Family")
        self.assertEqual(mapping_review.field_verdicts, {"category": "correct", "case_type": "", "filing_type": ""})
        self.assertEqual(mapping_review.verdict, "")

    def test_field_review_save_next_requires_all_fields(self):
        response = self.client.post(
            reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice",
            {
                "action": "save_next",
                "reviewed_title": "Form One",
                "title_verdict": "correct",
                "reviewed_form_id": "",
                "form_id_verdict": "correct",
                f"category_{self.m1.pk}": "Family",
                f"case_type_{self.m1.pk}": "Divorce",
                f"filing_type_{self.m1.pk}": "Complaint",
                f"category_verdict_{self.m1.pk}": "correct",
                f"case_type_verdict_{self.m1.pk}": "correct",
                f"filing_type_verdict_{self.m1.pk}": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "field answers are missing")
        self.assertFalse(FormReview.objects.exists())
        self.assertFalse(MappingVerdict.objects.exists())

    def test_field_review_complete_answers_are_resumable(self):
        response = self.client.post(
            reverse("crosswalk_review:review_form", args=["MA-01"]) + "?reviewer=Alice",
            {
                "action": "save_next",
                "reviewed_title": "Form One",
                "title_verdict": "correct",
                "reviewed_form_id": "CJD 101B",
                "form_id_verdict": "correct",
                f"category_{self.m1.pk}": "Family",
                f"case_type_{self.m1.pk}": "Divorce",
                f"filing_type_{self.m1.pk}": "Complaint",
                f"category_verdict_{self.m1.pk}": "correct",
                f"case_type_verdict_{self.m1.pk}": "correct",
                f"filing_type_verdict_{self.m1.pk}": "correct",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("workflow=fields", response.url)
        self.assertEqual(FormReview.objects.get(form=self.form1, reviewer_name="Alice").form_id_verdict, "correct")
        verdict = MappingVerdict.objects.get(mapping=self.m1, reviewer_name="Alice")
        self.assertEqual(verdict.verdict, "correct")
        self.assertTrue(all(value == "correct" for value in verdict.field_verdicts.values()))

    def test_export_json_includes_identity_only_form_reviews(self):
        FormReview.objects.create(
            form=self.form1,
            reviewer_name="Alice",
            reviewed_title="Form One",
            title_verdict="correct",
            reviewed_form_id="CJD 101B",
            form_id_verdict="correct",
        )

        response = self.client.get(reverse("crosswalk_review:export_json"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        form_data = next(item for item in response.json()["forms"] if item["canonical_id"] == "MA-01")
        self.assertEqual(form_data["reviews"][0]["reviewed_title"], "Form One")

    @patch("crosswalk_review.views.TylerTaxonomyClient")
    def test_taxonomy_options_uses_live_client_for_jurisdiction(self, client_class):
        client_class.return_value.base_url = "https://staging.example"
        client_class.return_value.categories.return_value = [
            {"route_key": "10", "name": "Family"},
        ]

        response = self.client.get(
            reverse("crosswalk_review:taxonomy_options", args=["categories"]),
            {"jurisdiction": "massachusetts", "court": "123", "filing_phase": "initial"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["options"], [{"route_key": "10", "name": "Family"}])
        client_class.return_value.categories.assert_called_once_with("massachusetts", "123", "initial")

    @patch("crosswalk_review.views.TylerTaxonomyClient")
    def test_taxonomy_options_normalizes_filing_phase(self, client_class):
        client_class.return_value.base_url = "https://staging.example"
        client_class.return_value.categories.return_value = []

        response = self.client.get(
            reverse("crosswalk_review:taxonomy_options", args=["categories"]),
            {"jurisdiction": "massachusetts", "court": "123", "filing_phase": " Initial "},
        )

        self.assertEqual(response.status_code, 200)
        client_class.return_value.categories.assert_called_once_with("massachusetts", "123", "initial")

    @patch("crosswalk_review.views.TylerTaxonomyClient")
    def test_taxonomy_options_rejects_unsafe_route_keys(self, client_class):
        response = self.client.get(
            reverse("crosswalk_review:taxonomy_options", args=["categories"]),
            {"jurisdiction": "massachusetts", "court": "../other", "filing_phase": "initial"},
        )

        self.assertEqual(response.status_code, 502)
        client_class.assert_not_called()

    @patch("crosswalk_review.views.TylerTaxonomyClient")
    def test_taxonomy_options_accepts_current_colon_and_space_court_keys(self, client_class):
        client_class.return_value.base_url = "https://staging.example"
        client_class.return_value.categories.return_value = [{"route_key": "7", "name": "Civil"}]

        for court in ("sc:chittendon", "reaknox 2"):
            with self.subTest(court=court):
                response = self.client.get(
                    reverse("crosswalk_review:taxonomy_options", args=["categories"]),
                    {"jurisdiction": "vermont", "court": court, "filing_phase": "initial"},
                )
                self.assertEqual(response.status_code, 200)

        self.assertEqual(client_class.return_value.categories.call_count, 2)

    def test_next_unreviewed_redirects_to_first_unreviewed(self):
        # Alice reviews MA-01
        MappingVerdict.objects.create(mapping=self.m1, reviewer_name="Alice", verdict="correct")

        # Next unreviewed should redirect to MA-02
        response = self.client.get(reverse("crosswalk_review:next_unreviewed") + "?reviewer=Alice")
        self.assertEqual(response.status_code, 302)
        self.assertIn("MA-02", response.url)

    def test_next_unreviewed_returns_partially_reviewed_form(self):
        CrosswalkMapping.objects.create(
            form=self.form1,
            mapping_index=1,
            filing_type="Answer",
        )
        MappingVerdict.objects.create(mapping=self.m1, reviewer_name="Alice", verdict="correct")

        response = self.client.get(reverse("crosswalk_review:next_unreviewed") + "?reviewer=Alice")
        self.assertEqual(response.status_code, 302)
        self.assertIn("MA-01", response.url)

    def test_next_unreviewed_when_all_reviewed(self):
        MappingVerdict.objects.create(mapping=self.m1, reviewer_name="Alice", verdict="correct")
        MappingVerdict.objects.create(mapping=self.m2, reviewer_name="Alice", verdict="correct")

        # When all reviewed, show the progress summary instead of looping.
        response = self.client.get(reverse("crosswalk_review:next_unreviewed") + "?reviewer=Alice")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("crosswalk_review:progress")))

    def test_progress_view(self):
        MappingVerdict.objects.create(mapping=self.m1, reviewer_name="Alice", verdict="correct")
        response = self.client.get(reverse("crosswalk_review:progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review progress")
        self.assertContains(response, "Alice")
        self.assertContains(response, "Form One")

    def test_progress_counts_reviewed_mappings_not_verdict_rows(self):
        second_mapping = CrosswalkMapping.objects.create(
            form=self.form1,
            mapping_index=1,
            filing_type="Answer",
        )
        MappingVerdict.objects.create(mapping=self.m1, reviewer_name="Alice", verdict="correct")
        MappingVerdict.objects.create(mapping=self.m1, reviewer_name="Bob", verdict="correct")

        response = self.client.get(reverse("crosswalk_review:progress"))
        form = next(item for item in response.context["forms"] if item.pk == self.form1.pk)
        self.assertEqual(form.mapping_count, 2)
        self.assertEqual(form.reviewed_mapping_count, 1)
        self.assertEqual(form.verdict_count, 2)
        self.assertContains(response, "1 / 2")
        self.assertContains(response, "Partial")
        self.assertTrue(CrosswalkMapping.objects.filter(pk=second_mapping.pk).exists())

    def test_export_csv(self):
        MappingVerdict.objects.create(
            mapping=self.m1,
            reviewer_name="Alice",
            verdict="correct",
            reviewer_notes="Looks good",
        )
        response = self.client.get(reverse("crosswalk_review:export_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode("utf-8")
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        self.assertEqual(rows[0][0], "canonical_id")
        self.assertEqual(rows[1][0], "MA-01")
        self.assertEqual(rows[1][11], "Alice")
        self.assertEqual(rows[1][12], "correct")
        self.assertEqual(rows[1][13], "Looks good")

    def test_export_csv_escapes_spreadsheet_formulas(self):
        MappingVerdict.objects.create(
            mapping=self.m1,
            reviewer_name="=HYPERLINK",
            verdict="incorrect",
            reviewer_notes="+SUM(1,1)",
        )
        response = self.client.get(reverse("crosswalk_review:export_csv"))
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"))))
        self.assertEqual(rows[1][11], "'=HYPERLINK")
        self.assertEqual(rows[1][13], "'+SUM(1,1)")


class LoadCrosswalkTests(TestCase):
    def _crosswalk_path(self, data):
        temporary_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False)
        with temporary_file:
            json.dump(data, temporary_file)
        path = Path(temporary_file.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_load_crosswalk_normalizes_nullable_values(self):
        path = self._crosswalk_path(
            {
                "registry": [
                    {
                        "form": {
                            "canonical_id": "TEST-NULLS",
                            "canonical_name": None,
                            "is_efileable": None,
                            "is_form": None,
                            "source_urls": None,
                        },
                        "mappings": [
                            {
                                "court_scope": None,
                                "filing_type": None,
                                "confidence": None,
                                "notes": None,
                            }
                        ],
                    }
                ]
            }
        )

        call_command("load_crosswalk", path=path, verbosity=0)

        form = CrosswalkForm.objects.get(pk="TEST-NULLS")
        mapping = form.mappings.get()
        self.assertEqual(form.canonical_name, "")
        self.assertFalse(form.is_efileable)
        self.assertTrue(form.is_form)
        self.assertEqual(form.source_urls, [])
        self.assertEqual(mapping.filing_type, "")
        self.assertEqual(mapping.court_names, [])
        self.assertIsNone(mapping.confidence)

    def test_bundled_crosswalk_loads_and_renders(self):
        expected_forms = len(json.loads(Path(settings.FORM_CODE_CROSSWALK_PATH).read_text())["registry"])
        call_command("load_crosswalk", stdout=io.StringIO())

        self.assertEqual(CrosswalkForm.objects.count(), expected_forms)
        # Title-identified forms intentionally have no inferred filing route.
        self.assertGreater(CrosswalkMapping.objects.count(), 0)
        first_form = CrosswalkForm.objects.order_by("registry_index").first()
        response = self.client.get(
            reverse("crosswalk_review:review_form", args=[first_form.pk]),
            {"reviewer": "Smoke test"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, first_form.canonical_name)

    def test_load_crosswalk_clear_rolls_back_on_invalid_data(self):
        CrosswalkForm.objects.create(
            canonical_id="EXISTING",
            canonical_name="Existing form",
        )
        path = self._crosswalk_path(
            {
                "registry": [
                    {
                        "form": {"canonical_id": "INVALID", "canonical_name": "Invalid form"},
                        "mappings": [{"confidence": 2}],
                    }
                ]
            }
        )

        with self.assertRaisesMessage(CommandError, "confidence must be between 0 and 1"):
            call_command("load_crosswalk", path=path, clear=True, verbosity=0)

        self.assertTrue(CrosswalkForm.objects.filter(pk="EXISTING").exists())
        self.assertFalse(CrosswalkForm.objects.filter(pk="INVALID").exists())

    def test_load_crosswalk_removes_stale_unreviewed_mappings(self):
        form = CrosswalkForm.objects.create(canonical_id="REFRESH", canonical_name="Refresh form")
        CrosswalkMapping.objects.create(form=form, mapping_index=0, filing_type="Keep")
        stale_mapping = CrosswalkMapping.objects.create(form=form, mapping_index=1, filing_type="Remove")
        path = self._crosswalk_path(
            {
                "registry": [
                    {
                        "form": {"canonical_id": "REFRESH", "canonical_name": "Refresh form"},
                        "mappings": [{"filing_type": "Keep"}],
                    }
                ]
            }
        )

        call_command("load_crosswalk", path=path, stdout=io.StringIO())

        self.assertFalse(CrosswalkMapping.objects.filter(pk=stale_mapping.pk).exists())
        self.assertEqual(form.mappings.count(), 1)

    def test_load_crosswalk_does_not_reassign_existing_verdict(self):
        form = CrosswalkForm.objects.create(canonical_id="REVIEWED", canonical_name="Reviewed form")
        mapping = CrosswalkMapping.objects.create(form=form, mapping_index=0, filing_type="Original")
        MappingVerdict.objects.create(mapping=mapping, reviewer_name="Alice", verdict="correct")
        path = self._crosswalk_path(
            {
                "registry": [
                    {
                        "form": {"canonical_id": "REVIEWED", "canonical_name": "Reviewed form"},
                        "mappings": [{"filing_type": "Replacement"}],
                    }
                ]
            }
        )

        with self.assertRaisesMessage(CommandError, "changed after verdicts were recorded"):
            call_command("load_crosswalk", path=path, stdout=io.StringIO())

        mapping.refresh_from_db()
        self.assertEqual(mapping.filing_type, "Original")
        self.assertEqual(mapping.verdicts.count(), 1)
