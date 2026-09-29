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
            createElement: () => ({
                textContent: "",
                get innerHTML() {
                    return this.textContent;
                }
            }),
            querySelector: (selector) => selector.includes("paymentIntent") ? (selector.includes(":checked") && intent.checked === false ? null : intent) : null,
            addEventListener() {}
        },
        window: {
            confirm: () => true,
            location: {
                search: ""
            }
        },
        URLSearchParams,
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
        window: context.window,
        apiUtils: context.apiUtils,
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
test("free first filing without an account explains the next step without creating a waiver", async () => {
    const calls = [];
    const {
        payment,
        node,
        intent
    } = pageHarness(async (url) => calls.push(url));
    intent.value = "pay";
    await payment.chooseIntent();
    assert.deepEqual(calls, []);
    assert.match(node("paymentMethodsContainer").innerHTML, /Add a credit or bank account to continue/);
    assert.match(node("paymentMethodsContainer").innerHTML, /Add credit or bank account/);
    assert.equal(node("submitButton").disabled, true);
});

test("waiver setup explains the zero charge and court approval", async () => {
    const {
        payment,
        node
    } = pageHarness(async () => waiver);
    await payment.chooseIntent();
    assert.match(node("successText").textContent, /\$0 due now/);
    assert.match(node("successText").textContent, /court may ask you to pay/);
});

test("the only active paid account is selected and quoted", async () => {
    const {
        payment,
        node,
        apiUtils
    } = pageHarness();
    apiUtils.fetchJSON = async () => ({
        success: true,
        data: [{
            paymentAccountID: "card",
            paymentAccountTypeCode: "CC"
        }, {
            paymentAccountID: "old",
            paymentAccountTypeCode: "CC",
            active: false
        }, {
            paymentAccountID: "wv",
            paymentAccountTypeCode: "WV"
        }]
    });
    payment.accountLabel = () => "My card";
    let quotes = 0;
    payment.selectAndQuote = async () => quotes++;
    payment.quoteRequestId = 1;
    await payment.choosePaidAccount(1);
    assert.match(node("paymentMethodsContainer").innerHTML, /value="card"[^>]*checked/);
    assert.doesNotMatch(node("paymentMethodsContainer").innerHTML, /value="wv"|value="old"/);
    assert.equal(quotes, 1);
});

test("a zero estimate automatically opens paid accounts even with a saved waiver", async () => {
    const {
        payment,
        node,
        intent,
        apiUtils
    } = pageHarness();
    intent.checked = false;
    node("estimated-zero-fees").textContent = "true";
    node("selected-payment-account-id").textContent = '"wv"';
    apiUtils.fetchJSON = async () => ({
        success: true,
        data: [{
            paymentAccountID: "wv",
            paymentAccountTypeCode: "WV"
        }]
    });
    let opened = false;
    payment.chooseIntent = async () => {
        opened = true;
    };
    await payment.loadAccounts();
    assert.equal(intent.checked, true);
    assert.equal(opened, true);
});

test("a saved waiver alone does not request another waiver automatically", async () => {
    const {
        payment,
        node,
        intent,
        apiUtils
    } = pageHarness();
    intent.checked = false;
    node("estimated-zero-fees").textContent = "false";
    node("selected-payment-account-id").textContent = '"wv"';
    apiUtils.fetchJSON = async () => ({
        success: true,
        data: [{
            paymentAccountID: "wv",
            paymentAccountTypeCode: "WV"
        }]
    });
    payment.chooseIntent = async () => assert.fail("Waiver requires an explicit choice");
    await payment.loadAccounts();
    assert.equal(intent.checked, false);
});

test("removing a payment method clears the selection and reloads accounts", async () => {
    const {
        payment,
        apiUtils,
        node
    } = pageHarness();
    const calls = [];
    apiUtils.delete = async (url) => {
        calls.push(url);
        return {
            success: true
        };
    };
    node("selected-payment-account").value = "old-card";
    payment.feeQuoteReady = true;
    payment.chooseIntent = async () => calls.push("reload");
    await payment.removeAccount({
        dataset: {
            accountId: "old-card",
            accountLabel: "Old card"
        }
    });
    assert.deepEqual(calls, ["/api/payment-accounts/old-card/", "reload"]);
    assert.equal(node("selected-payment-account").value, "");
    assert.equal(node("submitButton").disabled, true);
    assert.equal(node("successText").textContent, "Payment method removed.");
});

test("cancelling removal keeps the payment selection", async () => {
    const {
        payment,
        apiUtils,
        node,
        window
    } = pageHarness();
    window.confirm = () => false;
    apiUtils.delete = async () => assert.fail("Cancelled removal");
    node("selected-payment-account").value = "card";
    await payment.removeAccount({
        dataset: {
            accountId: "card"
        }
    });
    assert.equal(node("selected-payment-account").value, "card");
});

test("failed removal keeps the existing payment selection usable and permits retry", async () => {
    const {
        payment,
        apiUtils,
        node
    } = pageHarness();
    node("selected-payment-account").value = "card";
    node("selected-payment-account-name").value = "My card";
    node("paymentSection").hidden = false;
    payment.feeQuoteReady = true;
    payment.quoteRequestId = 7;
    apiUtils.delete = async () => {
        assert.equal(node("submitButton").disabled, true);
        throw new Error("offline");
    };
    const button = {
        dataset: {
            accountId: "card"
        }
    };
    await payment.removeAccount(button);
    assert.equal(button.disabled, false);
    assert.equal(payment.removingAccount, false);
    assert.equal(node("errorMessage").hidden, false);
    assert.equal(node("selected-payment-account").value, "card");
    assert.equal(node("selected-payment-account-name").value, "My card");
    assert.equal(node("paymentSection").hidden, false);
    assert.equal(payment.feeQuoteReady, true);
    assert.equal(payment.quoteRequestId, 7);
    assert.equal(node("submitButton").disabled, false);
});