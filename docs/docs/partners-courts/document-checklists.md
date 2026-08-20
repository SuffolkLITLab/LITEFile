---
id: document-checklists
title: Configuring document checklists & plans
sidebar_label: Document checklists
sidebar_position: 3
---

# Document checklists & filing plans <span className="wip-badge">WIP</span>

Document checklists give self-represented filers clear, plain-language guidance about what documents are required for their specific case type. Checklists are informative guides and do not block a filer from proceeding.

---

## 1. Defining case type matching & guidance

Checklists match against the **human-readable names** returned by the court e-filing system (never hardcoded numeric codes).

```yaml
# efile_app/efile/static/config/states/illinois.yaml

case_types:
  name_change:
    extends: "base_case_types.name_change"

    # Court names returned by the EFSP
    matches:
      names:
        - "Name Change" # Cook County County Division
        - "Change of Name" # Statewide Circuit Courts
      aliases:
        - "Petition - Change of Name"

    # Plain-language explanation for filers
    about:
      summary: >-
        A name change asks a judge to make your new name official. Most of the
        work is paperwork: a request that says who you are and what you want to
        be called, notice in a newspaper so the change is public, and an order
        for the judge to sign.
      learn_more_url: "https://www.illinoislegalaid.org/legal-information/changing-your-name"
      learn_more_label: "Changing your name in Illinois (Illinois Legal Aid Online)"

    documents:
      petition:
        label: "Request for name change"
        requirement: always
        role: lead
        description: "Your name now, the name you want, and how long you have lived in Illinois."
        filing_type_names:
          - "Petition for Name Change"
          - "Petition"
          - "Complaint"

      proposed_order:
        label: "Proposed order for the judge to sign"
        requirement: always
        filing_type_names:
          - "Proposed Order"
          - "Order"
          - "Other Document Not Listed"

      publication_notice:
        label: "Proof of newspaper publication"
        requirement: usually
        description: "Notice published in a local newspaper once a week for three consecutive weeks."
        filing_type_names:
          - "Certificate of Publication"
          - "Affidavit of Publication"
```

---

## 2. Requirement levels

Checklist items are grouped into three clear tiers:

| Requirement level | Displayed as | Meaning |
| :--- | :--- | :--- |
| `always` | **Always needed** | Mandatory document required to open or respond to the matter. |
| `usually` | **Usually needed** | Standard documents expected in the majority of cases of this type. |
| `sometimes` | **Sometimes needed** | Conditional documents required only when specific factual conditions apply. |

---

## 3. Two-sided cases & role-based checklists

In cases with two opposing sides (such as landlord/tenant evictions or domestic relations), the landlord and tenant need completely different documents and instructions.

Configure `filer_roles` to create role-tailored checklists:

```yaml
case_types:
  eviction:
    filer_roles:
      landlord:
        label: "The Landlord (or property owner/agent)"
        description: "You are asking the court to regain possession of the property."
        party_type_keywords: ["plaintiff", "landlord"]
      tenant:
        label: "The Tenant (or occupant)"
        description: "You are defending an eviction or responding to court notice."
        party_type_keywords: ["defendant", "tenant"]

    documents:
      complaint:
        label: "Eviction Complaint"
        requirement: always
        role: lead
        for_roles: ["landlord"] # Only shown to landlords

      appearance:
        label: "Appearance and Answer"
        requirement: always
        for_roles: ["tenant"] # Only shown to tenants

      proof_of_service:
        label: "Proof of Service"
        requirement: usually
        by_role:
          landlord:
            label: "Proof that the tenant was served with court papers"
            description: "Filed by the sheriff or special process server."
          tenant:
            label: "Proof that you sent a copy of your answer to the landlord"
            requirement: always
```
