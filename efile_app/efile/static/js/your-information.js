(function() {
    const form = document.getElementById("your-information-form");
    if (!form) return;

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