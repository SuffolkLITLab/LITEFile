(function() {
    const form = document.getElementById("party-details-form");
    if (!form) return;
    const personFields = form.querySelector(".person-fields");
    const organizationFields = form.querySelector(".organization-fields");

    // A suffix has to exactly match one of the court's own codes, so it's a
    // dropdown fed from the court rather than free text. If it can't load
    // (no court yet, network error), fall back to just the saved value so
    // nothing already on this party gets silently dropped.
    const suffixSelect = document.getElementById("suffix");
    if (suffixSelect) {
        const court = form.dataset.court;
        const selected = suffixSelect.dataset.selected || "";
        if (court) {
            fetch(`/api/dropdowns/name-suffixes/?${new URLSearchParams({
                jurisdiction: apiUtils.getCurrentJurisdiction(),
                court
            })}`, {
                    headers: {
                        "X-CSRFToken": apiUtils.getCSRFToken()
                    }
                })
                .then((response) => response.json())
                .then((result) => {
                    if (!result.success) return;
                    (result.data || []).forEach((option) => {
                        suffixSelect.add(new Option(option.text, option.value));
                    });
                    if (selected && !suffixSelect.querySelector(`option[value="${selected}"]`)) {
                        suffixSelect.add(new Option(selected, selected));
                    }
                    suffixSelect.value = selected;
                })
                .catch(() => {});
        } else if (selected) {
            suffixSelect.add(new Option(selected, selected));
            suffixSelect.value = selected;
        }
    }

    function updateKind() {
        const kind = form.elements.namedItem("party_kind").value;
        const isOrganization = kind === "organization";
        personFields.hidden = isOrganization;
        organizationFields.hidden = !isOrganization;
        form.elements.namedItem("first_name").required = !isOrganization;
        form.elements.namedItem("last_name").required = !isOrganization;
        form.elements.namedItem("organization_name").required = isOrganization;
    }

    form.querySelectorAll('input[name="party_kind"]').forEach((radio) => radio.addEventListener("change", updateKind));
    updateKind();
})();