const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function pageHarness(post) {
    const nodes = new Map();
    const node = (id) => {
        if (!nodes.has(id)) nodes.set(id, {
            value: "",
            hidden: true,
            disabled: false,
            style: {},
            textContent: id === "selected-payment-account-id" ? '""' : '{}',
            scrollIntoView() {},
            addEventListener() {},
            querySelectorAll: () => []
        });
        return nodes.get(id);
    };
    const intent = {
        value: "waiver"
    };
    const context = vm.createContext({
        document: {
            getElementById: node,
            querySelector: (selector) => selector.includes("paymentIntent") ? intent : null,
            addEventListener() {}
        },
        window: {},
        gettext: (text) => text,
        FilingPayload: {},
        apiUtils: {
            post,
            getCurrentJurisdiction: () => "illinois",
            fetchJSON: async () => ({
                success: true,
                data: []
            })
        }
    });
    // Only the checked-in browser script is evaluated; no external input.
    // eslint-disable-next-line sonarjs/code-eval
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../efile/static/js/payment.js"), "utf8") +
        "\nglobalThis.payment = PaymentPage;", context);
    return {
        payment: context.payment,
        node,
        intent
    };
}

const waiver = {
    success: true,
    data: {
        paymentAccountID: "waiver-1",
        accountName: "Existing waiver",
        paymentAccountTypeCode: "WV"
    }
};

test("waiver selection enables review without requesting a live fee quote", async () => {
    const calls = [];
    const {
        payment,
        node
    } = pageHarness(async (url) => {
        calls.push(url);
        return waiver;
    });
    await payment.chooseIntent();
    assert.deepEqual(calls, ["/api/waiver-account/"]);
    assert.equal(node("selected-payment-account").value, "waiver-1");
    assert.equal(node("selected-payment-account-type").value, "WV");
    assert.equal(node("submitButton").disabled, false);
    assert.equal(node("waiverHelp").hidden, false);
});

test("switching away from a pending waiver cannot restore its account", async () => {
    let resolve;
    const response = new Promise((done) => {
        resolve = done;
    });
    const {
        payment,
        node,
        intent
    } = pageHarness(() => response);
    const pending = payment.chooseIntent();
    intent.value = "pay";
    await payment.chooseIntent();
    resolve(waiver);
    await pending;
    assert.equal(node("selected-payment-account").value, "");
    assert.equal(node("submitButton").disabled, true);
    assert.equal(node("waiverHelp").hidden, true);
});

test("toggling back to waiver shares its pending creation request", async () => {
    let resolve;
    let calls = 0;
    const response = new Promise((done) => {
        resolve = done;
    });
    const {
        payment,
        intent,
        node
    } = pageHarness(() => {
        calls++;
        return response;
    });
    const first = payment.chooseIntent();
    intent.value = "pay";
    await payment.chooseIntent();
    intent.value = "waiver";
    const second = payment.chooseIntent();
    resolve(waiver);
    await Promise.all([first, second]);
    assert.equal(calls, 1);
    assert.equal(node("selected-payment-account").value, "waiver-1");
    assert.equal(node("submitButton").disabled, false);
});

test("waiver failures leave review disabled and can be retried", async () => {
    let attempts = 0;
    const {
        payment,
        node
    } = pageHarness(async () => {
        if (++attempts === 1) throw new Error("offline");
        return waiver;
    });
    await payment.chooseIntent();
    assert.equal(node("submitButton").disabled, true);
    assert.equal(node("errorMessage").hidden, false);
    await payment.chooseIntent();
    assert.equal(attempts, 2);
    assert.equal(node("submitButton").disabled, false);
});