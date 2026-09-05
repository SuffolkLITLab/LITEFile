const {
    test,
    expect
} = require('@playwright/test');
const path = require('path');
const {
    getTestConfig,
    loginViaLoginPage
} = require('./test-utils');

const SENTINEL_PDF = path.resolve(__dirname, '../../benchmarking/synthetic/filled_pdfs/flattened/IL-02.pdf');

test('real uploaded PDF is extracted and classified against live Tyler choices', async ({
    page
}) => {
    test.setTimeout(360000);
    await loginViaLoginPage(page, getTestConfig());

    await page.goto('/jurisdiction/illinois/options/');
    const start = page.locator('form[action$="/start-filing/"]:has(input[name="existing_case"][value="new"])');
    await Promise.all([
        page.waitForURL(/\/upload-documents\//),
        start.getByRole('button', {
            name: /^Begin/
        }).click(),
    ]);

    await page.locator('#documents-input').setInputFiles(SENTINEL_PDF);
    await page.getByRole('button', {
        name: 'Upload selected files'
    }).click();
    await expect(page.locator('.document-row')).toHaveCount(1, {
        timeout: 120000
    });
    await Promise.all([
        page.waitForURL(/\/extraction-review\//, {
            timeout: 300000
        }),
        page.locator('#continue-to-analysis').click(),
    ]);

    await expect(page.getByRole('heading', {
        name: /Check what we read from your document/i
    })).toBeVisible();
    await expect(page.locator('.extracted-details')).toContainText(/Petition for Divorce with Children/i);
    await expect(page.locator('.extracted-details')).toContainText('ATJ 105.3');
    const partyNames = page.locator('.review-parties input[name="party_name"]');
    await expect(partyNames.nth(0)).toHaveValue('Dana Kim');
    await expect(partyNames.nth(1)).toHaveValue('Elliot Kim');

    await expect(page.locator('#court_name')).toHaveValue(/Lake County/i, {
        timeout: 120000
    });
    await expect(page.locator('#case_category_name')).toHaveValue('Dissolution (Divorce) with Children', {
        timeout: 120000
    });
    await expect(page.locator('#case_type_name')).toHaveValue('Dissolution (with children)', {
        timeout: 120000
    });
    await expect(page.locator('#filing_type_name')).toHaveValue('Petition Dissolution of Marriage/Civil Union', {
        timeout: 120000
    });
    await expect(page.locator('input[type="radio"][name="existing_case"][value="new"]')).toBeChecked();
});