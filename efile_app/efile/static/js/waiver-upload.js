/* global PaymentPage, paymentJSON */
/* Add a supporting waiver PDF without leaving payment or changing the lead. */
document.addEventListener("DOMContentLoaded", () => {
    const open = document.getElementById("add-waiver-document");
    if (!open) return;
    const panel = document.getElementById("waiver-upload-panel");
    const filing = document.getElementById("waiver-filing-type");
    const confidentiality = document.getElementById("waiver-document-type");
    const file = document.getElementById("waiver-file");
    const upload = document.getElementById("upload-waiver-document");
    const status = document.getElementById("waiver-upload-status");
    let version = 0;
    let uploading = false;
    const url = () => window.withFilingDraft(open.dataset.url);
    const fill = (select, options, selected) => {
        select.replaceChildren();
        for (const item of options) {
            const option = document.createElement("option");
            option.value = item.code;
            option.textContent = item.name;
            select.appendChild(option);
        }
        select.value = selected;
    };
    const load = async (code = "") => {
        const current = ++version;
        upload.disabled = true;
        confidentiality.disabled = true;
        status.textContent = gettext("Loading court choices…");
        try {
            const endpoint = new URL(url(), window.location.origin);
            if (code) endpoint.searchParams.set("filing_type", code);
            const response = await fetch(endpoint, {
                credentials: "same-origin"
            });
            const data = await response.json();
            if (current !== version) return;
            if (!response.ok) throw new Error(data.error || gettext("Could not load court choices. Try again."));
            fill(filing, data.filing_types, data.selected);
            const choices = data.document_types;
            // Never silently choose Public when the court offers alternatives.
            const chosen = choices.length === 1 ? choices[0].code : "";
            fill(confidentiality, chosen ? choices : [{
                code: "",
                name: gettext("Choose a setting")
            }, ...choices], chosen);
            confidentiality.disabled = false;
            upload.disabled = false;
            status.textContent = "";
        } catch (error) {
            if (current === version) status.textContent = error.message;
        }
    };
    open.addEventListener("click", () => {
        panel.hidden = false;
        open.setAttribute("aria-expanded", "true");
        load().then(() => filing.focus());
    });
    filing.addEventListener("change", () => load(filing.value));
    upload.addEventListener("click", async () => {
        if (uploading) return;
        if (!file.files.length || !confidentiality.value) {
            status.textContent = gettext("Choose a PDF or Word document and a confidentiality setting.");
            (!file.files.length ? file : confidentiality).focus();
            return;
        }
        const body = new FormData();
        body.append("document", file.files[0]);
        body.append("filing_type", filing.value);
        body.append("document_type", confidentiality.value);
        body.append("fee_inputs_token", paymentJSON("fee-inputs-token"));
        body.append("csrfmiddlewaretoken", apiUtils.getCSRFToken());
        uploading = true;
        PaymentPage.waiverUploading = true;
        PaymentPage.setFeesState(false);
        for (const element of [open, upload, filing, confidentiality, file]) element.disabled = true;
        status.textContent = gettext("Uploading document…");
        try {
            const response = await fetch(url(), {
                method: "POST",
                body,
                credentials: "same-origin"
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || gettext("The upload failed. Try again."));
            if (data.preview_url) {
                window.location.assign(window.withFilingDraft(data.preview_url));
                return;
            }
            document.getElementById("fee-inputs-token").textContent = JSON.stringify(data.fee_inputs_token);
            document.getElementById("waiver-upload-required").hidden = true;
            const confirmation = document.getElementById("waiver-upload-confirmation");
            confirmation.hidden = false;
            confirmation.focus();
            // Old requests and quotes described a different set of documents.
            await PaymentPage.chooseIntent();
        } catch (error) {
            status.textContent = error.message;
        } finally {
            uploading = false;
            PaymentPage.waiverUploading = false;
            for (const element of [open, upload, filing, confidentiality, file]) element.disabled = false;
            PaymentPage.setFeesState(false);
        }
    });
});