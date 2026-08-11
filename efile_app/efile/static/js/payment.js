const PAYMENT_URLS = {
    accounts: "/api/payment-accounts/",
    token: "/api/auth/tyler-token/",
    fees: "/api/payment-fees/"
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
        document.getElementById("errorMessage").hidden = false;
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

    setFeesState(loading) {
        document.getElementById("loadingSpinner").style.display = loading ? "block" : "none";
        document.getElementById("submitButton").disabled = loading || !document.querySelector('input[name="paymentMethod"]:checked');
    },

    // Tyler's payment accounts aren't all cards -- assuming so mislabeled
    // waivers, ACH/bank accounts, and firm balances alike as "Card ending in
    // ****". Only claim "card" when the account actually carries card data;
    // otherwise fall back to whatever Tyler calls the account rather than
    // guessing a type we can't confirm.
    accountLabel(account, waiverCount) {
        if (account.paymentAccountTypeCode === "WV") {
            return waiverCount > 1 ? `${gettext("Payment waiver")}: ${account.accountName}` : gettext("Payment waiver");
        }
        if (account.cardLast4) {
            return `${account.cardType?.value || gettext("Card")} ${gettext("ending in")} ${account.cardLast4}`;
        }
        return account.accountName || account.paymentAccountTypeCode?.value || gettext("Payment account");
    },

    async loadAccounts() {
        const result = await apiUtils.fetchJSON(PAYMENT_URLS.accounts, "GET", {
            jurisdiction: apiUtils.getCurrentJurisdiction()
        });
        const accounts = result?.success ? result.data : [];
        const container = document.getElementById("paymentMethodsContainer");
        if (!accounts?.length) {
            container.innerHTML = `<div class="alert alert-info">${gettext("No payment methods found. Add one to continue.")}</div>
                <button type="button" class="btn btn-outline-primary" id="add-payment-method">${gettext("Add payment method")}</button>`;
            document.getElementById("add-payment-method").addEventListener("click", () => this.addAccount());
            return;
        }

        const saved = paymentJSON("selected-payment-account-id");
        const waiverCount = accounts.filter((account) => account.paymentAccountTypeCode === "WV").length;
        const rows = accounts.map((account, index) => {
            const label = this.accountLabel(account, waiverCount);
            const checked = saved ? String(saved) === String(account.paymentAccountID) : index === 0;
            return `<label><input class="form-check-input" type="radio" name="paymentMethod" value="${escapeAttribute(account.paymentAccountID)}" data-name="${escapeAttribute(label)}" data-type="${escapeAttribute(account.paymentAccountTypeCode || "")}" ${checked ? "checked" : ""}/> <span><strong>${escapeHTML(label)}</strong></span></label>`;
        }).join("");
        container.innerHTML = `<div class="compact-choice-list">${rows}</div>
        <button type="button" class="btn btn-link ps-0 mt-2" id="add-payment-method">+ ${gettext("Add another payment method")}</button>`;
        container.querySelectorAll('input[name="paymentMethod"]').forEach((input) => {
            input.addEventListener("change", () => this.selectAndQuote());
        });
        document.getElementById("add-payment-method").addEventListener("click", () => this.addAccount());
        await this.selectAndQuote();
    },

    async selectAndQuote() {
        const selected = document.querySelector('input[name="paymentMethod"]:checked');
        if (!selected) return;
        document.getElementById("selected-payment-account").value = selected.value;
        document.getElementById("selected-payment-account-name").value = selected.dataset.name;
        document.getElementById("selected-payment-account-type").value = selected.dataset.type || "";
        document.getElementById("paymentSection").hidden = true;
        document.getElementById("quoted-fee-total").value = "";
        document.getElementById("quoted-fee-breakdown").value = "";
        paymentMessages.hide();
        this.setFeesState(true);
        try {
            const uploadData = await apiUtils.getUploadData();
            const userData = FilingPayload.userDataFromCaseData(this.caseData);
            const efileData = this.buildEFilingData(userData, this.caseData, uploadData, selected.value);
            const result = await apiUtils.post(PAYMENT_URLS.fees, {
                efile_data: efileData,
                confirm_submission: true,
                payment_account_id: selected.value
            }, {}, {
                timeout: ApiUtils.FILING_TIMEOUT_MS
            });
            this.handleFeesResponse(result);
            this.storeFeeQuote(result);
        } catch (error) {
            paymentMessages.showError(error?.serverMessage || gettext("We could not calculate fees. Please try again."));
            this.setFeesState(false);
        }
    },

    // Persist the quote Review will later display, so it shows the same
    // numbers the filer already saw here instead of sending them back to
    // look them up again.
    storeFeeQuote(result) {
        if (!result?.success) return;
        const response = result.api_response || {};
        const fees = (response.allowanceCharge || [])
            .filter((fee) => fee.chargeIndicator?.value)
            .map((fee) => ({
                label: fee.allowanceChargeReason?.value || gettext("Court fee"),
                amount: fee.amount?.value || "0.00"
            }));
        document.getElementById("quoted-fee-total").value = response.feesCalculationAmount?.value || "0.00";
        document.getElementById("quoted-fee-breakdown").value = JSON.stringify(fees);
    },

    async addAccount() {
        const authData = await apiUtils.fetchJSON(PAYMENT_URLS.token, "GET", {
            jurisdiction: apiUtils.getCurrentJurisdiction()
        });
        if (!authData?.success || !authData.data?.tyler_token) {
            paymentMessages.showError(gettext("Authentication failed. Please sign in again."));
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
            original_url: `${window.location.origin}/jurisdiction/${jurisdiction}/payment/?payment_status=success`,
            error_url: `${window.location.origin}/jurisdiction/${jurisdiction}/payment/?payment_status=failure`
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

    init() {
        const status = new URLSearchParams(window.location.search).get("payment_status");
        if (status === "failure") paymentMessages.showError(gettext("The payment method was not added."));
        if (status === "success") paymentMessages.showSuccess(gettext("Payment method added."));
        this.loadAccounts().catch(() => paymentMessages.showError(gettext("We could not load payment methods.")));
    }
};

Object.assign(PaymentPage, FilingPayload);
document.addEventListener("DOMContentLoaded", () => PaymentPage.init());