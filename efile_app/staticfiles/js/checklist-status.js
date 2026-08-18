// Answering "I have it now" is the moment to offer to add it: waiting until the
// list is saved hides the one action that puts the document in the envelope.
// "I will file it later" is the moment to ask when, and only then.
(function() {
    document.querySelectorAll("input[type=radio][data-due-target]").forEach((radio) => {
        const dueField = document.getElementById(radio.dataset.dueTarget);
        const attachPrompt = document.getElementById(`attach-${radio.name.replace(/^status_/, "")}`);

        const row = radio.closest(".document-plan__item");

        radio.addEventListener("change", () => {
            if (!radio.checked) return;
            if (row) {
                // The row is tinted by the answer, so it has to follow one that
                // has been given but not yet saved.
                row.className = row.className.replace(/document-plan__item--\S+/, "");
                row.classList.add(`document-plan__item--${radio.value || "none"}`);
            }
            if (dueField) dueField.hidden = radio.value !== "later";
            if (!attachPrompt) return;
            attachPrompt.hidden = radio.value !== "have";
            if (radio.value === "have") attachPrompt.querySelector("input, select, button")?.focus();
        });
    });
})();