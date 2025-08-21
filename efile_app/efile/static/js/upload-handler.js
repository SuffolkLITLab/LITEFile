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
        
        this.initialized = false;
        
        this.init();
    }

    async init() {
        if (this.initialized) {
            console.warn('UploadHandler already initialized, skipping...');
            return;
        }
        
        // First, sync any localStorage data to session
        await this.syncFormDataToSession();
        
        this.setupEventListeners();
        this.setupDragAndDrop();
        
        this.initialized = true;
    }

    async syncFormDataToSession() {
        // Check if we have form data in localStorage
        const caseFormData = localStorage.getItem('caseFormData');
        if (caseFormData) {
            try {
                const response = await fetch('/api/save-case-data/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: caseFormData
                });

                if (response.ok) {
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

    async saveUploadDataToSession(uploadData) {
        try {
            const response = await fetch('/api/save-upload-data/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(uploadData)
            });

            if (!response.ok) {
                let errText = 'Failed to save upload data to session';
                try {
                    const errJson = await response.json();
                    errText = errJson.error || errJson.message || errText;
                } catch (e) {}
                throw new Error(errText);
            }

            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Failed to save upload data to session');
            }
        } catch (error) {
            console.error('Error saving upload data to session:', error);
            throw error;
        }
    }

    async saveFilesToSession() {
        try {
            // Create file metadata to save to session (we can't store actual File objects)
            const fileData = {
                lead: this.uploadedFiles.lead ? {
                    name: this.uploadedFiles.lead.name,
                    size: this.uploadedFiles.lead.size,
                    type: this.uploadedFiles.lead.type
                } : null,
                supporting: this.uploadedFiles.supporting.map(file => ({
                    name: file.name,
                    size: file.size,
                    type: file.type
                }))
            };

            // Also save any form options
            const filingComponent = document.getElementById('filingComponent')?.value || '';
            const certifiedCopies = document.getElementById('certifiedCopies')?.checked || false;
            const sealedConfidential = document.getElementById('sealedConfidential')?.checked || false;

            const uploadData = {
                files: fileData,
                options: {
                    filing_component: filingComponent,
                    certified_copies: certifiedCopies,
                    sealed_confidential: sealedConfidential
                }
            };

            const response = await fetch('/api/save-upload-data/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(uploadData)
            });

            if (!response.ok) {
                // Try to extract error message from JSON if available
                let errText = 'Failed to save upload data to session';
                try {
                    const errJson = await response.json();
                    errText = errJson.error || errJson.message || errText;
                } catch (e) {}
                throw new Error(errText);
            }

            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Failed to save upload data to session');
            }
        } catch (error) {
            console.error('Error saving files to session:', error);
            throw error;
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

        // Upload area clicks with aggressive throttling to prevent double firing
        let lastLeadClick = 0;
        let lastSupportingClick = 0;
        const CLICK_THROTTLE_MS = 1000; // 1 second throttle

        this.leadDocumentArea.addEventListener('click', (e) => {
            // Check if click is on file preview or remove button
            if (e.target.closest('.file-preview') || 
                e.target.closest('.file-remove') ||
                e.target.classList.contains('file-remove')) {
                return;
            }

            const now = Date.now();
            if (now - lastLeadClick < CLICK_THROTTLE_MS) {
                return;
            }

            lastLeadClick = now;
            
            // Prevent default and stop propagation to avoid any interference
            e.preventDefault();
            e.stopPropagation();
            
            // Use setTimeout to ensure this runs after any other event handlers
            setTimeout(() => {
                this.leadDocumentInput.click();
            }, 10);
        });

        this.supportingDocumentsArea.addEventListener('click', (e) => {
            // Check if click is on file preview or remove button
            if (e.target.closest('.file-preview') || 
                e.target.closest('.file-remove') ||
                e.target.classList.contains('file-remove')) {
                return;
            }

            const now = Date.now();
            if (now - lastSupportingClick < CLICK_THROTTLE_MS) {
                return;
            }

            lastSupportingClick = now;
            
            // Prevent default and stop propagation to avoid any interference
            e.preventDefault();
            e.stopPropagation();
            
            // Use setTimeout to ensure this runs after any other event handlers
            setTimeout(() => {
                this.supportingDocumentsInput.click();
            }, 10);
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

            // Ensure the native file input reflects the selection so browser validation works
            try {
                const dt = new DataTransfer();
                dt.items.add(validFiles[0]);
                if (this.leadDocumentInput) {
                    this.leadDocumentInput.files = dt.files;
                }
            } catch (e) {
                // Some older browsers may not support DataTransfer constructor in this context
                console.warn('Could not set native input.files via DataTransfer:', e);
            }
        } else {
            // Multiple supporting documents allowed
            this.uploadedFiles.supporting = [...this.uploadedFiles.supporting, ...validFiles];
            this.updateFilePreview(this.supportingDocumentsArea, this.uploadedFiles.supporting, 'supporting');

            // Update native supporting input FileList to match uploadedFiles.supporting
            try {
                const dt = new DataTransfer();
                this.uploadedFiles.supporting.forEach(file => dt.items.add(file));
                if (this.supportingDocumentsInput) {
                    this.supportingDocumentsInput.files = dt.files;
                }
            } catch (e) {
                console.warn('Could not set native supporting input.files via DataTransfer:', e);
            }
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
            <button type="button" class="file-remove">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Add event listener to the remove button with strong event prevention
        const removeButton = preview.querySelector('.file-remove');
        removeButton.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();

            if (type === 'lead') {
                this.uploadedFiles.lead = null;
                this.updateFilePreview(this.leadDocumentArea, [], 'lead');
                // Clear the native file input
                if (this.leadDocumentInput) {
                    this.leadDocumentInput.value = '';
                }
            } else {
                // Find and remove the specific file from the array
                const fileIndex = this.uploadedFiles.supporting.indexOf(file);
                if (fileIndex > -1) {
                    this.uploadedFiles.supporting.splice(fileIndex, 1);
                    this.updateFilePreview(this.supportingDocumentsArea, this.uploadedFiles.supporting, 'supporting');
                    
                    // Update native supporting input FileList
                    try {
                        const dt = new DataTransfer();
                        this.uploadedFiles.supporting.forEach(f => dt.items.add(f));
                        if (this.supportingDocumentsInput) {
                            this.supportingDocumentsInput.files = dt.files;
                        }
                    } catch (err) {
                        console.warn('Could not update native supporting input.files after removal:', err);
                    }
                }
            }
            
            this.updateSubmitButton();
            
            // Return false to ensure no further event processing
            return false;
        }, true); // Use capture phase to intercept before other handlers
        
        // Also add a mousedown event to completely prevent any interaction issues
        removeButton.addEventListener('mousedown', (e) => {
            e.stopPropagation();
        }, true);
        
        return preview;
    }

    removeFile(type, index) {
        if (type === 'lead') {
            this.uploadedFiles.lead = null;
            this.updateFilePreview(this.leadDocumentArea, [], 'lead');
            
            // Clear the native file input
            if (this.leadDocumentInput) {
                this.leadDocumentInput.value = '';
            }
        } else {
            this.uploadedFiles.supporting.splice(index, 1);
            // Regenerate all supporting file previews with correct indices
            this.updateFilePreview(this.supportingDocumentsArea, this.uploadedFiles.supporting, 'supporting');
            
            // Update native supporting input FileList
            try {
                const dt = new DataTransfer();
                this.uploadedFiles.supporting.forEach(file => dt.items.add(file));
                if (this.supportingDocumentsInput) {
                    this.supportingDocumentsInput.files = dt.files;
                }
            } catch (e) {
                console.warn('Could not update native supporting input.files after removal:', e);
            }
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
            // Upload documents directly to S3 and get URLs
            const uploadResult = await this.uploadToS3();

            // Now save the complete upload data (including URLs) to session
            const uploadDataWithUrls = {
                files: {
                    lead: null,
                    supporting: []
                },
                options: {
                    filing_component: document.getElementById('filingComponent')?.value || '',
                    certified_copies: document.getElementById('certifiedCopies')?.checked || false,
                    sealed_confidential: document.getElementById('sealedConfidential')?.checked || false
                }
            };

            // Process uploaded files and extract URLs
            if (uploadResult.files && uploadResult.files.length > 0) {
                // Find the lead document (first document or marked as 'lead')
                const leadDoc = uploadResult.files.find(f => f.type === 'lead') || uploadResult.files[0];
                if (leadDoc) {
                    uploadDataWithUrls.files.lead = {
                        name: leadDoc.original_name,
                        size: leadDoc.size,
                        type: this.uploadedFiles.lead.type,
                        url: leadDoc.public_url,
                        s3_key: leadDoc.key
                    };
                }

                // Process supporting documents
                const supportingDocs = uploadResult.files.filter(f => f.type === 'supporting');
                supportingDocs.forEach((doc, index) => {
                    const originalFile = this.uploadedFiles.supporting[index];
                    uploadDataWithUrls.files.supporting.push({
                        name: doc.original_name,
                        size: doc.size,
                        type: originalFile?.type,
                        url: doc.public_url,
                        s3_key: doc.key
                    });
                });
            }
            // Save the complete upload data with URLs to session
            await this.saveUploadDataToSession(uploadDataWithUrls);

            // Show success message briefly
            this.showSuccess('Documents uploaded successfully! Redirecting to review...');
            
            // Redirect to review page after 1 second
            setTimeout(() => {
                window.location.href = '/review/';
            }, 1000);

        } catch (error) {
            console.error('File upload error:', error);
            this.showError(error.message);
            this.submitButton.disabled = false;
        } finally {
            this.hideProgress();
        }
    }

    async uploadToS3() {
        const formData = new FormData();
        
        // Add lead document
        if (this.uploadedFiles.lead) {
            formData.append('documents', this.uploadedFiles.lead);
        }
        
        // Add supporting documents
        this.uploadedFiles.supporting.forEach(file => {
            formData.append('documents', file);
        });

        const response = await fetch('/api/simple-s3-upload/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': this.getCSRFToken()
            }
        });

        const result = await response.json();
        
        if (!result.success) {
            throw new Error(result.error);
        }
        
        return result;
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
    if (!window.uploadHandler) {
        window.uploadHandler = new UploadHandler();
    } else {
        console.warn('UploadHandler already exists, skipping initialization');
    }
});
