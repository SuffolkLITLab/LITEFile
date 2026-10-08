const test = require("node:test");
const assert = require("node:assert/strict");

const {
    mergeFiles
} = require("../efile/static/js/upload-documents.js");

function pdf(name, size, lastModified) {
    return {
        name,
        size,
        lastModified,
        type: "application/pdf"
    };
}

test("sequential drops append files instead of replacing the first drop", () => {
    const firstDrop = mergeFiles([], [pdf("petition.pdf", 100, 1)]);
    const secondDrop = mergeFiles(firstDrop, [pdf("affidavit.pdf", 200, 2)]);

    assert.deepEqual(secondDrop.map(file => file.name), ["petition.pdf", "affidavit.pdf"]);
});

test("the same PDF can be selected again for a different filing code", () => {
    const petition = pdf("petition.pdf", 100, 1);
    const files = mergeFiles([petition], [petition, pdf("exhibit.pdf", 300, 3)]);

    assert.deepEqual(files.map(file => file.name), ["petition.pdf", "petition.pdf", "exhibit.pdf"]);
});

test("removing one pending file leaves the other selected", () => {
    const files = mergeFiles([], [pdf("petition.pdf", 100, 1), pdf("petition.pdf", 200, 2)]);
    const remaining = files.filter((_file, index) => index !== 0);

    assert.equal(remaining.length, 1);
    assert.equal(remaining[0].size, 200);
});
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function uploadPage({
    pending = false,
    hasLead = true,
    fetch
}) {
    const nodes = new Map();

    function node(id) {
        if (!nodes.has(id)) nodes.set(id, {
            dataset: {},
            attributes: new Map(),
            listeners: {},
            classList: {
                toggle() {},
                add() {},
                remove() {}
            },
            addEventListener(event, callback) {
                this.listeners[event] = callback;
            },
            setAttribute(name, value) {
                this.attributes.set(name, value);
            },
            removeAttribute(name) {
                this.attributes.delete(name);
            },
            querySelector() {
                return null;
            }
        });
        return nodes.get(id);
    }
    node("document-upload-form").dataset = {
        hasLead: String(hasLead),
        extractionPending: String(pending),
        extractionStatusUrl: "/status/"
    };
    node("continue-to-analysis").dataset.continueUrl = "/preview/?return_to=review";
    node("upload-state").hidden = !pending;
    const timers = [];
    const context = vm.createContext({
        document: {
            getElementById: node,
            querySelector: () => null,
            querySelectorAll: () => []
        },
        window: {
            location: {
                href: "/upload/"
            },
            setTimeout: (callback) => timers.push(callback)
        },
        apiUtils: {
            getCSRFToken: () => "csrf"
        },
        FormData: class {},
        fetch
    });
    // eslint-disable-next-line sonarjs/code-eval
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../efile/static/js/upload-documents.js"), "utf8"), context);
    return {
        node,
        timers,
        submit: () => node("document-upload-form").listeners.submit({
            preventDefault() {}
        })
    };
}

function reply(data) {
    return {
        ok: true,
        json: async () => ({
            success: true,
            ...data
        })
    };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test("pending analysis blocks navigation until complete or failed", async () => {
    for (const status of ["complete", "failed"]) {
        let finish;
        const page = uploadPage({
            pending: true,
            fetch: () => new Promise(resolve => {
                finish = resolve;
            })
        });
        const link = page.node("continue-to-analysis");
        assert.equal(link.attributes.get("aria-disabled"), "true");
        assert.equal(link.attributes.has("href"), false);
        let prevented = false;
        link.listeners.click({
            preventDefault() {
                prevented = true;
            }
        });
        assert.equal(prevented, true);
        finish(reply({
            ready: true,
            status
        }));
        await flush();
        assert.equal(link.attributes.has("aria-disabled"), false);
        assert.equal(link.attributes.get("href"), "/preview/?return_to=review");
    }
});

test("a poll finishing during an upload cannot unlock navigation", async () => {
    let finishPoll;
    let finishUpload;
    const page = uploadPage({
        pending: true,
        fetch: (url) => new Promise(resolve => {
            if (url === "/status/") finishPoll = resolve;
            else finishUpload = resolve;
        })
    });
    const upload = page.submit();
    finishPoll(reply({
        ready: true,
        status: "complete"
    }));
    await flush();
    assert.equal(page.node("continue-to-analysis").attributes.has("href"), false);
    finishUpload(reply({
        extraction_pending: false
    }));
    await upload;
    assert.equal(page.node("continue-to-analysis").attributes.has("href"), false);
});

test("an upload failure restores an already ready filing", async () => {
    const page = uploadPage({
        fetch: async () => {
            throw new Error("Upload failed");
        }
    });
    const upload = page.submit();
    assert.equal(page.node("continue-to-analysis").attributes.has("href"), false);
    await upload;
    assert.equal(page.node("continue-to-analysis").attributes.get("href"), "/preview/?return_to=review");
    assert.equal(page.node("upload-error").hidden, false);
});

test("poll failures leave navigation blocked and schedule another check", async () => {
    const page = uploadPage({
        pending: true,
        fetch: async () => {
            throw new Error("Offline");
        }
    });
    await flush();
    assert.equal(page.node("continue-to-analysis").attributes.has("href"), false);
    assert.equal(page.timers.length, 1);
});