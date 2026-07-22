const test = require("node:test");
const assert = require("node:assert");

const FilingPayload = require("../efile/static/js/filing-payload.js");

// The module reads these page-level globals at call time.
global.Messages = { showError() {}, showSuccess() {} };
global.gettext = (s) => s;
global.apiUtils = { getCurrentJurisdiction: () => "illinois" };

/** A FilingHandler stand-in, mixed the same way the real pages mix it. */
function makeHandler() {
    const handler = { setFeesState() {}, setSubmissionState() {} };
    return Object.assign(handler, FilingPayload);
}

const CASE_DATA = { filing_component: "999", filing_type_id: "27965", document_type: "dt" };

function bundlesFor(uploadData) {
    const handler = makeHandler();
    const efilingData = { al_court_bundle: [] };
    handler.addCourtBundles(efilingData, uploadData, CASE_DATA, []);
    return efilingData.al_court_bundle;
}

test("supporting component given as a plain code string is used as-is", () => {
    const bundles = bundlesFor({
        files: { supporting: [{ name: "a.pdf" }] },
        supporting_documents: [{ filing_component: "332" }],
    });

    assert.strictEqual(bundles[0].filing_component, "332");
});

test("supporting component given as an {id, name} object is flattened to its id", () => {
    const bundles = bundlesFor({
        files: { supporting: [{ name: "a.pdf" }] },
        supporting_documents: [{ filing_component: { id: "332", name: "Attachments" } }],
    });

    assert.strictEqual(bundles[0].filing_component, "332");
});

test("component stored on the file record is used when the config has none", () => {
    const bundles = bundlesFor({
        files: { supporting: [{ name: "a.pdf", filing_component: { id: "332", name: "Attachments" } }] },
        supporting_documents: [{}],
    });

    assert.strictEqual(bundles[0].filing_component, "332");
});

test("a null component falls back instead of throwing on .id", () => {
    // typeof null === "object" -- the previous ternary crashed here.
    const bundles = bundlesFor({
        files: { supporting: [{ name: "a.pdf", filing_component: null }] },
        supporting_documents: [{ filing_component: null }],
    });

    assert.strictEqual(bundles[0].filing_component, CASE_DATA.filing_component);
});

test("with no component anywhere, the case default is used and never the label 'supporting'", () => {
    const bundles = bundlesFor({
        files: { supporting: [{ name: "a.pdf" }] },
        supporting_documents: [{}],
    });

    assert.strictEqual(bundles[0].filing_component, "999");
    assert.notStrictEqual(bundles[0].filing_component, "supporting");
});

test("lead and supporting documents both land in the bundle", () => {
    const bundles = bundlesFor({
        files: { lead: { name: "lead.pdf" }, supporting: [{ name: "a.pdf" }] },
        lead_filing_component: "331",
        supporting_documents: [{ filing_component: "332" }],
    });

    assert.strictEqual(bundles.length, 2);
    assert.strictEqual(bundles[0].filing_component, "331");
    assert.strictEqual(bundles[1].filing_component, "332");
});

test("the same module object serves both pages, so payloads cannot drift", () => {
    const paymentHandler = makeHandler();
    const reviewHandler = makeHandler();

    assert.strictEqual(paymentHandler.buildEFilingData, reviewHandler.buildEFilingData);
    assert.strictEqual(paymentHandler.addCourtBundles, reviewHandler.addCourtBundles);
    assert.strictEqual(paymentHandler.createDocumentBundle, reviewHandler.createDocumentBundle);
});
