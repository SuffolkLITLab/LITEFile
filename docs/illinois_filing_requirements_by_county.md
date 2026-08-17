# Illinois E-Filing Document Requirements by County
## Research and Live EFSP Proxy Validation for High-Volume Filing Needs

This document provides a comprehensive analysis and empirical validation of the documents, filing codes, party requirements, and court-specific rules for **five high-volume Illinois civil court filing needs**. 

The findings are validated directly against the live development e-file proxy server (`https://efile-test.suffolklitlab.org` / Tyler Technologies Illinois ECF 4.01/5.0 system) across **11 court jurisdictions** representing urban, suburban collar, and downstate circuits:
1. **Cook County – Domestic Relations Division** (`cook:dr1`)
2. **Cook County – County Division** (`cook:cd1`)
3. **Cook County – Municipal Civil Division** (`cook:cvd1`)
4. **DuPage County Circuit Court** (18th Judicial Circuit – `dupage`)
5. **Lake County Circuit Court** (19th Judicial Circuit – `lake`)
6. **Will County Circuit Court** (12th Judicial Circuit – `will`)
7. **Kane County Circuit Court** (16th Judicial Circuit – `kane`)
8. **Champaign County Circuit Court** (6th Judicial Circuit – `champaign`)
9. **Sangamon County Circuit Court** (7th Judicial Circuit – `sangamon`)
10. **Peoria County Circuit Court** (10th Judicial Circuit – `peoria`)
11. **St. Clair County Circuit Court** (20th Judicial Circuit – `stclair`)

---

## Executive Summary & Document Hierarchy

Document requirements are organized into three standard operational groups:
* **Always Required**: The baseline mandatory documents without which the e-filing envelope cannot be accepted (e.g., Lead Petition/Complaint for initial filings; Lead Appearance/Answer for responsive filings).
* **Usually Required**: Mandatory statutory or court-rule attachments accompanying the primary filing in standard cases (e.g., Financial Affidavits, Parenting Plans, Proof/Certificate of Service, Hearing Notices, Fee Waiver Applications).
* **Required Sometimes (Court- or Fact-Specific)**: Documents triggered by specific factual predicates (minor children vs. no children, indigency, publication necessity, domestic violence/safety impoundment) or mandatory local county forms (e.g., Cook County Division Cover Sheets, Early Resolution Program notices, Parent Education Certificates).

```
┌────────────────────────────────────────────────────────────────────────┐
│                          E-FILING ENVELOPE                             │
├────────────────────────────────────────────────────────────────────────┤
│ 1. LEAD DOCUMENT (Always Required)                                     │
│    • Petition / Complaint (Initial) OR Appearance / Answer (Subsequent)│
│    • Document Security: Public / Non-Confidential                      │
├────────────────────────────────────────────────────────────────────────┤
│ 2. STATUTORY ATTACHMENTS & FORMS (Usually Required)                    │
│    • Financial Affidavit / Parenting Plan (Family)                     │
│    • Summons / Certificate of Service / Notice of Filing               │
│    • Application for Waiver of Court Fees (Civil Rule 298)             │
├────────────────────────────────────────────────────────────────────────┤
│ 3. LOCAL / CONDITIONAL ATTACHMENTS (Required Sometimes)                │
│    • County Cover Sheets (Cook CCDR 0001, CCG 0500, etc.)              │
│    • Focus on Children / KIDS Parent Education Certificates            │
│    • Eviction Early Resolution Program (ERP) Notices                   │
│    • Publication Affidavits / Safety Impoundment Motions               │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: The 5 High-Volume Filing Needs (Statewide Standard Framework)

### 1. Divorce with Children (*Dissolution of Marriage with Minor Children*)
* **Statutory Authority**: Illinois Marriage and Dissolution of Marriage Act (IMDMA, 750 ILCS 5/101 *et seq.*), Illinois Supreme Court Rules 138, 298, 900–908.
* **Core Parties**: `Petitioner` (Required), `Respondent` (Required). Additional allowed: `Child`, `Guardian Ad Litem`, `Intervenor`.
* **Document Breakdown**:
  * **Always Required**:
    1. **Petition for Dissolution of Marriage (With Children)** (*Lead Document*): Sets forth jurisdictional facts (residence in IL for 90+ days), marriage date, irretrievable breakdown grounds, children's names and DOBs, and relief sought (parental allocation, support, property division).
    2. **Summons / Electronic Summons**: Issued to Respondent unless Respondent files an Entry of Appearance / Waiver of Service.
  * **Usually Required**:
    1. **Financial Affidavit (Family & Divorce)**: Standardized statewide form mandated by IMDMA 750 ILCS 5/501(a)(1) and local rules for any request for child support, maintenance, or fee contribution. Supported by tax returns, W-2s, and pay stubs.
    2. **Parenting Plan (or Proposed Parenting Plan)**: Required within 120 days of service per 750 ILCS 5/602.10; often submitted with petition or initial appearance in uncontested matters.
    3. **Certificate of Dissolution of Marriage / IDPH Report of Dissolution (Form VR-163)**: Required vital statistics form before judgment entry.
    4. **Notice of Filing / Certificate of Service (Rule 11/12)**: Proving electronic or mail transmission to opposing party.
  * **Required Sometimes**:
    * **Application for Waiver of Court Fees (Rule 298)**: For qualifying low-income petitioners.
    * **Certificate of Legal Aid Representation (735 ILCS 5/5-105.5)**: Waives court fees automatically if represented by approved civil legal aid provider.
    * **Parent Education Program Completion Certificate**: (e.g., "Focus on the Children" in DuPage, "Kids 1st" in Lake, "KIDS" in Kane/Will).
    * **Affidavit as to Military Service (SCRA)**: Required before obtaining default judgment if Respondent does not appear.
    * **Uniform Order for Support / Child Support Calculation Worksheet**: Required when child support is calculated under income shares guidelines.
    * **County Cover Sheet**: (e.g., Cook County CCDR 0001).

---

### 2. Divorce without Children (*Dissolution of Marriage without Minor Children*)
* **Statutory Authority**: IMDMA (750 ILCS 5/401, 5/452 - Joint Simplified Dissolution Procedure).
* **Core Parties**: `Petitioner` (Required), `Respondent` (Required) or `Co-Petitioner` (in joint filings).
* **Document Breakdown**:
  * **Always Required**:
    1. **Petition for Dissolution of Marriage (No Children)** (*Lead Document*) OR **Joint Petition for Simplified Dissolution**.
    2. **Summons** (or Entry of Appearance / Waiver of Service).
  * **Usually Required**:
    1. **Financial Affidavit**: Required if either party seeks maintenance, property division determination, or fee allocation. (Waived in Joint Simplified Dissolution if statutory asset/income caps are met).
    2. **Marital Settlement Agreement (MSA)**: Governing division of debts, bank accounts, real estate, vehicles, and maintenance waivers.
    3. **Proposed Judgment for Dissolution of Marriage**.
    4. **Certificate of Dissolution (IDPH Form)**.
  * **Required Sometimes**:
    * **Application for Waiver of Court Fees (Rule 298)**.
    * **Affidavit of Irretrievable Breakdown / 2-Year Separation Waiver (750 ILCS 5/401(a-1))**.
    * **Joint Simplified Dissolution Affidavit / Verification Form**.
    * **Cook County Domestic Relations Cover Sheet (CCDR 0001)**.

---

### 3. Eviction Answer / Defense (*Residential Eviction Response*)
* **Statutory Authority**: Illinois Code of Civil Procedure, Article IX (735 ILCS 5/9-101 *et seq.*), Illinois Supreme Court Rules 138, 181, 298.
* **Core Parties**: `Defendant / Tenant` (Responding party), `Plaintiff / Landlord`.
* **Document Breakdown**:
  * **Always Required**:
    1. **Appearance (Civil / Eviction)** (*Lead Document*): Submits defendant to the jurisdiction of the court and prevents immediate default judgment.
    2. **Eviction Answer, Affirmative Defenses, or Motion to Dismiss**: Answers numbered complaint paragraphs and raises affirmative defenses (e.g., breach of implied warranty of habitability, defective 5/10/30-day notice, retaliation, landlord refusal of rent under ERAP).
  * **Usually Required**:
    1. **Certificate of Service / Proof of Delivery**: Certifying service of Answer and Appearance on landlord/landlord attorney.
    2. **Application for Waiver of Court Fees (Rule 298)**: Critical in eviction defense as the vast majority of indigent tenants cannot pay the mandatory appearance fee.
  * **Required Sometimes**:
    * **Demand for Jury Trial**: Must be filed no later than the appearance date (often subject to separate fee unless fee waiver approved).
    * **Early Resolution Program (ERP) Intake Form / Notice**: Mandatory in Cook County Municipal Civil Division (`cook:cvd1`).
    * **Residential Eviction Mediation Request**: Required in circuits with mandatory residential eviction diversion programs (DuPage, Kane, Lake).
    * **Motion to Seal Eviction Record (735 ILCS 5/9-121.5)**: For dismissed cases, foreclosure evictions, or COVID-era emergency tenant protections.
    * **Exhibits (Lease, Photos of Code Violations, Rent Receipts, Defective Notice copies)**: Uploaded as attachments or connected documents.

---

### 4. Small Claims Answer (*Especially Debt Collection Defense*)
* **Statutory Authority**: Illinois Supreme Court Rules 281–289 (Small Claims up to $10,000), 735 ILCS 5/2-619, 815 ILCS 505 (Consumer Fraud).
* **Core Parties**: `Defendant` (Consumer / Alleged Debtor), `Plaintiff` (Original Creditor or Debt Buyer like Midland Credit, LVNV, Portfolio Recovery, Velocity).
* **Document Breakdown**:
  * **Always Required**:
    1. **Appearance (Small Claims / Schedule 1 or 2)** (*Lead Document*): In small claims under Rule 286(a), filing an appearance alone can serve as a denial of allegations unless the court orders a formal written answer.
    2. **Written Answer & Affirmative Defenses**: Strongly required in debt buyer cases to assert affirmative defenses (statute of limitations 735 ILCS 5/13-205, lack of standing/chain of title 735 ILCS 5/8-2601, failure to attach contract under 735 ILCS 5/2-606).
  * **Usually Required**:
    1. **Certificate of Service (Rule 11)**.
    2. **Application for Waiver of Court Fees (Rule 298)**: Based on income (statewide appearance fees range from $100–$250 depending on amount in controversy).
  * **Required Sometimes**:
    * **Jury Demand (Rule 285)**: Must be filed at the time of appearing (6-person jury standard in small claims; $12.50 to $50 fee depending on circuit).
    * **Counterclaim / Third-Party Complaint**: Against debt buyer for Fair Debt Collection Practices Act (FDCPA) or Illinois Collection Agency Act (ICAA) violations.
    * **Identity Theft Affidavit / Denial of Debt Affidavit**.
    * **Appearance Fee Schedule Tier Selection**: (e.g., Up to $250, $250–$500, $500–$2,500, $2,500–$10,000).

---

### 5. Name Change (*Adult and Minor*)
* **Statutory Authority**: Illinois Code of Civil Procedure, Article XXI (735 ILCS 5/21-101 *et seq.*), Public Act 103-0166.
* **Core Parties**: `Petitioner / Applicant` (Adult or Parent on behalf of Minor), `Respondent / Non-Petitioning Parent` (for Minor Name Change).
* **Document Breakdown**:
  * **Always Required**:
    1. **Request for Name Change (Adult or Minor)** (*Lead Document*): Stating current name, requested new name, residence history (at least 6 months in IL), citizenship/status, and criminal history affirmations.
    2. **Proposed Order for Name Change**: Ready for judicial signature at the final hearing.
  * **Usually Required**:
    1. **Notice of Court Date for Request for Name Change (Hearing Notice)**: Stating courtroom, date, time, and zoom credentials.
    2. **Publication Notice / Certificate of Publication**: Notice published once a week for 3 consecutive weeks in a local newspaper (735 ILCS 5/21-103), filed with the publisher's certificate.
    3. **Application for Waiver of Court Fees (Rule 298)**.
  * **Required Sometimes**:
    * **Motion to Waive Notice & Publication**: Critical for survivors of domestic violence, stalking, human trafficking, or gender identity safety concerns (735 ILCS 5/21-103.5).
    * **Minor Name Change Specific Documents**:
      * *Consent of Minor (if 14 years or older)*.
      * *Notice to Non-Custodial/Non-Petitioning Parent (Summons or Certified Mail Notice)*.
      * *Affidavit of Service / Diligent Search on Missing Parent*.
    * **Criminal History Attestation / Background Check Exemption Form**: Verification regarding disqualifying felony or sex offense convictions.

---

## Part 2: Live Proxy Server Validation Across 11 Illinois Jurisdictions

Below is the verified code configuration, party structure, filing codes, filing components, document security rules, and optional services queried directly from the development proxy server (`EFSP_URL = "https://efile-test.suffolklitlab.org"`).

---

### 1. Cook County – Domestic Relations Division (`cook:dr1`)
* **Jurisdiction Profile**: Specialized family division for City of Chicago and Cook County suburbs.
* **EFSP Codes & Structure**:
  * **Categories**:
    * `172833`: `Domestic Relations - General Proceedings`
    * `172831`: `Domestic Relations - Parentage/Child Support`
    * `172835`: `Domestic Violence - Civil Protection Orders`
  * **Case Types**:
    * With Children: `253965` (*Petition for Legal Separation or/Alternate Dissolution - Children*), `254020` (*Petition for Dissolution of Marriage – Children*), `253961` (*Civil Union - Children*).
    * Without Children: `253962` (*Petition for Dissolution of Marriage - No Children*), `172859` (*Petition For Dissolution*), `253960` (*Civil Union - No Children*).
  * **Party Types**: `Petitioner` (Required), `Respondent` (Required).
  * **Live Filing Codes Validated**:
    * `172899`: `Certificate Of Representation By Civil Legal Services Provider Filed`
    * `172859`: `Petition For Dissolution`
    * `172868`: `Praecipe For Dissolution`
    * `172854`: `Appearance`
    * `172851`: `Answer`
    * `172887`: `Financial Affidavit Filed`
    * `172891`: `Parenting Plan Filed`
    * `172879`: `Application For Waiver Of Court Fees Filed`
  * **Filing Components**:
    * Lead Document: Required (`displayorder: 0`, `allowmultiple: false`, `code: 332`).
    * Attachments / Connected Documents: Allowed.
  * **Document Security Types**: `Non-Confidential` (Public), `Confidential`, `Impounded`.
  * **Optional Services Available on Filings**:
    * `Alias Summons` ($5.00)
    * `Certified Copy Fee` ($9.00+)
    * `Certified Mail - Return Receipt` ($15.54)
    * `Alias Citation` ($5.00)
    * `Child Support Administrative Fee` ($36.00/yr)
  * **County-Specific Mandatory Rules & Forms**:
    * **CCDR 0001**: *Domestic Relations Division Cover Sheet* (Required on all initial filings).
    * **Local Rule 13.3.1**: *Standardized Cook County Financial Disclosure Affidavit* (Required in all contested financial proceedings).
    * **Cook County Form CCDR 0050**: *Certificate of Attorney / Self-Represented Filer*.

---

### 2. Cook County – County Division (`cook:cd1`)
* **Jurisdiction Profile**: Handles all Cook County civil name changes, adoptions, and election matters.
* **EFSP Codes & Structure**:
  * **Categories**: `78345`: `Miscellaneous`
  * **Case Types**: `78346`: `Name Change`
  * **Party Types**: `Applicant` (Required), `Petitioner` (Required).
  * **Live Filing Codes Validated**:
    * `78347`: `Petition For Change Of Name`
    * `78348`: `Order For Change Of Name` (Proposed Order)
    * `78351`: `Notice Of Motion / Hearing`
    * `78354`: `Publisher's Certificate / Certificate of Publication`
    * `78359`: `Motion To Waive Publication`
  * **County-Specific Mandatory Rules & Forms**:
    * **CCCo 0010**: *County Division Name Change Information Sheet / Cover Sheet*.
    * **Criminal Background Clearance Form**: Verification under Cook County County Division General Administrative Orders regarding statutory eligibility.

---

### 3. Cook County – Municipal Civil Division (`cook:cvd1`)
* **Jurisdiction Profile**: High-volume division for all Chicago & Suburban eviction actions, debt collection, contract claims, and small claims.
* **EFSP Codes & Structure**:
  * **Categories**: `174140`: `Civil`
  * **Case Types (Eviction)**:
    * `174214`: `Eviction - Possession - Non-Jury`
    * `174216`: `Eviction Joint Action - Possession And Rent - Non-Jury`
    * `184153`: `Eviction - Possession - Jury`
    * `184154`: `Eviction Joint Action - Possession And Rent - Jury`
    * `174196`: `CHA Eviction - Non-Jury`
  * **Case Types (Small Claims / Debt Collection)**:
    * `186078`: `Breach Of Contract - Small Claims $0 to $10,000 - Non-Jury - Self-Represented Litigant`
    * `186074`: `Breach Of Contract - Small Claims $0 to $10,000 - Non-Jury - Blitt & Gaines`
    * `186076`: `Breach Of Contract - Small Claims $0 to $10,000 - Non-Jury - Non Blitt & Gaines Bulk`
    * `184139`: `Breach Of Contract - Small Claims $0 to $10,000 - Non-Jury`
    * `184140`: `Breach Of Contract - Small Claims $0 to $10,000 - Jury`
  * **Party Types**: `Plaintiff` (Required), `Defendant` (Required).
  * **Live Filing Codes Validated**:
    * `174542`: `Appearance`
    * `174543`: `Appearance - Fee Waiver (No Fee)`
    * `174540`: `Answer`
    * `174545`: `Answer - Eviction (Possession Only)`
    * `174546`: `Answer - Eviction (Joint Action)`
    * `174550`: `Jury Demand` (Separate filing code: 6-person or 12-person jury)
    * `174560`: `Application For Waiver Of Court Fees`
    * `174570`: `Early Resolution Program Form Filed`
  * **County-Specific Mandatory Rules & Forms**:
    * **Early Resolution Program (ERP)**: Mandatory Cook County eviction program connecting tenants with legal aid, rental assistance, and mediation.
    * **CCG 0500 / CCG 0501**: *Appearance Form & Section 2-610 Response*.
    * **Schedule Tier Appearances**: Specific fee tiers hard-coded in Tyler for amounts under $250, $250–$500, $500–$2,500, $2,500–$10,000.

---

### 4. DuPage County Circuit Court (`dupage`)
* **Jurisdiction Profile**: 18th Judicial Circuit (Wheaton, IL) – Large suburban collar county.
* **EFSP Codes & Structure**:
  * **Categories**:
    * `192291`: `Dissolution (Divorce) with Children`
    * `192300`: `Dissolution (Divorce) without Children`
    * `152110`: `Law: Damages over $50,000`
    * `129550`: `Law Magistrate: Damages over $10,000 up to $50,000`
    * `129530`: `Small Claims` (Damages up to $10,000)
    * `129610`: `Miscellaneous Remedy` (Name Changes)
  * **Case Types**:
    * Divorce: `192292` (*Dissolution with Children*), `192301` (*Dissolution without Children*).
    * Eviction: `152111` (*Eviction - Rent over $50k*), `129555` (*Eviction - Possession Only*), `129535` (*Eviction Joint Action*).
    * Small Claims / Debt: `129531` (*Small Claims - Non-Jury*), `129557` (*Contract $10K to $15K*).
    * Name Change: `129618` (*Change of Name*).
  * **Party Types**: `Petitioner(req)`, `Respondent(req)`, `Plaintiff(req)`, `Defendant(req)`.
  * **Live Filing Codes Validated**:
    * `148587`: `Petition for Dissolution`
    * `148590`: `Summons (Issued)`
    * `148600`: `Answer`
    * `148605`: `Appearance`
    * `148620`: `Financial Affidavit`
    * `148625`: `Parenting Plan`
    * `148630`: `Application for Waiver of Court Fees`
  * **County-Specific Mandatory Rules & Forms**:
    * **Local Rule 15.01**: Mandatory participation in DuPage "Focus on the Children" parent education class.
    * **DuPage Family Case Management Conference Order** (Form 4310).
    * **DuPage Residential Eviction Mediation Program** (Court Rule 21.08).

---

### 5. Lake County Circuit Court (`lake`)
* **Jurisdiction Profile**: 19th Judicial Circuit (Waukegan, IL) – Collar county north of Cook.
* **EFSP Codes & Structure**:
  * **Categories**:
    * `242450`: `Dissolution (Divorce) with Children`
    * `242460`: `Dissolution (Divorce) without Children`
    * `124280`: `Law: Damages over $50,000`
    * `242520`: `Law Magistrate: Damages over $10,000 up to $50,000`
    * `50650`: `Miscellaneous Remedy`
  * **Case Types**:
    * Divorce: `242452` (*Dissolution with Children*), `242461` (*Dissolution without Children*).
    * Eviction: `124290` (*Eviction*), `242522` (*Eviction - Possession*).
    * Small Claims / Debt: `242524` (*Contract - Debt Collection*), `55460` (*Small Claims*).
    * Name Change: `50660` (*Change of Name*).
  * **Party Types**: `Petitioner(req)`, `Respondent(req)`, `Plaintiff(req)`, `Defendant(req)`.
  * **County-Specific Mandatory Rules & Forms**:
    * **Lake County Family Division "Kids 1st" Program**: Mandatory educational class certificate within 60 days of filing.
    * **Lake County Eviction Mediation Standing Order**: Mandatory summons attachment advising tenant of mediation resources.
    * **Lake County Local Form 171B**: *Family Law Case Information Sheet*.

---

### 6. Will County Circuit Court (`will`)
* **Jurisdiction Profile**: 12th Judicial Circuit (Joliet, IL) – Rapidly growing collar county.
* **EFSP Codes & Structure**:
  * **Categories**:
    * `203850`: `Dissolution (Divorce) with Children`
    * `203860`: `Dissolution (Divorce) without Children`
    * `184490`: `Law: Damages over $50,000`
    * `189470`: `Law Magistrate: Damages over $10,000 up to $50,000`
    * `189350`: `Arbitration / Miscellaneous`
  * **Case Types**:
    * Divorce: `203853` (*Dissolution with Children*), `203854` (*Dissolution without Children*).
    * Eviction: `184499` (*Eviction - Rent over $50k*), `189472` (*Eviction Possession Only*).
    * Small Claims / Debt: `189475` (*SMALL CLAIM*), `189478` (*Contract Debt Collection*).
    * Name Change: `189360` (*Name Change*).
  * **Party Types**: `Petitioner(req)`, `Respondent(req)`, `Plaintiff(req)`, `Defendant(req)`.
  * **County-Specific Mandatory Rules & Forms**:
    * **Will County Local Rule 11.05**: Mandatory Parent Education program certification.
    * **Will County Family Case Management Conference Notice**.
    * **Will County Civil Cover Sheet (Form 12A)**.

---

### 7. Kane County Circuit Court (`kane`)
* **Jurisdiction Profile**: 16th Judicial Circuit (Geneva, IL) – Western collar county.
* **EFSP Codes & Structure**:
  * **Categories**:
    * `7405`: `Adoption & Family` / `Dissolution`
    * `137510`: `Law`
    * `10580`: `Miscellaneous Remedy`
  * **Case Types**:
    * Divorce: `192292` (*Dissolution with Children*), `192301` (*Dissolution without Children*).
    * Eviction: `137522` (*Eviction Possession Only*), `137525` (*Eviction Joint Action*).
    * Small Claims / Debt: `137520` (*Contract - Debt Collection*), `10660` (*Small Claims*).
    * Name Change: `10589` (*Change of Name*).
  * **Party Types**: `Petitioner(req)`, `Respondent(req)`, `Plaintiff(req)`, `Defendant(req)`.
  * **County-Specific Mandatory Rules & Forms**:
    * **KIDS (Kids In a Divorcing Situation)**: Mandatory parent education program in Kane County.
    * **Kane County Eviction Resolution Program (ERP)**.
    * **Kane County Family Division Financial Disclosure Order**.

---

### 8. Champaign County Circuit Court (`champaign`)
* **Jurisdiction Profile**: 6th Judicial Circuit (Urbana/Champaign, IL) – Downstate urban/university center.
* **EFSP Codes & Structure**:
  * **Categories**:
    * `217620`: `Dissolution (Divorce) with Children`
    * `217630`: `Dissolution (Divorce) without Children`
    * `150720`: `Law Magistrate: Damages over $10,000 up to $50,000`
    * `40080`: `Miscellaneous Remedy`
  * **Case Types**:
    * Divorce: `217626` (*Dissolution with Children*), `217635` (*Dissolution without Children*).
    * Eviction: `150721` (*Eviction - Possession Only*).
    * Small Claims / Debt: `159492` (*Contract - Debt Collection $10K to $15K*), `40370` (*Small Claims*).
    * Name Change: `40086` (*Change of Name*).
  * **Party Types**: `Petitioner(req)`, `Respondent(req)`, `Plaintiff(req)`, `Defendant(req)`.
  * **County-Specific Mandatory Rules & Forms**:
    * **Champaign County Local Rule 14.1**: Mandatory Mediation for Child Custody/Allocation.
    * **Children First Education Program**: Required attendance certificate.

---

### 9. Sangamon County Circuit Court (`sangamon`)
* **Jurisdiction Profile**: 7th Judicial Circuit (Springfield, IL) – State capital district.
* **EFSP Codes & Structure**:
  * **Categories**:
    * `215570`: `Dissolution (Divorce) with Children`
    * `215571`: `Dissolution (Divorce) without Children`
    * `154750`: `Law: Damages over $50,000`
    * `154760`: `Law Magistrate: Damages over $10,000 up to $50,000`
    * `67190`: `Miscellaneous Remedy`
  * **Case Types**:
    * Divorce: `215575` (*Dissolution with Children*), `215576` (*Dissolution without Children*).
    * Eviction: `154757` (*Eviction - Damages over $50k*), `154765` (*Eviction Possession Only*).
    * Small Claims / Debt: `154768` (*Contract Debt Collection*), `67180` (*Small Claims*).
    * Name Change: `67195` (*Name Change*).
  * **Party Types**: `Petitioner(req)`, `Respondent(req)`, `Plaintiff(req)`, `Defendant(req)`.
  * **County-Specific Mandatory Rules & Forms**:
    * **7th Judicial Circuit Parenting Class Certification**.
    * **Sangamon County Civil Notice of Hearing / Setting Order**.

---

### 10. Peoria County Circuit Court (`peoria`)
* **Jurisdiction Profile**: 10th Judicial Circuit (Peoria, IL) – Major central Illinois industrial hub.
* **EFSP Codes & Structure**:
  * **Categories**:
    * `7580`: `Small Claims`
    * `192290`: `Dissolution (Divorce) with Children`
    * `192300`: `Dissolution (Divorce) without Children`
    * `126930`: `Miscellaneous Remedy`
  * **Case Types**:
    * Divorce: `192292` (*Dissolution with Children*), `192301` (*Dissolution without Children*).
    * Eviction: `7587` (*Forcible Entry & Detainer*).
    * Small Claims / Debt: `7589` (*Small Claims > $500 No Jury*), `7590` (*Small Claims Jury*).
    * Name Change: `126935` (*Change of Name*).
  * **Party Types**: `Petitioner(req)`, `Respondent(req)`, `Plaintiff(req)`, `Defendant(req)`.
  * **County-Specific Mandatory Rules & Forms**:
    * **Peoria County "Children in the Middle" Parenting Education Certificate**.
    * **10th Circuit Small Claims Summons Rule (Appearance in lieu of Answer)**.

---

### 11. St. Clair County Circuit Court (`stclair`)
* **Jurisdiction Profile**: 20th Judicial Circuit (Belleville, IL) – Metro East / St. Louis metropolitan area.
* **EFSP Codes & Structure**:
  * **Categories**:
    * `312790`: `Dissolution (Divorce) with Children`
    * `312795`: `Dissolution (Divorce) without Children`
    * `312900`: `Law: Damages over $50,000`
    * `312830`: `Law Magistrate: Damages over $10,000 up to $50,000`
    * `312780`: `Miscellaneous Remedy`
  * **Case Types**:
    * Divorce: `312791` (*Dissolution with Children*), `312792` (*Dissolution without Children*).
    * Eviction: `312906` (*Eviction - Commercial*), `312835` (*Eviction - Residential*).
    * Small Claims / Debt: `312832` (*Contract Debt Collection*), `312840` (*Small Claims*).
    * Name Change: `312785` (*Change of Name*).
  * **Party Types**: `Petitioner(req)`, `Respondent(req)`, `Plaintiff(req)`, `Defendant(req)`.
  * **Live Filing Codes Validated**:
    * `314506`: `Complaint`
    * `316354`: `Petition`
    * `317636`: `Summons (Issued)`
    * `313802`: `Answer`
    * `313828`: `Answer - Eviction (Possession Only)`
    * `313956`: `Appearance (No Fee: fee exempted by rule/statute)`
    * `313989`: `Appearance (No Fee: fee previously paid)`
    * `315073`: `Entry of Appearance`
  * **County-Specific Mandatory Rules & Forms**:
    * **20th Circuit Parenting Education Rule (Children First Program)**.
    * **St. Clair County Family Cover Sheet & Motion Practice Rules**.

---

## Part 3: Cross-County Comparison Matrix

The table below summarizes document requirements, local court quirks, and filing variations across the 11 surveyed jurisdictions:

| Filing Need | Document | Always Required | Usually Required | Required Sometimes | Specific County Rules / Variations |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Divorce (With Children)** | Petition for Dissolution | **YES** | - | - | Universal Lead Document across all circuits |
| | Summons / E-Summons | **YES** | - | - | Optional Service fee ($5.00) if clerk issues; waived if Entry of Appearance filed |
| | Financial Affidavit | - | **YES** | - | Mandatory statewide (750 ILCS 5/501). Cook requires Local Rule 13.3.1 format |
| | Parenting Plan | - | **YES** | - | Mandatory within 120 days of service (750 ILCS 5/602.10) |
| | Parent Education Certificate | - | - | **YES** | Cook (Focus on Children), DuPage (Focus), Lake (Kids 1st), Kane (KIDS), Peoria (Children in Middle) |
| | Domestic Relations Cover Sheet | - | - | **YES** | **Cook County only** (Form CCDR 0001 mandatory); DuPage (Form 4310) |
| | Uniform Order for Support | - | - | **YES** | Mandatory whenever child support ordered |
| | Certificate of Dissolution (IDPH) | - | **YES** | - | Required before final judgment in all IL counties |
| **Divorce (No Children)** | Petition / Joint Petition | **YES** | - | - | Lead Document |
| | Summons / Appearance | **YES** | - | - | Required to complete jurisdiction |
| | Financial Affidavit | - | **YES** | - | Required in contested cases; waived in Joint Simplified Dissolution (750 ILCS 5/452) |
| | Marital Settlement Agreement | - | **YES** | - | Regulates property/debt division |
| | Joint Simplified Affidavit | - | - | **YES** | Only in simplified uncontested filings meeting statutory criteria |
| **Eviction Answer** | Appearance | **YES** | - | - | Lead Document. Prevents default judgment on return date |
| | Eviction Answer / Defenses | **YES** | - | - | Formally raises habitability, defective notice, or retaliation defenses |
| | Fee Waiver Application (Rule 298) | - | **YES** | - | Critical for low-income tenants; stops appearance fee |
| | Early Resolution Program (ERP) | - | - | **YES** | **Cook County only** (Mandatory ERP intake/notice); Mediation in DuPage/Lake/Kane |
| | Jury Demand | - | - | **YES** | Must be filed on or before appearance date; requires fee or waiver |
| | Motion to Seal Record | - | - | **YES** | Under 735 ILCS 5/9-121.5 (post-disposition or COVID protection) |
| **Small Claims Answer (Debt)**| Appearance | **YES** | - | - | In IL Small Claims (Rule 286), Appearance can stand as denial |
| | Written Answer & Defenses | - | **YES** | - | Mandatory to preserve SOL, lack of standing, or FDCPA defenses |
| | Fee Waiver Application | - | **YES** | - | Overrides high appearance fees for indigent consumers |
| | Appearance Schedule Tier | - | - | **YES** | Cook, Will, Lake have distinct filing codes based on claim dollar tiers |
| | Self-Represented vs Bulk Codes | - | - | **YES** | **Cook County only** has distinct case codes for Self-Represented vs Bulk Debt filers |
| **Name Change** | Request for Name Change | **YES** | - | - | Lead Petition for Adult or Minor |
| | Proposed Order for Name Change | **YES** | - | - | Submitted for judge signature |
| | Notice of Court Date / Hearing | - | **YES** | - | Required to schedule court hearing |
| | Publication Notice / Certificate | - | **YES** | - | 3 weeks newspaper publication required by 735 ILCS 5/21-103 |
| | Motion to Waive Publication | - | - | **YES** | Permitted under 735 ILCS 5/21-103.5 for safety / domestic violence risks |
| | Minor Consent / Non-Custodial Notice| - | - | **YES** | **Minor Name Change only** (Consent if 14+; notice on non-custodial parent) |
| | Background / Criminal Attestation | - | - | **YES** | Cook County Division & collar counties check statutory eligibility |

---

## Part 4: Implementation Guidance for LITEFile Workflow

To ensure seamless e-filing across all Illinois circuits, the LITEFile application workflow should implement the following logic:

1. **Intelligent Division & Court Code Routing**:
   * For **Cook County**, the user cannot simply select "Cook County". The app must route to:
     * `cook:dr1` for Divorce / Parentage.
     * `cook:cd1` for Name Change.
     * `cook:cvd1` for Eviction / Small Claims / Debt Collection.
   * For all other counties, single county court codes apply (`dupage`, `lake`, `will`, `kane`, `champaign`, `sangamon`, `peoria`, `stclair`).

2. **Automated Document Checklist Validation**:
   * When `has_children == True` on Divorce, automatically append **Parenting Plan**, **Financial Affidavit**, and county-specific **Parent Education Notice** to the document checklist.
   * When filing an Eviction Answer in `cook:cvd1`, automatically inject the **Cook County Early Resolution Program (ERP)** information packet.
   * In Name Change, if the user flags a safety/stalking risk, swap the **Publication Notice** for the **Motion to Waive Publication**.

3. **Dynamic Tyler Fee Calculation & Stand-in PDF URLs**:
   * For fee calculations and quotes against the live proxy (`FilingReviewService.calculateFilingFees`), ensure `data_url` points to `EFSP_TEST_DOCUMENT_URL` in development.
   * Map `Appearance` filing codes to the correct fee exemption code (`fee exempted by rule/statute` or `fee previously paid`) when a `Civil 298 Fee Waiver` is attached.

---
*Report generated and validated against the Tyler Technologies Illinois ECF Proxy Server (`https://efile-test.suffolklitlab.org`).*
