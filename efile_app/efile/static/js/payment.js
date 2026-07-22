/**
 * Review Page JavaScript - Optimized Version
 * Handles review page functionality with improved organization and performance
 */

// Configuration constants
const CONFIG = {
    URLS: {
        PROFILE: '/api/auth/profile/',
        PAYMENT_ACCOUNTS: '/api/payment-accounts/',
        TYLER_TOKEN: '/api/auth/tyler-token/',
        SUBMIT_FILING: '/api/submit-final-filing/',
        QUERY_FEES: '/api/payment-fees/',
    }
};


// Utility functions
const Utils = {
    getElement(id) {
        return document.getElementById(id);
    },

    getElements(selector) {
        return document.querySelectorAll(selector);
    },

    parseJSON(elementId) {
        const element = this.getElement(elementId);
        return element ? JSON.parse(element.textContent) : {};
    },

    showElement(element) {
        if (element) element.style.display = "block";
    },

    hideElement(element) {
        if (element) element.style.display = "none";
    },

    // URL parameter helper
    getURLParam(param) {
        return new URLSearchParams(window.location.search).get(param);
    },

    cleanURL() {
        window.history.replaceState({}, document.title, window.location.pathname);
    }

};

// Message handling
const Messages = {
    show(type, message) {
        const messageDiv = Utils.getElement(type === 'error' ? 'errorMessage' : 'successMessage');
        const textElement = Utils.getElement(type === 'error' ? 'errorText' : 'successText');

        if (messageDiv && textElement) {
            textElement.textContent = message;
            Utils.showElement(messageDiv);
            messageDiv.scrollIntoView({
                behavior: "smooth",
                block: "center"
            });
        }
    },

    showError(message) {
        this.show('error', message);
    },

    showSuccess(message) {
        this.show('success', message);
    },

    hide() {
        Utils.hideElement(Utils.getElement('errorMessage'));
        Utils.hideElement(Utils.getElement('successMessage'));
    }
};

// UI Field management
const FieldManager = {
    // Consolidated field setting logic
    setFieldValue(fieldPrefix, value, displayValue = value) {
        const input = Utils.getElement(`${fieldPrefix}Input`);
        const text = Utils.getElement(`${fieldPrefix}Text`);

        if (input) input.value = value || "";
        if (text) text.textContent = displayValue || "";
    },

    getFieldValue(fieldPrefix) {
        const input = Utils.getElement(`${fieldPrefix}Input`);
        const text = Utils.getElement(`${fieldPrefix}Text`);
        const inputVal = input?.value?.trim();
        const textVal = text?.textContent?.trim();
        return (inputVal && inputVal.length > 0) ? inputVal : textVal;
    },

    startEditing(input, text, button, inputId) {
        Utils.hideElement(text);
        Utils.showElement(input);
        input.focus();
        input.select();
        button.textContent = "Save";
        button.onclick = () => this.saveField(input, text, button, inputId);
    },

    saveField(input, text, button, inputId) {
        text.textContent = input.value.trim();
        Utils.hideElement(input);
        Utils.showElement(text);
        button.textContent = "Edit";
        button.onclick = () => this.toggleEdit(inputId, button);
    }
};

// API handlers
const APIHandlers = {
    async loadPaymentAccounts() {
        const params = {
            jurisdiction: apiUtils.getCurrentJurisdiction()
        };
        const result = await apiUtils.fetchJSON(CONFIG.URLS.PAYMENT_ACCOUNTS, "GET", params);

        if (result?.success && result.data) {
            UIUpdater.updatePaymentMethodsSection(result.data);
            let elems = document.querySelectorAll('input[name="paymentMethod"]');
            elems.forEach(e => e.addEventListener("change", () => {
                window.queryFees();
            }));
            window.queryFees();
        } else {
            UIUpdater.showAddNewPaymentMethod();
        }
    }
};

// UI updaters
const UIUpdater = {
    updatePaymentMethodsSection(paymentAccounts) {
        const container = Utils.getElement('paymentMethodsContainer');
        if (!container || !paymentAccounts?.length) {
            return this.showAddNewPaymentMethod();
        }

        let html = '<div class="payment-methods-list">';

        let hasMultipleWaivers = paymentAccounts.filter((account) => account.paymentAccountTypeCode === "WV").length > 1;
        paymentAccounts.forEach((account, index) => {
            const isDefault = index === 0;
            const cardType = account.cardType?.value || "Card";
            const cardLast4 = account.cardLast4 || "****";
            let paymentText = `${cardType} ending in ${cardLast4}`;

            if (account.paymentAccountTypeCode === "WV") {
                if (hasMultipleWaivers) {
                    paymentText = `Payment Waiver (named "${account.accountName}")`;
                } else {
                    paymentText = 'Payment Waiver';
                }
            }

            html += `<div class="payment-method-item">
        <div class="form-check">
          <input class="form-check-input" type="radio" name="paymentMethod" 
                 id="payment_${index}" fullName="${paymentText}" value="${account.paymentAccountID}" ${isDefault ? "checked" : ""}>
          <label class="form-check-label" for="payment_${index}">
            <div class="payment-method-details">
              <div class="payment-method-info">
                <i class="fab fa-cc-${cardType.toLowerCase()}"></i>
                ${paymentText}
              </div>
            </div>
          </label>
        </div>
      </div>`;
        });

        html += `</div>
      <div class="add-payment-method mt-3">
        <button type="button" class="btn btn-outline-primary" onclick="PaymentHandler.addNewPaymentMethod()">
          <i class="fas fa-plus me-2"></i>Add New Payment Method
        </button>
      </div>`;

        container.innerHTML = html;
    },

    showAddNewPaymentMethod() {
        const container = Utils.getElement('paymentMethodsContainer');
        if (!container) return;

        container.innerHTML = `<div class="no-payment-methods">
      <div class="alert alert-info">
        <i class="fas fa-credit-card me-2"></i>
        No payment methods found. Please add a payment method to continue.
      </div>
      <button type="button" class="btn btn-primary" onclick="PaymentHandler.addNewPaymentMethod()">
        <i class="fas fa-plus me-2"></i>Add Payment Method
      </button>
    </div>`;
    }
};

// Payment handling
const PaymentHandler = {
    async addNewPaymentMethod() {
        try {
            const params = new URLSearchParams({
                jurisdiction: apiUtils.getCurrentJurisdiction(),
            });
            const authData = await apiUtils.fetchJSON(CONFIG.URLS.TYLER_TOKEN, "GET", params);

            if (!authData?.success || !authData.data?.tyler_token) {
                Messages.showError("Authentication failed. Please try again.");
                return;
            }

            this.redirectToPaymentForm(authData.data);
        } catch (error) {
            console.warn("Create payment error: %o", error);
            Messages.showError("Failed to create payment method. Please try again.");
        }
    },

    redirectToPaymentForm(authData) {
        const form = document.createElement("form");
        form.method = "post";

        const jurisdiction = authData.state || apiUtils.getCurrentJurisdiction();
        form.action = Utils.parseJSON('new-toga-url');

        let dateStr = new Date().toDateString();
        const fields = [
            ['account_name', `Payment Account made on ${dateStr}`],
            ['global', 'false'],
            ['type_code', 'CC'],
            ['tyler_info', authData.tyler_token],
            ['original_url', `${window.location.origin}/jurisdiction/${jurisdiction}/payment/?payment_status=success`],
            ['error_url', `${window.location.origin}/jurisdiction/${jurisdiction}/payment/?payment_status=failure`]
        ];

        fields.forEach(([name, value]) => {
            const input = document.createElement("input");
            input.type = "hidden";
            input.name = name;
            input.value = value;
            form.appendChild(input);
        });

        document.body.appendChild(form);
        form.submit();
    },

    handleCallback() {
        const status = Utils.getURLParam('payment_status');

        if (status === 'success') {
            Messages.showSuccess(gettext("Payment method added successfully!"));
            setTimeout(() => APIHandlers.loadPaymentAccounts(), 1000);
            Utils.cleanURL();
        } else if (status === 'failure') {
            Messages.showError(gettext("Failed to add payment method. Please try again."));
            Utils.cleanURL();
        }
    },

    calcPaymentCosts() {

    }
};

// Navigation
const Navigation = {
    goBack() {
        window.location.href = `/jurisdiction/${apiUtils.getCurrentJurisdiction()}/upload`;
    },

    async toReview() {
        const selectedPaymentMethod = document.querySelector('input[name="paymentMethod"]:checked');
        await apiUtils.saveCaseData({
            "selected_payment_account": selectedPaymentMethod.value,
            "selected_payment_account_name": selectedPaymentMethod.getAttribute("fullName")
        });

        window.location.href = `/jurisdiction/${apiUtils.getCurrentJurisdiction()}/review`;
    }
};

// Filing submission
const FilingHandler = {
    async queryFees() {
        document.getElementById("paymentSection").setAttribute("hidden", true);
        this.setFeesState(true);

        const userData = await this.collectUserData();
        const selectedPaymentMethod = document.querySelector('input[name="paymentMethod"]:checked');
        if (!selectedPaymentMethod) {
            this.setFeesState(false);
            return;
        }


        try {
            const result = await this.processFees(userData, selectedPaymentMethod.value);
            this.handleFeesResponse(result);
        } catch (error) {
            console.warn("Error on submission: %o", error)
            Messages.showError(gettext("An unexpected error occurred. Please try again."));
            this.setFeesState(false);
        }
    },

    async collectUserData() {
        const params = {
            jurisdiction: apiUtils.getCurrentJurisdiction()
        };
        const data = await apiUtils.fetchJSON(CONFIG.URLS.PROFILE, "GET", params);

        if (data?.success && data.data) {
            const profile = data.data;
            const fullName = [profile.first_name, profile.last_name].filter(n => n).join(" ");

            // Set all user fields
            return {
                fullName: fullName,
                address: profile.address,
                addressLine2: profile.address_line2,
                city: profile.city,
                state: profile.state,
                zip: profile.zip,
                email: profile.email,
                phone: profile.phone
            };
        }
        return {
            fullName: "",
            address: "",
            addressLine2: "",
            city: "Citytown",
            state: "IL",
            zip: "",
            email: "test@example.com",
            phone: "",
        };
    },

    setFeesState(isQueryingFees) {
        const submitButton = Utils.getElement('submitButton');
        const loadingSpinner = Utils.getElement('loadingSpinner');

        if (submitButton) submitButton.disabled = isQueryingFees;
        if (loadingSpinner) loadingSpinner.style.display = isQueryingFees ? "block" : "none";
    },

    async processFees(userData, paymentAccountID) {
        let [caseData, uploadData] = await Promise.all([
            apiUtils.getCaseData(),
            apiUtils.getUploadData()
        ]);

        caseData = caseData.data.case_data;

        const efilingData = this.buildEFilingData(userData, caseData, uploadData, paymentAccountID);

        return await apiUtils.post(CONFIG.URLS.QUERY_FEES, {
            efile_data: efilingData,
            confirm_submission: true,
            payment_account_id: paymentAccountID
        });
    },


    buildEFilingData(userData, caseData, uploadData, paymentAccountID) {
        const nameParts = userData.fullName.split(" ");
        const firstName = nameParts[0] || "";
        const lastName = nameParts.length > 1 ? nameParts[nameParts.length - 1] : "";
        const middleName = nameParts.length > 2 ? nameParts.slice(1, -1).join(" ") : "";

        const partyType = caseData.determined_party_type || caseData.petitioner_party_type || caseData.party_type;

        if (!partyType) {
            throw new Error('Party type could not be determined. This is required for eFiling.');
        }

        // Build user object
        const mainUser = {
            mobile_number: userData.phone,
            phone_number: userData.phone,
            address: {
                address: userData.address,
                unit: userData.addressLine2,
                city: userData.city,
                state: userData.state,
                zip: userData.zip,
                country: "US"
            },
            email: userData.email,
            party_type: partyType,
            date_of_birth: "",
            // The authenticated account is a firm filer, not a self-represented
            // party. Marking the filer as the party makes Tyler reject fees with
            // "Cannot specify self as party for a firm filer."
            is_form_filler: false,
            name: {
                first: firstName,
                middle: middleName,
                last: lastName,
                suffix: ""
            },
            is_new: true
        };

        const users = [mainUser];

        // Add second user if needed for name changes
        if (caseData.new_name_party_type) {
            users.push({
                ...mainUser,
                party_type: caseData.new_name_party_type,
                name: {
                    first: caseData.new_first_name || firstName,
                    middle: caseData.new_middle_name || middleName,
                    last: caseData.new_last_name || lastName,
                    suffix: caseData.new_suffix || ""
                }
            });
        }

        // Add second user if needed for name changes
        if (caseData.respondent_name_party_type) {
            users.push({
                party_type: caseData.respondent_name_party_type,
                name: {
                    first: caseData.respondent_first_name || "",
                    middle: caseData.respondent_middle_name || "",
                    last: caseData.respondent_last_name || "",
                    suffix: caseData.respondent_suffix || ""
                },
                is_new: true,
            });
        }

        let other_parties = [];

        if (caseData.other_first_name && caseData.other_party_type) {
            other_parties.push({
                party_type: caseData.other_party_type,
                name: {
                    first: caseData.other_first_name,
                    last: caseData.other_last_name
                },
                address: {
                    address: caseData.other_address_line_1,
                    unit: caseData.other_address_line_2,
                    city: caseData.other_address_city,
                    state: caseData.other_address_state,
                    zip: caseData.other_address_zip,
                    country: "US"
                },
                email: caseData.other_email,
                phone_number: caseData.other_phone_number,
                is_new: true,
            });
        }

        const efilingData = {
            efile_case_category: caseData.case_category,
            efile_case_type: caseData.case_type,
            efile_case_subtype: caseData.case_subtype,
            previous_case_id: caseData?.previous_case_id,
            docket_number: caseData?.docket_number,
            users,
            other_parties,
            user_started_case: !caseData?.previous_case_id,
            al_court_bundle: [],
            comments_to_clerk: "",
            tyler_payment_id: paymentAccountID,
            lead_contact: {
                name: {
                    first: firstName,
                    middle: middleName,
                    last: lastName
                },
                email: userData.email
            },
            return_date: ""
        };

        // Add court bundles for documents
        this.addCourtBundles(efilingData, uploadData, caseData, users);

        return efilingData;
    },

    addCourtBundles(efilingData, uploadData, caseData, users) {
        const courtName = caseData.court_name || caseData.court || "";
        if (courtName.toLowerCase().includes("cook") || courtName.toLowerCase().includes("dupage")) {
            efilingData.cross_references = {
                254500: "254500"
            };
        }

        // Add lead document
        if (uploadData?.files?.lead) {
            const leadBundle = this.createDocumentBundle(
                uploadData.files.lead,
                uploadData.lead_filing_type || caseData.filing_type,
                uploadData.lead_document_type || caseData.document_type,
                uploadData.lead_filing_component || caseData.filing_component,
                users,
                uploadData.lead_filing_type_name || caseData.case_type_name,
                uploadData.lead_document_type_name || "",
                uploadData.lead_cc_email
            );
            efilingData.al_court_bundle.push(leadBundle);
        }

        // Add supporting documents
        if (uploadData?.files?.supporting?.length > 0) {
            uploadData.files.supporting.forEach((doc, index) => {
                const config = uploadData.supporting_documents?.[index] || {};
                const configuredComponent = config.filing_component;
                const documentComponent = doc.filing_component;
                const filingComponent = typeof configuredComponent === "object"
                    ? configuredComponent.id
                    : configuredComponent || (typeof documentComponent === "object" ? documentComponent.id : documentComponent);
                const bundle = this.createDocumentBundle(
                    doc,
                    config.filing_type || caseData.filing_type_id,
                    config.document_type || caseData.document_type,
                    filingComponent || caseData.filing_component,
                    users,
                    config.filing_type_name || `Supporting Document ${index + 1}`,
                    config.document_type_name || "",
                    config.cc_email
                );
                efilingData.al_court_bundle.push(bundle);
            });
        }
    },

    createDocumentBundle(doc, filingType, documentType, filingComponent, users, description, docDescription, cc_email) {
        if (cc_email) {
            courtesy_copies = [cc_email]
        } else {
            courtesy_copies = []
        }
        return {
            proxy_enabled: true,
            filing_type: filingType,
            optional_services: [],
            due_date: null,
            filing_description: description,
            reference_number: "",
            filing_attorney: "",
            filing_comment: "",
            courtesy_copies: courtesy_copies,
            preliminary_copies: [],
            filing_parties: users.length === 1 ? ["users[0]"] : ["users[0]", "users[1]"],
            filing_action: "efile",
            tyler_merge_attachments: false,
            document_type: documentType,
            filing_component: filingComponent,
            filename: doc.name,
            document_description: docDescription,
            data_url: doc.url || doc.s3_url || doc.file_url || doc.download_url
        };
    },

    handleSubmissionResult(result) {
        if (result?.success) {
            Messages.showSuccess(gettext("Filing submitted successfully! You will be redirected to the confirmation page."));
            setTimeout(() => {
                const jurisdiction = apiUtils.getCurrentJurisdiction();
                window.location.href = result.redirect_url || `/jurisdiction/${jurisdiction}/filing-confirmation/`;
            }, 2000);
        } else {
            Messages.showError(result?.error || "An error occurred during submission.");
            this.setSubmissionState(false);
        }
    },

    handleFeesResponse(result) {
        if (result?.success) {
            let htmlStr = `
            <strong>Total</strong>: $${result.api_response.feesCalculationAmount.value}
            
            <ul>
            `;
            for (let specificFee of result.api_response.allowanceCharge) {
                if (specificFee.chargeIndicator.value) {
                    htmlStr += `<li><em>${specificFee.allowanceChargeReason.value}</em>:  $${specificFee.amount.value}</li>`;
                }
            }
            htmlStr += "</ul>";

            let infoElem = document.getElementById("paymentInfo");
            infoElem.innerHTML = htmlStr;
            document.getElementById("paymentSection").removeAttribute("hidden");
        } else {
            Messages.showError(result?.error || "An error occurred when calculating fees.");
        }
        this.setFeesState(false);
    }
};

// Main application initialization
const ReviewApp = {
    async init() {
        await this.loadAllData();
        PaymentHandler.handleCallback();
    },

    async loadAllData() {
        // Load other data in parallel
        await Promise.all([
            APIHandlers.loadPaymentAccounts()
        ]);
    }
};

// Global function exports for HTML onclick handlers
window.goBack = Navigation.goBack;
window.toReview = Navigation.toReview;
window.queryFees = FilingHandler.queryFees.bind(FilingHandler);
window.PaymentHandler = PaymentHandler;
window.Navigation = Navigation;

// Initialize app when DOM is ready
document.addEventListener("DOMContentLoaded", () => ReviewApp.init());
