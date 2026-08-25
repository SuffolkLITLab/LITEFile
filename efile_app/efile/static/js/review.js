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

const FilingHandler = {
    setSubmissionState(submitting) {
        document.getElementById("loadingSpinner").style.display = submitting ? "block" : "none";
        document.getElementById("submitButton").disabled = submitting || !document.getElementById("confirm-filing").checked;
    },

    setFeesState() {},

    async submitFiling() {
        if (!document.getElementById("confirm-filing").checked) {
            Messages.showError(gettext("Confirm that you reviewed the filing before you submit."));
            return;
        }
        Messages.hide();
        this.setSubmissionState(true);
        try {
            const caseData = reviewJSON("case-data");
            const userData = this.userDataFromCaseData(caseData);
            const efileData = this.buildEFilingData(
                userData,
                caseData,
                reviewJSON("upload-data"),
                reviewJSON("payment-account-id")
            );
            const result = await apiUtils.post("/api/submit-final-filing/", {
                efile_data: efileData,
                confirm_submission: true,
                payment_account_id: reviewJSON("payment-account-id")
            }, {}, {
                timeout: ApiUtils.SUBMISSION_TIMEOUT_MS
            });
            this.handleSubmissionResult(result);
        } catch (error) {
            Messages.showError(error?.serverMessage || gettext("We could not submit the filing. Please try again."));
            this.setSubmissionState(false);
        }
    }
};

Object.assign(FilingHandler, FilingPayload);
document.addEventListener("DOMContentLoaded", () => {
    const confirmation = document.getElementById("confirm-filing");
    confirmation.addEventListener("change", () => FilingHandler.setSubmissionState(false));
    document.getElementById("submitButton").addEventListener("click", () => FilingHandler.submitFiling());
});