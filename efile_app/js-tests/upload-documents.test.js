const test = require("node:test");
const assert = require("node:assert/strict");

const {
    mergeUniqueFiles
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
    const firstDrop = mergeUniqueFiles([], [pdf("petition.pdf", 100, 1)]);
    const secondDrop = mergeUniqueFiles(firstDrop, [pdf("affidavit.pdf", 200, 2)]);

    assert.deepEqual(secondDrop.map(file => file.name), ["petition.pdf", "affidavit.pdf"]);
});

test("an exact duplicate from a later drop is ignored", () => {
    const petition = pdf("petition.pdf", 100, 1);
    const files = mergeUniqueFiles([petition], [petition, pdf("exhibit.pdf", 300, 3)]);

    assert.deepEqual(files.map(file => file.name), ["petition.pdf", "exhibit.pdf"]);
});

test("removing one pending file leaves the other selected", () => {
    const files = mergeUniqueFiles([], [pdf("petition.pdf", 100, 1), pdf("affidavit.pdf", 200, 2)]);
    const remaining = files.filter(file => file.name !== "petition.pdf");

    assert.deepEqual(remaining.map(file => file.name), ["affidavit.pdf"]);
});