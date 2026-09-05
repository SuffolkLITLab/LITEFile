/* Keep this page's filing identity in its URLs, independently of shared cookies. */
(() => {
    const scope = JSON.parse(document.getElementById('draft-scope')?.textContent || 'null');
    if (!scope?.id) return;
    const paths = new Set(scope.paths);

    function withDraft(value, includeApi = false) {
        const url = new URL(value, window.location.href);
        if (url.origin !== window.location.origin) return value;
        if (!paths.has(url.pathname) && !(includeApi && url.pathname.startsWith('/api/'))) return value;
        // Resume links already name their target; never replace that selection.
        if (!url.searchParams.has('draft')) url.searchParams.set('draft', scope.id);
        return url.href;
    }
    window.withFilingDraft = withDraft;

    // A direct visit to an old, unscoped workflow URL adopts a session draft
    // once. Reload, history navigation, and subsequent requests stay with it.
    window.history.replaceState(window.history.state, '', withDraft(window.location.href));

    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, options) => {
        const originalUrl = input instanceof Request ? input.url : String(input);
        const scopedUrl = withDraft(originalUrl, true);
        if (input instanceof Request) {
            // Preserve the Request's body, method, headers, and cancellation.
            // Reconstructing it from a URL can discard a streaming body.
            const request = new Request(input, options);
            if (scopedUrl !== originalUrl) {
                request.headers.set('X-Filing-Draft', new URL(scopedUrl).searchParams.get('draft'));
            }
            return originalFetch(request);
        }
        return originalFetch(scopedUrl, options);
    };

    function scopeElements(root) {
        root.querySelectorAll('a[href], form').forEach(element => {
            const isForm = element.tagName === 'FORM';
            const attribute = isForm ? 'action' : 'href';
            const original = element.getAttribute(attribute) || window.location.href;
            const scoped = withDraft(original);
            element.setAttribute(attribute, scoped);
            // Browsers replace the action query when submitting GET forms.
            if (isForm && paths.has(new URL(scoped, window.location.href).pathname)) {
                let identity = element.querySelector('input[name="draft"]');
                if (!identity) {
                    identity = document.createElement('input');
                    identity.type = 'hidden';
                    identity.name = 'draft';
                    element.append(identity);
                }
                identity.value = new URL(scoped, window.location.href).searchParams.get('draft');
            }
        });
    }
    document.addEventListener('DOMContentLoaded', () => {
        scopeElements(document);
        // Also cover links/party forms inserted by the page's own scripts.
        new MutationObserver(() => scopeElements(document)).observe(document.body, {
            childList: true,
            subtree: true
        });
    });
})();