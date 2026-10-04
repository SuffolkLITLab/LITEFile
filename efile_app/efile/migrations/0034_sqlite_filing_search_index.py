"""Give local SQLite searches the same indexed token lookup as PostgreSQL."""

from django.db import migrations


def add_sqlite_search_index(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    # Tokens are already normalized, stemmed and expanded by the application.
    # Store postings only: the path table remains the source of document data.
    # No positional data is needed for our AND-of-whole-token queries. Retain
    # columns so jurisdiction and new/existing-case filters use postings too.
    schema_editor.execute(
        "CREATE VIRTUAL TABLE filing_code_search_fts USING fts5("
        "search_text, index_id, initial, content='efile_filingcodepath', content_rowid='id', "
        "tokenize='ascii', detail='column', columnsize=0)"
    )
    schema_editor.execute(
        "CREATE TRIGGER filing_code_search_insert AFTER INSERT ON efile_filingcodepath BEGIN "
        "INSERT INTO filing_code_search_fts(rowid, search_text, index_id, initial) "
        "VALUES (new.id, new.search_text, new.index_id, new.initial); END"
    )
    schema_editor.execute(
        "CREATE TRIGGER filing_code_search_delete AFTER DELETE ON efile_filingcodepath BEGIN "
        "INSERT INTO filing_code_search_fts(filing_code_search_fts, rowid, search_text, index_id, initial) "
        "VALUES ('delete', old.id, old.search_text, old.index_id, old.initial); END"
    )
    schema_editor.execute(
        "CREATE TRIGGER filing_code_search_update AFTER UPDATE OF id, search_text, index_id, initial "
        "ON efile_filingcodepath BEGIN "
        "INSERT INTO filing_code_search_fts(filing_code_search_fts, rowid, search_text, index_id, initial) "
        "VALUES ('delete', old.id, old.search_text, old.index_id, old.initial); "
        "INSERT INTO filing_code_search_fts(rowid, search_text, index_id, initial) "
        "VALUES (new.id, new.search_text, new.index_id, new.initial); END"
    )
    # Triggers maintain future changes; existing installations also need their
    # already-downloaded catalog indexed. No court API calls are necessary.
    schema_editor.execute("INSERT INTO filing_code_search_fts(filing_code_search_fts) VALUES ('rebuild')")


def remove_sqlite_search_index(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return
    for name in ("insert", "delete", "update"):
        schema_editor.execute(f"DROP TRIGGER filing_code_search_{name}")
    schema_editor.execute("DROP TABLE filing_code_search_fts")


class Migration(migrations.Migration):
    dependencies = [("efile", "0033_filing_code_search")]
    operations = [migrations.RunPython(add_sqlite_search_index, remove_sqlite_search_index)]
