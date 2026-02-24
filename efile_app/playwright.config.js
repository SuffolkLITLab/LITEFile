/**
 * Playwright Configuration File
 * 
 * This file configures Playwright for end-to-end testing.
 * Uncomment and modify the settings below as needed.
 */

const {
    defineConfig,
    devices
} = require('@playwright/test');

module.exports = defineConfig({
    // Test directory
    testDir: './tests',

    // Global setup file (uncomment to use setup.js)
    globalSetup: require.resolve('./tests/setup.js'),

    // Run tests in files in parallel
    fullyParallel: true,

    // Fail the build on CI if you accidentally left test.only in the source code
    forbidOnly: !!process.env.CI,

    // Retry on CI only
    retries: process.env.CI ? 2 : 0,

    // Opt out of parallel tests on CI
    workers: process.env.CI ? 1 : undefined,

    // Reporter to use
    reporter: 'list',

    // Global test timeout
    timeout: 600000, // 10 minutes

    // Shared settings for all the projects below
    use: {
        // Base URL to use in actions like `await page.goto('/')`
        baseURL: 'http://localhost:8000',

        // Collect trace when retrying the failed test
        trace: 'on-first-retry',
    },

    // Configure projects for major browsers
    projects: [{
            name: 'chromium',
            use: {
                ...devices['Desktop Chrome']
            },
        },

        // Uncomment for additional browsers
        // {
        //   name: 'firefox',
        //   use: { ...devices['Desktop Firefox'] },
        // },

        // {
        //   name: 'webkit',
        //   use: { ...devices['Desktop Safari'] },
        // },
    ],

    // Run your local dev server before starting the tests
    // webServer: {
    //   command: 'python manage.py runserver',
    //   url: 'http://localhost:8000',
    //   reuseExistingServer: !process.env.CI,
    // },
});

/**
 * SETUP INSTRUCTIONS:
 * 
 * 1. Uncomment the configuration above by removing the // comments
 * 2. Adjust the baseURL to match your Django development server (default: http://localhost:8000)
 * 3. Uncomment globalSetup line to use the setup.js file for test initialization
 * 4. Uncomment webServer section to automatically start Django server before tests
 * 5. Add additional browsers in projects array if needed
 * 6. Update package.json scripts to include: "test": "playwright test"
 * 
 * Example package.json test script:
 * "scripts": {
 *   "test": "playwright test",
 *   "test:headed": "playwright test --headed",
 *   "test:ui": "playwright test --ui"
 * }
 */