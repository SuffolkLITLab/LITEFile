
/**
 * FormValidation - Handles form validation and user interactions
 * Features: Real-time validation, draft saving, submission handling, API caching
 */
class FormValidation {
  constructor() {
    this.form = document.querySelector("#expertForm");

    if (!this.form) {
      console.error("Expert form not found!");
      return;
    }

    this.requiredFields = this.form.querySelectorAll("[required]");

    this.init();
  }

  init() {
    this.setupValidation();
    this.setupDraftSaving();
    this.setupFormSubmission();
    this.restoreSessionData();
  }

  setupValidation() {
    // Add validation styling for required fields
    this.requiredFields.forEach((field) => {
      field.addEventListener("invalid", function () {
        this.classList.add("is-invalid");
      });

      field.addEventListener("input", function () {
        if (this.validity.valid) {
          this.classList.remove("is-invalid");
          this.classList.add("is-valid");
        }
      });

      // Add blur validation for immediate feedback
      field.addEventListener("blur", function () {
        if (this.value.trim() && this.validity.valid) {
          this.classList.remove("is-invalid");
          this.classList.add("is-valid");
        } else if (this.value.trim() && !this.validity.valid) {
          this.classList.add("is-invalid");
        }
      });
    });
  }

  setupDraftSaving() {
    const draftButton = document.querySelector("#saveDraftBtn");
    if (draftButton) {
      draftButton.addEventListener("click", (e) => {
        // Provide immediate visual feedback
        const originalText = draftButton.innerHTML;
        draftButton.innerHTML =
          '<i class="fas fa-spinner fa-spin"></i> Saving...';
        draftButton.disabled = true;

        // Save the draft
        this.saveDraft();

        // Reset button after a short delay
        setTimeout(() => {
          draftButton.innerHTML = '<i class="fas fa-check"></i> Saved!';
          setTimeout(() => {
            draftButton.innerHTML = originalText;
            draftButton.disabled = false;
          }, 1500);
        }, 500);
      });
    } else {
      console.warn("Save Draft button not found");
    }
  }

  setupFormSubmission() {
    if (!this.form) {
      console.error("Cannot setup form submission - form not found");
      return;
    }

    // Add event listener to form submit
    this.form.addEventListener("submit", (e) => {
      this.handleFormSubmission(e);
    });

    // Also add event listener to the submit button directly as backup
    const submitButton = this.form.querySelector('button[type="submit"]');
    if (submitButton) {
      submitButton.addEventListener("click", (e) => {
        e.preventDefault();
        this.handleFormSubmission(e);
      });
    }
  }

  saveDraft() {
    const formData = this.collectFormData();

    // Check if form has meaningful content
    const hasContent = Object.values(formData).some(
      (value) => value && value.toString().trim() !== ""
    );

    if (!hasContent) {
      this.showNotification(
        "Please fill out some form fields before saving a draft.",
        "info"
      );
      return;
    }

    // Save to localStorage as backup
    const draftData = {
      data: formData,
      timestamp: new Date().toISOString(),
      savedBy: "user_action", // Indicate this was saved manually by user
    };

    localStorage.setItem("expertFormDraft", JSON.stringify(draftData));

    // TODO: Send to server when server-side draft functionality is implemented

    this.showNotification(
      "Draft saved successfully! You can return to this form later to continue.",
      "success"
    );
  }

  async handleFormSubmission(e) {
    e.preventDefault(); // Prevent default form submission
    e.stopPropagation(); // Stop event bubbling
    e.stopImmediatePropagation(); // Stop any other handlers

    // Refresh required fields list to include any dynamically added fields
    this.requiredFields = this.form.querySelectorAll("[required]");

    let isValid = true;
    const invalidFields = [];

    this.requiredFields.forEach((field) => {
      if (!field.validity.valid || !field.value.trim()) {
        isValid = false;
        field.classList.add("is-invalid");
        invalidFields.push(field.labels[0]?.textContent || field.name);
      } else {
        field.classList.remove("is-invalid");
        field.classList.add("is-valid");
      }
    });

    if (!isValid) {
      this.showValidationErrors(invalidFields);
      this.scrollToFirstError();
      return false;
    }
    
    // Collect form data and add friendly names
    const formData = this.collectFormData();
    const enhancedFormData = this.addFriendlyNames(formData);
    const currentJurisdiction = apiUtils.getCurrentJurisdiction();

    try {      
      // Save case data to session via API
      apiUtils.saveCaseData({data: enhancedFormData});
      window.location.replace(`/${currentJurisdiction}/upload/`);
    } catch (error) {
      console.error("Network error:", error);
      this.showNotification(
        "Error saving case data. Please try again.",
        "error"
      );
    }

    return false;
  }

  addFriendlyNames(formData) {
    const enhanced = { ...formData };

    // Add friendly names from dropdown text
    const dropdownMappings = [
      { field: "court", friendlyField: "court_name" },
      { field: "case_category", friendlyField: "case_category_name" },
      { field: "case_type", friendlyField: "case_type_name" },
      { field: "filing_type", friendlyField: "filing_type_name" },
      { field: "document_type", friendlyField: "document_type_name" },
    ];

    dropdownMappings.forEach(({ field, friendlyField }) => {
      const dropdown = this.form.querySelector(`[name="${field}"]`);

      if (dropdown && dropdown.value) {
        const selectedOption = dropdown.selectedOptions[0];
        if (
          selectedOption &&
          selectedOption.text &&
          selectedOption.text !== "Please select..."
        ) {
          // Clean up text by removing "(Recommended)" for court names
          let friendlyText = selectedOption.text;
          if (field === "court") {
            friendlyText = friendlyText
              .replace(/\s*\(Recommended\)\s*$/i, "")
              .trim();
          }
          enhanced[friendlyField] = friendlyText;
        }
      }
    });

    return enhanced;
  }

  collectFormData() {
    const formData = new FormData(this.form);
    const data = {};

    for (let [key, value] of formData.entries()) {
      if (data[key]) {
        // Handle multiple values (like checkboxes)
        if (Array.isArray(data[key])) {
          data[key].push(value);
        } else {
          data[key] = [data[key], value];
        }
      } else {
        data[key] = value;
      }
    }

    // Also collect disabled fields manually since FormData excludes them
    const disabledFields = this.form.querySelectorAll('input[disabled], select[disabled], textarea[disabled]');
    disabledFields.forEach(field => {
      if (field.name && field.value) {
        data[field.name] = field.value;
      }
    });

    return data;
  }

  showValidationErrors(invalidFields) {
    const message =
      invalidFields.length > 1
        ? `Please fill in the following required fields: ${invalidFields.join(
            ", "
          )}`
        : `Please fill in the required field: ${invalidFields[0]}`;

    this.showNotification(message, "error");
  }

  scrollToFirstError() {
    const firstError = this.form.querySelector(".is-invalid");
    if (firstError) {
      firstError.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      firstError.focus();
    }
  }

  showNotification(message, type = "info") {
    // Create notification element
    const notification = document.createElement("div");
    notification.className = `alert alert-${
      type === "error" ? "danger" : type
    } notification-toast`;
    notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
            animation: slideIn 0.3s ease-out;
        `;

    const icon =
      type === "success"
        ? "check-circle"
        : type === "error"
        ? "exclamation-circle"
        : "info-circle";

    notification.innerHTML = `
            <i class="fas fa-${icon}"></i> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

    document.body.appendChild(notification);

    // Auto-remove after 5 seconds
    // setTimeout(() => {
    //   if (notification.parentNode) {
    //     notification.style.animation = "slideOut 0.3s ease-in";
    //     setTimeout(() => {
    //       notification.remove();
    //     }, 300);
    //   }
    // }, 5000);

    // Add click to dismiss
    notification.querySelector(".btn-close")?.addEventListener("click", () => {
      notification.remove();
    });
  }

  // Method to restore draft data
  restoreDraft() {
    const draft = localStorage.getItem("expertFormDraft");
    if (draft) {
      try {
        const draftObj = JSON.parse(draft);
        const { data, timestamp, savedBy } = draftObj;
        const age = Date.now() - new Date(timestamp).getTime();

        // Only restore if draft is less than 24 hours old
        if (age < 24 * 60 * 60 * 1000) {
          this.populateForm(data);
          const saveMethod =
            savedBy === "user_action" ? "manually saved" : "auto-saved";
          this.showNotification(
            `Draft restored from previous session (${saveMethod})`,
            "info"
          );
        } else {
          // Remove old draft
          localStorage.removeItem("expertFormDraft");
        }
      } catch (error) {
        console.warn("Could not restore draft:", error);
        localStorage.removeItem("expertFormDraft"); // Remove corrupted draft
      }
    }
  }

  populateForm(data) {
    // Store data for later use with dynamic fields
    this.restorationData = data;

    Object.keys(data).forEach((key) => {
      const field = this.form.querySelector(`[name="${key}"]`);
      if (field) {
        if (field.type === "checkbox" || field.type === "radio") {
          field.checked = Array.isArray(data[key])
            ? data[key].includes(field.value)
            : data[key] === field.value;
        } else {
          field.value = Array.isArray(data[key]) ? data[key][0] : data[key];
        }

        // Trigger change event for dropdowns to update dependent fields
        if (field.tagName === "SELECT" || field.type === "radio") {
          field.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
    });

    // For case type field, trigger dynamic sections immediately, then populate dynamic fields
    if (data.case_type && window.dynamicFormSections) {
      // First, pass the restoration data to dynamic form sections
      window.dynamicFormSections.restoreDynamicFieldData(data);

      // Give time for change event to propagate and trigger dynamic sections
      setTimeout(() => {
        window.dynamicFormSections.handleCaseTypeChange();
        // Then wait for dynamic fields to actually be rendered in the DOM
        this.waitForDynamicFieldsAndPopulate(data);
      }, 200);
    }
  }

  async waitForDynamicFieldsAndPopulate(data) {
    // List of dynamic fields that we're waiting for
    const dynamicFields = [
      "petitioner_first_name",
      "petitioner_last_name",
      "new_first_name",
      "new_last_name",
    ];

    // Check if any of these fields exist in our data to restore
    const fieldsToRestore = dynamicFields.filter((field) => data[field]);

    if (fieldsToRestore.length === 0) {
      return;
    }

    // Wait up to 8 seconds for the fields to appear in the DOM (increased timeout)
    let attempts = 0;
    const maxAttempts = 80; // 8 seconds with 100ms intervals

    const checkInterval = setInterval(() => {
      attempts++;

      // Check if all required fields are now in the DOM
      const foundFields = fieldsToRestore.filter((fieldName) => {
        return this.form.querySelector(`[name="${fieldName}"]`) !== null;
      });

      // If all fields are found, or we've reached max attempts, populate what we can
      if (
        foundFields.length === fieldsToRestore.length ||
        attempts >= maxAttempts
      ) {
        clearInterval(checkInterval);
        this.populateDynamicFields(data);
      }
    }, 100);
  }

  populateDynamicFields(data) {
    // List of all possible dynamic fields that might be rendered after case type selection
    const dynamicFields = [
      "petitioner_first_name",
      "petitioner_last_name",
      "petitioner_address",
      "new_first_name",
      "new_last_name",
      // Add any other dynamic fields that might exist
      "petitioner_phone",
      "petitioner_email",
      "reason_for_change",
    ];

    let fieldsPopulated = 0;
    let fieldsNotFound = [];

    dynamicFields.forEach((key) => {
      if (data[key]) {
        const field = this.form.querySelector(`[name="${key}"]`);
        if (field) {
          // Handle different field types
          if (field.type === "checkbox" || field.type === "radio") {
            field.checked = Array.isArray(data[key])
              ? data[key].includes(field.value)
              : data[key] === field.value;
          } else {
            field.value = Array.isArray(data[key]) ? data[key][0] : data[key];
          }
          fieldsPopulated++;

          // Trigger validation styling if the field has content
          if (field.value && field.value.trim()) {
            field.classList.remove("is-invalid");
            field.classList.add("is-valid");
          }
        } else {
          fieldsNotFound.push(key);
        }
      }
    });

    // Show success notification if fields were populated
    if (fieldsPopulated > 0) {
      // this.showNotification(`Restored ${fieldsPopulated} name field(s) from saved data`, 'success');
    }
  }

  restoreSessionData() {
    // Check if case data is available from Django template context
    if (
      typeof window.caseData !== "undefined" &&
      window.caseData &&
      Object.keys(window.caseData).length > 0
    ) {
      // Wait for cascading dropdowns to initialize, then populate all dropdowns
      setTimeout(() => {
        this.populateDropdownsWithApiCalls(window.caseData);
        // this.showNotification('Restoring previous case data...', 'info');
      }, 2000); // Wait for initial dropdown system to load
    } else {
      // Fallback to draft restoration from localStorage
      this.restoreDraft();
    }
  }

  async populateDropdownsWithApiCalls(data) {
    // First populate all the non-dropdown form fields
    Object.keys(data).forEach((key) => {
      if (
        ![
          "court",
          "case_category",
          "case_type",
          "filing_type",
          "document_type",
        ].includes(key)
      ) {
        const field = this.form.querySelector(`[name="${key}"]`);
        if (field) {
          field.value = Array.isArray(data[key]) ? data[key][0] : data[key];
        }
      }
    });

    try {
      // Step 1: Load courts (should already be loaded, but ensure selection)
      if (data.court) {
        await this.waitForDropdownOptions("court");
        this.setDropdownValue("court", data.court);
      }

      // Step 2: Load case categories based on court
      if (data.court && data.case_category) {
        try {
          await this.loadCascadingDropdown(
            "court",
            data.court,
            "case_category"
          );
          this.setDropdownValue("case_category", data.case_category);
        } catch (error) {
          console.warn(
            "Failed to load case categories during restoration:",
            error
          );
        }
      }

      // Step 3: Load case types based on case category
      if (data.case_category && data.case_type) {
        try {
          await this.loadCascadingDropdown(
            "case_category",
            data.case_category,
            "case_type"
          );
          this.setDropdownValue("case_type", data.case_type);
        } catch (error) {
          console.warn("Failed to load case types during restoration:", error);
        }
      }

      // Step 4: Load filing types based on case type
      if (data.case_type && data.filing_type) {
        try {
          await this.loadCascadingDropdown(
            "case_type",
            data.case_type,
            "filing_type"
          );
          this.setDropdownValue("filing_type", data.filing_type);
        } catch (error) {
          console.warn(
            "Failed to load filing types during restoration:",
            error
          );
        }
      }

      // Step 5: Load document types based on filing type
      if (data.filing_type && data.document_type) {
        try {
          await this.loadCascadingDropdown(
            "filing_type",
            data.filing_type,
            "document_type"
          );
          this.setDropdownValue("document_type", data.document_type);
        } catch (error) {
          console.warn(
            "Failed to load document types during restoration:",
            error
          );
        }
      }

      // Step 6: After all dropdowns are restored, populate dynamic fields
      // Wait a bit for dynamic sections to be rendered, then populate dynamic fields
      if (data.case_type) {
        setTimeout(async () => {
          await this.waitForDynamicFieldsAndPopulate(data);
        }, 1000); // Give more time for dynamic sections to render
      }
    } catch (error) {
      console.error("Error during dropdown population:", error);
      this.showNotification("Error restoring some dropdown values", "error");
    }
  }

  async waitForDropdownOptions(dropdownName, maxWaitMs = 5000) {
    const dropdown = this.form.querySelector(`[name="${dropdownName}"]`);
    if (!dropdown) {
      throw new Error(`Dropdown ${dropdownName} not found`);
    }

    const startTime = Date.now();

    while (dropdown.options.length <= 1 && Date.now() - startTime < maxWaitMs) {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }

  async loadCascadingDropdown(
    parentDropdownName,
    parentValue,
    targetDropdownName
  ) {
    const parentDropdown = this.form.querySelector(
      `[name="${parentDropdownName}"]`
    );
    const targetDropdown = this.form.querySelector(
      `[name="${targetDropdownName}"]`
    );

    if (!parentDropdown || !targetDropdown) {
      throw new Error(
        `Dropdown not found: ${parentDropdownName} or ${targetDropdownName}`
      );
    }

    // Set parent dropdown value if not already set
    if (parentDropdown.value !== parentValue) {
      parentDropdown.value = parentValue;
    }

    // Trigger change event to populate target dropdown
    const changeEvent = new Event("change", { bubbles: true });
    parentDropdown.dispatchEvent(changeEvent);

    // Wait for target dropdown to be populated
    await this.waitForDropdownOptions(targetDropdownName, 10000);
  }

  setDropdownValue(dropdownName, value) {
    const dropdown = this.form.querySelector(`[name="${dropdownName}"]`);
    if (!dropdown) {
      console.warn(`Dropdown ${dropdownName} not found`);
      return;
    }

    // Special handling for filing_type search dropdown
    if (dropdownName === "filing_type" && window.filingTypeSearch) {
      const option = dropdown.querySelector(`option[value="${value}"]`);
      if (option) {
        // Use the search dropdown's setValue method to properly update both the hidden select and the UI
        window.filingTypeSearch.setValue(value, false); // Don't trigger change event to avoid cascading
      } else {
        console.warn(`Filing type option not found: ${value}`);
      }
      return;
    }

    // Check if the option exists for regular dropdowns
    const option = dropdown.querySelector(`option[value="${value}"]`);
    if (option) {
      dropdown.value = value;

      // Special handling for case_type - trigger dynamic form sections
      if (dropdownName === "case_type" && value) {
        setTimeout(() => {
          if (window.dynamicFormSections) {
            // Pass restoration data to dynamic sections first
            if (this.restorationData) {
              window.dynamicFormSections.restoreDynamicFieldData(
                this.restorationData
              );
            }

            window.dynamicFormSections.handleCaseTypeChange();
          } else {
            console.warn(
              "dynamicFormSections not available when setting case_type"
            );
            // Try to trigger manually
            const changeEvent = new Event("change", { bubbles: true });
            dropdown.dispatchEvent(changeEvent);
          }
        }, 300); // Give time for dropdown to settle
      }
    } else {
      console.warn(
        `Option with value "${value}" not found for ${dropdownName}`
      );
      // List available options for debugging
      const options = Array.from(dropdown.options).map((opt) => ({
        value: opt.value,
        text: opt.text,
      }));
    }
  }
}

// Add CSS for animations
const style = document.createElement("style");
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    .notification-toast {
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        border-radius: 8px;
    }
`;
document.head.appendChild(style);

// Export for module use or make globally available
if (typeof module !== "undefined" && module.exports) {
  module.exports = FormValidation;
} else {
  window.FormValidation = FormValidation;
}
