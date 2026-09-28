(function() {
    const form = document.getElementById("party-details-form");
    if (!form) return;
    const personFields = form.querySelector(".person-fields");
    const organizationFields = form.querySelector(".organization-fields");
    const addressToggle = document.getElementById("add-party-address");
    const addressFields = document.getElementById("party-address-fields");
    const addressExplainer = document.getElementById("address-explainer");
    const addressExplainerContent = document.getElementById("address-explainer-content");

    function updateAddressFields() {
        if (!addressToggle || !addressFields) return;
        addressFields.hidden = !addressToggle.checked;
        ["address_line_1", "city", "state", "zip_code"].forEach((name) => {
            form.elements.namedItem(name).required = addressToggle.checked;
        });
    }

    if (addressToggle) {
        addressToggle.addEventListener("change", updateAddressFields);
        updateAddressFields();
    }

    // Choosing the filer's own role for someone else asks whether they are
    // on the filer's side. The box is required only while it is showing.
    const sameRole = document.getElementById("same-role-confirm");
    if (sameRole) {
        const confirmBox = document.getElementById("same_role_confirmed");
        const sameRoleError = document.getElementById("same-role-error");
        const filerType = sameRole.dataset.filerPartyType;

        const showSameRoleError = () => {
            sameRoleError.hidden = false;
            sameRole.classList.add("same-role-confirm--invalid");
            confirmBox.setAttribute("aria-invalid", "true");
            confirmBox.setAttribute("aria-describedby", "same-role-help same-role-error");
        };
        const clearSameRoleError = () => {
            sameRoleError.hidden = true;
            sameRole.classList.remove("same-role-confirm--invalid");
            confirmBox.removeAttribute("aria-invalid");
            confirmBox.setAttribute("aria-describedby", "same-role-help");
        };
        const syncSameRole = () => {
            const chosen = form.querySelector('input[name="party_type"]:checked');
            const same = Boolean(chosen) && chosen.value === filerType;
            sameRole.hidden = !same;
            confirmBox.required = same;
            if (!same) {
                confirmBox.checked = false;
                clearSameRoleError();
            }
        };

        form.querySelectorAll('input[name="party_type"]').forEach((radio) => {
            radio.addEventListener("change", syncSameRole);
        });
        confirmBox.addEventListener("invalid", (event) => {
            event.preventDefault();
            showSameRoleError();
            confirmBox.focus();
        });
        confirmBox.addEventListener("change", () => {
            if (confirmBox.checked) clearSameRoleError();
        });
        syncSameRole();
        if (!sameRoleError.hidden) showSameRoleError();
    }

    if (addressExplainer && addressExplainerContent && window.bootstrap) {
        const popover = new window.bootstrap.Popover(addressExplainer, {
            title: addressExplainer.textContent.trim(),
            content: addressExplainerContent.innerHTML,
            html: true,
            trigger: "click",
            placement: "top",
            customClass: "address-explainer-popover"
        });
        document.addEventListener("click", (event) => {
            const inside = addressExplainer.contains(event.target) || event.target.closest(".address-explainer-popover");
            if (!inside) popover.hide();
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") popover.hide();
        });
    }

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