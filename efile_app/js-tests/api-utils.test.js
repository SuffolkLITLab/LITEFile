/**
 * Unit tests for ApiUtils caching behavior.
 *
 * Runs on Node's built-in test runner (`node --test`) with no extra deps.
 * Kept out of ./tests so Playwright's E2E runner does not pick it up.
 *
 * The rule these tests lock in: the localStorage cache is only for static,
 * shareable reference data (dropdowns, form config). Per-user / per-draft
 * state (case data, uploads, profile, payment accounts, tokens, fees) is
 * server-owned and must always be fetched fresh.
 */

const test = require("node:test");
const assert = require("node:assert");

// ApiUtils constructs a singleton and touches window/document/localStorage at
// module load, so stub those globals before requiring it.
const store = new Map();
globalThis.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
};
globalThis.window = {
    location: {
        origin: "http://localhost"
    }
};
globalThis.document = {
    querySelector: () => ({
        value: "test-csrf-token"
    }),
    cookie: ""
};

const {
    ApiUtils
} = require("../efile/static/js/api-utils.js");

function makeClient() {
    const client = new ApiUtils();
    client.clearAllCache();
    let calls = 0;
    // Replace the network layer so we can count real round trips.
    client.makeRequest = async (endpoint) => {
        calls += 1;
        return {
            success: true,
            endpoint,
            call: calls
        };
    };
    return {
        client,
        calls: () => calls
    };
}

test("reference-data GETs are cached: repeated reads hit the network once", async () => {
    const {
        client,
        calls
    } = makeClient();
    await client.get("/api/dropdowns/courts", {
        jurisdiction: "illinois"
    });
    await client.get("/api/dropdowns/courts", {
        jurisdiction: "illinois"
    });
    assert.strictEqual(calls(), 1);
});

test("draft state (case + upload data) is never cached", async () => {
    const {
        client,
        calls
    } = makeClient();
    await client.getCaseData();
    await client.getCaseData();
    await client.getUploadData();
    await client.getUploadData();
    assert.strictEqual(calls(), 4);
});

test("per-user reads via fetchJSON (profile, payment accounts, token) are not cached", async () => {
    const {
        client,
        calls
    } = makeClient();
    await client.fetchJSON("/api/payment-accounts", "GET", {
        jurisdiction: "illinois"
    });
    await client.fetchJSON("/api/payment-accounts", "GET", {
        jurisdiction: "illinois"
    });
    assert.strictEqual(calls(), 2);
});

test("saving case data does not populate the read cache", async () => {
    const {
        client,
        calls
    } = makeClient();
    await client.saveCaseData({
        court: "cook:cd"
    });
    await client.getCaseData();
    await client.getCaseData();
    // 1 save + 2 uncached reads
    assert.strictEqual(calls(), 3);
});