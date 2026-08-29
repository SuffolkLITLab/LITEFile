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
    const aiOptOut = document.getElementById("ai-opt-out");
    const aiNoteOn = document.getElementById("ai-note-on");
    const aiNoteOff = document.getElementById("ai-note-off");
    const aiExplainer = document.getElementById("ai-explainer");
    const aiExplainerContent = document.getElementById("ai-explainer-content");
    const aiRemember = document.getElementById("ai-remember");
    const aiRememberChoice = document.getElementById("ai-remember-choice");
    const selectedFiles = new Map();
    // The "remember this" row is offered only after the filer changes the
    // setting, and only for the rest of this page load. Until then the account
    // preference is not this request's business, so it is left out of the post.
    let rememberOffered = false;

    function aiIsOff() {
        return Boolean(aiOptOut && aiOptOut.checked);
    }

    if (aiExplainer && aiExplainerContent && window.bootstrap) {
        const popover = new window.bootstrap.Popover(aiExplainer, {
            title: aiExplainer.textContent.trim(),
            content: aiExplainerContent.innerHTML,
            html: true,
            trigger: "click",
            placement: "top",
            customClass: "ai-explainer-popover"
        });
        // Bootstrap's click trigger only closes on the trigger itself, which
        // leaves the panel stranded over the page once attention moves on.
        document.addEventListener("click", (event) => {
            const inside = aiExplainer.contains(event.target) || event.target.closest(".ai-explainer-popover");
            if (!inside) popover.hide();
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") popover.hide();
        });
    }

    function offerToRemember() {
        if (!aiRemember || rememberOffered) return;
        rememberOffered = true;
        if (window.bootstrap) new window.bootstrap.Collapse(aiRemember, {
            toggle: false
        }).show();
        else aiRemember.classList.add("show");
    }

    async function saveAiPreference() {
        const optedOut = aiOptOut.checked;
        const body = new FormData();
        body.append("action", "ai_preference");
        body.append("ai_opt_out", optedOut ? "yes" : "");
        if (rememberOffered && aiRememberChoice) {
            body.append("remember_ai_choice", aiRememberChoice.checked ? "yes" : "no");
        }
        body.append("csrfmiddlewaretoken", apiUtils.getCSRFToken());
        try {
            const response = await fetch(aiOptOut.dataset.preferenceUrl || window.location.href, {
                method: "POST",
                body
            });
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || "Could not save that choice.");
            // The document on file was already read the other way, so the page
            // is showing answers that no longer apply. Reload into the fresh
            // analysis instead of leaving them there.
            if (result.reanalyzing) window.location.reload();
        } catch (error) {
            errorBox.textContent = error.message;
            errorBox.hidden = false;
        }
    }

    if (aiOptOut) {
        aiOptOut.addEventListener("change", () => {
            const optedOut = aiOptOut.checked;
            if (aiNoteOn) aiNoteOn.hidden = optedOut;
            if (aiNoteOff) aiNoteOff.hidden = !optedOut;
            offerToRemember();
            saveAiPreference();
        });
    }

    if (aiRememberChoice) aiRememberChoice.addEventListener("change", saveAiPreference);

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
            let pendingDetail = "Analysis will continue in the background.";
            if (aiIsOff()) pendingDetail = "We are checking your PDF's text for a form number, without AI.";
            stateDetail.textContent = result.extraction_pending ?
                pendingDetail :
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
            let readyTitle = "Document analysis is ready";
            if (result.ai_opted_out) readyTitle = "We finished checking your document";
            stateTitle.textContent = result.status === "failed" ? "Your document is ready for manual review" : readyTitle;
            // Nothing is reviewed on this page: the details are on the next
            // one, so say where the checking actually happens.
            const nextPageNudge = "Review the information carefully on the next page.";
            stateDetail.textContent = result.total_pages > result.pages_analyzed ?
                `We read the first ${result.pages_analyzed} of ${result.total_pages} pages. ${nextPageNudge}` :
                nextPageNudge;
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