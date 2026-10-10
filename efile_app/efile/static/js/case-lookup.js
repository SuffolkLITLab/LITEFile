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

    const availability = window.filingAvailability.mount({
        form,
        notice: document.getElementById("filing-availability-notice"),
        selection: () => ({
            jurisdiction: apiUtils.getCurrentJurisdiction(),
            court: courtSelect.value
        }),
    });
    courtSelect.addEventListener("change", () => availability.check(courtSelect.closest(".form-field")));

    // Only Massachusetts shows this: its case numbers can name the court. The
    // guided court questions wait until the number has not settled the court,
    // so they never compete with an inferred one.
    const inferred = document.getElementById("inferred-court");
    const manualCourtField = document.getElementById("manual-court-field");
    let selector = null;
    let guidedCourt = false;
    // A court published while the questions are being drawn is not the filer's
    // own answer, so it does not stop the case number from settling the court.
    let selectorStarting = false;

    async function mountCourtSelector(courtCode) {
        const container = document.getElementById("court-selector");
        if (!container || !window.courtSelector) return false;
        selector ||= window.courtSelector.mount({
            container,
            jurisdiction: apiUtils.getCurrentJurisdiction(),
            select: courtSelect,
        });
        selectorStarting = true;
        let started;
        try {
            started = await selector.start(courtCode || "", guessedCourt || "");
        } finally {
            selectorStarting = false;
        }
        if (!started) {
            if (!guidedCourt) container.remove();
            return guidedCourt;
        }
        guidedCourt = true;
        courtSelect.hidden = true;
        // Native validation cannot point at a hidden field, and the selector is
        // what asks for the court now, so the check moves into the submit below.
        courtSelect.required = false;
        return true;
    }

    async function loadCourts() {
        // Guided questions where the jurisdiction configures them, the flat
        // list everywhere else. Either way the answer lands in the same select.
        if (!inferred && await mountCourtSelector(selectedCourtCode)) return;
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

    // The inferred court or the submit check asks for a court, not the browser.
    if (inferred) courtSelect.required = false;
    let inferenceGeneration = 0;
    let manualCourt = Boolean(selectedCourtCode);
    let inferredCode = "";
    let inferenceTimer;

    async function showManualCourt(courtCode = "") {
        inferred.hidden = true;
        if (!manualCourtField.hidden) return;
        manualCourtField.hidden = false;
        await mountCourtSelector(courtCode);
    }

    async function inferCourt() {
        if (!inferred || manualCourt) return;
        const generation = ++inferenceGeneration;
        try {
            const params = new URLSearchParams({
                docket_number: caseNumber.value
            });
            const response = await fetch(`${form.dataset.inferenceUrl}?${params}`);
            const result = await response.json();
            if (generation !== inferenceGeneration || manualCourt) return;
            const court = result.success && result.court;
            if (court) {
                inferred.hidden = false;
                manualCourtField.hidden = true;
                if (!Array.from(courtSelect.options).some(option => option.value === court.value)) {
                    courtSelect.add(new Option(court.text, court.value));
                }
                courtSelect.value = court.value;
                inferredCode = court.value;
                document.getElementById("inferred-court-name").textContent = `${gettext("Court identified from your case number:")} ${court.text}`;
            } else {
                if (inferredCode) courtSelect.value = "";
                inferredCode = "";
                await showManualCourt();
            }
            availability.check();
        } catch {
            if (generation !== inferenceGeneration) return;
            if (inferredCode) courtSelect.value = "";
            inferredCode = "";
            await showManualCourt();
            availability.check();
        }
    }
    if (inferred) {
        document.getElementById("change-inferred-court").addEventListener("click", async () => {
            manualCourt = true;
            ++inferenceGeneration;
            // The questions open on the inferred court, so changing it starts
            // from what the filer was just shown.
            await showManualCourt(inferredCode);
            const firstQuestion = guidedCourt && manualCourtField.querySelector("#court-selector input, #court-selector select, #court-selector button");
            (firstQuestion || courtSelect).focus();
        });
        courtSelect.addEventListener("change", () => {
            if (selectorStarting) return;
            manualCourt = true;
            ++inferenceGeneration;
        });
        caseNumber.addEventListener("input", () => {
            ++inferenceGeneration;
            if (!manualCourt && inferredCode) {
                // Wait for the new number to settle the court or not before
                // asking for one.
                courtSelect.value = "";
                inferredCode = "";
                inferred.hidden = true;
            }
            clearTimeout(inferenceTimer);
            inferenceTimer = setTimeout(inferCourt, 250);
        });
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        errorBox.hidden = true;
        state.hidden = false;
        submitButton.disabled = true;

        try {
            if (!courtSelect.value && inferred && !manualCourt) await inferCourt();
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

    loadCourts().then(() => {
        availability.check(courtSelect.closest(".form-field"));
        if (inferred && manualCourt) showManualCourt(selectedCourtCode);
        else inferCourt();
    });
})();