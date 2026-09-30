const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

test("free filing help follows the current quote and closes on errors", () => {
    const nodes = new Map();
    const node = (id) => {
        if (!nodes.has(id)) nodes.set(id, {
            hidden: true,
            dataset: {},
            replaceChildren(...children) {
                this.children = children;
            },
            hidePopover() {
                this.closed = true;
            }
        });
        return nodes.get(id);
    };
    const context = vm.createContext({
        document: {
            getElementById: node,
            addEventListener() {}
        },
        gettext: (text) => text,
        FilingPayload: {
            feeReceiptRow: (label, amount) => ({
                label,
                amount
            })
        }
    });
    // Only the checked-in script runs in this test.
    // eslint-disable-next-line sonarjs/code-eval
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../efile/static/js/review.js"), "utf8") +
        " globalThis.handler = FilingHandler;", context);
    const handler = context.handler;
    handler.freeFilingPopover = {
        hide: () => {
            node("popover").closed = true;
        }
    };
    handler.showFeeQuote({
        state: "current",
        total: "0.00",
        is_zero: true
    });
    assert.equal(node("free-filing-help").hidden, false);
    assert.equal(node("submit-button-label").textContent, "Submit filing");
    handler.showFeeQuote({
        state: "current",
        total: "10.00",
        is_zero: false,
        breakdown: [{
            label: "Court fee",
            amount: "10.00"
        }]
    });
    assert.equal(node("submit-button-label").textContent, "Submit and pay");
    assert.equal(node("fee-quote-breakdown").children.length, 1);
    assert.equal(node("free-filing-help").hidden, true);
    assert.equal(node("popover").closed, true);
    handler.showFeeQuote({
        state: "current",
        total: "0.00",
        is_zero: true
    });
    assert.equal(node("fee-quote-breakdown").children.length, 0);
    assert.equal(node("submit-button-label").textContent, "Submit filing");
    handler.showFeeError("Quote expired");
    assert.equal(node("free-filing-help").hidden, true);
    handler.showFeeQuote({
        state: "stale",
        total: "0.00",
        is_zero: true
    });
    assert.equal(node("free-filing-help").hidden, true);
});

test("submission waits for acceptance and available court requirements", () => {
    const confirmation = {
        checked: false,
        disabled: false
    };
    const button = {};
    const nodes = {
        "confirm-filing": confirmation,
        submitButton: button,
        loadingSpinner: {
            style: {}
        }
    };
    const context = vm.createContext({
        document: {
            getElementById: (id) => nodes[id],
            addEventListener() {}
        },
        FilingPayload: {}
    });
    // eslint-disable-next-line sonarjs/code-eval
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../efile/static/js/review.js"), "utf8") +
        " globalThis.handler = FilingHandler;", context);
    context.handler.feeQuoteState = "current";
    context.handler.setSubmissionState(false);
    assert.equal(button.disabled, true);
    confirmation.checked = true;
    context.handler.setSubmissionState(false);
    assert.equal(button.disabled, false);
    confirmation.disabled = true;
    context.handler.setSubmissionState(false);
    assert.equal(button.disabled, true);
});