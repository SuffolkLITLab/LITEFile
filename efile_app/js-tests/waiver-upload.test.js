const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function harness(fetch) {
    const nodes = new Map();
    const node = (id) => {
        if (!nodes.has(id)) nodes.set(id, {
            value: "",
            hidden: false,
            disabled: false,
            textContent: "",
            children: [],
            files: [],
            dataset: {
                url: "/waiver-documents/"
            },
            events: {},
            addEventListener(event, callback) {
                this.events[event] = callback;
            },
            setAttribute() {},
            focus() {
                this.focused = true;
            },
            replaceChildren() {
                this.children = [];
            },
            appendChild(child) {
                this.children.push(child);
            }
        });
        return nodes.get(id);
    };
    const payment = {
        setFeesState() {},
        async chooseIntent() {
            this.refreshed = true;
        }
    };
    const context = vm.createContext({
        document: {
            getElementById: node,
            createElement: () => ({}),
            addEventListener(_event, callback) {
                callback();
            }
        },
        window: {
            location: {
                origin: "https://example.com"
            },
            withFilingDraft: (url) => `${url}?draft=42`
        },
        URL,
        FormData,
        fetch,
        gettext: (text) => text,
        PaymentPage: payment,
        paymentJSON: () => "old-token",
        apiUtils: {
            getCSRFToken: () => "csrf"
        }
    });
    // Evaluates only the checked-in browser script.
    // eslint-disable-next-line sonarjs/code-eval
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../efile/static/js/waiver-upload.js"), "utf8"), context);
    return {
        node,
        payment
    };
}
const choices = {
    filing_types: [{
        code: "wv",
        name: "Affidavit of indigency"
    }],
    selected: "wv",
    document_types: [{
        code: "public",
        name: "Public"
    }, {
        code: "private",
        name: "Confidential"
    }]
};
const tick = () => new Promise((resolve) => setImmediate(resolve));

test("court filing type is selected but ambiguous confidentiality is not guessed", async () => {
    const {
        node
    } = harness(async (url) => {
        assert.equal(new URL(url).searchParams.get("draft"), "42");
        return {
            ok: true,
            json: async () => choices
        };
    });
    node("add-waiver-document").events.click();
    await tick();
    assert.equal(node("waiver-filing-type").value, "wv");
    assert.equal(node("waiver-document-type").value, "");
    assert.equal(node("waiver-upload-panel").hidden, false);
});

test("upload stays on payment and replaces the stale fee token", async () => {
    const {
        node,
        payment
    } = harness(async (_url, options) => {
        assert.equal(options.method, "POST");
        assert.equal(options.body.get("fee_inputs_token"), "old-token");
        assert.equal(options.body.get("document_type"), "private");
        return {
            ok: true,
            json: async () => ({
                success: true,
                fee_inputs_token: "new-token"
            })
        };
    });
    node("waiver-file").files = [new Blob(["test"], {
        type: "application/pdf"
    })];
    node("waiver-document-type").value = "private";
    node("waiver-filing-type").value = "wv";
    await node("upload-waiver-document").events.click();
    assert.equal(node("fee-inputs-token").textContent, '"new-token"');
    assert.equal(node("waiver-upload-required").hidden, true);
    assert.equal(node("waiver-upload-confirmation").hidden, false);
    assert.equal(payment.refreshed, true);
    assert.equal(payment.waiverUploading, false);
});

test("failed uploads keep the picker and file available for retry", async () => {
    const {
        node,
        payment
    } = harness(async () => ({
        ok: false,
        json: async () => ({
            error: "Try again."
        })
    }));
    node("waiver-file").files = [new Blob(["test"])];
    node("waiver-document-type").value = "private";
    await node("upload-waiver-document").events.click();
    assert.equal(node("waiver-upload-status").textContent, "Try again.");
    assert.equal(node("upload-waiver-document").disabled, false);
    assert.equal(node("waiver-upload-required").hidden, false);
    assert.equal(payment.refreshed, undefined);
});