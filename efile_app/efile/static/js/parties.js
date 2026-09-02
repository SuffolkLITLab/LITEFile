(function() {
    const guessButton = document.getElementById("apply-party-type-guess");
    const roleRadios = Array.from(document.querySelectorAll('input[name="filer_party_type"]'));
    const notAParty = document.getElementById("filer-not-a-party");
    const filingFor = document.getElementById("filing-for");

    function selectRole(value) {
        const radio = roleRadios.find((input) => input.value === value);
        if (!radio) return;
        radio.checked = true;
        radio.dispatchEvent(new Event("change", {
            bubbles: true
        }));
        radio.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
        radio.focus();
    }

    if (guessButton) {
        guessButton.addEventListener("click", () => {
            const hint = document.getElementById("party-type-hint");
            if (hint) hint.hidden = true;
            selectRole(guessButton.dataset.value);
        });
    }

    // "Who are you filing for?" only means anything to someone who has said
    // they are not a party themselves, so it follows that answer rather than
    // sitting on the screen as a second unexplained question.
    if (notAParty && filingFor) {
        const syncFilingFor = () => {
            filingFor.hidden = !notAParty.checked;
        };
        roleRadios.forEach((radio) => radio.addEventListener("change", syncFilingFor));
        syncFilingFor();
    }

    // The party list's "Add me as a party" shortcut: the filer is already on
    // this draft with a name and address, so adding themselves is answering
    // the role question above, not typing themselves in again. It takes them
    // to the question rather than answering it -- which party type they are
    // is a legal question, and picking one for them is how a filer ends up
    // filed under the wrong role without ever reading it.
    const addMe = document.getElementById("add-me-as-party");
    if (addMe) {
        addMe.addEventListener("click", () => {
            const firstPartyType = roleRadios.find((input) => input !== notAParty);
            if (!firstPartyType) return;
            if (notAParty) notAParty.checked = false;
            if (filingFor) filingFor.hidden = true;
            firstPartyType.scrollIntoView({
                behavior: "smooth",
                block: "center"
            });
            firstPartyType.focus();
        });
    }
})();