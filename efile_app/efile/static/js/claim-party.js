/**
 * "This party is me" -- confirming it, before it happens.
 *
 * Claiming a party replaces someone already in the case with the person
 * signed in, so the button opens a question rather than doing it. Two things
 * the question has to settle:
 *
 * * whose name the court sees, when the row and the account are not the same
 *   name -- the answer is required, because either one can be right and only
 *   the filer knows which;
 * * that this is not where someone says they are *helping* that party, which
 *   is the reading the words invite and the wrong one for anybody who is not
 *   that person.
 *
 * Every claim form posts through here, so a browser with no dialog support
 * still gets asked, and the server refuses an unanswered name question in
 * any case.
 */
(function() {
    const dialog = document.getElementById("claim-party-dialog");
    const forms = Array.from(document.querySelectorAll("form.claim-party-form"));
    if (!dialog || !forms.length) return;

    const title = document.getElementById("claim-party-title");
    const lede = document.getElementById("claim-party-lede");
    const helping = document.getElementById("claim-party-helping");
    const helpingDetail = document.getElementById("claim-party-helping-detail");
    const nameChoice = document.getElementById("claim-party-name-choice");
    const nameMine = document.getElementById("claim-party-name-mine");
    const nameTheirs = document.getElementById("claim-party-name-theirs");
    const nameError = document.getElementById("claim-party-name-error");
    const confirmButton = document.getElementById("claim-party-confirm");
    const cancelButton = document.getElementById("claim-party-cancel");
    const insteadButton = document.getElementById("claim-party-instead-filing-for");

    let activeForm = null;

    function choiceInputs() {
        return Array.from(dialog.querySelectorAll('input[name="claim_party_name_choice"]'));
    }

    function open(form) {
        activeForm = form;
        const partyName = form.dataset.partyName || gettext("this party");
        const role = form.dataset.partyRole || "";
        const filerName = form.dataset.filerName || "";
        const replacesAName = form.dataset.replacesAName === "true";

        title.textContent = interpolate(gettext("Replace %(name)s with you?"), {
            name: partyName
        }, true);
        lede.textContent = role ?
            interpolate(
                gettext("This filing lists %(name)s as the %(role)s. We will list you in that role instead, and take %(name)s off the filing."), {
                    name: partyName,
                    role: role
                }, true) :
            interpolate(
                gettext("We will list you in this case in place of %(name)s, and take them off the filing."), {
                    name: partyName
                }, true);

        helping.hidden = !replacesAName;
        if (replacesAName) {
            helpingDetail.textContent = interpolate(
                gettext("Only do this if %(name)s is you, written differently. If %(name)s is someone else and you are filing on their behalf, they should stay on the filing and you should tell us you are filing for them."), {
                    name: partyName
                }, true);
        }

        nameChoice.hidden = !replacesAName;
        nameError.hidden = true;
        choiceInputs().forEach((input) => {
            input.checked = false;
        });
        if (replacesAName) {
            nameMine.textContent = interpolate(gettext("Use my name: %(name)s"), {
                name: filerName
            }, true);
            nameTheirs.textContent = interpolate(
                gettext("Keep the name already in this case: %(name)s"), {
                    name: partyName
                }, true);
        }

        if (typeof dialog.showModal === "function") {
            dialog.showModal();
        } else {
            dialog.setAttribute("open", "open");
        }
    }

    function close() {
        activeForm = null;
        if (typeof dialog.close === "function") {
            dialog.close();
        } else {
            dialog.removeAttribute("open");
        }
    }

    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (form.dataset.confirmed === "true") return;
            event.preventDefault();
            open(form);
        });
    });

    confirmButton.addEventListener("click", () => {
        if (!activeForm) return;
        const replacesAName = activeForm.dataset.replacesAName === "true";
        let choice = "mine";
        if (replacesAName) {
            const chosen = choiceInputs().find((input) => input.checked);
            if (!chosen) {
                nameError.hidden = false;
                return;
            }
            choice = chosen.value;
        }
        const field = activeForm.querySelector('input[name="name_choice"]');
        if (field) field.value = choice;
        activeForm.dataset.confirmed = "true";
        const form = activeForm;
        close();
        form.submit();
    });

    cancelButton.addEventListener("click", close);
    dialog.addEventListener("cancel", close);

    // The way out for the misreading this dialog exists to catch: keep the
    // party on the filing and answer the role question the other way instead.
    if (insteadButton) {
        insteadButton.addEventListener("click", () => {
            const partyId = activeForm ? activeForm.dataset.partyId : "";
            close();
            const notAParty = document.getElementById("filer-not-a-party");
            const filingFor = document.querySelector(`input[name="filing_for"][value="${partyId}"]`);
            if (notAParty) {
                notAParty.checked = true;
                notAParty.dispatchEvent(new Event("change", {
                    bubbles: true
                }));
            }
            if (filingFor) filingFor.checked = true;
            const target = notAParty || filingFor;
            if (target) {
                target.scrollIntoView({
                    behavior: "smooth",
                    block: "center"
                });
                target.focus();
            }
        });
    }
})();