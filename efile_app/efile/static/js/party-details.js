(function() {
    const form = document.getElementById("party-details-form");
    if (!form) return;
    const personFields = form.querySelector(".person-fields");
    const organizationFields = form.querySelector(".organization-fields");

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