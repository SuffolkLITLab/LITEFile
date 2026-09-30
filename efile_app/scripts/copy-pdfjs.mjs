// Keep all PDF.js assets on our origin, including fonts for older court forms.
import { copyFileSync, cpSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "node_modules/pdfjs-dist");
const target = path.join(root, "efile/static/vendor/pdfjs");
mkdirSync(target, { recursive: true });
for (const name of ["pdf.min.mjs", "pdf.worker.min.mjs"]) {
    copyFileSync(path.join(source, "legacy/build", name), path.join(target, name));
}
for (const name of ["pdf_viewer.mjs", "pdf_viewer.css"]) {
    copyFileSync(path.join(source, "legacy/web", name), path.join(target, name));
}
for (const name of ["cmaps", "standard_fonts", "wasm"]) {
    cpSync(path.join(source, name), path.join(target, name), { recursive: true });
}
cpSync(path.join(source, "web/images"), path.join(target, "images"), { recursive: true });
copyFileSync(path.join(source, "LICENSE"), path.join(target, "LICENSE"));
