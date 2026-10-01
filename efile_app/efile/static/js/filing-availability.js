(function() {
    function mount({
        form,
        notice,
        selection
    }) {
        let generation = 0;
        let blocked = true;
        let controller;
        const buttons = Array.from(form.querySelectorAll('button[type="submit"]'));

        function show(message, unavailable) {
            blocked = unavailable;
            notice.textContent = message;
            notice.hidden = !message;
            buttons.forEach((button) => {
                button.disabled = unavailable;
            });
        }

        async function check(anchor) {
            const token = ++generation;
            controller?.abort();
            controller = new AbortController();
            if (anchor) anchor.append(notice);
            const values = selection();
            if (!values.court) {
                show("", false);
                return;
            }
            show(gettext("Checking filing availability…"), true);
            const params = new URLSearchParams({
                jurisdiction: values.jurisdiction,
                court: values.court,
                case_category: values.case_category || "",
                case_type: values.case_type || "",
            });
            (values.filing_types || []).forEach((value) => params.append("filing_type", value));
            try {
                const response = await fetch(`/api/filing-availability/?${params}`, {
                    signal: controller.signal
                });
                const result = await response.json();
                if (!response.ok || !result.success) throw new Error("Availability check failed");
                if (token !== generation) return;
                show(result.message, !result.available);
            } catch (error) {
                if (token !== generation || error.name === "AbortError") return;
                show(gettext("We could not check filing availability. Reload this page to try again."), true);
            }
        }

        // Also guard Enter-key submission while a check is pending or blocked.
        form.addEventListener("submit", (event) => {
            if (!blocked) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            notice.focus();
        }, true);
        return {
            check
        };
    }
    window.filingAvailability = {
        mount
    };
})();