const test = require("node:test");
const assert = require("node:assert");

const FilingPayload = require("../efile/static/js/filing-payload.js");

// The module reads these page-level globals at call time.
global.Messages = {
    showError() {},
    showSuccess() {}
};
global.gettext = (s) => s;
global.apiUtils = {
    getCurrentJurisdiction: () => "illinois"
};

/** A FilingHandler stand-in, mixed the same way the real pages mix it. */
function makeHandler() {
    const handler = {
        setFeesState() {},
        setSubmissionState() {}
    };
    return Object.assign(handler, FilingPayload);
}

const CASE_DATA = {
    filing_component: "999",
    filing_type_id: "27965",
    document_type: "dt"
};

function bundlesFor(uploadData) {
    const handler = makeHandler();
    const efilingData = {
        al_court_bundle: []
    };
    handler.addCourtBundles(efilingData, uploadData, CASE_DATA, []);
    return efilingData.al_court_bundle;
}

test("supporting component given as a plain code string is used as-is", () => {
    const bundles = bundlesFor({
        files: {
            supporting: [{
                name: "a.pdf"
            }]
        },
        supporting_documents: [{
            filing_component: "332"
        }],
    });

    assert.strictEqual(bundles[0].filing_component, "332");
});

test("supporting component given as an {id, name} object is flattened to its id", () => {
    const bundles = bundlesFor({
        files: {
            supporting: [{
                name: "a.pdf"
            }]
        },
        supporting_documents: [{
            filing_component: {
                id: "332",
                name: "Attachments"
            }
        }],
    });

    assert.strictEqual(bundles[0].filing_component, "332");
});

test("component stored on the file record is used when the config has none", () => {
    const bundles = bundlesFor({
        files: {
            supporting: [{
                name: "a.pdf",
                filing_component: {
                    id: "332",
                    name: "Attachments"
                }
            }]
        },
        supporting_documents: [{}],
    });

    assert.strictEqual(bundles[0].filing_component, "332");
});

test("a null component falls back instead of throwing on .id", () => {
    // typeof null === "object" -- the previous ternary crashed here.
    const bundles = bundlesFor({
        files: {
            supporting: [{
                name: "a.pdf",
                filing_component: null
            }]
        },
        supporting_documents: [{
            filing_component: null
        }],
    });

    assert.strictEqual(bundles[0].filing_component, CASE_DATA.filing_component);
});

test("with no component anywhere, the case default is used and never the label 'supporting'", () => {
    const bundles = bundlesFor({
        files: {
            supporting: [{
                name: "a.pdf"
            }]
        },
        supporting_documents: [{}],
    });

    assert.strictEqual(bundles[0].filing_component, "999");
    assert.notStrictEqual(bundles[0].filing_component, "supporting");
});

test("lead and supporting documents both land in the bundle", () => {
    const bundles = bundlesFor({
        files: {
            lead: {
                name: "lead.pdf"
            },
            supporting: [{
                name: "a.pdf"
            }]
        },
        lead_filing_component: "331",
        supporting_documents: [{
            filing_component: "332"
        }],
    });

    assert.strictEqual(bundles.length, 2);
    assert.strictEqual(bundles[0].filing_component, "331");
    assert.strictEqual(bundles[1].filing_component, "332");
});

test("each document's selected optional services reach fee and submission payloads", () => {
    const uploadData = {
        files: {
            lead: {
                name: "lead.pdf"
            },
            supporting: [{
                name: "exhibit.pdf"
            }]
        },
        lead_filing_component: "331",
        lead_requested_optional_services: ["certified-copy", "rush"],
        supporting_documents: [{
            filing_component: "332",
            requested_optional_services: ["courtesy-copy"]
        }]
    };

    // PaymentPage and FilingHandler both mix in this same builder. Constructing
    // both payloads here guards the fee quote/final submission parity directly.
    const feeQuotePayload = bundlesFor(uploadData);
    const submissionPayload = bundlesFor(uploadData);

    assert.deepStrictEqual(feeQuotePayload[0].optional_services, [
        {code: "certified-copy"},
        {code: "rush"}
    ]);
    assert.deepStrictEqual(feeQuotePayload[1].optional_services, [{code: "courtesy-copy"}]);
    assert.deepStrictEqual(submissionPayload, feeQuotePayload);
});

test("documents without selected optional services send an empty list", () => {
    const bundles = bundlesFor({
        files: {
            lead: {
                name: "lead.pdf"
            }
        },
        lead_filing_component: "331"
    });

    assert.deepStrictEqual(bundles[0].optional_services, []);
});

test("the same module object serves both pages, so payloads cannot drift", () => {
    const paymentHandler = makeHandler();
    const reviewHandler = makeHandler();

    assert.strictEqual(paymentHandler.buildEFilingData, reviewHandler.buildEFilingData);
    assert.strictEqual(paymentHandler.addCourtBundles, reviewHandler.addCourtBundles);
    assert.strictEqual(paymentHandler.createDocumentBundle, reviewHandler.createDocumentBundle);
});

test("Cook and DuPage get their court-specific self-represented cross references", () => {
    const handler = makeHandler();
    const cook = {
        al_court_bundle: []
    };
    const dupage = {
        al_court_bundle: []
    };

    handler.addCourtBundles(cook, {}, {
        ...CASE_DATA,
        court_name: "Cook County"
    }, []);
    handler.addCourtBundles(dupage, {}, {
        ...CASE_DATA,
        court_name: "DuPage County"
    }, []);

    assert.deepStrictEqual(cook.cross_references, {
        254500: "99500"
    });
    assert.deepStrictEqual(dupage.cross_references, {
        136524: "99500"
    });
});

test("saved filer information drives the filing contact instead of account profile data", () => {
    const handler = makeHandler();
    const caseData = {
        filing_parties: [{
            role: "filer",
            first_name: "Jordan",
            last_name: "Taylor",
            address_line_1: "123 Main Street",
            city: "Springfield",
            state: "IL",
            zip_code: "62701",
            email: "jordan@example.com",
            phone: "217-555-0100"
        }]
    };

    assert.deepStrictEqual(handler.userDataFromCaseData(caseData), {
        fullName: "Jordan Taylor",
        address: "123 Main Street",
        addressLine2: "",
        city: "Springfield",
        state: "IL",
        zip: "62701",
        email: "jordan@example.com",
        phone: "217-555-0100"
    });
});

test("amount_in_controversy is sent when the draft has one", () => {
    const handler = makeHandler();
    const caseData = {
        case_category: "cat",
        case_type: "type",
        amount_in_controversy: "12500.00",
        filing_parties: [{
            role: "filer",
            party_type: "PLA",
            first_name: "Jordan",
            last_name: "Taylor"
        }]
    };
    const userData = handler.userDataFromCaseData(caseData);

    const result = handler.buildEFilingData(userData, caseData, {}, "pay-1");

    assert.strictEqual(result.amount_in_controversy, "12500.00");
});

test("defendant aliases are included as the respondent in the filing payload", () => {
    const handler = makeHandler();
    const caseData = {
        case_category: "category",
        case_type: "divorce",
        filing_parties: [{
            role: "filer",
            party_type: "PET"
        }],
        defendant_party_type: "DEF",
        defendant_first_name: "Grace",
        defendant_last_name: "Hopper"
    };

    const userData = handler.userDataFromCaseData(caseData);
    const result = handler.buildEFilingData(userData, caseData, {}, "pay-1");

    assert.strictEqual(result.users[1].party_type, "DEF");
    assert.deepStrictEqual(result.users[1].name, {
        first: "Grace",
        middle: "",
        last: "Hopper",
        suffix: ""
    });
});

test("amount_in_controversy is omitted (not sent as empty/zero) when the draft has none", () => {
    const handler = makeHandler();
    const caseData = {
        case_category: "cat",
        case_type: "type",
        filing_parties: [{
            role: "filer",
            party_type: "PLA",
            first_name: "Jordan",
            last_name: "Taylor"
        }]
    };
    const userData = handler.userDataFromCaseData(caseData);

    const result = handler.buildEFilingData(userData, caseData, {}, "pay-1");

    assert.strictEqual("amount_in_controversy" in result, false);
});

test("durable non-filer parties are included without collapsing to one legacy party", () => {
    const handler = makeHandler();
    const caseData = {
        case_category: "cat",
        case_type: "type",
        filing_parties: [{
            role: "filer",
            party_type: "PLA",
            first_name: "Jordan",
            last_name: "Taylor"
        }, {
            role: "other",
            party_type: "DEF",
            first_name: "Alex",
            last_name: "Morgan"
        }, {
            role: "other",
            party_type: "DEF",
            organization_name: "Example LLC"
        }]
    };
    const userData = handler.userDataFromCaseData(caseData);
    const result = handler.buildEFilingData(userData, caseData, {}, "pay-1");

    assert.strictEqual(result.users[0].party_type, "PLA");
    assert.strictEqual(result.other_parties.length, 2);
    assert.strictEqual(result.other_parties[0].name.first, "Alex");
    assert.strictEqual(result.other_parties[1].name.first, "Example LLC");
});
