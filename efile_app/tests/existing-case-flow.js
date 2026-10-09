// Called by the Python live-server regression, with synthetic court responses.
const {
    chromium,
    expect
} = require('@playwright/test');

(async () => {
    const config = JSON.parse(process.env.EXISTING_CASE_BROWSER_CONFIG);
    const browser = await chromium.launch({
        headless: true
    });
    try {
        const context = await browser.newContext();
        await context.addCookies([{
            name: 'sessionid',
            value: config.session,
            url: config.base
        }]);
        const page = await context.newPage();
        page.setDefaultTimeout(10000);
        const json = (route, body) => route.fulfill({
            contentType: 'application/json',
            body: JSON.stringify(body)
        });
        await page.route('**/api/dropdowns/court-selector/**', route => json(route, {
            success: true,
            data: {
                available: false
            }
        }));
        await page.route('**/api/dropdowns/courts/**', route => json(route, {
            success: true,
            data: [{
                value: config.court,
                text: 'Sample court'
            }]
        }));
        await page.route('**/api/filing-availability/**', route => json(route, {
            success: true,
            available: true
        }));
        await page.route('**/api/suffolk/lookup-case/**', route => json(route, {
            success: true,
            caseInfo: {
                caseTrackingID: config.tracking,
                caseDocketID: config.docket
            }
        }));
        await page.route('**/api/payment-fees/**', route => json(route, {
            success: false,
            error: 'Synthetic browser test does not call live fees.'
        }));
        const url = step => `${config.base}/jurisdiction/illinois/${step}/?draft=${config.draft}`;
        await page.goto(url('case-lookup'));
        await page.getByLabel('Court', {
            exact: true
        }).selectOption(config.court);
        await page.locator('#case-number').fill(config.docket);
        await page.getByRole('button', {
            name: 'Find my case'
        }).click();
        await expect(page.getByRole('heading', {
            name: 'Is this your court case?'
        })).toBeVisible();
        await expect(page.getByRole('heading', {
            name: 'Already on the court case'
        })).toBeVisible();
        await page.getByRole('button', {
            name: 'Yes, this is my case'
        }).click();
        await page.waitForURL(/document-checklist/);
        await page.goto(url('parties') + '&return_to=review');
        await expect(page.locator('.party-row').filter({
            hasText: 'Already on the court case'
        })).toHaveCount(config.count);
        await expect(page.getByRole('link', {
            name: 'Edit',
            exact: true
        })).toHaveCount(0);
        await expect(page.getByRole('button', {
            name: 'Remove party'
        })).toHaveCount(0);
        await expect(page.getByRole('button', {
            name: 'Add another person'
        })).toHaveCount(0);
        // Court-party selection remains native keyboard-accessible.
        const selected = page.locator('input[name="filing_for"]').first();
        await selected.focus();
        await page.keyboard.press('Space');
        await expect(selected).toBeChecked();
        await page.getByRole('button', {
            name: /^Continue/
        }).click();
        await page.waitForURL(/\/review\//);
        const caseData = await page.locator('#case-data').textContent();
        const parties = JSON.parse(caseData).filing_parties.filter(p => p.source === 'court');
        expect(parties).toHaveLength(config.count);
        expect(parties.filter(p => p.is_filing_party)).toHaveLength(1);
        expect(parties.every(p => Boolean(p.external_party_id))).toBe(true);
        await page.goto(url('parties') + '&return_to=review');
        await page.getByRole('button', {
            name: 'This is me',
            exact: true
        }).first().click();
        await page.getByRole('button', {
            name: /^Continue/
        }).click();
        await page.waitForURL(/\/review\//);
        await expect(page.getByText(/Your account is linked to/)).toBeVisible();
        await expect(page.getByText(/This filing is on behalf of/)).toBeVisible();
        console.log('Existing-case browser flow passed: lookup, confirmation, read-only roster, keyboard selection, account link, review.');
    } finally {
        await browser.close();
    }
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});