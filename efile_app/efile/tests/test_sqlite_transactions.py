"""File-backed coverage for overlapping local upload/worker transactions."""

import sqlite3
from copy import deepcopy
from unittest.mock import Mock, patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import OperationalError
from django.db.utils import ConnectionHandler


@pytest.mark.django_db(transaction=True)
def test_upload_can_write_after_a_worker_attempts_to_write(tmp_path):
    config = deepcopy(settings.DATABASES["default"])
    if config["ENGINE"] != "django.db.backends.sqlite3":
        pytest.skip("SQLite-specific local configuration")
    config["NAME"] = tmp_path / "concurrent-upload.sqlite3"
    config.setdefault("OPTIONS", {})["timeout"] = 0.05
    upload = ConnectionHandler({"default": config})["default"]
    worker = sqlite3.connect(config["NAME"], timeout=0.05, isolation_level=None)
    try:
        with upload.cursor() as cursor:
            cursor.execute("CREATE TABLE activity (kind TEXT)")
        # Start as Django's outer atomic block does, then read before the
        # document is sent to storage. Another process attempts a write.
        upload.set_autocommit(False, force_begin_transaction_with_broken_autocommit=True)
        with upload.cursor() as cursor:
            cursor.execute("SELECT * FROM activity")
            cursor.fetchall()
        worker.execute("BEGIN")
        worker_waiting = False
        try:
            worker.execute("INSERT INTO activity VALUES ('worker')")
        except sqlite3.OperationalError as error:
            assert "locked" in str(error)
            worker_waiting = True
            worker.rollback()
        # DEFERRED lets the worker reserve the writer above, then raises
        # "database is locked" here instead of waiting, regardless of timeout.
        with upload.cursor() as cursor:
            cursor.execute("INSERT INTO activity VALUES ('upload')")
        upload.commit()
        if worker_waiting:
            worker.execute("INSERT INTO activity VALUES ('worker')")
        worker.commit()
        assert worker.execute("SELECT kind FROM activity ORDER BY kind").fetchall() == [("upload",), ("worker",)]
    finally:
        worker.rollback()
        worker.close()
        upload.close()


def test_extraction_supervisor_retries_sqlite_contention():
    command = "efile.management.commands.process_document_extractions"
    with (
        patch(f"{command}.connection", vendor="sqlite"),
        patch(f"{command}.close_old_connections"),
        patch(f"{command}.call_command"),
        patch(f"{command}.time.sleep", side_effect=[None, KeyboardInterrupt]),
        patch(
            "efile.services.document_extractions.claim_next_extraction",
            side_effect=[OperationalError("database is locked"), None],
        ) as claim,
    ):
        with pytest.raises(KeyboardInterrupt):
            call_command("process_document_extractions", stdout=Mock())
        assert claim.call_count == 2


@pytest.mark.parametrize("once,message", [(True, "database is locked"), (False, "no such table: missing")])
def test_extraction_supervisor_does_not_hide_other_database_failures(once, message):
    command = "efile.management.commands.process_document_extractions"
    with (
        patch(f"{command}.connection", vendor="sqlite"),
        patch(f"{command}.close_old_connections"),
        patch(f"{command}.call_command"),
        patch("efile.services.document_extractions.claim_next_extraction", side_effect=OperationalError(message)),
    ):
        with pytest.raises(OperationalError, match=message):
            call_command("process_document_extractions", once=once, stdout=Mock())
