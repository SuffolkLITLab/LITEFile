(function() {
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
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || "Could not add documents.");
            window.location.reload();
        } catch (error) {
            state.hidden = true;
            errorBox.textContent = error.message;
            errorBox.hidden = false;
            button.disabled = false;
        }
    });
})();