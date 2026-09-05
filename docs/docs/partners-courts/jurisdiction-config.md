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

### Other-party address rules

An other party's address is optional by default. Add a `party_address` rule only when a court or filing workflow is known to require it. The rule may be placed under `defaults`, under a case type, or directly under a court in `court_specific_requirements`. More specific layers override the default.

```yaml
defaults:
  party_address:
    required: false
    required_for_party_types: []
    required_for_filing_types: []
    required_for_services: []

court_specific_requirements:
  "example:civil":
    party_address:
      required_for_filing_types: ["SUMMONS"]
      required_for_services: ["PERSONAL_SERVICE"]
      reason: "The court needs an address to issue or serve these documents."
```

Set `required: true` when every other party in that layer needs an address. The three `required_for_*` lists may contain a Tyler code or name and are matched without regard to capitalization. A matching party type, filing type, or selected optional service makes the address required. LITEFile also honors an address-required flag from live Tyler party metadata if the code list provides one.

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

---

## 4. The court question

Every filing needs a court, and the e-filing service answers that question with one flat list: 207 courts in Illinois, 170 in Massachusetts. A single dropdown over that list asks a filer to recognize their court among the ones that happen to sort next to it.

`court_selector` replaces the list with the questions your state's court structure is actually made of. Illinois routes by county, Massachusetts by court department plus a place the filer knows, Vermont by Superior Court unit — and each of them narrows the same live court list. A jurisdiction with no `court_selector` section keeps the flat list.

```yaml
court_selector:
  title: "Choose the Vermont court for this filing"
  lede: >-
    Start with the court on your paperwork. Superior Court filings then need a
    division, and most divisions need the court unit the case belongs to.
  steps:
    - id: level
      type: choice
      label: "What Vermont court is this filing for?"
      options:
        - value: superior
          label: "Superior Court"
          help: "Vermont's trial court. You will choose a division next."
          courts:
            name_pattern: "Unit$|^Environmental Division$"
        - value: supreme
          label: "Supreme Court"
          courts:
            name_pattern: "^Supreme Court$"

    - id: unit
      type: select
      when:
        level: [superior]
      label: "Which court unit?"
      placeholder: "Choose a unit…"
      options_from_courts:
        match:
          name_pattern: " Unit$"
        strip: " Unit$"
        label: "{name} ({stem} County)"
```

### How the questions run

An answered question folds to a single line with a **Change** link, and once there is a court, every question folds and the screen states the answer. The court field shares a row with the case category and type, so the cascade has to collapse rather than push them down the page.

Steps are asked in order. A step is shown when its `when:` conditions hold and it has something to ask; the filer's answer narrows the pool of courts, and the deepest answer wins, so "Cook County" is replaced by the division under it. When the pool is down to one court, that is the court. When it is down to a handful, the filer chooses among those rather than among two hundred.

| Key | Meaning |
| --- | --- |
| `type` | `choice` (radio cards), `select` (a dropdown), or `location` (a place lookup). |
| `when` | `{level: [trial]}` shows the step only for those answers; `{department: {not: [land]}}` hides it for those. |
| `options` | Written-out answers. Each may carry a `courts:` query and any data a matcher needs. |
| `options_from_courts` | Answers read off the live court list instead — counties, Cook County's divisions, Vermont's units. A step generated this way disappears when it has fewer than two options, which is how only the counties that divide their Circuit Court get asked about divisions. |
| `option_groups` | One option per `members:` entry, all sharing the group's `courts:` query. Illinois asks which county an appeal came from and answers with its appellate district. |
| `alternative_to` | Two questions that name the same court. Both stay on screen; answering either one answers for both. |
| `short_label` | What the question is called once it is answered and folded to one line, e.g. `Division or courthouse`. Defaults to the full `label`, which is usually too long to read well there. |
| `default_by` / `default_hint` | Start a question at an answer, chosen from an earlier one: `{answer: county, values: {Cook: "cook:cvd"}}` starts a Cook County filing at Municipal Civil. A suggested answer never folds away and carries `default_hint` saying it is a suggestion, so it cannot be mistaken for something the filer said. |

### Naming the courts

E-filing services name courts so that they sort. Massachusetts lists a court as `Juvenile Court -- Suffolk County -- Boston`, department first, because that is how the list is organized — but nobody calls it that, and a filer holding paperwork is looking for the Boston Juvenile Court. `court_names` puts the name back:

```yaml
court_names:
  - match: '^Juvenile Court -+ (?P<county>.+?) -+ (?P<place>.+)$'
    name: "{place} Juvenile Court - {county}"
  - match: '^District Court -+ (?P<place>.+)$'
    name: "{place} District Court"
```

Each rule is a regular expression with named captures, and `name` is the rewrite. The first rule that matches wins; a name no rule matches is already right, so Vermont's `Addison Unit` and Massachusetts' `Middlesex Probate and Family Court` need no rules at all.

The rewrite happens once, when the court list is read, so everything downstream — the questions, the court finally chosen, and what is saved on the filing — uses the readable name. That includes the `courts:` queries below, so write them against the names as they read, not as the service lists them.

### Court queries

A `courts:` query says which courts an answer leads to. Every rule is optional and they combine with "and":

| Rule | Matches |
| --- | --- |
| `codes` | Exact court codes, in the order given. |
| `code_prefix`, `code_pattern` | The court's code starts with, or matches, this. |
| `name_pattern` | The court's name matches this (case-insensitive). |
| `exclude_code_pattern`, `exclude_name_pattern` | Drop the courts these match. |
| `group` | The court belongs to this group — see `group_by` below. |

Courts that are only a heading over the courts beneath them never reach the questions at all. "Cook County" is such a row: every Cook filing goes to one of the eighty locations whose code hangs off it, and choosing the county itself returns an empty case-category list with nothing to explain why. A court is dropped only when the e-filing service leaves it out of its fileable list **and** other courts hang off its code — Cook County - Chancery fails the second test, has locations under it, and takes filings of its own. A caption that names only such a county still routes: the questions it does settle are filled in, and `default_by` can start the rest somewhere sensible.

Prefer `name_pattern`. Court **names** are stable and readable; Tyler's codes differ from court to court and change without notice. `{value}`, and any earlier step's id, can be used as a placeholder inside a query.

`option_group_pattern` groups a dropdown under headings. It is matched against each court's name (after `strip`), and its named captures say which part is which: `group` is the heading, `label` is what to show under it, and `extra` is anything worth adding only when it is not the heading's own place. Cook County lists more than eighty locations, and reading them as one alphabetical run is what made the old dropdown unusable.

```yaml
        option_group_pattern: '^(?P<label>.*?)\s+-\s+(?P<group>District \d+)\b(?:\s+-\s+(?P<extra>.*))?$'
        option_group_names:
          - "District 1 - Chicago"
          - "District 2 - Skokie"
        option_group_other: "No courthouse given"
```

`option_group_names` gives each heading its full name and, by the order they are written in, the order they are shown in. That is how the Chicago courts come first in Cook County, where most of its filings go, rather than wherever the alphabet puts them; `option_group_other` heads the courts the pattern found no heading for, and they come last. Without `option_group_names`, headings are taken from the pattern itself and sorted, and a heading over a single court is dropped so that court keeps its full name.

`group_by` on the selector itself is a regular expression whose first capture is the group a court belongs to. Illinois needs one because it names its counties' courts every which way — `Adams County`, `Kankakee - Civil`, `Peoria CR`, `St. Clair County-Backlog` — and they all have to land in one county.

### Asking for a place instead of a county

A `location` step hands what the filer types to a matcher:

```yaml
    - id: place
      type: location
      when:
        level: [trial]
        department:
          not: [land]
      label: "Where is the case connected to?"
      placeholder: "Town, city, or street address"
      button_label: "Find courts"
      examples: ["Cambridge", "Somerville", "24 Beacon St, Boston"]
      matcher: macourts
      court_types_from: department
      manual_label: "Or choose your court from the list"
```

`matcher:` names the library that answers the question. `macourts` uses [MACourts](https://github.com/SuffolkLITLab/MACourts), which owns the Massachusetts court records and jurisdiction rules; `vtcourts` uses [VTCourts](https://github.com/SuffolkLITLab/VTCourts), which resolves a Vermont town, county, or ZIP to its Superior Court unit. `court_types_from` names the step whose chosen option carries the `court_types:` the matcher should search, where a matcher needs one. Matches are mapped back onto the e-filing service's own courts — by code where the source carries one, by name otherwise — and a court this environment does not carry is dropped rather than offered.

Massachusetts asks this way because its Trial Court departments do not divide the state the same way: the District Court that serves Somerville is not in the county its Probate and Family Court is, and which Boston Municipal Court division serves an address is a question about which side of a ward line the building is on. A filer knows their town. Asking them for a county produces a confident wrong answer.

The lookup is always an alternative, never a requirement, and there are two ways to say so. Massachusetts sets `manual_label`, which puts the department's full court list beside the lookup for a filer who already knows their court and for a place the rules cannot resolve. Vermont instead marks its lookup `alternative_to: unit`: the unit dropdown stays where it is, and the lookup is the way in for a filer who knows their town but not that the town is in the Washington Unit. Answering either one answers for both.

`no_match_hint` is what the screen says when the lookup finds nothing — worth wording per jurisdiction, since it should point at whichever alternative that state actually offers.

A cross-county ZIP, or two courts with overlapping jurisdiction, come back as a short list to confirm rather than as a guess between them.

:::tip Check your patterns against the live list
The court names a pattern has to match are the ones the e-filing service returns, and they need no authentication to read: `curl "https://efile-test.suffolklitlab.org/jurisdictions/vermont/codes/courts?with_names=true"`.
:::
