(function() {
    // New files are checked on this page, so come back to them after a change.
    const reloadAtChecks = () => {
        window.history.replaceState(window.history.state, "", "#document-checks");
        window.location.reload();
    };
    document.getElementById("document-checks")?.addEventListener("document-checks:change", reloadAtChecks);

    const form = document.getElementById("checklist-upload-form");
    if (!form) return;
    const state = document.getElementById("checklist-upload-state");
    const errorBox = document.getElementById("checklist-upload-error");

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        state.hidden = false;
        errorBox.hidden = true;
        const button = form.querySelector('button[type="submit"]');
        button.disabled = true;
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
            if (!response.ok || !result.success) throw new Error(result.error || "Could not add documents.");
            reloadAtChecks();
        } catch (error) {
            state.hidden = true;
            errorBox.textContent = error.message;
            errorBox.hidden = false;
            button.disabled = false;
        }
    });
})();