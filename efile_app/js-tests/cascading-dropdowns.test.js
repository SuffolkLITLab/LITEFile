const test = require("node:test");
const assert = require("node:assert/strict");

const CascadingDropdowns = require("../efile/static/js/cascading-dropdowns.js");

test("missing upload guesses do not break a new filing", async () => {
    globalThis.apiUtils = {
        getUploadData: async () => ({}),
        getCurrentJurisdiction: () => "illinois"
    };

    const dropdowns = new CascadingDropdowns();
    await dropdowns.loadGuesses();

    assert.deepEqual(dropdowns.guesses, {});

    globalThis.document = {
        getElementById: () => null
    };

    const requested = [];
    dropdowns.resetDependentDropdowns = () => {};
    dropdowns.clearAllRecommendationNotices = () => {};
    dropdowns.clearAllDropdownVisualIndicators = () => {};
    dropdowns.validateParameters = () => true;
    dropdowns.loadDropdownData = async (...args) => requested.push(args);

    assert.doesNotThrow(() => dropdowns.handleDropdownChange({
        id: "court",
        value: "adams"
    }));

    assert.equal(requested.length, 1);
    assert.equal(requested[0][0], "case_category");
    assert.equal(requested[0][2].guessed_case_category, undefined);
    assert.equal(requested[0][2].guessed_case_type, undefined);
});

test("failed upload guess requests fall back to an empty guess set", async () => {
    globalThis.apiUtils = {
        getUploadData: async () => {
            throw new Error("network unavailable");
        }
    };

    const dropdowns = new CascadingDropdowns();
    await dropdowns.loadGuesses();

    assert.deepEqual(dropdowns.guesses, {});
});