/**
 * ExpertForm - Main initialization and coordination
 * Coordinates all form functionality and initializes components
 */
class ExpertForm {
    constructor() {
        this.cascadingDropdowns = null;
        this.formValidation = null;
        this.initialized = false;
    }

    async init() {
        if (this.initialized) return;
        
        try {
            // Initialize cascading dropdowns first (they load user profile)
            this.cascadingDropdowns = new CascadingDropdowns();
            
            // Make cascading dropdowns globally accessible for jurisdiction switching
            window.cascadingDropdowns = this.cascadingDropdowns;
            
            // Initialize form validation
            this.formValidation = new FormValidation();
            
            // Make form validation available globally for dynamic sections
            window.formValidation = this.formValidation;
            
            if (window.caseData) {
                this.formValidation.populateForm(window.caseData);
            }
            
            // Note: Auto-save removed - drafts are now only saved when user clicks "Save Draft" button
            
            this.initialized = true;
            
        } catch (error) {
            console.error('Error initializing ExpertForm:', error);
            this.showError('There was an error loading the form. Please refresh the page.');
        }
    }

    // setupAutoSave() method removed - drafts are now only saved when user clicks "Save Draft" button
    // This prevents automatic saving and gives users full control over when drafts are saved
    
    hasFormContent(data) {
        // Check if form has meaningful content beyond empty strings
        return Object.values(data).some(value => 
            value && value.toString().trim() !== ''
        );
    }

    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger';
        errorDiv.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${message}`;
        
        const container = document.querySelector('.form-container');
        if (container) {
            container.insertBefore(errorDiv, container.firstChild);
        }
    }

    // Public methods for external access
    getCascadingDropdowns() {
        return this.cascadingDropdowns;
    }

    getFormValidation() {
        return this.formValidation;
    }

    // Method to manually trigger form save
    saveForm() {
        if (this.formValidation) {
            this.formValidation.saveDraft();
        }
    }

    // Method to reset form
    resetForm() {
        const form = document.querySelector('#expertForm');
        if (form) {
            form.reset();
            // Clear any validation classes
            form.querySelectorAll('.is-valid, .is-invalid').forEach(field => {
                field.classList.remove('is-valid', 'is-invalid');
            });
            // Clear localStorage draft
            localStorage.removeItem('expertFormDraft');
        }
    }
}

// Global instance
let expertFormInstance = null;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    expertFormInstance = new ExpertForm();
    expertFormInstance.init();
});

// Make available globally for debugging/external access
window.ExpertForm = ExpertForm;
window.getExpertFormInstance = () => expertFormInstance;
