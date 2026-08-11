(function() {
    const button = document.getElementById("apply-party-type-guess");
    if (!button) return;

    button.addEventListener("click", () => {
        const radio = document.querySelector(`input[name="filer_party_type"][value="${button.dataset.value}"]`);
        if (radio) {
            radio.checked = true;
            radio.scrollIntoView({
                behavior: "smooth",
                block: "center"
            });
        }
        const hint = document.getElementById("party-type-hint");
        if (hint) hint.hidden = true;
    });
})();