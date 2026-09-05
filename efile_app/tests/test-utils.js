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
    // Same Tyler test-EFM login the Python suite uses (efile/tests/) and that
    // CI supplies from secrets -- one name, so a working .env works everywhere.
    const username = process.env.TESTS_TYLER_USERNAME;
    const password = process.env.TESTS_TYLER_PASSWORD;
    const baseUrl = process.env.E2E_TEST_BASE_URL || 'http://localhost:8000';

    if (!username || !password) {
        throw new Error('TESTS_TYLER_USERNAME and TESTS_TYLER_PASSWORD must be set in .env file');
    }

    return {
        username,
        password,
        baseUrl
    };
}

async function waitForLogin(page) {
    try {
        await page.waitForURL(/\/options\/?$/, {
            timeout: 120000
        });
    } catch (error) {
        const alert = page.locator('[role="alert"]').first();
        const detail = await alert.isVisible().catch(() => false) ?
            `: ${await alert.innerText()}` :
            '';
        throw new Error(`Login did not reach the filing options page${detail}`, {
            cause: error
        });
    }
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
    await waitForLogin(page);
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
    await waitForLogin(page);
}

/**
 * Submit the extraction review after answering its conditional questions.
 * The filer-side question only appears for case types whose checklist differs
 * by side, and it is populated asynchronously after the taxonomy choices.
 */
async function continueFromExtractionReview(page, nextUrl = /\/(document-checklist|case-lookup)\//) {
    const reviewed = page.locator('input[name="reviewed_extraction"]');
    if (await reviewed.count()) await reviewed.check();

    const roleField = page.locator('#filer-role-field');
    if (await roleField.count()) {
        await page.waitForLoadState('networkidle', {
            timeout: 120000
        });
        if (await roleField.isVisible()) {
            await roleField.locator('input[name="filer_role"]').first().check();
        }
    }

    await Promise.all([
        page.waitForURL(nextUrl, {
            timeout: 120000
        }),
        page.getByRole('button', {
            name: /Confirm and continue/i
        }).click(),
    ]);
}

/**
 * Confirm the document checklist, first resolving a filer-side question if a
 * caller reached this page from an older or incomplete draft.
 */
async function continueFromDocumentChecklist(page) {
    const role = page.locator('input[name="filer_role"]:visible').first();
    if (await role.count()) {
        await role.check();
        await page.getByRole('button', {
            name: /Show my documents/i
        }).click();
        await page.locator('input[name="documents_complete"]').waitFor({
            state: 'visible',
            timeout: 120000
        });
    }

    await page.locator('input[name="documents_complete"]').check();
    await Promise.all([
        page.waitForURL(/\/organize-documents\//, {
            timeout: 120000
        }),
        page.getByRole('button', {
            name: /Continue to organize/i
        }).click(),
    ]);
}

/**
 * Choose a known court through the jurisdiction's visible guided questions.
 * Asking the selector endpoint for the route keeps state-specific court logic
 * out of the browser suite; the test still answers each rendered control.
 */
async function selectGuidedCourt(page, jurisdiction, courtCode) {
    const response = await page.request.get('/api/dropdowns/court-selector/', {
        params: {
            jurisdiction,
            court: courtCode
        }
    });
    if (!response.ok()) throw new Error(`Could not resolve the guided route for court ${courtCode}`);
    const payload = await response.json();
    const data = payload.data || {};
    if (!payload.success || !data.available) {
        throw new Error(`No guided court selector is available for ${jurisdiction}`);
    }

    for (const step of data.steps || []) {
        if (!step.answer) continue;
        if (step.type === 'location') continue;

        const choice = page.locator(`#court-selector input[data-step="${step.id}"][value="${step.answer}"]`);
        const select = page.locator(`#court-selector select[data-step="${step.id}"]`);

        if (step.type === 'choice') {
            await choice.waitFor({
                state: 'visible',
                timeout: 120000
            });
            await choice.check();
        } else {
            await select.waitFor({
                state: 'visible',
                timeout: 120000
            });
            await select.selectOption(step.answer);
        }
    }

    await page.locator('#court_code').waitFor({
        state: 'attached'
    });
    await page.waitForFunction((expected) => document.getElementById('court_code')?.value === expected, courtCode, {
        timeout: 120000
    });
}

// Alias for backward compatibility
const loginUser = loginViaLogout;

module.exports = {
    getTestConfig,
    loginUser,
    loginViaLogout,
    loginViaLoginPage,
    continueFromExtractionReview,
    continueFromDocumentChecklist,
    selectGuidedCourt
};