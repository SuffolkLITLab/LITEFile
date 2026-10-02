const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function listeners(target) {
    target.listeners = {};
    target.addEventListener = (event, handler) => {
        target.listeners[event] ||= [];
        target.listeners[event].push(handler);
    };
    target.fire = (event) => {
        for (const handler of target.listeners[event] || []) handler({
            preventDefault() {}
        });
    };
    return target;
}

function harness(rules) {
    const inputs = {};
    Object.keys(rules).forEach((field) => {
        inputs[field] = listeners({
            value: "",
            disabled: false,
            validity: "",
            attributes: {},
            closest: () => null,
            setCustomValidity(message) {
                this.validity = message;
            },
            setAttribute(name, value) {
                this.attributes[name] = value;
            }
        });
    });
    const form = listeners({
        elements: {
            namedItem: (name) => inputs[name] || null
        },
        checkValidity: () => Object.values(inputs).every((input) => !input.validity),
        reportValidity() {}
    });
    const document = listeners({
        getElementById(id) {
            if (id === "party-validation-rules") return {
                textContent: JSON.stringify(rules)
            };
            if (id === "your-information-form") return form;
            return null;
        }
    });
    const context = vm.createContext({
        document,
        window: {
            location: {
                search: ""
            }
        },
        URLSearchParams
    });
    // eslint-disable-next-line sonarjs/code-eval
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../efile/static/js/party-validation.js"), "utf8"), context);
    return inputs;
}

test("court rules with escaped hyphens are checked in the browser", () => {
    // portable_regex keeps Java's \- outside a class; a "u" RegExp rejects it.
    const {
        phone
    } = harness({
        phone: {
            regex: "^\\d{3}\\-\\d{4}$",
            message: "Use 555-1234"
        }
    });
    phone.value = "5551234x";
    phone.fire("input");
    assert.equal(phone.validity, "Use 555-1234");
    assert.equal(phone.attributes["aria-invalid"], "true");
    phone.value = "555-1234";
    phone.fire("input");
    assert.equal(phone.validity, "");
});