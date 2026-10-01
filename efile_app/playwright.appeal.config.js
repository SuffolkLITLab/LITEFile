const {
    defineConfig,
    devices
} = require('@playwright/test');

module.exports = defineConfig({
    testDir: './tests',
    testMatch: 'appeal-new-case.spec.js',
    fullyParallel: false,
    workers: 1,
    reporter: 'list',
    timeout: 120000,
    use: {
        baseURL: process.env.E2E_TEST_BASE_URL || 'http://127.0.0.1:8001',
        ...devices['Desktop Chrome'],
    },
});