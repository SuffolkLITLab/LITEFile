(function() {
    const form = document.getElementById("organize-documents-form");
    const contextElement = document.getElementById("organize-context");
    if (!form || !contextElement) return;

    const context = JSON.parse(contextElement.textContent);
    const list = document.getElementById("organize-list");
    const errorBox = document.getElementById("organize-error");
    const cards = () => Array.from(list.querySelectorAll(".organize-card"));
    let filingTypes = null;

    function optionValue(item) {
        return String(item.value || item.code || item.id || "");
    }

    function optionText(item) {
        return item.text || item.name || item.description || optionValue(item);
    }

    function setOptions(select, options, savedValue, placeholder) {
        select.innerHTML = "";
        if (!options.length) {
            const option = new Option(placeholder, "");
            select.add(option);
            select.disabled = true;
            return;
        }
        select.add(new Option(placeholder, ""));
        options.forEach((item) => {
            const option = new Option(optionText(item), optionValue(item));
            // Some filing types require an amount in controversy; case_questions
            // asks for it later, but only needs to if this is set on the chosen
            // filing type for at least one document in the filing.
            option.dataset.amountInControversyRequired =
                String(item.amountincontroversy || "").toLowerCase() === "required";
            select.add(option);
        });
        select.value = savedValue || "";
        select.disabled = false;
    }

    function setRadioOptions(container, options, savedValue, fieldName, placeholder) {
        container.innerHTML = "";
        if (!options.length) {
            const message = document.createElement("small");
            message.textContent = placeholder;
            container.appendChild(message);
            return;
        }
        options.forEach((item, index) => {
            const label = document.createElement("label");
            const input = document.createElement("input");
            input.className = "form-check-input";
            input.type = "radio";
            input.name = fieldName;
            input.value = optionValue(item);
            input.required = true;
            input.checked = input.value === savedValue || (!savedValue && options.length === 1 && index === 0);
            const text = document.createElement("span");
            text.textContent = optionText(item);
            label.append(input, text);
            container.appendChild(label);
        });
    }

    async function getJson(url) {
        const response = await fetch(url, {
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": apiUtils.getCSRFToken(),
            },
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || "The court's document choices could not be loaded.");
        }
        return result.data || [];
    }

    async function loadFilingTypes() {
        if (filingTypes) return filingTypes;
        const params = new URLSearchParams({
            jurisdiction: context.jurisdiction,
            court: context.court,
            case_category: context.case_category,
            case_type: context.case_type,
            existing_case: context.existing_case,
            guessed_filing_type: context.guessed_filing_type || "",
        });
        filingTypes = await getJson(`/api/dropdowns/filing-types/?${params}`);
        return filingTypes;
    }

    async function loadDependentOptions(card, filingType) {
        const documentType = card.querySelector(".document-type-options");
        const component = card.querySelector(".filing-component-options");
        const documentId = card.dataset.documentId;
        if (!filingType) {
            setRadioOptions(documentType, [], "", `document-type-${documentId}`, "Select a filing type first");
            setRadioOptions(component, [], "", `filing-component-${documentId}`, "Select a filing type first");
            return;
        }

        documentType.innerHTML = "<small>Loading choices…</small>";
        component.innerHTML = "<small>Loading choices…</small>";
        const documentParams = new URLSearchParams({
            jurisdiction: context.jurisdiction,
            court: context.court,
            parent: filingType,
        });
        const componentParams = new URLSearchParams({
            jurisdiction: context.jurisdiction,
            court: context.court,
            filing_type: filingType,
        });
        const [documentTypes, components] = await Promise.all([
            getJson(`/api/dropdowns/document-types/?${documentParams}`),
            getJson(`/api/get-filing-components/?${componentParams}`),
        ]);
        setRadioOptions(
            documentType,
            documentTypes,
            card.dataset.documentType,
            `document-type-${documentId}`,
            "No confidentiality choices are available",
        );

        let savedComponent = card.dataset.filingComponent;
        if (!savedComponent && components.length) {
            const preferredWord = card.dataset.role === "lead" ? "lead" : "attachment";
            const preferred = components.find((item) => optionText(item).toLowerCase().includes(preferredWord));
            savedComponent = optionValue(preferred || components[0]);
        }
        setRadioOptions(
            component,
            components,
            savedComponent,
            `filing-component-${documentId}`,
            "No document roles are available",
        );
    }

    // Keywords for the optional services filers actually look for. Courts can
    // list a dozen+ services (interpreter requests, sealed filings, various
    // process-server fees...); surfacing all of them by default buries the
    // handful people come here for, so only these -- plus anything marked
    // required -- show before the "Show more options" toggle.
    const COMMON_OPTIONAL_SERVICE_KEYWORDS = [
        "certified",
        "copy",
        "copies",
        "expedit",
        "priority",
        "rush",
        "courtesy",
    ];

    function isCommonOptionalService(name) {
        const lower = (name || "").toLowerCase();
        return COMMON_OPTIONAL_SERVICE_KEYWORDS.some((keyword) => lower.includes(keyword));
    }

    function buildOptionalServiceLabel(service, saved) {
        const code = String(service.code ?? service.id ?? "");
        const label = document.createElement("label");
        label.className = "form-check mb-2";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.className = "form-check-input optional-service";
        input.value = code;
        input.checked = Boolean(service.required) || saved.has(code);
        input.disabled = Boolean(service.required);
        const span = document.createElement("span");
        span.className = "form-check-label";
        let text = service.name || service.text || code;
        const fee = parseFloat(service.fee);
        if (fee > 0) text += ` ($${fee.toFixed(2)})`;
        span.textContent = text;
        label.append(input, span);
        return {
            code,
            label
        };
    }

    function appendOptionalService(container, service, saved) {
        const {
            code,
            label
        } = buildOptionalServiceLabel(service, saved);
        if (!code) return;
        container.appendChild(label);
        if (service.description) {
            const description = document.createElement("small");
            description.className = "d-block optional-service-description";
            description.textContent = service.description;
            container.appendChild(description);
        }
    }

    async function loadOptionalServices(card, filingType) {
        const container = card.querySelector(".optional-services-list");
        if (!filingType) {
            container.innerHTML = "<small>Select a filing type first</small>";
            return;
        }
        container.innerHTML = "<small>Loading choices…</small>";
        const params = new URLSearchParams({
            jurisdiction: context.jurisdiction,
            court: context.court,
            filing_type_id: filingType,
        });
        let services;
        try {
            services = await getJson(`/api/dropdowns/optional-services/?${params}`);
        } catch (error) {
            container.innerHTML = "";
            return;
        }
        services = services.filter((service) => service.code ?? service.id);
        if (!services.length) {
            container.innerHTML = "";
            return;
        }

        const saved = new Set((card.dataset.optionalServices || "").split(",").filter(Boolean));
        let primary = services.filter((service) => service.required || isCommonOptionalService(service.name));
        let rest = services.filter((service) => !primary.includes(service));
        if (!primary.length) {
            primary = services.slice(0, 4);
            rest = services.slice(4);
        }

        container.innerHTML = "";
        primary.forEach((service) => appendOptionalService(container, service, saved));

        if (rest.length) {
            const moreContainer = document.createElement("div");
            moreContainer.hidden = true;
            rest.forEach((service) => appendOptionalService(moreContainer, service, saved));

            const toggle = document.createElement("button");
            toggle.type = "button";
            toggle.className = "btn btn-link optional-services-toggle";
            const showMoreText = interpolate(ngettext("Show %s more option", "Show %s more options", rest.length), [rest.length]);
            toggle.textContent = showMoreText;
            toggle.addEventListener("click", () => {
                const wasExpanded = !moreContainer.hidden;
                moreContainer.hidden = wasExpanded;
                toggle.textContent = wasExpanded ? showMoreText : gettext("Show fewer options");
            });

            container.append(toggle, moreContainer);
        }
    }

    async function initializeCard(card) {
        const filingType = card.querySelector(".filing-type");
        setOptions(filingType, await loadFilingTypes(), card.dataset.filingType, "Choose a filing type");
        filingType.addEventListener("change", async () => {
            card.dataset.documentType = "";
            card.dataset.filingComponent = "";
            try {
                await Promise.all([
                    loadDependentOptions(card, filingType.value),
                    loadOptionalServices(card, filingType.value),
                ]);
            } catch (error) {
                showError(error.message);
            }
        });
        await Promise.all([
            loadDependentOptions(card, filingType.value),
            loadOptionalServices(card, filingType.value),
        ]);

        const checkbox = card.querySelector(".courtesy-copy-toggle");
        const emailWrap = card.querySelector(".courtesy-email-wrap");
        const email = card.querySelector(".courtesy-email");
        checkbox.addEventListener("change", () => {
            emailWrap.hidden = !checkbox.checked;
            email.required = checkbox.checked;
            if (!checkbox.checked) email.value = "";
        });
        email.required = checkbox.checked;
    }

    function updatePositions() {
        const supporting = cards().filter((card) => card.dataset.role === "supporting");
        supporting.forEach((card, index) => {
            card.querySelector(".organize-card__position").textContent = `Additional document ${index + 1}`;
            card.querySelector(".move-up").disabled = index === 0;
            card.querySelector(".move-down").disabled = index === supporting.length - 1;
        });
    }

    list.addEventListener("click", (event) => {
        const button = event.target.closest(".move-up, .move-down");
        if (!button) return;
        const card = button.closest(".organize-card");
        const supporting = cards().filter((item) => item.dataset.role === "supporting");
        const index = supporting.indexOf(card);
        if (button.classList.contains("move-up") && index > 0) {
            list.insertBefore(card, supporting[index - 1]);
        } else if (button.classList.contains("move-down") && index < supporting.length - 1) {
            supporting[index + 1].after(card);
        }
        updatePositions();
    });

    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
        errorBox.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        errorBox.hidden = true;
        if (!form.reportValidity()) return;
        const button = document.getElementById("save-document-details");
        button.disabled = true;
        const documents = cards().map((card) => {
            const filingType = card.querySelector(".filing-type");
            const documentType = card.querySelector('.document-type-options input:checked');
            const component = card.querySelector('.filing-component-options input:checked');
            const courtesyEmail = card.querySelector(".courtesy-copy-toggle").checked ?
                card.querySelector(".courtesy-email").value : "";
            const requestedOptionalServices = Array.from(card.querySelectorAll(".optional-service:checked"))
                .map((input) => input.value);
            return {
                id: Number(card.dataset.documentId),
                name: card.querySelector(".document-name").value,
                filing_type: filingType.value,
                filing_type_name: filingType.selectedOptions[0]?.text || "",
                document_type: documentType?.value || "",
                document_type_name: documentType?.closest("label")?.innerText.trim() || "",
                filing_component: component?.value || "",
                filing_component_name: component?.closest("label")?.innerText.trim() || "",
                courtesy_copy_email: courtesyEmail,
                requested_optional_services: requestedOptionalServices,
                requires_amount_in_controversy: filingType.selectedOptions[0]?.dataset.amountInControversyRequired === "true",
            };
        });

        try {
            const response = await fetch(window.location.href, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": apiUtils.getCSRFToken(),
                },
                body: JSON.stringify({
                    documents,
                    main_document_id: Number(form.elements.namedItem("main_document").value),
                    return_to: context.return_to || "",
                }),
            });
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || "Could not save document details.");
            window.location.assign(result.redirect_url);
        } catch (error) {
            showError(error.message);
            button.disabled = false;
        }
    });

    Promise.all(cards().map(initializeCard)).then(updatePositions).catch((error) => showError(error.message));
})();