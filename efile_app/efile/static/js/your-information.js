(function() {
    const form = document.getElementById("your-information-form");
    if (!form) return;

    // A suffix has to exactly match one of the court's own codes, so it's a
    // dropdown fed from the court rather than free text. If it can't load
    // (no court yet, network error), fall back to just the saved value so
    // nothing already on the draft gets silently dropped.
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

    // The server fills these in before the page renders when it can reach the
    // filer's account. Fetching again would cost a request to show values that
    // are already on screen.
    if (form.dataset.profilePrefilled === "1") return;

    const fieldMap = {
        first_name: "first_name",
        last_name: "last_name",
        address_line_1: "address",
        address_line_2: "address_line2",
        city: "city",
        state: "state",
        zip_code: "zip",
        email: "email",
        phone: "phone",
    };
    const params = new URLSearchParams({
        jurisdiction: apiUtils.getCurrentJurisdiction()
    });
    fetch(`/api/auth/profile/?${params}`, {
            headers: {
                "X-CSRFToken": apiUtils.getCSRFToken()
            }
        })
        .then((response) => response.json())
        .then((result) => {
            if (!result.success || !result.data) return;
            Object.entries(fieldMap).forEach(([fieldName, profileKey]) => {
                const input = form.elements.namedItem(fieldName);
                if (input && !input.value) input.value = result.data[profileKey] || "";
            });
        })
        .catch(() => {});
})();