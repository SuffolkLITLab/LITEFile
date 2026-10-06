"""Portable, indexable expressions for filing catalog updates."""

from django.db.models import CharField, Func


class CourtCode(Func):
    # Literal paths let SQLite match the expression index. Parameterized JSON
    # paths in ordinary court__code lookups cannot use that index.
    function = "JSON_EXTRACT"
    template = "JSON_EXTRACT(%(expressions)s, '$.code')"
    output_field = CharField()

    def as_postgresql(self, compiler, connection, **extra_context):
        return self.as_sql(compiler, connection, template="(%(expressions)s ->> 'code')", **extra_context)
