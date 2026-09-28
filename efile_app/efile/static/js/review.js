const reviewJSON = (id) => JSON.parse(document.getElementById(id).textContent);

const Messages = {
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

const USABLE_FEE_STATES = ["current", "waived"];

const FilingHandler = {
    feeQuoteState: "missing",

    setSubmissionState(submitting) {
        document.getElementById("loadingSpinner").style.display = submitting ? "block" : "none";
        // Never against a total the filer has not seen for this filing: the
        // button waits until the quote on the page is the current one.
        document.getElementById("submitButton").disabled = submitting ||
            !document.getElementById("confirm-filing").checked ||
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

    showFeeQuote(quote) {
        const amount = document.getElementById("fee-quote-amount");
        const list = document.getElementById("fee-quote-breakdown");
        amount.textContent = `$${quote.total}`;
        list.replaceChildren(...(quote.breakdown || []).map((fee) => {
            const item = document.createElement("li");
            item.textContent = `${fee.label}: $${fee.amount}`;
            return item;
        }));
        document.getElementById("fee-quote").dataset.state = quote.state;
        document.getElementById("fee-quote-total").hidden = false;
        document.getElementById("fee-quote-pending").hidden = true;
        document.getElementById("fee-quote-error").hidden = true;
    },

    showFeeError(message) {
        document.getElementById("fee-quote-pending").hidden = true;
        document.getElementById("fee-quote-total").hidden = true;
        document.getElementById("fee-quote-error-text").textContent = message;
        document.getElementById("fee-quote-error").hidden = false;
    },

    // The quote saved on Payment no longer matches this filing (or there is
    // none): ask the court again from here rather than sending the filer back
    // to Payment to find out what changed.
    async refreshFeeQuote() {
        this.feeQuoteState = "stale";
        this.setSubmissionState(false);
        try {
            const result = await apiUtils.post("/api/payment-fees/", {
                efile_data: this.buildCurrentFilingData(),
                confirm_submission: true,
                payment_account_id: reviewJSON("payment-account-id")
            }, {}, {
                timeout: ApiUtils.FEE_TIMEOUT_MS
            });
            const quote = result?.quote;
            if (!result?.success || !result.quote_recorded || !quote || !USABLE_FEE_STATES.includes(quote.state)) {
                throw new Error(gettext("The court did not return a fee total for this filing."));
            }
            this.feeQuoteState = quote.state;
            this.showFeeQuote(quote);
        } catch (error) {
            this.feeQuoteState = "missing";
            this.showFeeError(`${error?.serverMessage || error?.message || gettext("We could not calculate the court's fees.")} ${gettext("You cannot submit until the fees are known.")}`);
        }
        this.setSubmissionState(false);
    },

    async submitFiling() {
        if (!document.getElementById("confirm-filing").checked) {
            Messages.showError(gettext("Confirm that you reviewed the filing before you submit."));
            return;
        }
        Messages.hide();
        this.setSubmissionState(true);
        try {
            const efileData = this.buildCurrentFilingData();
            const result = await apiUtils.post("/api/submit-final-filing/", {
                efile_data: efileData,
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
            Messages.showError(error?.serverMessage || gettext("We could not submit the filing. Please try again."));
            this.setSubmissionState(false);
        }
    }
};

Object.assign(FilingHandler, FilingPayload);
document.addEventListener("DOMContentLoaded", () => {
    const confirmation = document.getElementById("confirm-filing");
    FilingHandler.feeQuoteState = reviewJSON("fee-quote-state");
    if (!USABLE_FEE_STATES.includes(FilingHandler.feeQuoteState)) FilingHandler.refreshFeeQuote();
    confirmation.addEventListener("change", () => FilingHandler.setSubmissionState(false));
    document.getElementById("submitButton").addEventListener("click", () => FilingHandler.submitFiling());
});