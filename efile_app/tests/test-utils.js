/**
 * Test Utilities
 * 
 * Common utilities and configuration for Playwright tests.
 * Import this in your test files instead of duplicating environment setup.
 */

/**
 * Get test configuration from environment variables
 * @returns {Object} Test configuration object
 */
function getTestConfig() {
    const username = process.env.E2E_TEST_USERNAME;
    const password = process.env.E2E_TEST_PASSWORD;
    const baseUrl = process.env.E2E_TEST_BASE_URL || 'http://localhost:8000';

    if (!username || !password) {
        throw new Error('E2E_TEST_USERNAME and E2E_TEST_PASSWORD must be set in .env file');
    }

    return {
        username,
        password,
        baseUrl
    };
}

/**
 * Common login flow for tests (via logout page - ensures clean session)
 * @param {Page} page - Playwright page object
 * @param {Object} config - Test configuration
 */
async function loginViaLogout(page, config = getTestConfig()) {
    console.log(`Logging in as ${config.username} to ${config.baseUrl}`);

    // Configure context to preserve session cookies
    await page.context().addCookies([]);

    // Navigate to logout page
    await page.goto(`${config.baseUrl}/jurisdiction/illinois/logout`);

    // Fill in login credentials
    await page.getByLabel('Email address').fill(config.username);
    await page.getByLabel('Password').fill(config.password);

    // Submit the form
    await page.getByRole('button', {
        name: /Sign In/i
    }).click();

    // Wait for navigation to complete
    await page.waitForURL(/\/options\/?$/);
}

/**
 * Common login flow for tests (via login page)
 * @param {Page} page - Playwright page object
 * @param {Object} config - Test configuration
 */
async function loginViaLoginPage(page, config = getTestConfig()) {
    console.log(`Logging in as ${config.username} to ${config.baseUrl}`);

    // Navigate to login page
    await page.goto(`${config.baseUrl}/jurisdiction/illinois/login`);

    // Fill in login credentials
    await page.getByLabel('Email address').fill(config.username);
    await page.getByLabel('Password').fill(config.password);

    // Submit the form
    await page.getByRole('button', {
        name: /Sign In/i
    }).click();

    // Wait for navigation to complete
    await page.waitForURL(/\/options\/?$/);
}

// Alias for backward compatibility
const loginUser = loginViaLogout;

module.exports = {
    getTestConfig,
    loginUser,
    loginViaLogout,
    loginViaLoginPage
};