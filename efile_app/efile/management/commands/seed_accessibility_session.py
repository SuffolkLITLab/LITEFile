"""Create deterministic, local-only data for browser accessibility checks."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.test import Client

from efile.models import FilingDocument, FilingDraft, FilingParty, FilingPlan
from efile.services.current_drafts import CURRENT_DRAFT_SESSION_KEY
from efile.workflow import ExistingCase, WorkflowStepKey


class Command(BaseCommand):
    help = "Seed a local browser session for the Axe accessibility suite."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True, help="Path for Playwright storage state JSON.")
        parser.add_argument("--origin", default="http://127.0.0.1:8000", help="Origin served to Playwright.")

    def handle(self, *args, **options):
        user_model = settings.AUTH_USER_MODEL
        from django.apps import apps

        user_class = apps.get_model(user_model)
        user, _ = user_class.objects.update_or_create(
            username="accessibility-checker",
            defaults={
                "email": "accessibility-checker@example.com",
                "tyler_jurisdiction": "illinois",
                "tyler_username": "accessibility-checker@example.com",
                "first_name": "Avery",
                "last_name": "Checker",
            },
        )
        user.set_unusable_password()
        user.save()

        FilingDraft.objects.filter(user=user).delete()
        FilingPlan.objects.filter(user=user).delete()
        plan = FilingPlan.objects.create(user=user, jurisdiction="illinois", title="Accessibility test filing")
        draft = FilingDraft.objects.create(
            user=user,
            plan=plan,
            jurisdiction="illinois",
            workflow_version=2,
            existing_case=ExistingCase.NEW,
            current_step=WorkflowStepKey.REVIEW,
            court_code="cook:cvd1",
            court_name="Cook County",
            case_category_code="6198",
            case_category_name="Small Claims",
            case_type_code="183541",
            case_type_name="Contract",
            filing_type_code="143132",
            filing_type_name="Complaint",
            document_checklist_acknowledged=True,
            selected_payment_account_id="a11y-payment-account",
            selected_payment_account_name="Accessibility payment account",
            quoted_fee_total="0.00",
        )
        FilingDocument.objects.create(
            draft=draft,
            role=FilingDocument.Role.LEAD,
            name="Accessibility complaint.pdf",
            original_filename="Accessibility complaint.pdf",
            filing_type_code="143132",
            filing_type_name="Complaint",
            document_type_code="public",
            document_type_name="Public",
        )
        FilingParty.objects.create(
            draft=draft,
            role="filer",
            sort_order=0,
            first_name="Avery",
            last_name="Checker",
            address_line_1="100 Main Street",
            city="Chicago",
            state="IL",
            zip_code="60601",
            email=user.email,
            party_type="plaintiff",
            party_type_name="Plaintiff",
            is_filing_party=True,
        )
        other_party = FilingParty.objects.create(
            draft=draft,
            role="other",
            sort_order=1,
            first_name="Jordan",
            last_name="Example",
        )

        # Let Django's own test client construct the authenticated session. This
        # tracks framework changes to session-auth details without duplicating
        # private authentication keys in this browser-only fixture command.
        client = Client()
        client.force_login(user)
        session = client.session
        session[CURRENT_DRAFT_SESSION_KEY] = draft.pk
        session["jurisdiction"] = "illinois"
        session["auth_tokens"] = {"TYLER-TOKEN-ILLINOIS": "accessibility-test-token"}
        session.save()

        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "cookies": [
                        {
                            "name": settings.SESSION_COOKIE_NAME,
                            "value": session.session_key,
                            "domain": "127.0.0.1",
                            "path": "/",
                            "expires": -1,
                            "httpOnly": True,
                            "secure": False,
                            "sameSite": "Lax",
                        }
                    ],
                    "origins": [],
                },
                indent=2,
            )
        )
        self.stdout.write(self.style.SUCCESS(f"Seeded accessibility session for party {other_party.pk}."))
