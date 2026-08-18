(function() {
    const contextEl = document.getElementById("extraction-context");
    const form = document.getElementById("extraction-review-form");
    if (!contextEl || !form) return;

    const context = JSON.parse(contextEl.textContent);
    const guesses = context.guesses || {};
    const errorBox = document.getElementById("extraction-review-error");

    const fields = {
        court: {
            select: document.getElementById("court_code"),
            nameInput: document.getElementById("court_name"),
            guessKey: "court",
            savedCode: context.court_code,
        },
        case_category: {
            select: document.getElementById("case_category_code"),
            nameInput: document.getElementById("case_category_name"),
            guessKey: "case category",
            savedCode: context.case_category_code,
        },
        case_type: {
            select: document.getElementById("case_type_code"),
            nameInput: document.getElementById("case_type_name"),
            guessKey: "case type",
            savedCode: context.case_type_code,
        },
        filing_type: {
            select: document.getElementById("filing_type_code"),
            nameInput: document.getElementById("filing_type_name"),
            guessKey: "filing type",
            savedCode: context.filing_type_code,
        },
    };

    Object.entries(fields).forEach(([key, field]) => {
        const root = field.select.closest(".review-field");
        field.display = root.querySelector(".review-field__display");
        field.input = root.querySelector(".review-field__input");
        field.valueEl = root.querySelector(".review-field__value");
        field.hint = root.querySelector(".review-field__hint");
        root.querySelector(".review-field__edit").addEventListener("click", () => {
            setMode(key, "edit");
            // The Edit button lives inside the display panel that setMode just
            // hid, so without this the click would strand focus on <body>.
            field.select.focus();
        });
    });

    function setMode(key, mode) {
        const field = fields[key];
        field.display.hidden = mode !== "found";
        field.input.hidden = mode !== "edit";
    }

    function optionValue(item) {
        return String(item.value ?? item.code ?? item.id ?? "");
    }

    function escapeHtml(value) {
        const holder = document.createElement("span");
        holder.textContent = value ?? "";
        return holder.innerHTML;
    }

    function optionText(item) {
        return (item.text || item.name || optionValue(item)).replace(/\s*\(Recommended\)$/, "");
    }

    async function getJson(url) {
        const response = await fetch(url, {
            headers: {
                "X-CSRFToken": apiUtils.getCSRFToken()
            }
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || "Could not load choices from the court.");
        }
        return result.data || [];
    }

    const PLACEHOLDERS = {
        court: "Choose a court",
        case_category: "Choose a court first",
        case_type: "Choose a case category first",
        filing_type: "Choose a case type first",
    };

    const DOWNSTREAM = {
        court: ["case_category", "case_type", "filing_type"],
        case_category: ["case_type", "filing_type"],
        case_type: ["filing_type"],
        filing_type: [],
    };

    function resetField(key, placeholder) {
        const field = fields[key];
        field.select.innerHTML = `<option value="">${placeholder}</option>`;
        field.select.disabled = true;
        field.nameInput.value = "";
        field.hint.textContent = "";
        setMode(key, "edit");
    }

    function resetDownstream(key) {
        DOWNSTREAM[key].forEach((child) => resetField(child, PLACEHOLDERS[child]));
    }

    function existingCaseWire() {
        const checked = form.querySelector('input[name="existing_case"]:checked');
        return checked && checked.value === "existing" ? "yes" : "no";
    }

    async function populate(key, options, placeholder) {
        const field = fields[key];
        field.select.innerHTML = `<option value="">${placeholder}</option>`;
        options.forEach((item) => {
            const opt = new Option(optionText(item), optionValue(item));
            if (item.recommended || item.selected || item.default) opt.dataset.recommended = "true";
            field.select.add(opt);
        });
        field.select.disabled = options.length === 0;

        const recommended = Array.from(field.select.options).find((o) => o.dataset.recommended);
        const savedOption = field.savedCode ?
            Array.from(field.select.options).find((o) => o.value === field.savedCode) :
            null;
        const chosen = savedOption || recommended;

        if (chosen) {
            field.select.value = chosen.value;
            field.nameInput.value = chosen.textContent;
            field.valueEl.textContent = chosen.textContent;
            setMode(key, "found");
            await ADVANCE[key]();
        } else {
            field.hint.textContent = guesses[field.guessKey] ?
                "We found a hint in your document, but we could not match it to a choice below." :
                "We could not find this in your document.";
            setMode(key, "edit");
        }
    }

    async function loadCourts() {
        const field = fields.court;
        field.select.disabled = true;
        field.select.innerHTML = "<option value=\"\">Loading courts…</option>";
        try {
            const options = await getJson(`/api/dropdowns/courts/?${new URLSearchParams({
                jurisdiction: context.jurisdiction,
                guessed_court: guesses.court || "",
            })}`);
            await populate("court", options, PLACEHOLDERS.court);
        } catch (error) {
            resetField("court", PLACEHOLDERS.court);
            field.select.disabled = false;
            field.hint.textContent = error.message;
        }
    }

    async function loadCaseCategories() {
        const courtCode = fields.court.select.value;
        resetDownstream("case_category");
        if (!courtCode) {
            resetField("case_category", PLACEHOLDERS.case_category);
            return;
        }
        const field = fields.case_category;
        field.select.disabled = true;
        field.select.innerHTML = "<option value=\"\">Loading case categories…</option>";
        try {
            const options = await getJson(`/api/dropdowns/case-categories/?${new URLSearchParams({
                jurisdiction: context.jurisdiction,
                court: courtCode,
                guessed_case_category: guesses["case category"] || "",
            })}`);
            await populate("case_category", options, "Choose a case category");
        } catch (error) {
            resetField("case_category", "Choose a case category");
            field.select.disabled = false;
            field.hint.textContent = error.message;
        }
    }

    async function loadCaseTypes() {
        const courtCode = fields.court.select.value;
        const categoryCode = fields.case_category.select.value;
        resetDownstream("case_type");
        if (!courtCode || !categoryCode) {
            resetField("case_type", PLACEHOLDERS.case_type);
            return;
        }
        const field = fields.case_type;
        field.select.disabled = true;
        field.select.innerHTML = "<option value=\"\">Loading case types…</option>";
        try {
            const options = await getJson(`/api/dropdowns/case-types/?${new URLSearchParams({
                jurisdiction: context.jurisdiction,
                court: courtCode,
                parent: categoryCode,
                guessed_case_type: guesses["case type"] || "",
            })}`);
            await populate("case_type", options, "Choose a case type");
        } catch (error) {
            resetField("case_type", "Choose a case type");
            field.select.disabled = false;
            field.hint.textContent = error.message;
        }
    }

    async function loadFilingTypes() {
        const courtCode = fields.court.select.value;
        const categoryCode = fields.case_category.select.value;
        const typeCode = fields.case_type.select.value;
        resetDownstream("filing_type");
        if (!courtCode || !categoryCode || !typeCode) {
            resetField("filing_type", PLACEHOLDERS.filing_type);
            return;
        }
        const field = fields.filing_type;
        field.select.disabled = true;
        field.select.innerHTML = "<option value=\"\">Loading filing types…</option>";
        try {
            const options = await getJson(`/api/dropdowns/filing-types/?${new URLSearchParams({
                jurisdiction: context.jurisdiction,
                court: courtCode,
                case_category: categoryCode,
                case_type: typeCode,
                existing_case: existingCaseWire(),
                guessed_filing_type: guesses["filing type"] || "",
            })}`);
            await populate("filing_type", options, "Choose a filing type");
        } catch (error) {
            resetField("filing_type", "Choose a filing type");
            field.select.disabled = false;
            field.hint.textContent = error.message;
        }
    }

    // Which side of the case the filer is on. Only some case types have sides
    // -- an eviction is two different filings depending on who is making it --
    // and which ones depends on the case type chosen above, so the question
    // appears and disappears with it.
    const roleField = document.getElementById("filer-role-field");
    const roleOptions = document.getElementById("filer-role-options");
    let savedRole = context.filer_role || "";

    function chosenRole() {
        return roleOptions.querySelector('input[name="filer_role"]:checked')?.value || "";
    }

    function roleOptionHtml(role) {
        const hint = role.suggested && !savedRole ?
            ` <em class="filer-role__hint">${gettext("probably you, from the document you uploaded")}</em>` :
            "";
        const description = role.description ? `<small>${escapeHtml(role.description)}</small>` : "";
        return `
      <label>
        <input type="radio" name="filer_role" value="${escapeHtml(role.id)}"${role.id === savedRole ? " checked" : ""} />
        <span><strong>${escapeHtml(role.label)}${hint}</strong>${description}</span>
      </label>`;
    }

    async function loadFilerRoles() {
        // Keep an answer the filer already gave while they edit other fields.
        savedRole = chosenRole() || savedRole;
        const caseTypeName = fields.case_type.nameInput.value;
        if (!caseTypeName) {
            roleField.hidden = true;
            roleOptions.innerHTML = "";
            return;
        }
        let roles = [];
        try {
            roles = await getJson(`/api/filer-roles/?${new URLSearchParams({
                jurisdiction: context.jurisdiction,
                court: fields.court.select.value,
                case_category_name: fields.case_category.nameInput.value,
                case_type_name: caseTypeName,
                filing_type_name: fields.filing_type.nameInput.value,
            })}`);
        } catch (error) {
            // A case type with no sides is the norm, and so is the answer to
            // this call being nothing. Failing quietly leaves the filer with
            // the screen they had before, rather than an error about a
            // question most cases never ask.
            console.warn("Could not load the sides of this case:", error);
        }
        roleOptions.innerHTML = roles.map(roleOptionHtml).join("");
        roleField.hidden = roles.length === 0;
    }

    async function loadFilingTypesAndRoles() {
        await loadFilingTypes();
        await loadFilerRoles();
    }

    const ADVANCE = {
        court: loadCaseCategories,
        case_category: loadCaseTypes,
        case_type: loadFilingTypesAndRoles,
        filing_type: async () => {},
    };

    fields.court.select.addEventListener("change", () => {
        fields.court.nameInput.value = fields.court.select.selectedOptions[0]?.textContent || "";
        loadCaseCategories();
    });
    fields.case_category.select.addEventListener("change", () => {
        fields.case_category.nameInput.value = fields.case_category.select.selectedOptions[0]?.textContent || "";
        loadCaseTypes();
    });
    fields.case_type.select.addEventListener("change", () => {
        fields.case_type.nameInput.value = fields.case_type.select.selectedOptions[0]?.textContent || "";
        loadFilingTypesAndRoles();
    });
    fields.filing_type.select.addEventListener("change", () => {
        fields.filing_type.nameInput.value = fields.filing_type.select.selectedOptions[0]?.textContent || "";
        loadFilerRoles();
    });

    form.querySelectorAll('input[name="existing_case"]').forEach((radio) => {
        radio.addEventListener("change", () => {
            if (fields.case_type.select.value) loadFilingTypesAndRoles();
        });
    });

    // Tyler rejects a docket/case number on a new case ("doesn't allow
    // subsequent filing into non-indexed cases"), so keep the field out of
    // the way unless the filer is sure they have one.
    const docketToggleWrap = document.getElementById("docket-number-toggle");
    const docketCheckbox = document.getElementById("has-docket-number");
    const docketInput = document.getElementById("docket_number");
    const docketHint = document.getElementById("docket-number-hint");

    function updateDocketNumberVisibility() {
        const existingCase = form.querySelector('input[name="existing_case"]:checked')?.value;
        if (existingCase === "existing") {
            docketToggleWrap.hidden = true;
            docketInput.hidden = false;
            docketHint.hidden = false;
            return;
        }
        docketToggleWrap.hidden = false;
        const show = docketCheckbox.checked;
        docketInput.hidden = !show;
        docketHint.hidden = !show;
        if (!show) docketInput.value = "";
    }

    docketCheckbox.addEventListener("change", updateDocketNumberVisibility);
    form.querySelectorAll('input[name="existing_case"]').forEach((radio) => {
        radio.addEventListener("change", updateDocketNumberVisibility);
    });
    if (docketInput.value.trim()) docketCheckbox.checked = true;
    updateDocketNumberVisibility();

    form.addEventListener("submit", (event) => {
        const isNew = form.querySelector('input[name="existing_case"]:checked')?.value === "new";
        const missingCase = isNew && (!fields.court.select.value || !fields.case_category.select.value || !fields.case_type.select.value);
        const missingRole = !roleField.hidden && !chosenRole();
        if (!missingCase && !missingRole) return;

        event.preventDefault();
        errorBox.textContent = missingCase ?
            "Choose a court, case category, and case type from the lists to continue." :
            "Choose which side of this case you are on to continue.";
        errorBox.hidden = false;
        (missingCase ? errorBox : roleField).scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    });

    loadCourts();
})();