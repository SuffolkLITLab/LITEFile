---
id: index
title: Partner & court guide overview
sidebar_label: Overview (WIP)
sidebar_position: 1
---

# Partner & court configuration guide <span className="wip-badge">Work in progress</span>

:::warning Work in progress (WIP)
This section is actively being expanded as new court systems, case types, and partner integrations are brought online. Contact the [Suffolk LIT Lab](mailto:litlab@suffolk.edu) for technical collaboration or pilot deployment inquiries.
:::

LITEFile is engineered from the ground up to be **declarative, customizable, and multi-jurisdictional**. Court administrators, state administrative offices of the courts (AOCs), and legal aid partners (such as Illinois Legal Aid Online) can configure:

- **Court & partner branding**: Official court seals, partner badges, help line phone numbers, and customized terms of service.
- **Dynamic case types & checklists**: Rule-based filing plans that advise filers which documents are needed for their case.
- **Court-specific overrides**: Tailored document rules and clerk phone numbers down to the individual county or division level.
- **AI document extraction prompts**: Customized prompt instructions and deduction hints for state-specific case codes and court nomenclature.

---

## How LITEFile configures jurisdictions

```
efile_app/efile/static/config/
├── README.md                    # Technical documentation
├── base-case-types.yaml         # Base configuration (shared across states)
└── states/
    ├── illinois.yaml            # Complete Illinois court configuration
    ├── massachusetts.yaml       # Massachusetts Trial Court configuration
    └── vermont.yaml             # Vermont Judiciary configuration
```

- **Base configuration (`base-case-types.yaml`)**: Defines common party structures, input widgets, and default field validations.
- **State configuration (`states/{jurisdiction}.yaml`)**: Inherits from base and specifies state court naming conventions, document checklists, filing type mappings, and court contact directories.

---

## Guides in this section

1. [**Jurisdiction & court configuration**](./jurisdiction-config.md): Setting up state metadata, logos, court codes, and clerk contact numbers.
2. [**Document checklists & filing plans**](./document-checklists.md): Authoring plain-language document checklists with requirement levels and role-based conditions.
3. [**Customizing AI extraction & prompts**](./ai-customization.md): Fine-tuning LLM extraction prompts and field dictionaries for court documents.
4. [**Docassemble & AssemblyLine integration**](./interview-integration.md): Connecting automated interview workflows to e-file directly.
