/**
 * Review Page JavaScript - Optimized Version
 * Handles review page functionality with improved organization and performance
 */

// Configuration constants
const CONFIG = {
    VALIDATION: {
        EMAIL_REGEX: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
        ZIP_REGEX: /^\d{5}(-\d{4})?$/,
        PHONE_REGEX: /^\+?\d{7,15}$/
    },
    URLS: {
        UPLOAD_DATA: '/api/get-upload-data/',
        PROFILE: '/api/auth/profile/',
        PAYMENT_ACCOUNTS: '/api/payment-accounts/',
        TYLER_TOKEN: '/api/auth/tyler-token/',
        SUBMIT_FILING: '/api/submit-final-filing/',
        CASE_DATA: '/api/get-case-data/',
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

    // Validation helpers
    isValidEmail(email) {
        return email && CONFIG.VALIDATION.EMAIL_REGEX.test(email);
    },

    isValidZip(zip) {
        return zip && CONFIG.VALIDATION.ZIP_REGEX.test(zip);
    },

    isValidPhone(phone) {
        if (!phone) return false;
        const cleaned = phone.replace(/[\s()-\.]/g, "");
        return CONFIG.VALIDATION.PHONE_REGEX.test(cleaned);
    },
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

// Data management
const DataManager = {
    async fetchJSON(url, options = {}) {
        try {
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': apiUtils.getCSRFToken(),
                    ...options.headers
                },
                ...options
            });
            return response.ok ? await response.json() : null;
        } catch (error) {
            console.error(`Fetch error for ${url}:`, error);
            return null;
        }
    },

    async getCaseData() {
        return Utils.parseJSON('case-data');
    },

    getFriendlyNames() {
        return Utils.parseJSON('friendly-names');
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

    toggleEdit(inputId, button) {
        const input = Utils.getElement(inputId);
        const text = Utils.getElement(inputId.replace("Input", "Text"));
        if (!input || !text || !button) return;

        const isEditing = input.style.display !== "none";

        if (!isEditing) {
            this.startEditing(input, text, button, inputId);
        } else {
            this.saveField(input, text, button, inputId);
        }
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

// Form validation
const FormValidator = {
    validateUserData(userData) {
        const {
            fullName,
            address,
            city,
            state,
            zip,
            email,
            phone
        } = userData;

        const requiredFields = [{
            value: fullName,
            name: 'Name'
        }, {
            value: address,
            name: 'Address Line 1'
        }, {
            value: city,
            name: 'City'
        }, {
            value: state,
            name: 'State'
        }, {
            value: zip,
            name: 'ZIP Code'
        }, {
            value: email,
            name: 'Email'
        }, {
            value: phone,
            name: 'Phone'
        }];

        // Check required fields
        for (const field of requiredFields) {
            if (!field.value) {
                return `${field.name} is required.`;
            }
        }

        // Validate formats
        if (!Utils.isValidZip(zip)) {
            return "Please enter a valid ZIP code (e.g. 60601 or 60601-1234).";
        }

        if (!Utils.isValidPhone(phone)) {
            return "Please enter a valid phone number.";
        }

        if (!Utils.isValidEmail(email)) {
            return "Please provide a valid email address.";
        }

        return null; // No validation errors
    }
};

// API handlers
const APIHandlers = {
    async fetchPartyType() {
        const caseData = await DataManager.getCaseData();

        if (!caseData.court || !caseData.case_type) return;

        const params = {
            jurisdiction: apiUtils.getCurrentJurisdiction(),
            court: caseData.court,
            case_type: caseData.case_type,
            existing_case: caseData.existing_case || 'no'
        };

        const result = await apiUtils.getPartyTypes(params);

        if (result?.success) {
            console.log('Party types received:', result.party_types);
            console.log('Selected party type:', result.selected_party_type);
        } else {
            console.error('Party type fetch failed:', result?.error);
        }
    },

    async loadUserInfo() {
        const params = {
            jurisdiction: apiUtils.getCurrentJurisdiction()
        };
        const data = await apiUtils.fetchJSON(CONFIG.URLS.PROFILE, "GET", params);

        if (data?.success && data.data) {
            const profile = data.data;
            const fullName = [profile.first_name, profile.last_name].filter(n => n).join(" ");

            // Set all user fields
            const fields = [
                ['userName', fullName],
                ['userAddressLine1', profile.address],
                ['userAddressLine2', profile.address_line2],
                ['userCity', profile.city],
                ['userState', profile.state],
                ['userZip', profile.zip],
                ['userEmail', profile.email],
                ['userPhone', profile.phone]
            ];

            fields.forEach(([prefix, value]) => FieldManager.setFieldValue(prefix, value));
        } else {
            // Set empty values for all fields on failure
            ['userName', 'userAddressLine1', 'userAddressLine2', 'userCity', 'userState', 'userZip', 'userEmail', 'userPhone']
            .forEach(prefix => FieldManager.setFieldValue(prefix, "", "Please provide"));
        }
    },

    async loadUploadData() {
        const data = await apiUtils.getUploadData();
        if (data) {
            UIUpdater.updateDocumentsSection(data);
        }
    },

    async loadPaymentAccounts() {
        try {
            const caseData = await DataManager.getCaseData();
            UIUpdater.updatePaymentMethodsSection(caseData.selected_payment_account, caseData.selected_payment_account_name || "Your payment");
            await window.queryFees();
        } catch (ex) {
            console.error(ex);
            UIUpdater.showAddNewPaymentMethod();
        }
    }
};

// UI updaters
const UIUpdater = {
    updateCaseInfo(caseData, friendlyNames) {
        const caseTypeEl = Utils.getElement('caseTypeValue');
        const courtEl = Utils.getElement('courtValue');

        if (caseTypeEl) {
            caseTypeEl.textContent = friendlyNames.case_type || caseData.case_type_name || caseData.case_type || "Not specified";
        }
        if (courtEl) {
            courtEl.textContent = friendlyNames.court || caseData.court_name || caseData.court || "Not specified";
        }
    },

    updateDocumentsSection(uploadData) {
        const container = Utils.getElement('documentsContainer');
        if (!container) return;

        let html = "";

        // Lead document
        if (uploadData.files?.lead) {
            const docName = uploadData.files.lead.name.includes("Name Change") ? "Name Change Form" : "Lead Document";
            html += this.createDocumentHTML(docName, uploadData.files.lead.name, 'lead', true);
        } else {
            html += `<div class="document-group"><h6>1. Lead Document (required)</h6><div class="text-muted mb-2">No document found</div></div>`;
        }

        // Supporting documents
        if (uploadData.files?.supporting?.length > 0) {
            html += '<div class="document-group mt-4"><h6>2. Fee Waiver (optional)</h6><div class="text-muted mb-2">File or Files</div><div class="document-list">';

            uploadData.files.supporting.forEach(file => {
                html += `<div class="document-item">
          <i class="fas fa-file-pdf"></i>
          <span class="document-name">${file.name}</span>
          <button class="change-btn" onclick="Navigation.changeDocument('supporting')">Change</button>
        </div>`;
            });

            html += '</div></div>';
        }

        container.innerHTML = html;
    },

    createDocumentHTML(title, filename, type, required = false) {
        return `<div class="document-group">
      <h6>1. ${title} ${required ? '(required)' : ''}</h6>
      <div class="text-muted mb-2">File or Files</div>
      <div class="document-list">
        <div class="document-item">
          <i class="fas fa-file-pdf"></i>
          <span class="document-name">${filename}</span>
          <button class="change-btn" onclick="Navigation.changeDocument('${type}')">Change</button>
        </div>
      </div>
    </div>`;
    },

    updatePaymentMethodsSection(account, account_name) {
        const container = Utils.getElement('paymentMethodsContainer');
        let html = '<div class="payment-methods-list">';

        //const cardType = account.cardType?.value || "Card";
        //const cardLast4 = account.cardLast4 || "****";
        //let paymentText = `${cardType} ending in ${cardLast4}`;

        html += `<div class="payment-method-item">
        <div class="form-check">
          <div name="paymentMethod" 
                 id="paymentAccountID" value="${account}">
          <span class="form-check-label">
            <div class="payment-method-details">
              <div class="payment-method-info">
                ${account_name}
              </div>
            </div>
          </span>
        </div>
            <a style="margin-left: auto;" href="/jurisdiction/${apiUtils.getCurrentJurisdiction()}/payment">Change payment method</a>
      </div>`;

        html += `</div>`;

        container.innerHTML = html;
    },

    showAddNewPaymentMethod() {
        const container = Utils.getElement('paymentMethodsContainer');
        if (!container) return;

        container.innerHTML = `<div class="no-payment-methods">
      <div class="alert alert-info">
        <i class="fas fa-credit-card me-2"></i>
        No payment methods found. Please <a href="/jurisdiction/${apiUtils.getCurrentJurisdiction()}/payment">go back to add a payment method</a>.
      </div>
    </div>`;
    }
};

// Navigation
const Navigation = {
    goBack() {
        window.location.href = `/jurisdiction/${apiUtils.getCurrentJurisdiction()}/payment`;
    },

    changeDocument(type) {
        const jurisdiction = apiUtils.getCurrentJurisdiction();
        if (type === "lead") {
            // TODO: still save all of the existing stuff?
            window.location.href = `/jurisdiction/${jurisdiction}/upload_first`;
        } else {
            window.location.href = `/jurisdiction/${jurisdiction}/upload`;
        }
    }
};

// Filing submission
const FilingHandler = {
    async submitFiling() {
        const userData = this.collectUserData();
        const validationError = FormValidator.validateUserData(userData);

        if (validationError) {
            Messages.showError(validationError);
            return;
        }

        const selectedPaymentMethod = document.getElementById('paymentAccountID');
        if (!selectedPaymentMethod) {
            Messages.showError(gettext("Please select a payment method to continue."));
            return;
        }

        this.setSubmissionState(true);
        Messages.hide();

        try {
            const result = await this.processSubmission(userData, selectedPaymentMethod.getAttribute("value"));
            this.handleSubmissionResult(result);
        } catch (error) {
            console.error("Error on submission: %o", error)
            Messages.showError(gettext("An unexpected error occurred. Please try again."));
            this.setSubmissionState(false);
        }
    },

    async queryFees() {
        const userData = await this.collectUserData();
        const selectedPaymentMethod = document.getElementById('paymentAccountID');

        this.setFeesState(true);

        try {
            const result = await this.processFees(userData, selectedPaymentMethod.getAttribute("value"));
            this.handleFeesResponse(result);
        } catch (error) {
            console.error("Error on submission: %o", error)
            Messages.showError(gettext("An unexpected error occurred. Please try again."));
            this.setFeesState(false);
        }
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

    collectUserData() {
        return {
            fullName: FieldManager.getFieldValue('userName'),
            address: FieldManager.getFieldValue('userAddressLine1'),
            addressLine2: FieldManager.getFieldValue('userAddressLine2'),
            city: FieldManager.getFieldValue('userCity'),
            state: FieldManager.getFieldValue('userState'),
            zip: FieldManager.getFieldValue('userZip'),
            email: FieldManager.getFieldValue('userEmail'),
            phone: FieldManager.getFieldValue('userPhone')
        };
    },

    setFeesState(isQueryingFees) {
        const submitButton = Utils.getElement('submitButton');
        const loadingSpinner = Utils.getElement('loadingSpinner');

        if (submitButton) submitButton.disabled = isQueryingFees;
        if (loadingSpinner) loadingSpinner.style.display = isQueryingFees ? "block" : "none";
    },

    setSubmissionState(isSubmitting) {
        const submitButton = Utils.getElement('submitButton');
        const loadingSpinner = Utils.getElement('loadingSpinner');

        if (submitButton) submitButton.disabled = isSubmitting;
        if (loadingSpinner) loadingSpinner.style.display = isSubmitting ? "block" : "none";
    },

    async processSubmission(userData, paymentAccountID) {
        let [caseData, uploadData] = await Promise.all([
            apiUtils.getCaseData(),
            apiUtils.getUploadData()
        ]);

        caseData = caseData.data.case_data;

        const efilingData = this.buildEFilingData(userData, caseData, uploadData, paymentAccountID);

        return await DataManager.fetchJSON(CONFIG.URLS.SUBMIT_FILING, {
            method: 'POST',
            body: JSON.stringify({
                efile_data: efilingData,
                confirm_submission: true,
                payment_account_id: paymentAccountID
            })
        });
    }
};

// buildEFilingData / addCourtBundles / createDocumentBundle /
// handleSubmissionResult / handleFeesResponse are shared with the other
// filing page. See filing-payload.js -- keep payload changes there so the
// fee quote and the submitted filing cannot drift apart.
Object.assign(FilingHandler, FilingPayload);

// Main application initialization
const ReviewApp = {
    async init() {
        await this.loadAllData();
        APIHandlers.fetchPartyType();
    },

    async loadAllData() {
        const caseData = DataManager.getCaseData();
        const friendlyNames = DataManager.getFriendlyNames();

        // Update case info immediately if available
        if (Object.keys(caseData).length > 0 || Object.keys(friendlyNames).length > 0) {
            UIUpdater.updateCaseInfo(caseData, friendlyNames);
        }

        // Load other data in parallel
        await Promise.all([
            APIHandlers.loadUserInfo(),
            APIHandlers.loadUploadData(),
        ]);
        await APIHandlers.loadPaymentAccounts()
    }
};

// Global function exports for HTML onclick handlers
window.toggleEdit = FieldManager.toggleEdit.bind(FieldManager);
window.goBack = Navigation.goBack;
window.submitFiling = FilingHandler.submitFiling.bind(FilingHandler);
window.queryFees = FilingHandler.queryFees.bind(FilingHandler);
window.Navigation = Navigation;

// Initialize app when DOM is ready
document.addEventListener("DOMContentLoaded", () => ReviewApp.init());
