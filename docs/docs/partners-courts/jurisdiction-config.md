---
id: jurisdiction-config
title: Configuring jurisdiction-specific features
sidebar_label: Jurisdiction config
sidebar_position: 2
---

# Jurisdiction & court configuration <span className="wip-badge">WIP</span>

All jurisdiction-specific branding, court rules, and document mappings live in single, human-readable YAML files located at `efile_app/efile/static/config/states/{jurisdiction}.yaml`.

---

## 1. High-level jurisdiction metadata

The `jurisdiction` section configures the application title, brand identity, navigation logos, official court statements, and support contact details.

```yaml
# efile_app/efile/static/config/states/illinois.yaml

jurisdiction:
  name: "Illinois eFile"
  code: "illinois"
  display_name: "Illinois"
  brand_name: "LITEFile"
  logo: "img/litefile-logo.svg"
  logo_alt: "LITEFile logo"
  icon: "fas fa-balance-scale"
  svg: "img/IL.svg"
  api_endpoint: "/api/illinois"
  official_court_name: "the Illinois Courts"
  official_tool_statement: "LITEFile is an official, approved electronic filing tool of the Illinois Courts."
  court_logos:
    - name: "Illinois Courts"
      src: "img/court-logo-illinois.svg"
      alt: "Seal of the Supreme Court of Illinois"
  partner_logos:
    - name: "Illinois Legal Aid Online (ILAO)"
      src: "img/logo-ilao.png"
      alt: "Illinois Legal Aid Online logo"
      url: "https://www.illinoislegalaid.org/"
      role: "Project & Funding Partner"
  help_url: "https://www.ilcourthelp.gov/"
  help_number: "833-411-1121"
  contact_email: "litlab@suffolk.edu"
  contact_address: "Suffolk University Law School LIT Lab, 120 Tremont Street, Boston, MA"
```

### Configurable elements:
- `official_tool_statement`: Displayed on the footer and login splash screen to provide court legitimacy.
- `court_logos` & `partner_logos`: Array of logos displayed across the landing page, header, and footer.
- `help_url` & `help_number`: Shown to filers when an error occurs or when a filing is rejected.
- `contact_email` & `contact_address`: Displayed on the Terms of Service and Privacy Policy pages.

---

## 2. Court-specific requirements & clerk contact details

Different courts within the same state often have distinct divisional rules, cover sheet requirements, or clerk contact information. Configure these using `court_specific_requirements`:

```yaml
court_specific_requirements:
  "cook:cd1": # Cook County Circuit Court - County Division
    contact:
      name: "Clerk of the Circuit Court of Cook County - County Division"
      phone: "312-603-5030"
      email: "countydivision@cookcountycourt.com"
      url: "https://www.cookcountyclerkofcourt.org/"
    case_types:
      name_change:
        documents:
          county_division_cover_sheet:
            label: "County Division Cover Sheet"
            requirement: always
            role: supporting
```

:::tip Clerk contact information
When a filing is rejected by a court clerk, LITEFile automatically surfaces the clerk's phone number and email address directly on the filer's status screen so they know who to call for assistance.
:::

---

## 3. Wording that differs by state

Courts do not use the same words for the same thing. The document that opens a case is a *petition* in Illinois and a *complaint* in Vermont, and telling a Vermont filer to look for a petition is wrong information, not a stylistic difference.

The `text` section holds the strings this state says differently. Every key has an English default in `efile_app/efile/utils/ui_text.py`; anything you do not list keeps that default.

```yaml
# efile_app/efile/static/config/states/vermont.yaml

text:
  terms:
    starting_document_example: "complaint"
  about:
    project_partner_description: >-
      LITEFile's Vermont e-filing integration was developed in close partnership
      with Legal Services Vermont (LSV), who collaborated on funding, building,
      and deploying LITEFile to expand accessible electronic court filing for
      self-represented litigants in Vermont.
```

### How keys work

- Keys are nested in YAML and referred to elsewhere with dots: `terms.starting_document_example`.
- Keys under `terms` are short nouns. Each one is also available to every longer string as a placeholder named for its last segment, so changing `starting_document_example` changes every sentence that names it.
- Longer strings can also use `{brand_name}`, `{state_name}`, `{state_code}`, and `{court_name}`, which come from the `jurisdiction` and `state` sections of the same file.

### What is *not* here

Ordinary copy that no state wants to change stays in the templates. Only strings a state might genuinely reword belong in `text`, so the file stays readable and reviewable by the people who own the wording.

:::tip Check your keys
A misspelled key is ignored, which means the page quietly keeps the default wording — the exact wording you were trying to change. `manage.py check` reports any `text` key that does not exist (`efile.W002`), so run it after editing.
:::

### Translation

Strings configured here are translatable along with the rest of the application. `xgettext` cannot read YAML, so `manage.py extract_config_text` restates them in a generated Python file that `makemessages` reads. Each string carries its key as the gettext message context, so one key's Illinois wording and Vermont wording stay separate messages for a translator. See `efile_app/efile/locale/README.md` for the full workflow.
