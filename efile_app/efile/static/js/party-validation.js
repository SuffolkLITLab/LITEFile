// Rules originate in court metadata. Server validation also runs without JS.
(() => {
    const data = document.getElementById("party-validation-rules");
    if (!data) return;
    const form = document.getElementById("your-information-form") || document.getElementById("party-details-form");
    const rules = JSON.parse(data.textContent);
    const normalizePhone = (value) => {
        let normalized = value.replace(/[-()]/g, "").trim();
        if (normalized.includes("+")) {
            if (normalized.startsWith("+1") || normalized.startsWith("+0")) {
                normalized = normalized.replaceAll("+1", "+1 ").replaceAll("+0", "+0 ");
            }
            return normalized;
        }
        return normalized.replaceAll(" ", "");
    };
    const validate = (field, rule) => {
        const input = form.elements.namedItem(field);
        if (!input) return;
        if (input.disabled || input.closest("[hidden]")) {
            input.setCustomValidity("");
            return;
        }
        let invalid = false;
        if (input.value && rule.regex) {
            try {
                // No "u" flag: it rejects identity escapes such as \- that
                // portable_regex accepts and Python treats as literals.
                const regex = new RegExp(rule.regex);
                invalid = !regex.test(input.value) && !(field === "phone" && regex.test(normalizePhone(input.value)));
            } catch {
                /* Java expressions unsupported by this browser stay server validated. */
            }
        }
        const message = invalid ? rule.message : "";
        input.setCustomValidity(message);
        input.setAttribute("aria-invalid", String(invalid));
        const feedback = document.getElementById(`error_${field}`);
        if (feedback) {
            feedback.textContent = message;
            feedback.hidden = !message;
        }
    };
    Object.entries(rules).forEach(([field, rule]) => {
        const input = form.elements.namedItem(field);
        if (!input) return;
        if (rule.required && ["email", "phone"].includes(field)) input.required = true;
        input.addEventListener("input", () => validate(field, rule));
        input.addEventListener("blur", () => validate(field, rule));
        // Pre-filled/extracted values deserve the same validation as typing.
        validate(field, rule);
    });
    form.addEventListener("submit", (event) => {
        Object.entries(rules).forEach(([field, rule]) => validate(field, rule));
        if (!form.checkValidity()) {
            event.preventDefault();
            form.reportValidity();
        }
    });
    // Clear validity on hidden name fields when switching to an organization.
    form.addEventListener("change", () => {
        Object.entries(rules).forEach(([field, rule]) => validate(field, rule));
    });
    document.addEventListener("DOMContentLoaded", () => {
        const field = new URLSearchParams(window.location.search).get("focus");
        // Only addressable form fields; never interpret a URL as a selector.
        const id = field === "suffix" ? "suffix" : `id_${field}`;
        const input = field ? document.getElementById(id) : null;
        if (input && form.contains(input)) {
            const address = input.closest("#party-address-fields");
            if (address?.hidden) {
                const toggle = document.getElementById("add-party-address");
                toggle.checked = true;
                toggle.dispatchEvent(new Event("change"));
            }
            input.focus();
        }
    });
})();