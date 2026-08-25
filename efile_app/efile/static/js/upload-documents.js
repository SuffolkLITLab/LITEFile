(function() {
    function fileKey(file) {
        return [file.name, file.size, file.lastModified, file.type].join("::");
    }

    function mergeUniqueFiles(existingFiles, incomingFiles) {
        const merged = new Map();
        Array.from(existingFiles).forEach((file) => merged.set(fileKey(file), file));
        Array.from(incomingFiles).forEach((file) => {
            const key = fileKey(file);
            if (!merged.has(key)) merged.set(key, file);
        });
        return Array.from(merged.values());
    }

    if (typeof module !== "undefined" && module.exports) {
        module.exports = {
            fileKey,
            mergeUniqueFiles
        };
    }
    if (typeof document === "undefined") return;

    const form = document.getElementById("document-upload-form");
    if (!form) return;

    const input = document.getElementById("documents-input");
    const dropZone = document.getElementById("document-drop-zone");
    const uploadButton = document.getElementById("upload-button");
    const state = document.getElementById("upload-state");
    const stateTitle = document.getElementById("upload-state-title");
    const stateDetail = document.getElementById("upload-state-detail");
    const errorBox = document.getElementById("upload-error");
    const pendingSection = document.getElementById("pending-files");
    const pendingList = document.getElementById("pending-file-list");
    const pendingCount = document.getElementById("pending-file-count");
    const continueButton = document.getElementById("continue-to-analysis");
    const selectedFiles = new Map();

    function syncFiles() {
        const transfer = new DataTransfer();
        selectedFiles.forEach((file) => transfer.items.add(file));
        input.files = transfer.files;
        uploadButton.disabled = selectedFiles.size === 0;
        pendingSection.hidden = selectedFiles.size === 0;
        pendingCount.textContent = selectedFiles.size;
        pendingList.replaceChildren();
        selectedFiles.forEach((file, key) => {
            const row = document.createElement("div");
            row.className = "pending-file-row";
            const name = document.createElement("span");
            name.textContent = file.name;
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "btn btn-link text-danger pending-file-remove";
            remove.dataset.fileKey = key;
            remove.textContent = "Remove";
            remove.setAttribute("aria-label", `Remove ${file.name}`);
            row.append(name, remove);
            pendingList.append(row);
        });
        const fileCountLabel = selectedFiles.size === 1 ? "file" : "files";
        dropZone.querySelector("strong").textContent = selectedFiles.size ?
            `${selectedFiles.size} ${fileCountLabel} selected` :
            "Choose PDFs or drag them here";
    }

    function addFiles(files) {
        const merged = mergeUniqueFiles(selectedFiles.values(), files);
        selectedFiles.clear();
        merged.forEach((file) => selectedFiles.set(fileKey(file), file));
        syncFiles();
    }

    input.addEventListener("change", () => addFiles(input.files));
    ["dragenter", "dragover"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.add("drop-zone--active");
        });
    });
    ["dragleave", "drop"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.remove("drop-zone--active");
        });
    });
    dropZone.addEventListener("drop", (event) => addFiles(event.dataTransfer.files));
    pendingList.addEventListener("click", (event) => {
        const button = event.target.closest(".pending-file-remove");
        if (!button) return;
        selectedFiles.delete(button.dataset.fileKey);
        syncFiles();
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        errorBox.hidden = true;
        state.hidden = false;
        uploadButton.disabled = true;
        stateTitle.textContent = "Uploading your documents…";
        stateDetail.textContent = "Keep this page open while the files upload.";

        try {
            const response = await fetch(window.location.href, {
                method: "POST",
                body: new FormData(form),
                headers: {
                    "X-CSRFToken": apiUtils.getCSRFToken()
                },
            });
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || "Upload failed.");
            stateTitle.textContent = result.extraction_pending ? "Your documents are uploaded" : "Your documents are ready";
            stateDetail.textContent = result.extraction_pending ?
                "Analysis will continue in the background." :
                "Review what we found before you continue.";
            window.setTimeout(() => window.location.reload(), 300);
        } catch (error) {
            state.hidden = true;
            errorBox.textContent = error.message;
            errorBox.hidden = false;
            uploadButton.disabled = false;
        }
    });

    document.querySelectorAll(".remove-document").forEach((button) => {
        button.addEventListener("click", async () => {
            if (!window.confirm("Remove this document from your filing?")) return;
            const body = new FormData();
            body.append("action", "remove");
            body.append("document_id", button.dataset.documentId);
            body.append("csrfmiddlewaretoken", apiUtils.getCSRFToken());
            const response = await fetch(window.location.href, {
                method: "POST",
                body
            });
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            const result = await response.json();
            if (response.ok && result.success) window.location.reload();
            else window.alert(result.error || "Could not remove the document.");
        });
    });

    async function pollExtraction() {
        if (!form.dataset.extractionStatusUrl || state.hidden) return;
        try {
            const response = await fetch(form.dataset.extractionStatusUrl, {
                headers: {
                    "X-CSRFToken": apiUtils.getCSRFToken()
                },
            });
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || "Could not check document analysis.");
            if (!result.ready) {
                window.setTimeout(pollExtraction, 2500);
                return;
            }

            state.querySelector(".spinner-border")?.remove();
            stateTitle.textContent = result.status === "failed" ?
                "Your document is ready for manual review" :
                "Document analysis is ready";
            stateDetail.textContent = result.total_pages > result.pages_analyzed ?
                `We reviewed the first ${result.pages_analyzed} of ${result.total_pages} pages.` :
                "Review every detail before continuing.";
            continueButton.classList.remove("disabled");
            continueButton.removeAttribute("aria-disabled");
            continueButton.removeAttribute("tabindex");
            const analyzingPill = document.querySelector(".status-pill--analyzing");
            if (analyzingPill) {
                analyzingPill.classList.replace("status-pill--analyzing", "status-pill--ready");
                analyzingPill.innerHTML = '<i class="fa-solid fa-check" aria-hidden="true"></i> Ready';
            }
        } catch (error) {
            stateDetail.textContent = error.message;
            window.setTimeout(pollExtraction, 5000);
        }
    }

    pollExtraction();
})();