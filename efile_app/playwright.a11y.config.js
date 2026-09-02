const {
    defineConfig,
    devices
} = require('@playwright/test');

module.exports = defineConfig({
    testDir: './tests',
    testMatch: 'accessibility.spec.js',
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 1 : 0,
    workers: 1,
    reporter: process.env.CI ? [
        ['list'],
        ['json', {
            outputFile: 'test-results/a11y-playwright.json'
        }]
    ] : 'list',
    timeout: 120000,
    use: {
        baseURL: process.env.A11Y_TEST_BASE_URL || 'http://127.0.0.1:8000',
        trace: 'on-first-retry',
    },
    projects: [{
        name: 'chromium',
        use: {
            ...devices['Desktop Chrome']
        }
    }],
});