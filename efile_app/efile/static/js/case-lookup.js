(function() {
    const form = document.getElementById("case-lookup-form");
    if (!form) return;

    const courtSelect = document.getElementById("court");
    const caseNumber = document.getElementById("case-number");
    const state = document.getElementById("lookup-state");
    const errorBox = document.getElementById("lookup-error");
    const submitButton = document.getElementById("find-case-button");
    const guessedCourt = JSON.parse(document.getElementById("guessed-court").textContent || '""');
    const selectedCourtCode = JSON.parse(document.getElementById("selected-court-code").textContent || '""');

    async function loadCourts() {
        try {
            const response = await apiUtils.fetchJSON("/api/dropdowns/courts/", "GET", {
                jurisdiction: apiUtils.getCurrentJurisdiction(),
                guessed_court: guessedCourt,
            });
            if (!response.success) throw new Error(response.error || "Could not load courts.");
            courtSelect.innerHTML = '<option value="">Choose a court</option>';
            response.data.forEach((court) => {
                const option = document.createElement("option");
                option.value = court.value;
                option.textContent = court.text;
                if (court.value === selectedCourtCode || (!selectedCourtCode && (court.selected || court.default))) {
                    option.selected = true;
                }
                courtSelect.appendChild(option);
            });
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