/**
 * Upload Handler for Document Submission
 * Handles file uploads, drag & drop, and Suffolk API integration
 */

class UploadHandler {
    constructor() {
        this.form = document.getElementById('uploadForm');
        this.leadDocumentArea = document.getElementById('leadDocumentArea');
        this.supportingDocumentsArea = document.getElementById('supportingDocumentsArea');
        this.leadDocumentInput = document.getElementById('leadDocument');
        this.supportingDocumentsInput = document.getElementById('supportingDocuments');
        this.submitButton = document.getElementById('submitButton');
        this.uploadProgress = document.getElementById('uploadProgress');
        this.errorAlert = document.getElementById('errorAlert');
        this.successAlert = document.getElementById('successAlert');
        
        this.uploadedFiles = {
            lead: null,
            supporting: []
        };
        
        this.init();
    }

    async init() {
        // First, sync any localStorage data to session
        await this.syncFormDataToSession();
        
        this.setupEventListeners();
        this.setupDragAndDrop();
    }

    async syncFormDataToSession() {
        // Check if we have form data in localStorage
        const caseFormData = localStorage.getItem('caseFormData');
        if (caseFormData) {
            try {
                console.log('Syncing form data to session...');
                
                const response = await fetch('/api/save-form-data/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: caseFormData
                });

                if (response.ok) {
                    console.log('Form data synced to session successfully');
                    // Clear localStorage since it's now in session
                    localStorage.removeItem('caseFormData');
                } else {
                    console.warn('Failed to sync form data to session');
                }
            } catch (error) {
                console.error('Error syncing form data:', error);
            }
        }
    }

    getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }

    setupEventListeners() {
        // Form submission
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleFormSubmission();
        });

        // File input changes
        this.leadDocumentInput.addEventListener('change', (e) => {
            this.handleFileSelection(e.target.files, 'lead');
        });

        this.supportingDocumentsInput.addEventListener('change', (e) => {
            this.handleFileSelection(e.target.files, 'supporting');
        });

        // Upload area clicks
        this.leadDocumentArea.addEventListener('click', () => {
            this.leadDocumentInput.click();
        });

        this.supportingDocumentsArea.addEventListener('click', () => {
            this.supportingDocumentsInput.click();
        });
    }

    setupDragAndDrop() {
        // Lead document area
        this.setupDragDropForArea(this.leadDocumentArea, 'lead');
        
        // Supporting documents area
        this.setupDragDropForArea(this.supportingDocumentsArea, 'supporting');
    }

    setupDragDropForArea(area, type) {
        area.addEventListener('dragover', (e) => {
            e.preventDefault();
            area.classList.add('dragover');
        });

        area.addEventListener('dragleave', (e) => {
            e.preventDefault();
            area.classList.remove('dragover');
        });

        area.addEventListener('drop', (e) => {
            e.preventDefault();
            area.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            this.handleFileSelection(files, type);
        });
    }

    handleFileSelection(files, type) {
        if (files.length === 0) return;

        // Validate files
        const validFiles = [];
        for (let file of files) {
            if (this.validateFile(file)) {
                validFiles.push(file);
            }
        }

        if (validFiles.length === 0) return;

        if (type === 'lead') {
            // Only one lead document allowed
            this.uploadedFiles.lead = validFiles[0];
            this.updateFilePreview(this.leadDocumentArea, [validFiles[0]], 'lead');
        } else {
            // Multiple supporting documents allowed
            this.uploadedFiles.supporting = [...this.uploadedFiles.supporting, ...validFiles];
            this.updateFilePreview(this.supportingDocumentsArea, this.uploadedFiles.supporting, 'supporting');
        }

        this.updateSubmitButton();
    }

    validateFile(file) {
        // Check file type
        if (!file.type.includes('pdf') && !file.name.toLowerCase().endsWith('.pdf')) {
            this.showError(`Invalid file type: ${file.name}. Only PDF files are allowed.`);
            return false;
        }

        // Check file size (10MB limit)
        const maxSize = 10 * 1024 * 1024; // 10MB
        if (file.size > maxSize) {
            this.showError(`File too large: ${file.name}. Maximum size is 10MB.`);
            return false;
        }

        return true;
    }

    updateFilePreview(area, files, type) {
        // Clear existing preview
        const existingPreviews = area.querySelectorAll('.file-preview');
        existingPreviews.forEach(preview => preview.remove());

        // Add file previews
        files.forEach((file, index) => {
            const preview = this.createFilePreview(file, type, index);
            area.appendChild(preview);
        });

        // Hide/show placeholder
        const placeholder = area.querySelector('.upload-placeholder');
        if (placeholder) {
            placeholder.style.display = files.length > 0 ? 'none' : 'block';
        }
    }

    createFilePreview(file, type, index) {
        const preview = document.createElement('div');
        preview.className = 'file-preview';
        
        const fileSize = this.formatFileSize(file.size);
        
        preview.innerHTML = `
            <div class="file-info">
                <i class="fas fa-file-pdf"></i>
                <div>
                    <div class="fw-semibold">${file.name}</div>
                    <div class="text-muted small">${fileSize}</div>
                </div>
            </div>
            <button type="button" class="file-remove" onclick="uploadHandler.removeFile('${type}', ${index})">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        return preview;
    }

    removeFile(type, index) {
        if (type === 'lead') {
            this.uploadedFiles.lead = null;
            this.updateFilePreview(this.leadDocumentArea, [], 'lead');
        } else {
            this.uploadedFiles.supporting.splice(index, 1);
            this.updateFilePreview(this.supportingDocumentsArea, this.uploadedFiles.supporting, 'supporting');
        }
        
        this.updateSubmitButton();
    }

    updateSubmitButton() {
        const hasLeadDocument = this.uploadedFiles.lead !== null;
        this.submitButton.disabled = !hasLeadDocument;
    }

    async handleFormSubmission() {
        if (!this.uploadedFiles.lead) {
            this.showError('Please upload a lead document before continuing.');
            return;
        }

        this.showProgress();
        this.submitButton.disabled = true;

        try {
            // Step 1: Create filing with case data
            const filing = await this.createFiling();
            
            if (!filing.success) {
                throw new Error(filing.error);
            }

            // Step 2: Upload documents
            await this.uploadDocuments(filing.filing_id);

            // Step 3: Show success and redirect
            this.showSuccess('Filing created and documents uploaded successfully!');
            
            // Redirect to review page after 2 seconds
            setTimeout(() => {
                window.location.href = '/review/'; // Adjust URL as needed
            }, 2000);

        } catch (error) {
            console.error('Filing submission error:', error);
            this.showError(error.message);
            this.submitButton.disabled = false;
        } finally {
            this.hideProgress();
        }
    }

    async createFiling() {
        const formData = new FormData(this.form);
        
        const response = await fetch('/api/create-filing/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        });

        return await response.json();
    }

    async uploadDocuments(filingId) {
        const formData = new FormData();
        
        // Add lead document
        if (this.uploadedFiles.lead) {
            formData.append('documents', this.uploadedFiles.lead);
        }
        
        // Add supporting documents
        this.uploadedFiles.supporting.forEach(file => {
            formData.append('documents', file);
        });

        // Add filing component info
        const filingComponent = document.getElementById('filingComponent').value;
        formData.append('filing_component', filingComponent);
        
        // Add options
        const certifiedCopies = document.getElementById('certifiedCopies').checked;
        const sealedConfidential = document.getElementById('sealedConfidential').checked;
        
        formData.append('certified_copies', certifiedCopies);
        formData.append('sealed_confidential', sealedConfidential);

        const response = await fetch('/api/upload-documents/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        });

        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.error);
        }
        
        return result;
    }

    showProgress() {
        this.uploadProgress.style.display = 'block';
        this.hideAlerts();
    }

    hideProgress() {
        this.uploadProgress.style.display = 'none';
    }

    showError(message) {
        this.hideAlerts();
        document.getElementById('errorMessage').textContent = message;
        this.errorAlert.style.display = 'block';
        
        // Scroll to error
        this.errorAlert.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    showSuccess(message) {
        this.hideAlerts();
        document.getElementById('successMessage').textContent = message;
        this.successAlert.style.display = 'block';
        
        // Scroll to success
        this.successAlert.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    hideAlerts() {
        this.errorAlert.style.display = 'none';
        this.successAlert.style.display = 'none';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.uploadHandler = new UploadHandler();
});
