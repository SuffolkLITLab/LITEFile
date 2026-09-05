(function() {
    const form = document.getElementById("case-lookup-form");
    if (!form) return;

    const courtSelect = document.getElementById("court");
    const caseNumber = document.getElementById("case-number");
    const state = document.getElementById("lookup-state");
    const errorBox = document.getElementById("lookup-error");
    const submitButton = document.getElementById("find-case-button");
    const guessedCourt = JSON.parse(document.getElementById("guessed-court").textContent || '""');
    const extractionHelp = document.getElementById("court-extraction-help");
    const selectedCourtCode = JSON.parse(document.getElementById("selected-court-code").textContent || '""');

    async function mountCourtSelector() {
        const container = document.getElementById("court-selector");
        if (!container || !window.courtSelector) return false;
        const selector = window.courtSelector.mount({
            container,
            jurisdiction: apiUtils.getCurrentJurisdiction(),
            select: courtSelect,
        });
        const started = await selector.start(selectedCourtCode || "", guessedCourt || "");
        if (!started) {
            container.remove();
            return false;
        }
        courtSelect.hidden = true;
        // Native validation cannot point at a hidden field, and the selector is
        // what asks for the court now, so the check moves into the submit below.
        courtSelect.required = false;
        return true;
    }

    async function loadCourts() {
        // Guided questions where the jurisdiction configures them, the flat
        // list everywhere else. Either way the answer lands in the same select.
        if (await mountCourtSelector()) return;
        try {
            const response = await apiUtils.fetchJSON("/api/dropdowns/courts/", "GET", {
                jurisdiction: apiUtils.getCurrentJurisdiction(),
                guessed_court: guessedCourt,
            });
            if (!response.success) throw new Error(response.error || "Could not load courts.");
            courtSelect.innerHTML = '<option value="">Choose a court</option>';
            let hasMarkedCourt = false;
            response.data.forEach((court) => {
                const option = document.createElement("option");
                option.value = court.value;
                option.textContent = court.text;
                // The guess only earns a marker when it matches a real court, so the
                // help text that explains the marker waits for one to show up.
                if (String(court.text || "").trim().endsWith("*")) hasMarkedCourt = true;
                if (court.value === selectedCourtCode || (!selectedCourtCode && (court.selected || court.default))) {
                    option.selected = true;
                }
                courtSelect.appendChild(option);
            });
            if (extractionHelp) extractionHelp.hidden = !hasMarkedCourt;
        } catch (error) {
            courtSelect.innerHTML = '<option value="">Courts could not be loaded</option>';
            errorBox.textContent = error.message;
            errorBox.hidden = false;
        }
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        errorBox.hidden = true;
        state.hidden = false;
        submitButton.disabled = true;

        try {
            if (!courtSelect.value) throw new Error("Choose a court to search for your case.");
            const jurisdiction = apiUtils.getCurrentJurisdiction();
            const lookup = await apiUtils.fetchJSON("/api/suffolk/lookup-case/", "GET", {
                court: courtSelect.value,
                caseNumber: caseNumber.value.trim(),
                jurisdiction,
            });
            if (!lookup.success || !lookup.caseInfo?.caseTrackingID) {
                throw new Error(lookup.error || "We could not find a matching case. Check the court and case number.");
            }

            const selectedCourt = courtSelect.selectedOptions[0];
            const caseInfo = lookup.caseInfo;
            const saveResponse = await fetch(window.location.href, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": apiUtils.getCSRFToken(),
                },
                body: JSON.stringify({
                    court: courtSelect.value,
                    court_name: apiUtils.cleanOptionText(selectedCourt?.textContent),
                    case_tracking_id: caseInfo.caseTrackingID,
                    case_docket_id: caseInfo.caseDocketID || caseNumber.value.trim(),
                    case_title: caseInfo.caseTitle || "",
                    case_category_code: caseInfo.caseCategoryCode || "",
                    case_category_name: caseInfo.caseCategoryName || "",
                    case_type_code: caseInfo.caseTypeCode || "",
                    case_type_name: caseInfo.caseTypeName || "",
                }),
            });
            const saved = await saveResponse.json();
            if (!saveResponse.ok || !saved.success) throw new Error(saved.error || "Could not save the case.");
            window.location.href = saved.redirect_url;
        } catch (error) {
            errorBox.textContent = error.message;
            errorBox.hidden = false;
            state.hidden = true;
            submitButton.disabled = false;
        }
    });

    loadCourts();
})();