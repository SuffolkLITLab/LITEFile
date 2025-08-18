/**
 * API Utilities - Common functions for API communication
 * Features: CSRF handling, request building, error handling
 */
class ApiUtils {
    constructor() {
        this.baseUrl = window.location.origin;
        this.csrfToken = this.getCSRFToken();
        this.cache = this.getCache();
        this.cacheExpiry = 24 * 60 * 60 * 1000; // 24 hours in milliseconds
        
        console.log('🚀 ApiUtils initialized:', {
            baseUrl: this.baseUrl,
            hasCSRFToken: !!this.csrfToken,
            existingCacheEntries: Object.keys(this.cache).length,
            cacheExpiry: this.cacheExpiry
        });
        
        // Clear expired cache entries on initialization
        this.clearExpiredCache();
    }

    getCache() {
        try {
            const cached = localStorage.getItem('apiResponseCache');
            return cached ? JSON.parse(cached) : {};
        } catch (error) {
            console.warn('Error loading API cache:', error);
            return {};
        }
    }

    saveCache() {
        try {
            const cacheString = JSON.stringify(this.cache);
            localStorage.setItem('apiResponseCache', cacheString);
            console.log('💾 Cache saved to localStorage:', {
                entries: Object.keys(this.cache).length,
                size: cacheString.length,
                keys: Object.keys(this.cache).map(k => k.substring(0, 30) + '...')
            });
        } catch (error) {
            console.error('❌ Error saving API cache:', error);
        }
    }

    getCacheKey(endpoint, params = {}) {
        const sortedParams = Object.keys(params).sort().reduce((result, key) => {
            result[key] = params[key];
            return result;
        }, {});
        return `${endpoint}_${JSON.stringify(sortedParams)}`;
    }

    isCacheValid(cacheEntry) {
        if (!cacheEntry || !cacheEntry.timestamp) {
            return false;
        }
        const age = Date.now() - cacheEntry.timestamp;
        return age < this.cacheExpiry;
    }

    getCachedResponse(endpoint, params = {}) {
        const cacheKey = this.getCacheKey(endpoint, params);
        const cacheEntry = this.cache[cacheKey];
        
        if (this.isCacheValid(cacheEntry)) {
            const age = Date.now() - cacheEntry.timestamp;
            console.log(`🟢 Cache HIT for ${endpoint}:`, {
                params,
                ageMinutes: Math.round(age / 60000),
                cacheKey: cacheKey.substring(0, 50) + '...'
            });
            return cacheEntry.data;
        }
        
        console.log(`🔴 Cache MISS for ${endpoint}:`, {
            params,
            reason: !cacheEntry ? 'No cache entry' : 'Cache expired',
            cacheKey: cacheKey.substring(0, 50) + '...'
        });
        return null;
    }

    setCachedResponse(endpoint, params = {}, data) {
        const cacheKey = this.getCacheKey(endpoint, params);
        this.cache[cacheKey] = {
            data: data,
            timestamp: Date.now()
        };
        this.saveCache();
        console.log(`💾 Cached response for ${endpoint}:`, {
            params,
            dataSize: JSON.stringify(data).length,
            cacheKey: cacheKey.substring(0, 50) + '...',
            totalCacheEntries: Object.keys(this.cache).length
        });
    }

    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (!token) {
            console.warn('CSRF token not found. Some API requests may fail.');
        }
        return token;
    }

    buildUrl(endpoint, params = {}) {
        const url = new URL(endpoint, this.baseUrl);
        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined) {
                url.searchParams.append(key, params[key]);
            }
        });
        return url;
    }

    getDefaultHeaders() {
        const headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        };

        if (this.csrfToken) {
            headers['X-CSRFToken'] = this.csrfToken;
        }

        return headers;
    }

    async makeRequest(endpoint, options = {}) {
        const {
            method = 'GET',
            params = {},
            data = null,
            headers = {},
            timeout = 30000
        } = options;

        try {
            const url = this.buildUrl(endpoint, params);
            
            const requestOptions = {
                method,
                headers: { ...this.getDefaultHeaders(), ...headers }
            };

            if (data && method !== 'GET') {
                requestOptions.body = JSON.stringify(data);
            }

            // Create a timeout promise
            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('Request timeout')), timeout);
            });

            // Race between fetch and timeout
            const response = await Promise.race([
                fetch(url, requestOptions),
                timeoutPromise
            ]);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            return result;

        } catch (error) {
            console.error('API request failed:', error);
            throw this.handleApiError(error);
        }
    }

    handleApiError(error) {
        if (error.message === 'Request timeout') {
            return new Error('Request timed out. Please check your connection and try again.');
        } else if (error.message.includes('Failed to fetch')) {
            return new Error('Network error. Please check your connection.');
        } else if (error.message.includes('HTTP error')) {
            const status = error.message.match(/status: (\d+)/)?.[1];
            switch (status) {
                case '400':
                    return new Error('Invalid request. Please check your input.');
                case '401':
                    return new Error('Authentication required. Please log in.');
                case '403':
                    return new Error('Access denied. You don\'t have permission for this action.');
                case '404':
                    return new Error('Resource not found.');
                case '429':
                    return new Error('Too many requests. Please wait a moment and try again.');
                case '500':
                    return new Error('Server error. Please try again later.');
                default:
                    return new Error('An unexpected error occurred.');
            }
        }
        return error;
    }

    // Convenience methods for common HTTP verbs
    async get(endpoint, params = {}) {
        // Check cache first
        const cachedResponse = this.getCachedResponse(endpoint, params);
        if (cachedResponse !== null) {
            return cachedResponse;
        }

        // Make API request if not cached
        const response = await this.makeRequest(endpoint, { params });
        
        // Cache the response
        this.setCachedResponse(endpoint, params, response);
        
        return response;
    }

    async post(endpoint, data = {}, params = {}) {
        return this.makeRequest(endpoint, { 
            method: 'POST', 
            data, 
            params 
        });
    }

    async put(endpoint, data = {}, params = {}) {
        return this.makeRequest(endpoint, { 
            method: 'PUT', 
            data, 
            params 
        });
    }

    async patch(endpoint, data = {}, params = {}) {
        return this.makeRequest(endpoint, { 
            method: 'PATCH', 
            data, 
            params 
        });
    }

    async delete(endpoint, params = {}) {
        return this.makeRequest(endpoint, { 
            method: 'DELETE', 
            params 
        });
    }

    // Cache management methods
    clearCache() {
        this.cache = {};
        localStorage.removeItem('apiResponseCache');
        console.log('API cache cleared');
    }

    clearExpiredCache() {
        const now = Date.now();
        let cleared = 0;
        
        Object.keys(this.cache).forEach(key => {
            const entry = this.cache[key];
            if (!this.isCacheValid(entry)) {
                delete this.cache[key];
                cleared++;
            }
        });
        
        if (cleared > 0) {
            this.saveCache();
            console.log(`🧹 Cleared ${cleared} expired cache entries`);
        }
    }

    // Debug and testing methods
    getCacheStats() {
        const stats = {
            totalEntries: Object.keys(this.cache).length,
            validEntries: 0,
            expiredEntries: 0,
            cacheSize: JSON.stringify(this.cache).length,
            entries: []
        };

        Object.keys(this.cache).forEach(key => {
            const entry = this.cache[key];
            const isValid = this.isCacheValid(entry);
            const age = Date.now() - entry.timestamp;
            
            if (isValid) {
                stats.validEntries++;
            } else {
                stats.expiredEntries++;
            }
            
            stats.entries.push({
                key: key.substring(0, 50) + (key.length > 50 ? '...' : ''),
                ageMinutes: Math.round(age / 60000),
                isValid,
                dataSize: JSON.stringify(entry.data).length
            });
        });

        return stats;
    }

    logCacheStats() {
        const stats = this.getCacheStats();
        console.log('📊 Cache Statistics:', stats);
        return stats;
    }

    // Method to test cache functionality
    async testCache(endpoint = '/api/counties/', params = {}) {
        console.log('🧪 Testing cache functionality...');
        
        // First call - should be a cache miss
        console.log('Making first API call (should be cache MISS):');
        const start1 = performance.now();
        const result1 = await this.get(endpoint, params);
        const time1 = performance.now() - start1;
        
        // Second call - should be a cache hit
        console.log('Making second API call (should be cache HIT):');
        const start2 = performance.now();
        const result2 = await this.get(endpoint, params);
        const time2 = performance.now() - start2;
        
        console.log('🧪 Cache Test Results:', {
            firstCallTime: `${time1.toFixed(2)}ms`,
            secondCallTime: `${time2.toFixed(2)}ms`,
            speedup: `${(time1 / time2).toFixed(1)}x faster`,
            dataMatches: JSON.stringify(result1) === JSON.stringify(result2)
        });
        
        return { result1, result2, time1, time2 };
    }

    // Method to refresh CSRF token if needed
    async refreshCSRFToken() {
        try {
            const response = await fetch('/api/csrf-token/', {
                method: 'GET',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            
            if (response.ok) {
                const data = await response.json();
                this.csrfToken = data.csrf_token;
                
                // Update the token in the form if it exists
                const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
                if (tokenInput) {
                    tokenInput.value = this.csrfToken;
                }
            }
        } catch (error) {
            console.warn('Could not refresh CSRF token:', error);
        }
    }
}

// Create global instance
const apiUtils = new ApiUtils();

// Test localStorage immediately
console.log('🧪 Testing localStorage on load...');
try {
    localStorage.setItem('cacheTest', 'test');
    const testValue = localStorage.getItem('cacheTest');
    console.log('✅ localStorage is working:', testValue === 'test');
    localStorage.removeItem('cacheTest');
} catch (error) {
    console.error('❌ localStorage is not available:', error);
}

// Global cache testing functions for browser console
window.testCache = () => apiUtils.testCache();
window.cacheStats = () => apiUtils.logCacheStats();
window.clearCache = () => apiUtils.clearCache();
window.getCacheData = () => apiUtils.cache;

// Simple test to add something to cache manually
window.testCacheManually = () => {
    console.log('🧪 Manually testing cache...');
    apiUtils.setCachedResponse('/test/endpoint', { test: 'param' }, { test: 'data' });
    console.log('Cache after manual test:', apiUtils.cache);
    console.log('LocalStorage after manual test:', localStorage.getItem('apiResponseCache'));
};

// Export for module use or make globally available
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ApiUtils, apiUtils };
} else {
    window.ApiUtils = ApiUtils;
    window.apiUtils = apiUtils;
}
