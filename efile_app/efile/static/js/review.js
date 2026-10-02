const reviewJSON = (id) => JSON.parse(document.getElementById(id).textContent);

const Messages = {
    hide() {
        document.getElementById("errorMessage").hidden = true;
        document.getElementById("successMessage").hidden = true;
    },
    showError(message, actions = []) {
        document.getElementById("errorText").textContent = message;
        window.FilingErrorActions?.render("filing-error-actions", actions);
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

const USABLE_FEE_STATES = ["current", "waived"];

const FilingHandler = {
    feeQuoteState: "missing",

    // A disabled checkbox means the court requirements could not be loaded.
    filingConfirmed() {
        const checkbox = document.getElementById("confirm-filing");
        return checkbox.checked && !checkbox.disabled;
    },

    setSubmissionState(submitting) {
        document.getElementById("loadingSpinner").style.display = submitting ? "block" : "none";
        // Never against a total the filer has not seen for this filing: the
        // button waits until the quote on the page is the current one.
        document.getElementById("submitButton").disabled = submitting ||
            !this.filingConfirmed() ||
            !USABLE_FEE_STATES.includes(this.feeQuoteState);
    },

    setFeesState() {},

    buildCurrentFilingData() {
        const caseData = reviewJSON("case-data");
        return this.buildEFilingData(
            this.userDataFromCaseData(caseData),
            caseData,
            reviewJSON("upload-data"),
            reviewJSON("payment-account-id")
        );
    },

    initFreeFilingPopover() {
        const trigger = document.getElementById("free-filing-explainer");
        const content = document.getElementById("free-filing-explainer-content");
        if (!trigger || !content || !window.bootstrap) return;
        this.freeFilingPopover = new window.bootstrap.Popover(trigger, {
            title: trigger.textContent.trim(),
            content: content.innerHTML,
            html: true,
            trigger: "click",
            placement: "top",
            customClass: "info-explainer-popover"
        });
        document.addEventListener("click", (event) => {
            const inside = trigger.contains(event.target) || event.target.closest(".info-explainer-popover");
            if (!inside) this.freeFilingPopover.hide();
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") this.freeFilingPopover.hide();
        });
    },

    setFreeFilingHelp(visible) {
        const help = document.getElementById("free-filing-help");
        if (help) help.hidden = !visible;
        if (!visible) this.freeFilingPopover?.hide();
    },

    showFeeQuote(quote) {
        this.setFreeFilingHelp(quote.state === "current" && quote.is_zero === true);
        const amount = document.getElementById("fee-quote-amount");
        const list = document.getElementById("fee-quote-breakdown");
        amount.textContent = Number(quote.total).toLocaleString("en-US", {
            style: "currency",
            currency: "USD"
        });
        const fees = quote.is_zero ? [] : (quote.breakdown || []);
        list.replaceChildren(...fees.map((fee) => this.feeReceiptRow(fee.label, fee.amount)));
        document.getElementById("submit-button-label").textContent =
            quote.state === "current" && Number(quote.total) > 0 ? gettext("Submit and pay") : gettext("Submit filing");
        document.getElementById("fee-quote").dataset.state = quote.state;
        document.getElementById("fee-quote-total").hidden = false;
        document.getElementById("fee-quote-pending").hidden = true;
        document.getElementById("fee-quote-error").hidden = true;
        window.FilingErrorActions?.render("fee-error-actions", []);
    },

    showFeeError(message, actions = []) {
        this.setFreeFilingHelp(false);
        document.getElementById("submit-button-label").textContent = gettext("Submit filing");
        document.getElementById("fee-quote-breakdown").replaceChildren();
        document.getElementById("fee-quote-pending").hidden = true;
        document.getElementById("fee-quote-total").hidden = true;
        document.getElementById("fee-quote-error-text").textContent = message;
        window.FilingErrorActions?.render("fee-error-actions", actions);
        document.getElementById("fee-quote-error").hidden = false;
    },

    // The quote saved on Payment no longer matches this filing (or there is
    // none): ask the court again from here rather than sending the filer back
    // to Payment to find out what changed.
    async refreshFeeQuote() {
        this.feeQuoteState = "stale";
        this.setFreeFilingHelp(false);
        this.setSubmissionState(false);
        try {
            const result = await apiUtils.post("/api/payment-fees/", {
                efile_data: this.buildCurrentFilingData(),
                confirm_submission: true,
                payment_account_id: reviewJSON("payment-account-id"),
                fee_inputs_token: reviewJSON("fee-inputs-token")
            }, {}, {
                timeout: ApiUtils.FEE_TIMEOUT_MS
            });
            const quote = result?.quote;
            if (result?.success && result.quote_superseded) {
                // This page shows an older version of the filing than the
                // one saved now, so its fees would be for the wrong filing.
                throw new Error(gettext("This filing changed while we were calculating fees, perhaps in another window. Reload this page to see the current filing."));
            }
            if (!result?.success || !result.quote_recorded || !quote || !USABLE_FEE_STATES.includes(quote.state)) {
                throw new Error(gettext("The court did not return a fee total for this filing."));
            }
            this.feeQuoteState = quote.state;
            this.showFeeQuote(quote);
        } catch (error) {
            this.feeQuoteState = "missing";
            this.showFeeError(`${error?.serverMessage || error?.message || gettext("We could not calculate the court's fees.")} ${gettext("You cannot submit until the fees are known.")}`, error?.errorActions);
        }
        this.setSubmissionState(false);
    },

    async submitFiling() {
        if (!this.filingConfirmed()) {
            Messages.showError(gettext("Confirm that you reviewed the filing before you submit."));
            return;
        }
        Messages.hide();
        this.setSubmissionState(true);
        try {
            const efileData = this.buildCurrentFilingData();
            const result = await apiUtils.post("/api/submit-final-filing/", {
                efile_data: efileData,
                disclaimer_token: reviewJSON("disclaimer-token"),
                confirm_submission: true,
                payment_account_id: reviewJSON("payment-account-id")
            }, {}, {
                timeout: ApiUtils.SUBMISSION_TIMEOUT_MS
            });
            this.handleSubmissionResult(result);
        } catch (error) {
            if (error?.status === 412) {
                // Something changed in another tab since this page loaded.
                await this.refreshFeeQuote();
            }
            Messages.showError(error?.serverMessage || gettext("We could not submit the filing. Please try again."), error?.errorActions);
            this.setSubmissionState(false);
        }
    }
};

Object.assign(FilingHandler, FilingPayload);
document.addEventListener("DOMContentLoaded", () => {
    FilingHandler.initFreeFilingPopover();
    const confirmation = document.getElementById("confirm-filing");
    FilingHandler.feeQuoteState = reviewJSON("fee-quote-state");
    if (!USABLE_FEE_STATES.includes(FilingHandler.feeQuoteState)) FilingHandler.refreshFeeQuote();
    confirmation.addEventListener("change", () => FilingHandler.setSubmissionState(false));
    document.getElementById("submitButton").addEventListener("click", () => FilingHandler.submitFiling());
});