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
        this.setupFilingComponentListeners();
        
        this.initialized = true;
    }

    setupFilingComponentListeners() {
        // Listen for changes to lead filing component
        const leadFilingComponent = document.getElementById('leadFilingComponent');
        if (leadFilingComponent) {
            leadFilingComponent.addEventListener('change', () => {
                this.updateSubmitButton();
            });
        }

        // Use event delegation for supporting filing components since they're added dynamically
        document.addEventListener('change', (e) => {
            if (e.target && e.target.classList.contains('supporting-filing-component')) {
                this.updateSubmitButton();
            }
        });
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

            // Collect lead document options
            const leadFilingComponent = document.getElementById('leadFilingComponent')?.value || '';
            const leadCertifiedCopies = document.getElementById('leadCertifiedCopies')?.checked || false;
            const leadSealedConfidential = document.getElementById('leadSealedConfidential')?.checked || false;

            // Collect supporting document options
            const supportingOptions = [];
            this.uploadedFiles.supporting.forEach((file, index) => {
                supportingOptions.push({
                    filing_component: document.getElementById(`supportingFilingComponent${index}`)?.value || '',
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

            // Automatically upload lead document
            this.uploadFileImmediately(validFiles[0], type, 0);
        } else {
            // Multiple supporting documents allowed
            const startIndex = this.uploadedFiles.supporting.length;
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

            // Automatically upload each new supporting document
            validFiles.forEach((file, index) => {
                this.uploadFileImmediately(file, type, startIndex + index);
            });
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

        // Show/hide document options based on whether files are uploaded
        if (type === 'lead') {
            const leadOptions = document.getElementById('leadDocumentOptions');
            if (leadOptions) {
                leadOptions.style.display = files.length > 0 ? 'block' : 'none';
            }
        } else if (type === 'supporting') {
            // Update supporting documents options
            this.updateSupportingDocumentsOptions(files);
        }

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
            }            this.updateSubmitButton();
            
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
            const optionsHTML = window.createSupportingDocumentOptions ? 
                window.createSupportingDocumentOptions(index, file.name) :
                this.createSupportingDocumentOptionsHTML(index, file.name);
            
            const div = document.createElement('div');
            div.innerHTML = optionsHTML;
            optionsContainer.appendChild(div.firstElementChild);
        });
        
        // Initialize search dropdowns for supporting documents
        this.initializeSupportingFilingTypeDropdowns(files);
        
        // Populate dropdowns with filing components if available
        if (window.globalFilingComponents && window.populateFilingComponentDropdown) {
            const supportingDropdowns = optionsContainer.querySelectorAll('.supporting-filing-component');
            supportingDropdowns.forEach(dropdown => {
                window.populateFilingComponentDropdown(dropdown);
            });
        }
    }

    async initializeSupportingFilingTypeDropdowns(files) {        
        // Use global filing types data if available, otherwise wait for it to load
        const checkGlobalData = () => {
            if (window.globalFilingTypes && window.globalFilingTypes.length > 0) {
                // Initialize each supporting document's filing type dropdown
                files.forEach((file, index) => {
                    const filingTypeDropdown = document.getElementById(`supportingFilingType${index}_search`);
                    if (filingTypeDropdown && window.SearchDropdown) {
                        const searchDropdown = new window.SearchDropdown(`supportingFilingType${index}`, {
                            placeholder: 'Search filing types...'
                        });
                        searchDropdown.updateOptions(window.globalFilingTypes);
                        
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

    getCSRFToken() {
        return (
            document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
            document
                .querySelector('meta[name="csrf-token"]')
                ?.getAttribute("content") ||
            ""
        );
    }

    setupSupportingDocumentCascading(index) {
        const filingTypeSelect = document.getElementById(`supportingFilingType${index}`);
        const documentTypeSelect = document.getElementById(`supportingDocumentType${index}`);
        const filingComponentSelect = document.getElementById(`supportingFilingComponent${index}`);

        if (filingTypeSelect && documentTypeSelect && filingComponentSelect) {
            filingTypeSelect.addEventListener('change', async () => {
                const selectedFilingTypeId = filingTypeSelect.value;                
                if (selectedFilingTypeId) {
                    await window.populateDocumentTypes(selectedFilingTypeId, documentTypeSelect);
                    filingComponentSelect.innerHTML = '<option value="">Select document type first</option>';
                } else {
                    documentTypeSelect.innerHTML = '<option value="">Select filing type first</option>';
                    filingComponentSelect.innerHTML = '<option value="">Select document type first</option>';
                }
            });

            documentTypeSelect.addEventListener('change', () => {
                const selectedDocumentType = documentTypeSelect.value;
                
                if (selectedDocumentType) {
                    window.populateFilingComponents(selectedDocumentType, filingComponentSelect);
                } else {
                    filingComponentSelect.innerHTML = '<option value="">Select document type first</option>';
                }
            });

            filingComponentSelect.addEventListener('change', () => {
                const selectedComponent = filingComponentSelect.value;
            });
        }
    }

    createSupportingDocumentOptionsHTML(index, fileName) {
        return `
            <div class="document-options mt-3 supporting-document-options" id="supportingDocumentOptions${index}">
                <h6 class="mb-3"><strong>Options for: ${fileName}</strong></h6>
                <div class="row">
                    <div class="col-md-6">
                        <label for="supportingFilingComponent${index}" class="form-label"><strong>Filing Component</strong> <span class="required">*</span></label>
                        <select class="form-select supporting-filing-component" id="supportingFilingComponent${index}" name="supporting_filing_component_${index}" required>
                            <option value="">Select a document type</option>
                        </select>
                    </div>
                </div>
                
                <div class="row mt-3">
                    <div class="col-md-6">
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" id="supportingCertifiedCopies${index}" name="supporting_certified_copies_${index}">
                            <label class="form-check-label" for="supportingCertifiedCopies${index}">
                                Request certified copies when filed
                            </label>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" id="supportingSealedConfidential${index}" name="supporting_sealed_confidential_${index}">
                                <label class="form-check-label" for="supportingSealedConfidential${index}">
                                Request documents be sealed/confidential
                            </label>
                        </div>
                    </div>
                </div>
            </div>
        `;
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
        let hasAllFilingComponents = true;

        // Check if lead document has filing component selected
        if (hasLeadDocument) {
            const leadFilingComponent = document.getElementById('leadFilingComponent');
            if (leadFilingComponent && !leadFilingComponent.value) {
                hasAllFilingComponents = false;
            }
        }

        // Check if all supporting documents have filing components selected
        this.uploadedFiles.supporting.forEach((file, index) => {
            const supportingFilingComponent = document.getElementById(`supportingFilingComponent${index}`);
            if (supportingFilingComponent && !supportingFilingComponent.value) {
                hasAllFilingComponents = false;
            }
        });

        this.submitButton.disabled = !hasLeadDocument || !hasAllFilingComponents;
    }

    async uploadFileImmediately(file, type, index) {
        try {
            // Show upload progress for this specific file
            this.showFileUploadProgress(file.name, type, index);

            // Create FormData with just this file
            const formData = new FormData();
            formData.append('documents', file);

            const response = await fetch('/api/simple-s3-upload/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': this.getCSRFToken()
                }
            });

            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error || 'Upload failed');
            }

            // Update file preview to show successful upload
            this.showFileUploadSuccess(file.name, type, index);

            // Store the upload result for later use during form submission
            if (type === 'lead') {
                this.uploadedFiles.lead.uploadResult = result;
            } else {
                this.uploadedFiles.supporting[index].uploadResult = result;
            }

        } catch (error) {
            console.error('Error uploading file immediately:', error);
            this.showFileUploadError(file.name, type, index, error.message);
        }
    }

    showFileUploadProgress(fileName, type, index) {
        const selector = type === 'lead' ? '.file-preview' : `.file-preview:nth-child(${index + 2})`;
        const preview = type === 'lead' 
            ? this.leadDocumentArea.querySelector(selector)
            : this.supportingDocumentsArea.querySelector(selector);
        
        if (preview) {
            const statusDiv = preview.querySelector('.upload-status') || document.createElement('div');
            statusDiv.className = 'upload-status';
            statusDiv.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Uploading...';
            if (!preview.querySelector('.upload-status')) {
                preview.appendChild(statusDiv);
            }
        }
    }

    showFileUploadSuccess(fileName, type, index) {
        const selector = type === 'lead' ? '.file-preview' : `.file-preview:nth-child(${index + 2})`;
        const preview = type === 'lead' 
            ? this.leadDocumentArea.querySelector(selector)
            : this.supportingDocumentsArea.querySelector(selector);
        
        if (preview) {
            const statusDiv = preview.querySelector('.upload-status');
            if (statusDiv) {
                statusDiv.innerHTML = '<i class="fas fa-check-circle text-success me-1"></i>Uploaded';
            }
        }
    }

    showFileUploadError(fileName, type, index, error) {
        const selector = type === 'lead' ? '.file-preview' : `.file-preview:nth-child(${index + 2})`;
        const preview = type === 'lead' 
            ? this.leadDocumentArea.querySelector(selector)
            : this.supportingDocumentsArea.querySelector(selector);
        
        if (preview) {
            const statusDiv = preview.querySelector('.upload-status');
            if (statusDiv) {
                statusDiv.innerHTML = '<i class="fas fa-exclamation-triangle text-danger me-1"></i>Upload failed';
                statusDiv.title = error;
            }
        }
    }

    async handleFormSubmission() {
        if (!this.uploadedFiles.lead) {
            this.showError('Please upload a lead document before continuing.');
            return;
        }

        // Validate that lead document has filing component selected
        const leadFilingComponent = document.getElementById('leadFilingComponent')?.value;
        if (!leadFilingComponent) {
            this.showError('Please select a filing component for your lead document.');
            return;
        }

        // Validate that all supporting documents have filing components selected
        for (let i = 0; i < this.uploadedFiles.supporting.length; i++) {
            const supportingFilingComponent = document.getElementById(`supportingFilingComponent${i}`)?.value;
            if (!supportingFilingComponent) {
                this.showError(`Please select a filing component for supporting document: ${this.uploadedFiles.supporting[i].name}`);
                return;
            }
        }

        try {
            // Collect dropdown values for lead document
            const leadFilingTypeSelect = document.getElementById('leadFilingType');
            const leadDocumentTypeSelect = document.getElementById('leadDocumentType');
            const leadFilingComponentSelect = document.getElementById('leadFilingComponent');
            
            const leadFilingType = leadFilingTypeSelect ? leadFilingTypeSelect.value : '';
            const leadFilingTypeName = leadFilingTypeSelect && leadFilingTypeSelect.selectedOptions[0] ? leadFilingTypeSelect.selectedOptions[0].text : '';
            const leadDocumentType = leadDocumentTypeSelect ? leadDocumentTypeSelect.value : '';
            const leadDocumentTypeName = leadDocumentTypeSelect && leadDocumentTypeSelect.selectedOptions[0] ? leadDocumentTypeSelect.selectedOptions[0].text : '';
            const leadFilingComponentValue = leadFilingComponentSelect ? leadFilingComponentSelect.value : '';
            const leadFilingComponentName = leadFilingComponentSelect && leadFilingComponentSelect.selectedOptions[0] ? leadFilingComponentSelect.selectedOptions[0].text : '';

            // Collect supporting document dropdown values
            const supportingDocuments = [];
            const supportingDropdowns = document.querySelectorAll('[id*="supportingFilingType"]:not([id*="_search"])');
            supportingDropdowns.forEach((dropdown, index) => {
                const filingType = dropdown.value;
                const filingTypeName = dropdown.selectedOptions[0]?.text || '';
                const docTypeSelect = document.getElementById(`supportingDocumentType${index}`);
                const docType = docTypeSelect?.value || '';
                const docTypeName = docTypeSelect?.selectedOptions[0]?.text || '';
                const componentSelect = document.getElementById(`supportingFilingComponent${index}`);
                const component = componentSelect?.value || '';
                const componentName = componentSelect?.selectedOptions[0]?.text || '';
                
                const supportingDoc = {
                    filing_type: filingType,
                    filing_type_name: filingTypeName,
                    document_type: docType,
                    document_type_name: docTypeName,
                    filing_component: component,
                    filing_component_name: componentName
                };
                
                supportingDocuments.push(supportingDoc);
            });

            // Prepare upload data using already uploaded files (since files are uploaded immediately on selection)
            const uploadDataWithUrls = {
                files: {
                    lead: null,
                    supporting: []
                },
                options: {
                    lead: {
                        filing_component: leadFilingComponent,
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
                // Add supporting documents dropdown data
                supporting_documents: supportingDocuments
            };

            // Use already uploaded file data (files were uploaded immediately when selected)
            if (this.uploadedFiles.lead && this.uploadedFiles.lead.uploadResult) {
                const leadResult = this.uploadedFiles.lead.uploadResult;
                uploadDataWithUrls.files.lead = {
                    name: this.uploadedFiles.lead.name,
                    size: this.uploadedFiles.lead.size,
                    type: this.uploadedFiles.lead.type,
                    url: leadResult.files[0]?.public_url,
                    s3_key: leadResult.files[0]?.key,
                    filing_component: leadFilingComponent
                };
            }

            // Process supporting documents that were already uploaded
            this.uploadedFiles.supporting.forEach((file, index) => {
                if (file.uploadResult) {
                    const supportingFilingComponent = document.getElementById(`supportingFilingComponent${index}`)?.value || '';
                    
                    uploadDataWithUrls.files.supporting.push({
                        name: file.name,
                        size: file.size,
                        type: file.type,
                        url: file.uploadResult.files[0]?.public_url,
                        s3_key: file.uploadResult.files[0]?.key,
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

            // Redirect to review page
            window.location.href = '/review/';

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
