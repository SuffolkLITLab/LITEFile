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