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

// --- error reporting ---------------------------------------------------------
//
// The server answers a rejected filing with {success: false, error: "..."} that
// names what the filer must correct -- a missing required party type, a document
// the EFSP could not fetch. Collapsing every 400 to "Invalid request. Please
// check your input." hid two real, separately-diagnosable failures behind one
// unactionable sentence.

function stubFetch(response) {
    const client = new ApiUtils();
    globalThis.fetch = async () => response;
    return client;
}

function jsonResponse({ ok, status, body }) {
    const response = {
        ok,
        status,
        json: async () => body,
    };
    response.clone = () => response;
    return response;
}

test("a failed request surfaces the server's own error message", async () => {
    const client = stubFetch(jsonResponse({
        ok: false,
        status: 400,
        body: { success: false, error: "This case type requires a Plaintiff." },
    }));

    await assert.rejects(
        () => client.post("/api/payment-fees/", {}),
        (error) => {
            assert.strictEqual(error.message, "This case type requires a Plaintiff.");
            assert.strictEqual(error.serverMessage, "This case type requires a Plaintiff.");
            assert.strictEqual(error.status, 400);
            return true;
        },
    );
});

test("a failure with no parseable body still reports the status", async () => {
    const response = {
        ok: false,
        status: 500,
        json: async () => {
            throw new Error("not JSON");
        },
    };
    response.clone = () => response;
    const client = stubFetch(response);

    await assert.rejects(
        () => client.post("/api/payment-fees/", {}),
        (error) => {
            assert.match(error.message, /Server error/);
            return true;
        },
    );
});

test("a successful response is returned unchanged", async () => {
    const client = stubFetch(jsonResponse({
        ok: true,
        status: 200,
        body: { success: true, api_response: { feesCalculationAmount: { value: 0 } } },
    }));

    const result = await client.post("/api/payment-fees/", {});

    assert.strictEqual(result.success, true);
});


// --- long-running filing calls ----------------------------------------------

test("fee quotes and submissions may raise the request timeout", async () => {
    // The generic 30s default reported a timeout for an Adams County fee quote
    // the server answered successfully after 43s. Callers pass the longer budget
    // explicitly rather than raising it for every request on the page.
    const client = new ApiUtils();
    let seenTimeout = null;
    client.makeRequest = async (endpoint, options) => {
        seenTimeout = options.timeout;
        return { success: true };
    };

    await client.post("/api/payment-fees/", {}, {}, { timeout: ApiUtils.FILING_TIMEOUT_MS });

    assert.strictEqual(seenTimeout, ApiUtils.FILING_TIMEOUT_MS);
    assert.ok(ApiUtils.FILING_TIMEOUT_MS > 60000, "must outlast the server's own 60s timeout");
});
