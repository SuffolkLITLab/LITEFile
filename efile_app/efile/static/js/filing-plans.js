// Offer the filer's own court cases as things a plan can be linked to.
//
// Tyler identifies a case by a tracking ID that no one can be expected to type,
// so the only honest way to link one is to pick it from cases the filer already
// has. The list comes from their accepted filings.
(function() {
    const pickers = document.querySelectorAll(".plan-case-picker");
    if (!pickers.length) return;

    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";

    function escapeHtml(value) {
        const element = document.createElement("span");
        element.textContent = value ?? "";
        return element.innerHTML;
    }

    async function acceptedCases() {
        const since = new Date();
        since.setFullYear(since.getFullYear() - 5);
        const response = await apiUtils.get("/api/filings", {
            start_date: since.toISOString().split("T")[0]
        }, true);
        const filings = response.data || [];

        let courtNames = {};
        try {
            const courts = (await apiUtils.get("/api/dropdowns/courts")).data || [];
            courtNames = courts.reduce((names, court) => {
                names[court.value] = court.text;
                return names;
            }, {});
        } catch (error) {
            console.warn("Could not load court names:", error);
        }

        // One case can have many filings; the filer is choosing the case.
        const cases = new Map();
        for (const filing of filings) {
            if (filing.filing_status !== "accepted") continue;
            if (!filing.case_tracking_id || !filing.case_number) continue;
            if (cases.has(filing.case_tracking_id)) continue;
            cases.set(filing.case_tracking_id, {
                case_tracking_id: filing.case_tracking_id,
                docket_number: filing.case_number,
                case_title: filing.case_title || "",
                court_code: filing.court_code || "",
                court_name: courtNames[filing.court_code] || ""
            });
        }
        return [...cases.values()];
    }

    function caseFormHtml(planId, courtCase) {
        return `
      <form method="post" class="plan-case-option">
        <input type="hidden" name="csrfmiddlewaretoken" value="${escapeHtml(csrfToken)}" />
        <input type="hidden" name="action" value="link_case" />
        <input type="hidden" name="plan_id" value="${escapeHtml(planId)}" />
        <input type="hidden" name="case_tracking_id" value="${escapeHtml(courtCase.case_tracking_id)}" />
        <input type="hidden" name="court_name" value="${escapeHtml(courtCase.court_name)}" />
        <span>
          <strong>${escapeHtml(courtCase.docket_number)}</strong>
          <small>${escapeHtml([courtCase.case_title, courtCase.court_name].filter(Boolean).join(" · "))}</small>
        </span>
        <button class="btn btn-outline-primary btn-sm" type="submit">${gettext("Use this case")}</button>
      </form>`;
    }

    acceptedCases().then((cases) => {
        pickers.forEach((picker) => {
            if (!cases.length) {
                picker.innerHTML = `<p class="text-muted">${gettext(
                    "You have no accepted court cases yet. Once the court accepts a filing, its case will show up here."
                )}</p>`;
                return;
            }
            picker.innerHTML = cases.map((courtCase) => caseFormHtml(picker.dataset.planId, courtCase)).join("");
        });
    }).catch((error) => {
        console.warn("Could not load your court cases:", error);
        pickers.forEach((picker) => {
            picker.innerHTML = `<p class="text-muted">${gettext("We could not load your court cases right now.")}</p>`;
        });
    });
})();