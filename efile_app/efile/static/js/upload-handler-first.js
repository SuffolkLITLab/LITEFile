/**
 * Upload Handler for Document Submission
 * Handles file uploads, drag & drop, and Suffolk API integration
 */

class UploadHandler {
    constructor() {
        this.form = document.getElementById('uploadForm');
        this.leadDocumentArea = document.getElementById('leadDocumentArea');
        this.leadDocumentInput = document.getElementById('leadDocument');
        this.submitButton = document.getElementById('submitButton');
        this.uploadProgress = document.getElementById('uploadProgress');
        this.errorAlert = document.getElementById('errorAlert');
        this.successAlert = document.getElementById('successAlert');

        this.uploadedFile = null;
        this.uploadPromise = null;
        this.leadPersisted = false;

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
        // Send stuff from localStorage to server
        const caseFormData = localStorage.getItem('caseFormData');
        if (caseFormData) {
            try {
                await apiUtils.saveCaseData(caseFormdata);
                // Clear localStorage since it's now in session
                localStorage.removeItem('caseFormData');
            } catch (error) {
                console.error('Error syncing form data:', error);
            }
        }
        // Take stuff from server and show on page
        const response = await apiUtils.getUploadData();
        const lead = response?.files?.lead;
        if (lead) {
            this.uploadedFile = lead;
            this.leadPersisted = true;
            this.updateFilePreview(this.leadDocumentArea, lead);
            document.getElementById("leadDocument").removeAttribute("required");
        }
    }

    /**
     * Build the durable-draft payload for a lead document that S3 has accepted.
     * Used both by the save-on-upload path and by the save-on-Continue retry, so
     * the two can never drift.
     * @param {Object} uploadedLead - one entry from the upload response's `files`
     */
    buildLeadPayload(uploadedLead) {
        return {
            files: {
                lead: {
                    name: this.uploadedFile.name,
                    size: this.uploadedFile.size,
                    type: this.uploadedFile.type,
                    url: uploadedLead.public_url || uploadedLead.url,
                    s3_key: uploadedLead.key,
                },
            },
            options: { lead: {} },
        };
    }

    async saveUploadDataToSession(uploadData) {
        try {
            const payload = {
                ...uploadData,
                jurisdiction_id: uploadData.jurisdiction_id || apiUtils.getCurrentJurisdiction()
            };
            const result = await apiUtils.saveFirstUploadData(payload);
            if (!result.success) {
                throw new Error(result.error || 'Failed to save upload data to session');
            }
        } catch (error) {
            console.error('Error saving upload data to session:', error);
            throw error;
        }
    }

    setupEventListeners() {
        // Form submission
        if (this.form) {
            this.form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handleFormSubmission();
            });
        }

        // File input changes
        this.leadDocumentInput.addEventListener('change', (e) => {
            this.handleFileSelection(e.target.files);
        });

        // Upload area clicks with aggressive throttling to prevent double firing
        let lastLeadClick = 0;
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
    }

    setupDragAndDrop() {
        // Lead document area
        let area = this.leadDocumentArea;
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
            this.handleFileSelection(files);
        });
    }

    handleFileSelection(files) {
        if (files.length === 0) return;

        // Validate files
        const validFiles = [];
        for (let file of files) {
            if (this.validateFile(file)) {
                validFiles.push(file);
            }
        }

        if (validFiles.length === 0) return;

        // Only one lead document allowed
        this.uploadedFile = validFiles[0];
        this.updateFilePreview(this.leadDocumentArea, validFiles[0]);

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

        // Automatically upload lead document
        this.uploadPromise = this.uploadFileImmediately(validFiles[0], 0);

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

        this.hideAlerts();

        return true;
    }

    updateFilePreview(area, file) {
        // Clear existing preview
        const existingPreviews = area.querySelectorAll('.file-preview');
        existingPreviews.forEach(preview => preview.remove());

        // Add file previews
        if (file) {
            const preview = this.createFilePreview(file);
            area.appendChild(preview);
        }

        // Show/hide document options based on whether files are uploaded
        const leadOptions = document.getElementById('leadDocumentOptions');
        if (leadOptions) {
            leadOptions.style.display = file ? 'block' : 'none';
        }

        // Hide/show placeholder
        const placeholder = area.querySelector('.upload-placeholder');
        if (placeholder) {
            placeholder.style.display = file ? 'none' : 'block';
        }
    }

    createFilePreview(file) {
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

            this.uploadedFile = null;
            this.updateFilePreview(this.leadDocumentArea, null);
            // Clear the native file input
            if (this.leadDocumentInput) {
                this.leadDocumentInput.value = '';
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

    updateSubmitButton() {
        const hasLeadDocument = this.uploadedFile !== null;
        this.submitButton.disabled = !hasLeadDocument;
    }

    async uploadFileImmediately(file, index) {
        try {
            // Show upload progress for this specific file
            this.showFileUploadProgress(file.name, index);

            // Create FormData with just this file
            const formData = new FormData();
            formData.append('documents', file);

            const response = await fetch('/api/simple-s3-upload/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': apiUtils.getCSRFToken()
                }
            });

            const result = await response.json();

            if (!result.success) {
                throw new Error(result.error || 'Upload failed');
            }

            // Update file preview to show successful upload
            this.showFileUploadSuccess(file.name, index);

            // Store the upload result for later use during form submission
            this.uploadedFile.uploadResult = result;

            // Persist the lead as soon as S3 accepts it. This keeps a refresh
            // or navigation from losing the document before the user clicks
            // Continue.
            const uploadedLead = result.files?.[0];
            if (uploadedLead) {
                try {
                    await this.saveUploadDataToSession(this.buildLeadPayload(uploadedLead));
                    this.leadPersisted = true;
                } catch (error) {
                    // Continue still retries the same save, so an interim
                    // persistence failure should not discard the S3 result.
                    console.warn('Could not persist lead upload immediately:', error);
                }
            }

        } catch (error) {
            console.error('Error uploading file immediately:', error);
            this.showFileUploadError(file.name, index, error.message);
        }
    }

    showFileUploadProgress(fileName, type, index) {
        const selector = '.file-preview';
        const preview = this.leadDocumentArea.querySelector(selector)

        if (preview) {
            const statusDiv = preview.querySelector('.upload-status') || document.createElement('div');
            statusDiv.className = 'upload-status';
            statusDiv.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Uploading...';
            if (!preview.querySelector('.upload-status')) {
                preview.appendChild(statusDiv);
            }
        }
    }

    showFileUploadSuccess(fileName, index) {
        const selector = '.file-preview';
        const preview = this.leadDocumentArea.querySelector(selector);

        if (preview) {
            const statusDiv = preview.querySelector('.upload-status');
            if (statusDiv) {
                statusDiv.innerHTML = '<i class="fas fa-check-circle text-success me-1"></i>Uploaded';
            }
        }
    }

    showFileUploadError(fileName, index, error) {
        const selector = '.file-preview';
        const preview = this.leadDocumentArea.querySelector(selector)

        if (preview) {
            const statusDiv = preview.querySelector('.upload-status');
            if (statusDiv) {
                statusDiv.innerHTML = '<i class="fas fa-exclamation-triangle text-danger me-1"></i>Upload failed';
                statusDiv.title = error;
            }
        }
    }

    async handleFormSubmission() {
        if (!this.uploadedFile) {
            this.showError('Please upload a lead document before continuing.');
            return;
        }

        // File selection starts an asynchronous S3 upload. Wait for both the
        // upload and its durable-draft save before navigating away.
        if (this.uploadPromise) {
            await this.uploadPromise;
            this.uploadPromise = null;
        }

        if (!this.uploadedFile.uploadResult && !(this.uploadedFile.url && this.uploadedFile.s3_key)) {
            this.showError('The lead document upload did not finish. Please try again.');
            return;
        }

        if (this.uploadedFile.uploadResult && !this.leadPersisted) {
            this.showWaiting("Saving your document...");
            try {
                const uploadedLead = this.uploadedFile.uploadResult.files?.[0];
                if (!uploadedLead) {
                    throw new Error('The lead document upload did not return a file.');
                }
                await this.saveUploadDataToSession(this.buildLeadPayload(uploadedLead));
                this.leadPersisted = true;
            } catch (error) {
                console.error('Error persisting lead upload:', error);
                this.showError(error.message);
                return;
            }
        }

        if (this.uploadedFile.url && this.uploadedFile.s3_key) {
            // We've already uploaded the file previously. Just continue.
            const jurisdiction = apiUtils.getCurrentJurisdiction();
            window.location.href = `/jurisdiction/${jurisdiction}/expert_form/`;
            return;
        }

        this.showWaiting("Processing your form...");

        try {
            // Prepare upload data using already uploaded files (since files are uploaded immediately on selection)
            const uploadDataWithUrls = {
                files: {
                    lead: null
                },
                options: {
                    lead: {}
                }
            };

            // Use already uploaded file data (files were uploaded immediately when selected)
            if (this.uploadedFile && this.uploadedFile.uploadResult) {
                const leadResult = this.uploadedFile.uploadResult;
                uploadDataWithUrls.files.lead = {
                    name: this.uploadedFile.name,
                    size: this.uploadedFile.size,
                    type: this.uploadedFile.type,
                    url: leadResult.files[0]?.public_url,
                    s3_key: leadResult.files[0]?.key
                };
            }

            // The lead was already saved after S3 accepted it. Only retry the
            // legacy submit-time save if an upload result is unexpectedly absent.
            if (!this.leadPersisted) {
                await this.saveUploadDataToSession(uploadDataWithUrls);
            }


            // Redirect to next page
            const jurisdiction = apiUtils.getCurrentJurisdiction();
            window.location.href = `/jurisdiction/${jurisdiction}/expert_form/`;

        } catch (error) {
            console.error('Form submission error:', error);
            this.showError(error.message);
        }
    }



    showError(message) {
        this.hideAlerts();
        document.getElementById('errorMessage').textContent = message;
        this.errorAlert.style.display = 'block';

        // Scroll to error
        this.errorAlert.scrollIntoView({
            behavior: 'smooth',
            block: 'center'
        });
    }

    showWaiting(message) {
        this.hideAlerts();
        document.getElementById('successMessage').textContent = message;
        document.getElementById('submitButton').disabled = true;
        this.successAlert.style.display = 'block';

        // Scroll to success
        this.successAlert.scrollIntoView({
            behavior: 'smooth',
            block: 'center'
        });
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
