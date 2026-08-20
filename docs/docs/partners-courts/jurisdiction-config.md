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
