/**
 * Browser checks for editing choices on Confirm case.
 *
 * Needs a running server and the seeded session the accessibility suite uses;
 * the court lists themselves are mocked in the browser. See the spec's header.
 */
const {
    defineConfig,
    devices
} = require('@playwright/test');

module.exports = defineConfig({
    testDir: './tests',
    testMatch: 'confirm-case-editing.spec.js',
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 1 : 0,
    workers: 1,
    reporter: 'list',
    timeout: 60000,
    use: {
        baseURL: process.env.CONFIRM_CASE_BASE_URL || process.env.A11Y_TEST_BASE_URL || 'http://127.0.0.1:8000',
        trace: 'on-first-retry',
    },
    projects: [{
        name: 'chromium',
        use: {
            ...devices['Desktop Chrome']
        }
    }],
});