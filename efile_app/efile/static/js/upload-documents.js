(function() {
    const form = document.getElementById("document-upload-form");
    if (!form) return;

    const input = document.getElementById("documents-input");
    const dropZone = document.getElementById("document-drop-zone");
    const uploadButton = document.getElementById("upload-button");
    const state = document.getElementById("upload-state");
    const stateTitle = document.getElementById("upload-state-title");
    const stateDetail = document.getElementById("upload-state-detail");
    const errorBox = document.getElementById("upload-error");

    function setFiles(files) {
        if (!files.length) return;
        const transfer = new DataTransfer();
        Array.from(files).forEach((file) => transfer.items.add(file));
        input.files = transfer.files;
        uploadButton.disabled = false;
        dropZone.querySelector("strong").textContent = `${files.length} file${files.length === 1 ? "" : "s"} selected`;
    }

    input.addEventListener("change", () => setFiles(input.files));
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
    dropZone.addEventListener("drop", (event) => setFiles(event.dataTransfer.files));

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        errorBox.hidden = true;
        state.hidden = false;
        uploadButton.disabled = true;
        stateTitle.textContent = "Uploading your documents…";
        stateDetail.textContent = "Keep this page open.";

        const analyzingTimer = window.setTimeout(() => {
            stateTitle.textContent = "Analyzing your lead document…";
            stateDetail.textContent = "We're looking for the court, case type, and case number.";
        }, 900);

        try {
            const response = await fetch(window.location.href, {
                method: "POST",
                body: new FormData(form),
                headers: {
                    "X-CSRFToken": apiUtils.getCSRFToken()
                },
            });
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || "Upload failed.");
            stateTitle.textContent = "Your documents are ready";
            stateDetail.textContent = "Review what we found before continuing.";
            window.setTimeout(() => window.location.reload(), 500);
        } catch (error) {
            state.hidden = true;
            errorBox.textContent = error.message;
            errorBox.hidden = false;
            uploadButton.disabled = false;
        } finally {
            window.clearTimeout(analyzingTimer);
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
            const result = await response.json();
            if (response.ok && result.success) window.location.reload();
            else window.alert(result.error || "Could not remove the document.");
        });
    });
})();