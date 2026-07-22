from django.test import override_settings

from efile.api.filing_views import rewrite_fallback_filing_components, rewrite_local_document_urls
from efile.utils.s3_upload_handler import S3UploadHandler


def test_local_public_url_uses_current_tunnel_after_restart(tmp_path):
    tunnel_log = tmp_path / "cloudflared.log"
    tunnel_log.write_text(
        "Requesting new quick Tunnel...\n"
        "https://old-tunnel.trycloudflare.com\n"
        "Requesting new quick Tunnel...\n"
        "https://current-tunnel.trycloudflare.com\n",
        encoding="utf-8",
    )

    with override_settings(
        LOCAL_PUBLIC_UPLOAD_TUNNEL_LOG=str(tunnel_log),
        LOCAL_PUBLIC_UPLOAD_WAIT_SECONDS=0,
    ):
        assert (
            S3UploadHandler.get_local_public_url("efile-documents/lead/document.pdf")
            == "https://current-tunnel.trycloudflare.com/api/public-upload/efile-documents/lead/document.pdf"
        )


def test_stale_local_document_url_is_rewritten(tmp_path):
    tunnel_log = tmp_path / "cloudflared.log"
    tunnel_log.write_text(
        "Requesting new quick Tunnel...\nhttps://current-tunnel.trycloudflare.com\n",
        encoding="utf-8",
    )
    efile_data = {
        "al_court_bundle": [
            {
                "data_url": "http://localstack:4566/forms-mvp-xf6361/efile-documents/lead/document.pdf?signature=old"
            }
        ]
    }

    with override_settings(
        LOCAL_PUBLIC_UPLOAD_TUNNEL_LOG=str(tunnel_log),
        LOCAL_PUBLIC_UPLOAD_WAIT_SECONDS=0,
    ):
        rewrite_local_document_urls(efile_data)

    assert efile_data["al_court_bundle"][0]["data_url"] == (
        "https://current-tunnel.trycloudflare.com/api/public-upload/efile-documents/lead/document.pdf"
    )


def test_raw_s3_key_is_rewritten_to_local_public_url(tmp_path):
    tunnel_log = tmp_path / "cloudflared.log"
    tunnel_log.write_text(
        "Requesting new quick Tunnel...\nhttps://current-tunnel.trycloudflare.com\n",
        encoding="utf-8",
    )
    efile_data = {"al_court_bundle": [{"data_url": "efile-documents/lead/document.pdf"}]}

    with override_settings(
        LOCAL_PUBLIC_UPLOAD_TUNNEL_LOG=str(tunnel_log),
        LOCAL_PUBLIC_UPLOAD_WAIT_SECONDS=0,
    ):
        rewrite_local_document_urls(efile_data)

    assert efile_data["al_court_bundle"][0]["data_url"] == (
        "https://current-tunnel.trycloudflare.com/api/public-upload/efile-documents/lead/document.pdf"
    )


def test_stale_quick_tunnel_document_url_is_rewritten(tmp_path):
    tunnel_log = tmp_path / "cloudflared.log"
    tunnel_log.write_text(
        "Requesting new quick Tunnel...\nhttps://current-tunnel.trycloudflare.com\n",
        encoding="utf-8",
    )
    efile_data = {
        "al_court_bundle": [
            {"data_url": "https://old-tunnel.trycloudflare.com/api/public-upload/efile-documents/lead/document.pdf"}
        ]
    }

    with override_settings(
        LOCAL_PUBLIC_UPLOAD_TUNNEL_LOG=str(tunnel_log),
        LOCAL_PUBLIC_UPLOAD_WAIT_SECONDS=0,
    ):
        rewrite_local_document_urls(efile_data)

    assert efile_data["al_court_bundle"][0]["data_url"] == (
        "https://current-tunnel.trycloudflare.com/api/public-upload/efile-documents/lead/document.pdf"
    )


def test_legacy_supporting_label_is_resolved_to_court_code(monkeypatch, settings):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return [{"code": "331", "name": "Lead Document"}, {"code": "332", "name": "Attachments"}]

    monkeypatch.setattr("efile.api.filing_views.requests.get", lambda *args, **kwargs: Response())
    settings.EFSP_URL = "https://efile-test.example"
    efile_data = {
        "al_court_bundle": [{"filing_type": "27965", "filing_component": "supporting"}]
    }

    rewrite_fallback_filing_components(efile_data, "illinois", "adams")

    assert efile_data["al_court_bundle"][0]["filing_component"] == "332"
