/**
 * Upload Handler for Document Submission
 * Handles file uploads, drag & drop, and Suffolk API integration
 */

const FileStatus = Object.freeze({
    UPLOADING: Symbol("uploading"),
    SUCCESS: Symbol("success"),
    FAILED: Symbol("failed")
});

class UploadHandler {
    constructor() {
        this.form = document.getElementById('uploadForm');
        this.leadDocumentArea = document.getElementById('leadDocumentArea');
        this.supportingDocumentsArea = document.getElementById('supportingDocumentsArea');
        this.supportingDocumentsInput = document.getElementById('supportingDocuments');
        this.submitButton = document.getElementById('submitButton');
        this.uploadProgress = document.getElementById('uploadProgress');
        this.errorAlert = document.getElementById('errorAlert');
        this.successAlert = document.getElementById('successAlert');

        this.uploadedFiles = [];
        this.uploadedFileStatuses = [];

        // Store filing components here once loaded
        this.globalFilingComponentLead = {};
        this.globalFilingComponentSupport = {};
        this.globalFilingTypes = [];

        this.jurisdiction = apiUtils.getCurrentJurisdiction();

        this.initialized = false;

        this.init();
    }

    async init() {
        if (this.initialized) {
            console.warn('UploadHandler already initialized, skipping...');
            return;
        }

        await this.loadFilingComponents();

        // First, sync any localStorage data to session
        await this.syncFormDataToSession();

        this.setupEventListeners();
        this.setupDragAndDrop();
        this.setupListeners();

        this.setupCascadingDropdowns();

        this.initialized = true;
    }

    toggleCCEmail(inputElement, checked) {
        if (checked) {
            inputElement.parentElement.removeAttribute("hidden");
            inputElement.parentElement.setAttribute("required", true);
        } else {
            inputElement.parentElement.setAttribute("hidden", true);
            inputElement.removeAttribute("required");
        }
    }

    setupListeners() {
        // Listen for changes to lead filing component
        const leadDocumentType = document.getElementById('leadDocumentType');
        if (leadDocumentType) {
            leadDocumentType.addEventListener('change', () => {
                this.updateSubmitButton();
            });
        }

        const leadCertifiedCopies = document.getElementById('leadCertifiedCopies');
        if (leadCertifiedCopies) {
            leadCertifiedCopies.addEventListener('change', (e) => {
                let inputElement = document.getElementById('leadCertifiedCopyEmail');
                this.toggleCCEmail(inputElement, e.target.checked)
            })
        }

        // Use event delegation for supporting filing components since they're added dynamically
        document.addEventListener('change', (e) => {
            if (e.target && e.target.classList.contains('document-type-select')) {
                this.updateSubmitButton();
            } else if (e.target && e.target.classList.contains('supporting-certified-copies')) {
                let idToChange = e.target.id.replace("supportingCertifiedCopies", "supportingCertifiedCopyEmail");
                let inputElement = document.getElementById(idToChange);
                if (e.target.checked) {
                    inputElement.parentElement.removeAttribute("hidden");
                    inputElement.setAttribute("required", true);
                    if (!inputElement.value) {
                        inputElement.value = document.getElementById("leadCertifiedCopyEmail").value;
                    }
                } else {
                    inputElement.parentElement.setAttribute("hidden", true);
                    inputElement.removeAttribute("required");
                }
            }
        });
    }

    async syncFormDataToSession() {
        // Check if we have form data in localStorage
        const caseFormData = localStorage.getItem('caseFormData');
        if (caseFormData) {
            try {
                await apiUtils.saveCaseData(caseFormData);
                // Clear localStorage since it's now in session
                localStorage.removeItem('caseFormData');
            } catch (error) {
                console.error('Error syncing form data:', error);
            }
        }
        // Take stuff from server and show on page. Upload metadata is optional
        // while a draft is being created, and the page should still initialize
        // if the metadata request temporarily fails.
        let upload_data = {};
        try {
            upload_data = await apiUtils.getUploadData() || {};
        } catch (error) {
            console.warn('Could not load saved upload data:', error);
        }
        await this.prepLeadFileSelection(upload_data);

        await this.prepSupportingFileSelection(upload_data);
    }

    async saveUploadDataToSession(uploadData) {
        try {
            const result = await apiUtils.saveUploadData(uploadData);
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
                supporting: this.uploadedFiles.map(file => ({
                    name: file.name,
                    size: file.size,
                    type: file.type
                }))
            };

            // Collect lead document options
            const leadFilingComponent = document.getElementById('leadFilingComponent')?.value || '';
            const leadCertifiedCopies = document.getElementById('leadCertifiedCopies')?.checked || false;
            const leadSealedConfidential = document.getElementById('leadSealedConfidential')?.checked || false;

            // Collect supporting document options
            const supportingOptions = [];
            this.uploadedFiles.forEach((file, index) => {
                supportingOptions.push({
                    filing_component: this.globalFilingComponentSupport,
                    certified_copies: document.getElementById(`supportingCertifiedCopies${index}`)?.checked || false,
                    sealed_confidential: document.getElementById(`supportingSealedConfidential${index}`)?.checked || false
                });
            });

            const uploadData = {
                files: fileData,
                options: {
                    lead: {
                        filing_component: leadFilingComponent,
                        certified_copies: leadCertifiedCopies,
                        sealed_confidential: leadSealedConfidential
                    },
                    supporting: supportingOptions
                }
            };

            const response = await apiUtils.saveUploadData(uploadData);
            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || 'Failed to save upload data to session');
            }
        } catch (error) {
            console.error('Error saving files to session:', error);
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

    async setupDragAndDrop() {
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

    async prepLeadFileSelection(upload_data) {
        const lead = upload_data?.files?.lead;

        // A draft may not have a lead document yet (for example after an
        // interrupted upload). Leave the options hidden and let the page
        // recover without throwing during initialization.
        if (!lead) {
            return;
        }

        // Add file previews
        const preview = this.createFilePreviewNoRemove(lead.name, lead.size);
        this.leadDocumentArea.appendChild(preview);

        // Show/hide document options based on whether files are uploaded
        const leadOptions = document.getElementById('leadDocumentOptions');
        if (leadOptions) {
            leadOptions.style.display = 'block';
        }

        if (upload_data.lead_filing_type) {
            this.initializeFilingTypeDropdown(document.getElementById("leadFilingType_search"));
            window[`leadFilingTypeDropdown`].selectOption({
                "text": upload_data.lead_filing_type_name,
                "value": upload_data.lead_filing_type
            });

            await this.populateDocumentTypes(upload_data.lead_filing_type, document.getElementById("leadDocumentType"));
        }
        if (upload_data.lead_document_type) {
            document.getElementById("leadDocumentType").value = upload_data.lead_document_type;
        }
        if (upload_data.lead_cc_email) {
            let input_element = document.getElementById("leadCertifiedCopies")
            input_element.checked = true;
            this.toggleCCEmail(input_element, true);
            document.getElementById("leadCertifiedCopyEmail").value = upload_data.lead_cc_email;
        }
    }

    async prepSupportingFileSelection(upload_data) {
        this.uploadedFiles = upload_data?.files?.supporting || [];
        if (this.uploadedFiles && this.uploadedFiles.length > 0) {
            this.uploadedFileStatuses = this.uploadedFiles.map(f => FileStatus.SUCCESS);
            this.updateFilePreview(this.supportingDocumentsArea, this.uploadedFiles, this.uploadedFileStatuses);
            const supportingDocuments = upload_data?.supporting_documents || [];
            for (let index = 0; index < supportingDocuments.length; index++) {
                let d = supportingDocuments[index];

                if (d.filing_type) {
                    this.initializeFilingTypeDropdown(document.getElementById(`supportingFilingType${index}_search`));
                    window[`supportingFilingType${index}Dropdown`].selectOption({
                        "text": d.filing_type_name,
                        "value": d.filing_type
                    });

                    await this.populateDocumentTypes(d.filing_type, document.getElementById(`supportingDocumentType${index}`));
                }
                if (d.document_type) {
                    document.getElementById(`supportingDocumentType${index}`).value = d.document_type;
                }
                if (d.cc_email) {
                    let input_element = document.getElementById(`supportingFilingType${index}`);
                    input_element.checked = true;
                    this.toggleCCEmail(input_element, true);
                    document.getElementById(`supportingCertifiedCopyEmail${index}`).value = d.cc_email;
                }
            };
        }
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

        // Multiple supporting documents allowed
        const startIndex = this.uploadedFiles.length;
        this.uploadedFiles = [...this.uploadedFiles, ...validFiles];
        this.uploadedFileStatuses = [...this.uploadedFileStatuses, validFiles.map(f => FileStatus.UPLOADING)];
        this.updateFilePreview(this.supportingDocumentsArea, this.uploadedFiles, this.uploadedFileStatuses);

        // Update native supporting input FileList to match uploadedFiles.supporting
        try {
            const dt = new DataTransfer();
            this.uploadedFiles.forEach(file => dt.items.add(file));
            if (this.supportingDocumentsInput) {
                this.supportingDocumentsInput.files = dt.files;
            }
        } catch (e) {
            console.warn('Could not set native supporting input.files via DataTransfer:', e);
        }

        // Automatically upload each new supporting document
        validFiles.forEach((file, index) => {
            this.uploadFileImmediately(file, type, startIndex + index);
        });

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

    updateFilePreview(area, files, file_statuses) {
        // Clear existing preview
        const existingPreviews = area.querySelectorAll('.file-preview');
        existingPreviews.forEach(preview => preview.remove());

        // Add file previews
        files.forEach((file, index) => {
            const preview = this.createFilePreview(file, index);
            area.appendChild(preview);
        });

        // Update supporting documents options
        this.updateSupportingDocumentsOptions(files);
        file_statuses.forEach((status, index) => {
            if (status === FileStatus.SUCCESS) {
                this.showFileUploadSuccess(index);
            } else if (status === FileStatus.FAILED) {
                this.showFileUploadError(index, "Failed");
            } else if (status === FileStatus.UPLOADING) {
                this.showFileUploadProgress(index);
            }
        });

        // Hide/show placeholder
        const placeholder = area.querySelector('.upload-placeholder');
        if (placeholder) {
            placeholder.style.display = files.length > 0 ? 'none' : 'block';
        }

    }

    createFilePreviewNoRemove(file_name, file_size) {
        const preview = document.createElement('div');
        preview.className = 'file-preview-lead';

        const fileSize = this.formatFileSize(file_size);

        preview.innerHTML = `
            <div class="file-info">
                <i class="fas fa-file-pdf"></i>
                <div>
                    <div class="fw-semibold">${file_name}</div>
                    <div class="text-muted small">${fileSize}</div>
                </div>
            </div>
        `;

        return preview;
    }

    createFilePreview(file, index) {
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
            this.removeFile(index);
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();

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

    updateSupportingDocumentsOptions(files) {
        const optionsContainer = document.getElementById('supportingDocumentsOptions');
        if (!optionsContainer) return;

        // Clear existing options
        optionsContainer.innerHTML = '';

        // Add options for each supporting document
        files.forEach((file, index) => {
            const optionsHTML = createSupportingDocumentOptions(index, file.name);

            const div = document.createElement('div');
            div.innerHTML = optionsHTML;
            optionsContainer.appendChild(div.firstElementChild);
        });

        // Initialize search dropdowns for supporting documents
        this.initializeSupportingFilingTypeDropdowns(files);
    }

    async initializeSupportingFilingTypeDropdowns(files) {
        // Use global filing types data if available, otherwise wait for it to load
        const checkGlobalData = () => {
            if (this.globalFilingTypes && this.globalFilingTypes.length > 0) {
                // Initialize each supporting document's filing type dropdown
                files.forEach((file, index) => {
                    const filingTypeDropdown = document.getElementById(`supportingFilingType${index}_search`);
                    if (filingTypeDropdown && window.SearchDropdown) {
                        const searchDropdown = new window.SearchDropdown(`supportingFilingType${index}`, {
                            placeholder: 'Search filing types...'
                        });
                        searchDropdown.updateOptions(this.globalFilingTypes);

                        // Store reference for later use
                        window[`supportingFilingType${index}Dropdown`] = searchDropdown;
                    } else {
                        console.warn(`Dropdown element not found for supportingFilingType${index}_search`);
                    }

                    // Setup cascading dropdown logic
                    this.setupSupportingDocumentCascading(index);
                });
            } else {
                // Wait a bit and try again
                setTimeout(checkGlobalData, 100);
            }
        };

        checkGlobalData();
    }

    setupSupportingDocumentCascading(index) {
        const filingTypeSelect = document.getElementById(`supportingFilingType${index}`);
        const documentTypeSelect = document.getElementById(`supportingDocumentType${index}`);

        if (filingTypeSelect && documentTypeSelect) {
            filingTypeSelect.addEventListener('change', async () => {
                const selectedFilingTypeId = filingTypeSelect.value;
                if (selectedFilingTypeId) {
                    await this.populateDocumentTypes(selectedFilingTypeId, documentTypeSelect);
                } else {
                    documentTypeSelect.innerHTML = '<option value="">Select filing type first</option>';
                }
            });
        }
    }

    removeFile(index) {
        this.uploadedFiles.splice(index, 1);
        this.uploadedFileStatuses.splice(index, 1);
        // Regenerate all supporting file previews with correct indices
        this.updateFilePreview(this.supportingDocumentsArea, this.uploadedFiles, this.uploadedFileStatuses);

        // Update native supporting input FileList
        try {
            const dt = new DataTransfer();
            this.uploadedFiles.forEach(file => dt.items.add(file));
            if (this.supportingDocumentsInput) {
                this.supportingDocumentsInput.files = dt.files;
            }
        } catch (e) {
            console.warn('Could not update native supporting input.files after removal:', e);
        }

        this.updateSubmitButton();
    }

    updateSubmitButton() {
        let hasAllFilingComponents = true;

        let uploadsSucceeded = this.uploadedFileStatuses.every(st => st === FileStatus.SUCCESS);

        // Check if lead document has filing component selected
        const leadFilingType = document.getElementById('leadFilingType');
        if (leadFilingType && !leadFilingType.value) {
            hasAllFilingComponents = false;
        }

        // Check if all supporting documents have filing components selected
        if (this.uploadedFiles) {
            this.uploadedFiles.forEach((file, index) => {
                const supportingFilingType = document.getElementById(`supportingFilingType${index}`);
                if (supportingFilingType && !supportingFilingType.value) {
                    hasAllFilingComponents = false;
                }
            });
        }
        this.submitButton.disabled = !uploadsSucceeded || !hasAllFilingComponents;
    }

    async uploadFileImmediately(file, type, index) {
        try {
            this.showFileUploadProgress(index);

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
                this.uploadedFileStatuses[index] = FileStatus.FAILED;
                throw new Error(result.error || 'Upload failed');
            }

            // Update file preview to show successful upload
            this.showFileUploadSuccess(index);

            // Store the upload result for later use during form submission
            this.uploadedFiles[index].uploadResult = result;

        } catch (error) {
            console.error('Error uploading file immediately:', error);
            this.showFileUploadError(index, error.message);
        }
    }

    showFileUploadProgress(index) {
        this.uploadedFileStatuses[index] = FileStatus.UPLOADING;
        const selector = `.file-preview:nth-child(${index + 3})`;
        const preview = this.supportingDocumentsArea.querySelector(selector);

        if (preview) {
            const statusDiv = preview.querySelector('.upload-status') || document.createElement('div');
            statusDiv.className = 'upload-status';
            statusDiv.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Uploading...';
            if (!preview.querySelector('.upload-status')) {
                preview.appendChild(statusDiv);
            }
        }
    }

    showFileUploadSuccess(index) {
        this.uploadedFileStatuses[index] = FileStatus.SUCCESS;
        const selector = `.file-preview:nth-child(${index + 3})`;
        const preview = this.supportingDocumentsArea.querySelector(selector);

        if (preview) {
            const statusDiv = preview.querySelector('.upload-status') || document.createElement("div");
            statusDiv.className = 'upload-status';
            statusDiv.innerHTML = '<i class="fas fa-check-circle text-success me-1"></i>Uploaded';
            if (!preview.querySelector(".upload-status")) {
                preview.appendChild(statusDiv);
            }
        }
    }

    showFileUploadError(index, error) {
        this.uploadedFileStatuses[index] = FileStatus.FAILED;
        const selector = `.file-preview:nth-child(${index + 3})`;
        const preview = this.supportingDocumentsArea.querySelector(selector);

        if (preview) {
            const statusDiv = preview.querySelector('.upload-status') || document.createElement("div");
            statusDiv.className = "upload-status";
            statusDiv.innerHTML = '<i class="fas fa-exclamation-triangle text-danger me-1"></i>Upload failed';
            statusDiv.title = error;
            if (!preview.querySelector('.upload-status')) {
                preview.appendChild(statusDiv);
            }
        }
    }

    async handleFormSubmission() {
        // Validate that all supporting documents have filing components selected
        for (let i = 0; i < this.uploadedFiles.length; i++) {
            const supportingFilingType = document.getElementById(`supportingFilingType${i}`)?.value;
            if (!supportingFilingType) {
                this.showError(`Please select a filing component for supporting document: ${this.uploadedFiles[i].name}`);
                return;
            }
            const supportingDocumentType = document.getElementById(`supportingDocumentType${i}`)?.value;
            if (!supportingDocumentType) {
                this.showError(`Please select a document type for supporting document: ${this.uploadedFiles[i].name}`);
                return;
            }
        }

        try {
            // Collect dropdown values for lead document
            const leadFilingTypeSelect = document.getElementById('leadFilingType');
            const leadDocumentTypeSelect = document.getElementById('leadDocumentType');

            const leadFilingType = leadFilingTypeSelect ? leadFilingTypeSelect.value : '';
            const leadFilingTypeName = leadFilingTypeSelect && leadFilingTypeSelect.selectedOptions[0] ? leadFilingTypeSelect.selectedOptions[0].text : '';
            const leadDocumentType = leadDocumentTypeSelect ? leadDocumentTypeSelect.value : '';
            const leadDocumentTypeName = leadDocumentTypeSelect && leadDocumentTypeSelect.selectedOptions[0] ? leadDocumentTypeSelect.selectedOptions[0].text : '';

            if (!leadFilingType || !leadDocumentType) {
                this.showError('Please select a filing type and document type for the lead document.');
                return;
            }

            const leadFilingComponentValue = this.globalFilingComponentLead.id;
            const leadFilingComponentName = this.globalFilingComponentLead.name;

            let leadCCEmail = document.getElementById('leadCertifiedCopyEmail').value;
            if (!document.getElementById('leadCertifiedCopies').checked) {
                leadCCEmail = null;
            }

            // Collect supporting document dropdown values
            const supportingDocuments = [];
            const supportingDropdowns = document.querySelectorAll('select[id*="supportingFilingType"]:not([id*="_search"])');
            supportingDropdowns.forEach((dropdown, index) => {
                const filingType = dropdown.value;
                const filingTypeName = dropdown.selectedOptions[0]?.text || '';
                const docTypeSelect = document.getElementById(`supportingDocumentType${index}`);
                const docType = docTypeSelect?.value || '';
                const docTypeName = docTypeSelect?.selectedOptions[0]?.text || '';
                const component = this.globalFilingComponentSupport.id;
                const componentName = this.globalFilingComponentSupport.name;

                let supportingCCEmail = document.getElementById(`supportingCertifiedCopyEmail${index}`).value;
                if (!document.getElementById(`supportingCertifiedCopies${index}`).checked) {
                    supportingCCEmail = null;
                }

                const supportingDoc = {
                    filing_type: filingType,
                    filing_type_name: filingTypeName,
                    document_type: docType,
                    document_type_name: docTypeName,
                    filing_component: component,
                    filing_component_name: componentName,
                    cc_email: supportingCCEmail
                };

                supportingDocuments.push(supportingDoc);
            });

            // Prepare upload data using already uploaded files (since files are uploaded immediately on selection)
            const uploadDataWithUrls = {
                files: [],
                options: {
                    lead: {
                        filing_component: {
                            id: leadFilingComponentValue,
                            name: leadFilingComponentName
                        },
                        certified_copies: document.getElementById('leadCertifiedCopies')?.checked || false,
                        sealed_confidential: document.getElementById('leadSealedConfidential')?.checked || false
                    },
                    supporting: []
                },
                // Add dropdown data for lead document
                lead_filing_type: leadFilingType,
                lead_filing_type_name: leadFilingTypeName,
                lead_document_type: leadDocumentType,
                lead_document_type_name: leadDocumentTypeName,
                lead_filing_component: leadFilingComponentValue,
                lead_filing_component_name: leadFilingComponentName,
                lead_cc_email: leadCCEmail,
                // Add supporting documents dropdown data
                supporting_documents: supportingDocuments
            };
            // Process supporting documents that were already uploaded
            this.uploadedFiles.forEach((file, index) => {
                const supportingFilingComponent = this.globalFilingComponentSupport;
                if (file.uploadResult) {
                    file.url = file.uploadResult.files[0]?.public_url;
                    file.s3_key = file.uploadResult.files[0]?.key;
                }
                if (file.s3_key && file.url) {
                    uploadDataWithUrls.files.push({
                        name: file.name,
                        size: file.size,
                        type: file.type,
                        url: file.url,
                        s3_key: file.s3_key,
                        filing_component: supportingFilingComponent
                    });

                    // Also add to options array
                    uploadDataWithUrls.options.supporting.push({
                        filing_component: supportingFilingComponent,
                        certified_copies: document.getElementById(`supportingCertifiedCopies${index}`)?.checked || false,
                        sealed_confidential: document.getElementById(`supportingSealedConfidential${index}`)?.checked || false
                    });
                }
            });

            // Save the complete upload data to session
            await this.saveUploadDataToSession(uploadDataWithUrls);


            // Redirect to payments page
            window.location.href = `/jurisdiction/${this.jurisdiction}/payment/`;

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

    showSuccess(message) {
        this.hideAlerts();
        document.getElementById('successMessage').textContent = message;
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

    populateForm(data) {
        this.restorationData = data;

        Object.keys(data).forEach((key) => {
            const field = this.form.querySelector(`[name="${key}"]`);
            if (field) {
                if (field.type === "checkbox" || field.type === "radio") {
                    field.checked = Array.isArray(data[key]) ?
                        data[key].includes(field.value) :
                        data[key] === field.value;
                } else {
                    field.value = Array.isArray(data[key]) ? data[key][0] : data[key];
                }

                // Trigger change event for dropdowns to update dependent fields
                if (field.tagName === "SELECT") {
                    field.dispatchEvent(new Event("change", {
                        bubbles: true
                    }));
                }
            }
        });

    }

    async loadFilingComponents() {
        try {
            // Use our backend API endpoint instead of direct Suffolk API call to avoid CORS
            const response = await fetch(`/api/get-filing-components/?jurisdiction=${this.jurisdiction}`, {
                method: "GET",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": apiUtils.getCSRFToken(),
                },
            });

            if (!response.ok) {
                throw new Error(
                    `Failed to load filing components: ${response.status}`
                );
            }

            const result = await response.json();
            if (result.success && result.data) {
                // TODO(brycew): Make selecting Lead document and attachment more resillient
                result.data.map((component) => {
                    if (component.name === "Lead Document") {
                        this.globalFilingComponentLead = {
                            id: component.code,
                            name: component.name
                        };
                    }
                    if (component.name === "Attachments") {
                        this.globalFilingComponentSupport = {
                            id: component.code,
                            name: component.name
                        };
                    }
                });

                // Some filing types expose only one filing component. In
                // that case the EFSP still expects that component's code for
                // supporting documents; never send the UI label "supporting".
                if (!this.globalFilingComponentSupport.id && this.globalFilingComponentLead.id) {
                    this.globalFilingComponentSupport = {
                        id: this.globalFilingComponentLead.id,
                        name: this.globalFilingComponentLead.name
                    };
                }
            } else {
                console.error("API returned error:", result.error);
            }
        } catch (error) {
            console.error("Error loading filing components:", error);
        }
    }

    async initializeSearchDropdowns() {
        // Get case data from Django context (passed from the view)
        const caseClassification = JSON.parse(document.getElementById("case-classification").textContent);
        const court = caseClassification.court || sessionStorage.getItem("selected_court");
        const caseType = caseClassification.case_type || sessionStorage.getItem("selected_case_type");
        // TODO(brycew): add escapejs to other templated stuff I've added
        // TODO(brycew): check that this works at all fallbacks
        const categoryType = caseClassification.case_category || sessionStorage.getItem("selected_category_type");
        const existingCase = sessionStorage.getItem("existing_case") || "no";

        if (!court || !caseType) {
            console.warn(
                "Missing court or case_type for filing type dropdown initialization"
            );
            return;
        }

        let uploadData = {};
        try {
            uploadData = await apiUtils.getUploadData() || {};
        } catch (error) {
            console.warn('Could not load upload guesses:', error);
        }
        const guesses = uploadData.guesses || {};

        // Fetch filing types data only once
        if (this.globalFilingTypes.length === 0) {
            try {
                const apiUrl = `/api/dropdowns/filing-types/?jurisdiction=${this.jurisdiction}&court=${encodeURIComponent(
              court
            )}&case_category=${encodeURIComponent(categoryType)}&case_type=${encodeURIComponent(
              caseType
            )}&existing_case=${existingCase}&guessed_filing_type=${guesses["filing type"]}`;

                const response = await fetch(apiUrl, {
                    method: "GET",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": apiUtils.getCSRFToken(),
                    },
                });

                if (!response.ok) {
                    throw new Error(
                        `Failed to load filing types: ${response.status}`
                    );
                }

                const result = await response.json();
                if (result.success && result.data) {
                    this.globalFilingTypes = result.data.map((item, index) => {
                        const processedItem = {
                            value: item.value || item.code || item.id,
                            text: item.text || item.name || item.description,
                        };
                        return processedItem;
                    });
                } else {
                    console.error("API returned error:", result.error);
                    return;
                }
            } catch (error) {
                console.error("Error loading filing types:", error);
                return;
            }
        }

        // Initialize all existing filing type search dropdowns
        this.initializeFilingTypeDropdowns();
    }

    async populateDocumentTypes(filingTypeId, documentTypeSelect) {
        try {
            // Get court data from Django context to pass required parameters
            const court = JSON.parse(document.getElementById("case-classification").textContent)["court"] || sessionStorage.getItem("selected_court");

            if (!court) {
                console.error("Missing court parameter for document types API");
                documentTypeSelect.innerHTML =
                    '<option value="">Missing court data</option>';
                return;
            }

            let params = {
                jurisdiction: this.jurisdiction,
                court: court,
                parent: filingTypeId,
            }
            const result = await apiUtils.get('/api/dropdowns/document-types', params, true);
            if (result.success && result.data) {
                documentTypeSelect.innerHTML =
                    '<option value="">Select an option</option>';
                result.data.forEach((docType) => {
                    const option = document.createElement("option");
                    option.value = docType.value || docType.code || docType.id;
                    option.textContent =
                        docType.text || docType.name || docType.description;
                    documentTypeSelect.appendChild(option);
                });
            } else {
                console.error("API returned error:", result.error);
                documentTypeSelect.innerHTML =
                    '<option value="">Error loading document types</option>';
            }
        } catch (error) {
            console.error("Error loading document types:", error);
            documentTypeSelect.innerHTML =
                '<option value="">Error loading document types</option>';
        }
    }

    setupCascadingDropdowns() {
        // Lead document cascading dropdowns
        const leadFilingTypeSelect = document.getElementById("leadFilingType");
        const leadDocumentTypeSelect =
            document.getElementById("leadDocumentType");

        if (leadFilingTypeSelect) {
            leadFilingTypeSelect.addEventListener("change", () => {
                const selectedFilingTypeId = leadFilingTypeSelect.value;

                if (selectedFilingTypeId) {
                    this.populateDocumentTypes(
                        selectedFilingTypeId,
                        leadDocumentTypeSelect
                    );
                    // Don't reset filing components - they should remain available
                }
            });
        }
    }

    initializeFilingTypeDropdowns() {
        // Initialize filing type search dropdowns
        const filingTypeDropdowns = document.querySelectorAll(
            '[id*="FilingType_search"]'
        );

        filingTypeDropdowns.forEach((dropdown) => this.initializeFilingTypeDropdown(dropdown));
    }

    initializeFilingTypeDropdown(dropdown) {
        // Extract the base field ID from the search input ID
        const fieldId = dropdown.id.replace("_search", "");

        const searchDropdown = new SearchDropdown(fieldId, {
            placeholder: gettext("Search filing types..."),
        });
        searchDropdown.updateOptions(this.globalFilingTypes);

        // Store reference for later use
        window[`${fieldId}Dropdown`] = searchDropdown;
    }

}

function populateDropdownFallback(dropdown) {
    if (!dropdown) return;

    dropdown.innerHTML = `
                <option value="">${gettext("Select a document type")}</option>
                <option value="lead">${gettext("Lead Document")}</option>
                <option value="supporting">${gettext("Supporting Document")}</option>
                <option value="exhibit">${gettext("Exhibit")}</option>
            `;
}

function createSupportingDocumentOptions(index, fileName) {
    const html = `
                <div class="document-options mt-3 supporting-document-options" id="supportingDocumentOptions${index}">
                    <h6 class="mb-3"><strong>Options for: ${fileName}</strong></h6>
                    <!-- No \`required\` on the controls below: search-dropdown.js hides the input
                         once a choice is made and the <select> is always d-none, so the browser
                         would refuse to submit with "not focusable" exactly when the field IS
                         filled in. handleSubmit validates these instead. -->
                    <div class="row" style="align-items: baseline">
                        <div class="col-md-6">
                            <label for="supportingFilingType${index}" class="form-label"><strong>Filing Type</strong> <span class="required">*</span></label>
                            <div class="search-dropdown-container" id="supportingFilingType${index}-container">
                                <input
                                  type="text"
                                  class="form-control search-dropdown-input"
                                  id="supportingFilingType${index}_search"
                                  name="supportingFilingType${index}_search"
                                  placeholder="Search filing types..."
                                  autocomplete="off"
                                />
                                
                                <select
                                  class="form-select dropdown-field d-none"
                                  id="supportingFilingType${index}"
                                  name="supporting_filing_type_${index}"
                                >
                                  <option value="">Select Filing Type</option>
                                </select>
                                
                                <div class="search-dropdown-results" id="supportingFilingType${index}-results" style="display: none;">
                                  <div class="search-no-results">No matching options found</div>
                                </div>
                                
                                <div class="search-dropdown-selected" id="supportingFilingType${index}-selected" style="display: none;">
                                  <span class="selected-text"></span>
                                  <button type="button" class="btn-clear" aria-label="Clear selection">&times;</button>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <label for="supportingDocumentType${index}" class="form-label"><strong>Request Documents to be Sealed / Confidential?</strong> <span class="required">*</span></label>
                            <select class="form-select document-type-select" id="supportingDocumentType${index}" name="supporting_document_type_${index}">
                                <option value="">Select filing type first</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="row mt-3">
                        <div class="col-md-6">
                            <div class="form-check">
                                <input class="form-check-input supporting-certified-copies" type="checkbox" id="supportingCertifiedCopies${index}" name="supporting_certified_copies_${index}">
                                <label class="form-check-label" for="supportingCertifiedCopies${index}">
                                    Request certified copies when filed
                                </label>
                            </div>
                            <div class="form-text" hidden>
                                <label class="form-text-label form-label" for="supportingCertifiedCopyEmail${index}"><strong>Email:</strong></label>
                                <input class="form-text-input form-control" type="email" id="supportingCertifiedCopyEmail${index}" name="supporting_certified_copy_email_${index}">
                            </div>
                        </div>
                    </div>
                </div>
            `;

    return html;
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (!window.uploadHandler) {
        window.uploadHandler = new UploadHandler();
    } else {
        console.warn('UploadHandler already exists, skipping initialization');
    }
});