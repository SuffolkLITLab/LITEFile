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
    PARTY_TYPES: '/api/get-party-types/',
    UPLOAD_DATA: '/api/get-upload-data/',
    PROFILE: '/api/auth/profile/',
    PAYMENT_ACCOUNTS: '/api/payment-accounts/',
    TYLER_TOKEN: '/api/auth/tyler-token/',
    SUBMIT_FILING: '/api/submit-final-filing/',
  }
};


// Utility functions
const Utils = {
  getCSRFToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
           document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
           "";
  },

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
      messageDiv.scrollIntoView({ behavior: "smooth", block: "center" });
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
          'X-CSRFToken': Utils.getCSRFToken(),
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

  getCaseData() {
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
    const { fullName, address, city, state, zip, email, phone } = userData;
    
    const requiredFields = [
      { value: fullName, name: 'Name' },
      { value: address, name: 'Address Line 1' },
      { value: city, name: 'City' },
      { value: state, name: 'State' },
      { value: zip, name: 'ZIP Code' },
      { value: email, name: 'Email' },
      { value: phone, name: 'Phone' }
    ];

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
    const caseData = DataManager.getCaseData();
    
    if (!caseData.court || !caseData.case_type) return;

    const params = new URLSearchParams({
      jurisdiction: apiUtils.getCurrentJurisdiction(),
      court: caseData.court,
      case_type: caseData.case_type,
      existing_case: caseData.existing_case || 'no'
    });

    const result = await DataManager.fetchJSON(`${CONFIG.URLS.PARTY_TYPES}?${params}`);
    
    if (result?.success) {
      console.log('Party types received:', result.party_types);
      console.log('Selected party type:', result.selected_party_type);
    } else {
      console.error('Party type fetch failed:', result?.error);
    }
  },

  async loadUserInfo() {
    const params = new URLSearchParams({
      jurisdiction: apiUtils.getCurrentJurisdiction(),
    });
    const data = await DataManager.fetchJSON(`${CONFIG.URLS.PROFILE}?${params}`);
    
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
    const data = await DataManager.fetchJSON(CONFIG.URLS.UPLOAD_DATA);
    if (data) {
      UIUpdater.updateDocumentsSection(data);
    }
  },

  async loadPaymentAccounts() {
    const params = new URLSearchParams({
      jurisdiction: apiUtils.getCurrentJurisdiction(),
    });
    const result = await DataManager.fetchJSON(`${CONFIG.URLS.PAYMENT_ACCOUNTS}?${params}`);
    
    if (result?.success && result.data) {
      UIUpdater.updatePaymentMethodsSection(result.data);
    } else {
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
                 id="payment_${index}" value="${account.paymentAccountID}" ${isDefault ? "checked" : ""}>
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
      const authData = await DataManager.fetchJSON(`${CONFIG.URLS.TYLER_TOKEN}?${params}`);
      
      if (!authData?.success || !authData.data?.tyler_token) {
        Messages.showError("Authentication failed. Please try again.");
        return;
      }

      this.redirectToPaymentForm(authData.data);
    } catch (error) {
      console.log("Create payment error: %o", error);
      Messages.showError("Failed to create payment method. Please try again.");
    }
  },

  redirectToPaymentForm(authData) {
    const form = document.createElement("form");
    form.method = "post";
    
    const jurisdiction = authData.state || apiUtils.getCurrentJurisdiction();
    // TODO: we should revisit this hardcoded value in the future too
    form.action = `http://localhost:9100/jurisdictions/${encodeURIComponent(jurisdiction)}/payments/new-toga-account`;

    let dateStr = new Date().toDateString();
    const fields = [
      ['account_name', `Payment Account made on ${dateStr}`],
      ['global', 'false'],
      ['type_code', 'CC'],
      ['tyler_info', authData.tyler_token],
      ['original_url', `${window.location.origin}/${jurisdiction}/review/?payment_status=success`],
      ['error_url', `${window.location.origin}/${jurisdiction}/review/?payment_status=failure`]
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
      Messages.showSuccess("Payment method added successfully!");
      setTimeout(() => APIHandlers.loadPaymentAccounts(), 1000);
      Utils.cleanURL();
    } else if (status === 'failure') {
      Messages.showError("Failed to add payment method. Please try again.");
      Utils.cleanURL();
    }
  }
};

// Navigation
const Navigation = {
  goBack() {
    window.location.href = `/${apiUtils.getCurrentJurisdiction()}/upload`;
  },

  changeDocument(type) {
    window.location.href = `/${apiUtils.getCurrentJurisdiction()}/upload`;
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

    const selectedPaymentMethod = document.querySelector('input[name="paymentMethod"]:checked');
    if (!selectedPaymentMethod) {
      Messages.showError("Please select a payment method to continue.");
      return;
    }

    this.setSubmissionState(true);
    Messages.hide();

    try {
      const result = await this.processSubmission(userData, selectedPaymentMethod.value);
      this.handleSubmissionResult(result);
    } catch (error) {
      console.log("Error on submission: %o", error)
      Messages.showError("An unexpected error occurred. Please try again.");
      this.setSubmissionState(false);
    }
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

  setSubmissionState(isSubmitting) {
    const submitButton = Utils.getElement('submitButton');
    const loadingSpinner = Utils.getElement('loadingSpinner');
    
    if (submitButton) submitButton.disabled = isSubmitting;
    if (loadingSpinner) loadingSpinner.style.display = isSubmitting ? "block" : "none";
  },

  async processSubmission(userData, paymentAccountID) {
    const [caseData, uploadData] = await Promise.all([
      Promise.resolve(DataManager.getCaseData()),
      DataManager.fetchJSON(CONFIG.URLS.UPLOAD_DATA)
    ]);

    const efilingData = this.buildEFilingData(userData, caseData, uploadData, paymentAccountID);
    
    return await DataManager.fetchJSON(CONFIG.URLS.SUBMIT_FILING, {
      method: 'POST',
      body: JSON.stringify({
        efile_data: efilingData,
        confirm_submission: true,
        payment_account_id: paymentAccountID
      })
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
      is_form_filler: true,
      name: { first: firstName, middle: middleName, last: lastName, suffix: "" },
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

    const efilingData = {
      efile_case_category: caseData.case_category,
      efile_case_type: caseData.case_type,
      efile_case_subtype: caseData.case_subtype,
      previous_case_id: caseData?.previous_case_id,
      docket_number: caseData?.docket_number,
      users,
      other_parties: [],
      user_started_case: !caseData?.previous_case_id,
      al_court_bundle: [],
      cross_references: "",
      comments_to_clerk: "",
      tyler_payment_id: paymentAccountID,
      lead_contact: {
        name: { first: firstName, middle: middleName, last: lastName },
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
      efilingData.cross_references = { 254500: "254500" };
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
        uploadData.lead_document_type_name || ""
      );
      efilingData.al_court_bundle.push(leadBundle);
    }

    // Add supporting documents
    if (uploadData?.files?.supporting?.length > 0) {
      uploadData.files.supporting.forEach((doc, index) => {
        const config = uploadData.supporting_documents?.[index] || {};
        const bundle = this.createDocumentBundle(
          doc,
          config.filing_type || caseData.filing_type_id,
          config.document_type || caseData.document_type,
          config.filing_component || "supporting",
          users,
          config.filing_type_name || `Supporting Document ${index + 1}`,
          config.document_type_name || ""
        );
        efilingData.al_court_bundle.push(bundle);
      });
    }
  },

  createDocumentBundle(doc, filingType, documentType, filingComponent, users, description, docDescription) {
    return {
      proxy_enabled: true,
      filing_type: filingType,
      optional_services: [],
      due_date: null,
      filing_description: description,
      reference_number: "",
      filing_attorney: "",
      filing_comment: "",
      courtesy_copies: [],
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
      Messages.showSuccess("Filing submitted successfully! You will be redirected to the confirmation page.");
      setTimeout(() => {
        const jurisdiction = apiUtils.getCurrentJurisdiction();
        window.location.href = result.redirect_url || `/${jurisdiction}/filing-confirmation/`;
      }, 2000);
    } else {
      Messages.showError(result?.error || "An error occurred during submission.");
      this.setSubmissionState(false);
    }
  }
};

// Main application initialization
const ReviewApp = {
  async init() {
    await this.loadAllData();
    PaymentHandler.handleCallback();
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
      APIHandlers.loadPaymentAccounts()
    ]);
  }
};

// Global function exports for HTML onclick handlers
window.toggleEdit = FieldManager.toggleEdit.bind(FieldManager);
window.goBack = Navigation.goBack;
window.submitFiling = FilingHandler.submitFiling.bind(FilingHandler);
window.PaymentHandler = PaymentHandler;
window.Navigation = Navigation;

// Initialize app when DOM is ready
document.addEventListener("DOMContentLoaded", () => ReviewApp.init());
