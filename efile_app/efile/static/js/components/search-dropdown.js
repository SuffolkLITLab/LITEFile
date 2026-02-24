/**
 * SearchDropdown - A reusable search and type-ahead dropdown component
 * 
 * Features:
 * - Type-ahead search with highlighting
 * - Keyboard navigation (arrow keys, Enter, Escape)
 * - Mouse interaction
 * - Clear selection functionality
 * - Integration with hidden select element for form submission
 * - Support for external option updates
 * - Accessibility features
 */
class SearchDropdown {
    constructor(fieldId, options = {}) {
        this.fieldId = fieldId;
        this.options = {
            placeholder: 'Search...',
            noResultsText: 'No matching options found',
            ...options
        };

        // Get DOM elements
        this.input = document.getElementById(`${fieldId}_search`);
        this.select = document.getElementById(fieldId);
        this.results = document.getElementById(`${fieldId}-results`);
        this.selected = document.getElementById(`${fieldId}-selected`);
        this.container = document.getElementById(`${fieldId}-container`);

        // State
        this.allOptions = [];
        this.filteredOptions = [];
        this.highlightedIndex = -1;
        this.isInitialized = false;
        this.isUpdatingSelect = false; // Flag to prevent infinite loops

        this.init();
    }

    init() {
        if (!this.input || !this.select || !this.results || !this.selected) {
            console.error(`SearchDropdown: Required elements not found for field ${this.fieldId}`);
            return;
        }

        this.setupEventListeners();
        this.isInitialized = true;
    }

    setupEventListeners() {
        // Input events
        this.input.addEventListener('input', (e) => this.handleInput(e));
        this.input.addEventListener('focus', (e) => this.handleFocus(e));
        this.input.addEventListener('blur', (e) => this.handleBlur(e));
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));

        // Clear button
        const clearBtn = this.selected.querySelector('.btn-clear');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearSelection());
        }

        // Hidden select changes (for external updates)
        this.select.addEventListener('change', () => this.syncFromSelect());

        // Click outside to close
        document.addEventListener('click', (e) => {
            if (this.container && !this.container.contains(e.target)) {
                this.hideResults();
            }
        });
    }

    handleInput(e) {
        const query = e.target.value.toLowerCase();
        this.filterOptions(query);
        this.showResults();
        this.highlightedIndex = -1;
    }

    handleFocus(e) {
        if (this.allOptions.length > 0) {
            this.filterOptions(e.target.value.toLowerCase());
            this.showResults();
        }
    }

    handleBlur(e) {
        // Delay hiding to allow clicks on results
        setTimeout(() => {
            if (this.container && !this.container.contains(document.activeElement)) {
                this.hideResults();
            }
        }, 150);
    }

    handleKeydown(e) {
        if (!this.isResultsVisible()) return;

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.highlightNext();
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.highlightPrevious();
                break;
            case 'Enter':
                e.preventDefault();
                this.selectHighlighted();
                break;
            case 'Escape':
                e.preventDefault();
                this.hideResults();
                break;
        }
    }

    updateOptions(options) {
        this.allOptions = options.map(option => ({
            value: option.value,
            text: option.text,
            searchText: option.text.toLowerCase()
        }));

        // Update the hidden select as well
        this.select.innerHTML = `<option value="">Select ${this.getFieldLabel()}</option>`;
        options.forEach(option => {
            const optionElement = document.createElement('option');
            optionElement.value = option.value;
            optionElement.textContent = option.text;
            this.select.appendChild(optionElement);
        });

        this.filterOptions();
    }

    filterOptions(query = '') {
        if (query === '') {
            this.filteredOptions = [...this.allOptions];
        } else {
            this.filteredOptions = this.allOptions.filter(option =>
                option.searchText.includes(query)
            );
        }
        this.renderResults();
    }

    renderResults() {
        if (this.filteredOptions.length === 0) {
            this.results.innerHTML = `<div class="search-no-results">${this.options.noResultsText}</div>`;
        } else {
            this.results.innerHTML = this.filteredOptions
                .map((option, index) => `
          <div class="search-dropdown-item" data-value="${option.value}" data-index="${index}">
            ${this.highlightMatch(option.text, this.input.value)}
          </div>
        `).join('');

            // Add event listeners to result items
            this.results.querySelectorAll('.search-dropdown-item').forEach((item, index) => {
                item.addEventListener('mousedown', (e) => {
                    e.preventDefault(); // Prevent blur
                    this.selectOption(this.filteredOptions[index]);
                });

                item.addEventListener('mouseenter', () => {
                    this.highlightedIndex = index;
                    this.updateHighlight();
                });
            });
        }
    }

    highlightMatch(text, query) {
        if (!query) return text;

        const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        return text.replace(regex, '<strong>$1</strong>');
    }

    highlightNext() {
        this.highlightedIndex = Math.min(this.highlightedIndex + 1, this.filteredOptions.length - 1);
        this.updateHighlight();
    }

    highlightPrevious() {
        this.highlightedIndex = Math.max(this.highlightedIndex - 1, 0);
        this.updateHighlight();
    }

    updateHighlight() {
        this.results.querySelectorAll('.search-dropdown-item').forEach((item, index) => {
            item.classList.toggle('highlighted', index === this.highlightedIndex);
        });
    }

    selectHighlighted() {
        if (this.highlightedIndex >= 0 && this.highlightedIndex < this.filteredOptions.length) {
            this.selectOption(this.filteredOptions[this.highlightedIndex]);
        }
    }

    selectOption(option) {
        this.isUpdatingSelect = true;
        this.input.value = option.text;
        this.select.value = option.value;
        this.showSelected(option.text);
        this.hideResults();

        // Trigger change event on the hidden select
        this.select.dispatchEvent(new Event('change', {
            bubbles: true
        }));
        this.isUpdatingSelect = false;
    }

    showSelected(text) {
        const selectedText = this.selected.querySelector('.selected-text');
        if (selectedText) {
            selectedText.textContent = text;
        }
        this.selected.style.display = 'flex';
        this.input.style.display = 'none';
    }

    clearSelection() {
        if (this.isUpdatingSelect) return; // Prevent infinite loops

        this.isUpdatingSelect = true;
        this.input.value = '';
        this.select.value = '';
        this.selected.style.display = 'none';
        this.input.style.display = 'block';
        this.hideResults();

        // Focus the input
        if (!this.input.disabled) {
            this.input.focus();
        }

        // Trigger change event on the hidden select
        this.select.dispatchEvent(new Event('change', {
            bubbles: true
        }));
        this.isUpdatingSelect = false;
    }

    syncFromSelect() {
        if (this.isUpdatingSelect) return; // Prevent infinite loops

        // If the select was changed externally, update the search input
        const selectedOption = this.select.selectedOptions[0];
        if (selectedOption && selectedOption.value) {
            this.input.value = selectedOption.text;
            this.showSelected(selectedOption.text);
        } else {
            this.isUpdatingSelect = true;
            this.input.value = '';
            this.selected.style.display = 'none';
            this.input.style.display = 'block';
            this.hideResults();
            this.isUpdatingSelect = false;
        }
    }

    showResults() {
        this.results.style.display = 'block';
    }

    hideResults() {
        this.results.style.display = 'none';
        this.highlightedIndex = -1;
    }

    isResultsVisible() {
        return this.results.style.display !== 'none';
    }

    enable() {
        this.input.disabled = false;
        this.select.disabled = false;
        this.input.placeholder = this.options.placeholder;
    }

    disable() {
        this.input.disabled = true;
        this.select.disabled = true;
        this.input.placeholder = 'Select dependencies first';
        this.clearSelection();
        this.hideResults();
    }

    reset() {
        this.clearSelection();
        this.allOptions = [];
        this.filteredOptions = [];
        this.select.innerHTML = `<option value="">Select ${this.getFieldLabel()}</option>`;
    }

    getValue() {
        return this.select.value;
    }

    setValue(value, triggerChange = true) {
        const option = this.allOptions.find(opt => opt.value === value);
        if (option) {
            this.selectOption(option);
            if (!triggerChange) {
                // If we don't want to trigger change, we need to prevent it
                this.select.value = value;
                this.input.value = option.text;
                this.showSelected(option.text);
            }
        }
    }

    getFieldLabel() {
        const label = this.container?.previousElementSibling?.querySelector('label')?.textContent;
        return label ? label.replace('*', '').trim() : 'Option';
    }

    // Static method to create multiple search dropdowns
    static createMultiple(fieldIds, options = {}) {
        const instances = {};
        fieldIds.forEach(fieldId => {
            instances[fieldId] = new SearchDropdown(fieldId, options[fieldId] || {});
        });
        return instances;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SearchDropdown;
}

// Make available globally
window.SearchDropdown = SearchDropdown;