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
        root.querySelector(".review-field__edit").addEventListener("click", () => setMode(key, "edit"));
    });

    function setMode(key, mode) {
        const field = fields[key];
        field.display.hidden = mode !== "found";
        field.input.hidden = mode !== "edit";
    }

    function optionValue(item) {
        return String(item.value ?? item.code ?? item.id ?? "");
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
                "We found a hint in your document, but couldn't match it to an exact choice below." :
                "We couldn't find this in your document.";
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

    const ADVANCE = {
        court: loadCaseCategories,
        case_category: loadCaseTypes,
        case_type: loadFilingTypes,
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
        loadFilingTypes();
    });
    fields.filing_type.select.addEventListener("change", () => {
        fields.filing_type.nameInput.value = fields.filing_type.select.selectedOptions[0]?.textContent || "";
    });

    form.querySelectorAll('input[name="existing_case"]').forEach((radio) => {
        radio.addEventListener("change", () => {
            if (fields.case_type.select.value) loadFilingTypes();
        });
    });

    form.addEventListener("submit", (event) => {
        const isNew = form.querySelector('input[name="existing_case"]:checked')?.value === "new";
        const missing = isNew && (!fields.court.select.value || !fields.case_category.select.value || !fields.case_type.select.value);
        if (missing) {
            event.preventDefault();
            errorBox.textContent = "Choose a court, case category, and case type from the lists to continue.";
            errorBox.hidden = false;
            errorBox.scrollIntoView({
                behavior: "smooth",
                block: "center"
            });
        }
    });

    loadCourts();
})();