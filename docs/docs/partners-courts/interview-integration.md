---
id: interview-integration
title: Integration with guided interviews & Docassemble
sidebar_label: Guided interview integration
sidebar_position: 5
---

# Guided interview & Docassemble integration <span className="wip-badge">WIP</span>

LITEFile pairs naturally with guided interview engines like the [Document Assembly Line](https://assemblyline.suffolklitlab.org) and [Docassemble](https://docassemble.org) to provide an end-to-end access to justice pipeline:

```
Pro Se User → Guided Interview Form Prep → PDF Generated → LITEFile Pre-fill & Upload → EFSP E-Filing → Court Review
```

---

## 1. Handoff architecture

When a user completes a guided interview on a Docassemble or AssemblyLine server, the interview can package the resulting PDF files and redirect the user directly to LITEFile with pre-populated session variables.

### Key integration points:
1. **Direct PDF delivery via S3**: The interview uploads generated PDFs directly to the secure S3 bucket with temporary pre-signed keys.
2. **Session pre-fill API**: The interview transmits initial metadata (jurisdiction, court code, case category, party names) to LITEFile's session API.
3. **Seamless authentication**: If single sign-on is enabled between platforms, the user transitions straight into the review and submission steps.

---

## 2. Roadmap & standards

The LIT Lab is actively developing standardized data schemas for guided interview to e-filing handoffs based on the **Electronic Court Filing (ECF) 5.0** standard and the **Legal XML** working group specifications.

For technical inquiries or to participate in integration testing, contact the [Suffolk LIT Lab](mailto:litlab@suffolk.edu).
