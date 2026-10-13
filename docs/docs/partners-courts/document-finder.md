---
id: document-finder
title: Configuring the document finder
sidebar_label: Document finder
sidebar_position: 4
---

# Document finder <span className="wip-badge">WIP</span>

The document finder helps a filer who does not know yet which documents they
need. They describe what they want to do in their own words — *change my name*,
*respond to a small claims case* — and LITEFile shows the documents filings like
that often include, plus links to guided interviews, official blank forms, and
help pages.

Filers reach it from the **Upload documents** step ("Not sure which documents you
need?"), from the start page, or directly at
`/jurisdiction/<state>/find-documents/`. It works without signing in, and a
filer who opens it from Upload can go back to the same draft.

The finder is a small, static index. Each entry, called an *intent*, points at a
checklist you have already written in `case_types` or `case_categories` (see
[Document checklists](./document-checklists.md)). It never has its own list of
documents, so the finder and the filer's plan always agree.

---

## 1. Adding an intent

Intents live in the `document_finder` section of the state file:

```yaml
# efile_app/efile/static/config/states/illinois.yaml
document_finder:
  links_checked_on: "2026-10-13"
  intents:
    respond_to_an_eviction:          # used in the page address
      title: "Respond to an eviction"
      summary: "Your landlord has started a case to make you leave, and you want to take part."
      keywords: [evicted, kicked out, landlord wants me to leave]
      filing_path: existing          # new | existing
      checklist:
        case_type: eviction          # or case_category: small_claims
      filer_role: tenant             # required when the case type has filer_roles
```

| Key | What it does |
| --- | --- |
| `title` | What the filer sees in the results. Write it as something a person would say. |
| `summary` | One sentence that helps a filer tell similar intents apart. |
| `keywords` | Extra words and phrases to search by. See [Search keywords](#2-search-keywords). |
| `filing_path` | `new` if this filing starts a case, `existing` if it goes into one. Shown as a label, used as a search filter, and carried into a new filing. |
| `checklist` | The `case_types` or `case_categories` key whose checklist to show. |
| `filer_role` | Which side of the case, for case types that declare `filer_roles`. Without it, a two-sided case shows no list. |
| `lead_filing_type_name` | Optional. Shows the items whose `when.lead_filing_type_names` match, such as the extra items for a child's name change. |

Statewide items are shown, and items a court adds in
`court_specific_requirements` are listed separately under "Some courts also ask
for", because the filer has not chosen a court yet.

## 2. Search keywords

A search lists an intent when one of the filer's words appears in its title, its
keywords, or the court's own case type names (`matches.names`) — or when every
word appears somewhere on it, including its document labels. Several matches are
all shown, best first; the filer chooses.

Searches ignore case, word endings (*evicted* finds *eviction*), and common words
such as *my*, *case*, and *court*. The synonym groups in
`efile/data/filing_code_search.yaml` (`concepts`) also apply, so *summary
process* and *eviction* are treated alike.

Good keywords are the words filers actually use: *kicked out*, *being sued*,
*security deposit*. Avoid words that fit many intents, such as *motion*.

## 3. Interview, form, and help links

Links go in `resources` for the intent as a whole, or in `document_resources`
keyed by the checklist item ID for one document:

```yaml
      resources:
        - kind: interview
          label: "Respond to an eviction (Easy Form)"
          source: "Illinois Legal Aid Online"
          url: "https://www.illinoislegalaid.org/legal-information/respond-eviction"
      document_resources:
        appearance:
          - kind: form
            label: "Appearance"
            source: "Illinois Courts"
            url: "https://ilcourtsaudio.blob.core.windows.net/.../AP%20Appearance.pdf"
```

`kind` is one of:

- `interview` — a guided interview that helps fill in the forms. Shown first and
  labelled **Guided interview**.
- `form` — an official blank or fillable form, labelled **Blank form**.
- `instructions` — official instructions for completing the forms.
- `help` — a court or legal-help page about this kind of case.

Rules:

- Only add links a partner has reviewed. Never guess an address.
- Links must start with `https://`. Others are dropped and logged. Write spaces
  in an address as `%20`.
- Every link opens in a new tab. The page tells filers that these sites do not
  file anything for them.
- Use YAML anchors (`&fee_waiver_resources` / `*fee_waiver_resources`) to reuse
  the same links across intents.

## 4. Keeping links current

Court PDF addresses change when a form is revised. Check every link with:

```bash
cd efile_app
uv run python manage.py check_document_finder_links
```

It lists each link that does not open and exits with an error if any fail.
Update `links_checked_on` when you have checked them.

## 5. What the finder does not do

- It does not choose a court, case type, or filing type. "Start this filing"
  starts an ordinary filing that only knows whether it starts a case or joins
  one. Codes are still chosen against the court's live lists.
- It does not make a checklist item required. The list stays a guide.
- A state with no `document_finder` section shows a short "no guides yet" page
  with the state's court-help contact, and the Upload step does not link to it.
