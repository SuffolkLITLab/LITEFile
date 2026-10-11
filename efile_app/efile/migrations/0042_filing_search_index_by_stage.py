from django.db import migrations

# One GIN index over every path made Postgres fetch each path matching a word in
# every jurisdiction and stage (832,000 rows for "complaint" on staging), then
# discard all but the current index's new- or existing-case paths. A partial
# index per stage drops most of those before any table read, and lets court
# filters combine with the (index, court code) index.


def add_stage_indexes(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        # Staging's role times statements out at two minutes; an index over
        # every Illinois path takes longer to build.
        schema_editor.execute("SET statement_timeout = 0")
        for name, predicate in (
            ("filing_code_search_initial_gin", "initial"),
            ("filing_code_search_existing_gin", "NOT initial"),
        ):
            # A failed concurrent build leaves an invalid index of the same name.
            schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
            schema_editor.execute(
                f"CREATE INDEX CONCURRENTLY {name} ON efile_filingcodepath "
                f"USING GIN (to_tsvector('simple'::regconfig, COALESCE(search_text, ''))) WHERE {predicate}"
            )
        schema_editor.execute("DROP INDEX CONCURRENTLY IF EXISTS filing_code_search_gin")
        schema_editor.execute("RESET statement_timeout")


def remove_stage_indexes(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET statement_timeout = 0")
        schema_editor.execute("DROP INDEX CONCURRENTLY IF EXISTS filing_code_search_gin")
        schema_editor.execute(
            "CREATE INDEX CONCURRENTLY filing_code_search_gin ON efile_filingcodepath "
            "USING GIN (to_tsvector('simple'::regconfig, COALESCE(search_text, '')))"
        )
        for name in ("filing_code_search_initial_gin", "filing_code_search_existing_gin"):
            schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        schema_editor.execute("RESET statement_timeout")


class Migration(migrations.Migration):
    # CONCURRENTLY cannot run in a transaction; it keeps filing searches and
    # index refreshes working while the indexes build.
    atomic = False

    dependencies = [
        ("efile", "0041_provisional_filing_type"),
    ]

    operations = [migrations.RunPython(add_stage_indexes, remove_stage_indexes)]
