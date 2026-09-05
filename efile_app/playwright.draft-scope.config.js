// Browser-only transport checks; no EFSP account or live server is needed.
const {
    defineConfig
} = require('@playwright/test');

module.exports = defineConfig({
    testDir: './tests',
    testMatch: 'draft-scope.spec.js',
    timeout: 30000,
    use: {
        browserName: 'chromium',
        headless: true
    },
});