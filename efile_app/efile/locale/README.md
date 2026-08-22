# Translations

Compiled message catalogs go here, one directory per language
(`locale/es/LC_MESSAGES/django.po`). The directory is empty on purpose: LITEFile
ships English only today, and this is the plumbing that makes a second language
a translation job rather than a code change.

## Where user-facing copy lives

| Kind of string | Where it lives | Picked up by |
| --- | --- | --- |
| Ordinary UI copy | `{% translate %}` / `{% blocktranslate %}` in the template, `gettext` in Python | `makemessages` reads templates and Python directly |
| Copy a state may reword | `UI_STRINGS` in `efile/utils/ui_text.py`, rendered with `{% ui_text "key" %}` | `makemessages`, from the defaults in that file |
| A state's actual rewording | The `text:` section of `efile/static/config/states/<state>.yaml` | `manage.py extract_config_text`, then `makemessages` |

The third row is the reason for the extra step. `xgettext` cannot read YAML, so
the Vermont partner paragraph would be missing from the catalog and would fall
back to English on an otherwise translated page. `extract_config_text` restates
those strings as `pgettext_lazy` calls in the generated
`efile/config_text_strings.py`, which `makemessages` then reads like any other
source file.

Each string is extracted with its UI text key as the gettext message *context*,
so the Illinois wording and the Vermont wording of one key stay two separate
messages that a translator can tell apart.

## Adding a language

`gettext` must be installed (`apt install gettext`, `brew install gettext`).

```bash
cd efile_app
uv run python manage.py extract_config_text     # config copy -> Python stub
uv run python manage.py makemessages -l es      # write locale/es/LC_MESSAGES/django.po
# translate the .po file
uv run python manage.py compilemessages         # write the .mo files Django reads
```

Then add the language to `LANGUAGES` in `efile/settings_base.py`.
`LocaleMiddleware` is already in the middleware stack, so once a language is
listed and compiled, a filer whose browser asks for it gets it.

## Keeping the catalog honest

`manage.py extract_config_text --check` fails if a `text:` section changed
without the stub being regenerated. A system check (`efile.W002`) reports any
`text:` key in a state file that does not match a key in `UI_STRINGS`, which is
how a typo in configured copy gets noticed instead of silently reverting the
page to its default wording.
