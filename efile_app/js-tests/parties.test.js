const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function harness() {
    const radio = (value) => ({
        value,
        checked: false,
        listeners: {},
        addEventListener(event, handler) {
            this.listeners[event] ||= [];
            this.listeners[event].push(handler);
        },
        click(detail) {
            (this.listeners.click || []).forEach((handler) => handler({
                detail
            }));
        },
        change() {
            (this.listeners.change || []).forEach((handler) => handler());
        }
    });
    const plaintiff = radio("plaintiff");
    const other = radio("not-a-party");
    const filingFor = {};
    const submitted = [];
    const save = {};
    const form = {
        querySelector: () => save,
        requestSubmit: (button) => submitted.push(button)
    };
    const nodes = {
        "your-role": form,
        "filing-for": filingFor,
        "filer-not-a-party": other
    };
    const context = vm.createContext({
        document: {
            getElementById: (id) => nodes[id],
            querySelectorAll: () => [plaintiff, other]
        }
    });
    // Only the checked-in browser script is evaluated.
    // eslint-disable-next-line sonarjs/code-eval
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../efile/static/js/parties.js"), "utf8"), context);
    return {
        plaintiff,
        other,
        filingFor,
        submitted,
        save
    };
}

test("clicking a court role immediately submits Save role", () => {
    const page = harness();
    assert.equal(page.submitted.length, 0);
    page.plaintiff.checked = true;
    page.plaintiff.change();
    page.plaintiff.click(1);
    assert.deepEqual(page.submitted, [page.save]);
    assert.equal(page.filingFor.disabled, true);
});

test("filing for someone else reveals the questions before saving", () => {
    const page = harness();
    page.other.checked = true;
    page.other.change();
    assert.equal(page.submitted.length, 0);
    assert.equal(page.filingFor.hidden, false);
    assert.equal(page.filingFor.disabled, false);
});

test("keyboard role changes do not submit the form", () => {
    const page = harness();
    page.plaintiff.checked = true;
    page.plaintiff.change();
    page.plaintiff.click(0);
    assert.equal(page.submitted.length, 0);
});