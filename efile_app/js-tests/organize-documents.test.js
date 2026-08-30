const test = require("node:test");
const assert = require("node:assert");

// The browser-only initializer exits before touching the DOM in this test.
globalThis.document = {
    getElementById: () => null
};

const {
    preferredConfidentialityValue
} = require("../efile/static/js/organize-documents.js");

const choices = [{
    value: "PUBLIC",
    confidentiality: "non_confidential"
}, {
    value: "SEALED",
    confidentiality: "confidential"
}, ];

test("the jurisdiction default selects non-confidential", () => {
    assert.strictEqual(preferredConfidentialityValue(choices, "", "non_confidential"), "PUBLIC");
});

test("a saved filer choice takes precedence over the jurisdiction default", () => {
    assert.strictEqual(preferredConfidentialityValue(choices, "SEALED", "non_confidential"), "SEALED");
});

test("two choices stay unselected when a jurisdiction configures no default", () => {
    assert.strictEqual(preferredConfidentialityValue(choices, "", ""), "");
});