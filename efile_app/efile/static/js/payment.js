const PAYMENT_URLS = {
    accounts: "/api/payment-accounts/",
    accountTypes: "/api/payment-account-types/",
    token: "/api/auth/tyler-token/",
    fees: "/api/payment-fees/",
    waiver: "/api/waiver-account/"
};

// Tyler sends Active as a JAXB element ({value: true, ...}), not a bare boolean.
const isActive = (account) => {
    const active = account.active?.value ?? account.active;
    return active !== false && active !== "false";
};

const paymentJSON = (id) => {
    const element = document.getElementById(id);
    return element ? JSON.parse(element.textContent) : {};
};

const paymentMessages = {
    hide() {
        document.getElementById("errorMessage").hidden = true;
        document.getElementById("successMessage").hidden = true;
    },
    showError(message) {
        document.getElementById("errorText").textContent = message;
        const box = document.getElementById("errorMessage");
        box.hidden = false;
        box.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    },
    showSuccess(message) {
        document.getElementById("successText").textContent = message;
        document.getElementById("successMessage").hidden = false;
    }
};
window.Messages = paymentMessages;

const escapeHTML = (value) => {
    const span = document.createElement("span");
    span.textContent = String(value || "");
    return span.innerHTML;
};

const escapeAttribute = (value) => escapeHTML(value).replaceAll('"', "&quot;").replaceAll("'", "&#39;");

const PaymentPage = {
    caseData: paymentJSON("case-data"),
    feeQuoteReady: false,
    // code -> the court's own name for that account type (e.g. "CC" -> "Credit
    // Card"), fetched from GetPaymentAccountTypeList. Populated by
    // loadAccountTypes(); empty if that call fails, which just means the
    // generic fallback in accountLabel() is used instead.
    typeDescriptions: {},

    setFeesState(loading) {
        document.getElementById("loadingSpinner").style.display = loading ? "block" : "none";
        document.getElementById("submitButton").disabled = loading || !this.feeQuoteReady || !document.getElementById("selected-payment-account").value;
    },

    async loadAccountTypes() {
        try {
            const result = await apiUtils.fetchJSON(PAYMENT_URLS.accountTypes, "GET", {
                jurisdiction: apiUtils.getCurrentJurisdiction()
            });
            const types = result?.success ? result.data : [];
            (types || []).forEach((type) => {
                if (type.code) this.typeDescriptions[type.code] = type.description || type.code;
            });
        } catch {
            // The court's own type names are a nicety, not a requirement --
            // accountLabel() falls back to the account's own name if this
            // list never loads.
        }
    },

    // Tyler's payment accounts aren't all cards -- assuming so mislabeled
    // waivers, ACH/bank accounts, and firm balances alike as "Card ending in
    // ****". Only claim "card" when the account actually carries card data;
    // otherwise use the court's own name for the account type, falling back
    // to whatever Tyler calls the account if that type list didn't load.
    accountLabel(account, waiverCount) {
        if (account.paymentAccountTypeCode === "WV") {
            return waiverCount > 1 ? `${gettext("Payment waiver")}: ${account.accountName}` : gettext("Payment waiver");
        }
        if (account.cardLast4) {
            return `${account.cardType?.value || gettext("Card")} ${gettext("ending in")} ${account.cardLast4}`;
        }
        const typeName = this.typeDescriptions[account.paymentAccountTypeCode];
        if (typeName && account.accountName) return `${typeName}: ${account.accountName}`;
        return typeName || account.accountName || gettext("Payment account");
    },

    async loadAccounts() {
        const result = await apiUtils.fetchJSON(PAYMENT_URLS.accounts, "GET", {
            jurisdiction: apiUtils.getCurrentJurisdiction()
        });
        if (!result?.success || !Array.isArray(result.data)) throw new Error("Account lookup failed");
        this.accounts = result.data.filter((account) => isActive(account));
        const saved = paymentJSON("selected-payment-account-id");
        const account = this.accounts.find((item) => String(item.paymentAccountID) === String(saved));
        if (document.querySelector('input[name="paymentIntent"]:checked')) return;
        let intent = account ? "pay" : "";
        if (account?.paymentAccountTypeCode === "WV") intent = "waiver";
        if (new URLSearchParams(window.location.search).get("payment_status") === "success") intent = "pay";
        if (intent) {
            document.querySelector(`input[name="paymentIntent"][value="${intent}"]`).checked = true;
            await this.chooseIntent();
        }
    },

    async chooseIntent() {
        const intent = document.querySelector('input[name="paymentIntent"]:checked')?.value;
        const requestId = this.quoteRequestId = (this.quoteRequestId || 0) + 1;
        this.feeQuoteReady = false;
        document.getElementById("selected-payment-account").value = "";
        document.getElementById("paymentSection").hidden = true;
        const container = document.getElementById("paymentMethodsContainer");
        container.innerHTML = "";
        paymentMessages.hide();
        this.setFeesState(false);
        document.getElementById("waiverHelp").hidden = intent !== "waiver";
        if (intent === "waiver") return this.chooseWaiver(requestId);
        if (intent === "pay") return this.choosePaidAccount(requestId);
    },

    async chooseWaiver(requestId) {
        this.setFeesState(true);
        try {
            // Share an in-flight creation when someone toggles back and forth.
            this.waiverRequest ||= apiUtils.post(PAYMENT_URLS.waiver, {
                preferred_id: paymentJSON("selected-payment-account-id") || ""
            }, {
                jurisdiction: apiUtils.getCurrentJurisdiction()
            });
            const result = await this.waiverRequest;
            if (!result?.success || !result.data?.paymentAccountID) throw new Error("Waiver setup failed");
            if (requestId !== this.quoteRequestId) return;
            const account = result.data;
            document.getElementById("selected-payment-account").value = account.paymentAccountID;
            document.getElementById("selected-payment-account-name").value = account.accountName;
            document.getElementById("selected-payment-account-type").value = "WV";
            this.feeQuoteReady = true;
        } catch {
            this.waiverRequest = null;
            if (requestId !== this.quoteRequestId) return;
            paymentMessages.showError(gettext("We could not set up your waiver account. Please try again."));
            this.showChoiceRetry();
        } finally {
            if (requestId === this.quoteRequestId) this.setFeesState(false);
        }
    },

    async choosePaidAccount(requestId) {
        const container = document.getElementById("paymentMethodsContainer");
        try {
            // A lookup failure is not evidence that there are no accounts.
            const result = await apiUtils.fetchJSON(PAYMENT_URLS.accounts, "GET", {
                jurisdiction: apiUtils.getCurrentJurisdiction()
            });
            if (requestId !== this.quoteRequestId) return;
            if (!result?.success || !Array.isArray(result.data)) throw new Error("Account lookup failed");
            const accounts = result.data.filter((account) => account.paymentAccountTypeCode !== "WV" && isActive(account));
            const saved = paymentJSON("selected-payment-account-id");
            const selectedId = accounts.some((account) => String(account.paymentAccountID) === String(saved)) ? saved : accounts[0]?.paymentAccountID;
            const rows = accounts.map((account) => {
                const label = this.accountLabel(account, 0);
                return `<label><input class="form-check-input" type="radio" name="paymentMethod" value="${escapeAttribute(account.paymentAccountID)}" data-name="${escapeAttribute(label)}" data-type="${escapeAttribute(account.paymentAccountTypeCode || "")}" ${String(selectedId) === String(account.paymentAccountID) ? "checked" : ""}/> <span><strong>${escapeHTML(label)}</strong></span></label>`;
            }).join("");
            container.innerHTML = `<div class="compact-choice-list">${rows}</div>
                <button type="button" class="btn btn-outline-primary mt-2" id="add-payment-method">${gettext("Add credit or bank account")}</button>`;
            container.querySelectorAll('input[name="paymentMethod"]').forEach((input) => {
                input.addEventListener("change", () => this.selectAndQuote());
            });
            document.getElementById("add-payment-method").addEventListener("click", () => this.addAccount());
            if (accounts.length) await this.selectAndQuote();
        } catch {
            if (requestId === this.quoteRequestId) {
                paymentMessages.showError(gettext("We could not load payment methods. Please try again."));
                this.showChoiceRetry();
            }
        }
    },

    showChoiceRetry() {
        const container = document.getElementById("paymentMethodsContainer");
        container.innerHTML = `<button type="button" class="btn btn-outline-primary" id="retry-payment-choice">${gettext("Try again")}</button>`;
        document.getElementById("retry-payment-choice").addEventListener("click", () => this.chooseIntent());
    },

    async selectAndQuote() {
        const selected = document.querySelector('input[name="paymentMethod"]:checked');
        if (!selected) return;
        this.quoteRequestId = (this.quoteRequestId || 0) + 1;
        const currentRequestId = this.quoteRequestId;
        document.getElementById("selected-payment-account").value = selected.value;
        document.getElementById("selected-payment-account-name").value = selected.dataset.name;
        document.getElementById("selected-payment-account-type").value = selected.dataset.type || "";
        document.getElementById("paymentSection").hidden = true;
        this.feeQuoteReady = false;
        paymentMessages.hide();
        this.setFeesState(true);
        try {
            const uploadData = await apiUtils.getUploadData();
            if (currentRequestId !== this.quoteRequestId) return;
            const userData = FilingPayload.userDataFromCaseData(this.caseData);
            const efileData = this.buildEFilingData(userData, this.caseData, uploadData, selected.value);
            const result = await apiUtils.post(PAYMENT_URLS.fees, {
                efile_data: efileData,
                confirm_submission: true,
                payment_account_id: selected.value,
                fee_inputs_token: paymentJSON("fee-inputs-token")
            }, {}, {
                timeout: ApiUtils.FEE_TIMEOUT_MS
            });
            if (currentRequestId !== this.quoteRequestId) return;
            // The server keeps the quote for Review once it can read a total
            // from it; one it could not read is not a quote to go on with.
            this.feeQuoteReady = Boolean(result?.success && result.quote_recorded);
            this.handleFeesResponse(result);
            if (result?.success && result.quote_superseded) {
                paymentMessages.showError(gettext("This filing changed while we were calculating fees, perhaps in another window. Reload this page to calculate them again."));
            } else if (result?.success && !result.quote_recorded) {
                paymentMessages.showError(gettext("The court did not return a fee total for this filing. Try again, or contact the court before you file."));
            }
        } catch (error) {
            if (currentRequestId !== this.quoteRequestId) return;
            this.feeQuoteReady = false;
            paymentMessages.showError(error?.serverMessage || gettext("We could not calculate fees. Please try again."));
            this.setFeesState(false);
        }
    },

    async addAccount() {
        const authData = await apiUtils.fetchJSON(PAYMENT_URLS.token, "GET", {
            jurisdiction: apiUtils.getCurrentJurisdiction()
        });
        if (!authData?.success || !authData.data?.tyler_token) {
            paymentMessages.showError(gettext("We could not verify your account. Please sign in again."));
            return;
        }
        const jurisdiction = authData.data.state || apiUtils.getCurrentJurisdiction();
        const form = document.createElement("form");
        form.method = "post";
        form.action = paymentJSON("new-toga-url");
        const fields = {
            account_name: `Payment account made on ${new Date().toDateString()}`,
            global: "false",
            type_code: "CC",
            tyler_info: authData.data.tyler_token,
            original_url: window.withFilingDraft(`${window.location.origin}/jurisdiction/${jurisdiction}/payment/?payment_status=success`),
            error_url: window.withFilingDraft(`${window.location.origin}/jurisdiction/${jurisdiction}/payment/?payment_status=failure`)
        };
        Object.entries(fields).forEach(([name, value]) => {
            const input = document.createElement("input");
            input.type = "hidden";
            input.name = name;
            input.value = value;
            form.appendChild(input);
        });
        document.body.appendChild(form);
        form.submit();
    },

    async init() {
        const status = new URLSearchParams(window.location.search).get("payment_status");
        if (status === "failure") paymentMessages.showError(gettext("The payment method was not added."));
        if (status === "success") paymentMessages.showSuccess(gettext("Payment method added."));
        document.querySelectorAll('input[name="paymentIntent"]').forEach((input) => {
            input.addEventListener("change", () => this.chooseIntent());
        });
        await this.loadAccountTypes();
        this.loadAccounts().catch(() => paymentMessages.showError(gettext("We could not load payment methods.")));
    }
};

Object.assign(PaymentPage, FilingPayload);
document.addEventListener("DOMContentLoaded", () => PaymentPage.init());