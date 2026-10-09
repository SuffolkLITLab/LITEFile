const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function element() {
    return {
        children: [],
        events: {},
        value: "",
        textContent: "",
        append(child) {
            this.children.push(child);
        },
        replaceChildren() {
            this.children = [];
        },
        addEventListener(name, callback) {
            this.events[name] = callback;
        },
        focus() {
            this.focused = true;
        },
        dispatchEvent(event) {
            this.changed = event.type;
        },
    };
}

test("finder searches supplied case choices and applies the selected code", () => {
    const input = element(),
        results = element(),
        status = element(),
        select = element();
    const container = {
        open: true,
        querySelector: selector => ({
            ".filing-search": input,
            ".filing-search-results": results,
            ".filing-search-status": status
        })[selector]
    };
    const context = {
        window: {},
        document: {
            createElement: element
        },
        Event: class {
            constructor(type) {
                this.type = type;
            }
        },
        gettext: text => text,
        interpolate: text => text
    };
    // Execute only the checked-in script under test in an isolated DOM stub.
    // eslint-disable-next-line sonarjs/code-eval
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../efile/static/js/filing-code-search.js"), "utf8"), context);
    context.window.filingCodeSearch.mountFilingTypeOnly({
        container,
        select,
        choices: [{
            value: "motion",
            text: "Motion to dismiss"
        }, {
            value: "answer",
            text: "Answer"
        }, ]
    });
    input.value = "dismiss motion";
    input.events.input();
    assert.equal(results.children.length, 1);
    const button = results.children[0].children[0];
    assert.equal(button.textContent, "Motion to dismiss");
    button.events.click();
    assert.equal(select.value, "motion");
    assert.equal(select.changed, "change");
    assert.equal(select.focused, true);
    assert.equal(container.open, false);
    input.value = "initial complaint";
    input.events.input();
    assert.equal(results.children.length, 0);
    assert.match(status.textContent, /No matching/);
});