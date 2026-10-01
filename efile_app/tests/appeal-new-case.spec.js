/**
 * Browser regression for appellate case metadata (#266).
 *
 * In four terminals from efile_app, make a disposable database and run:
 *   python tests/appeal-efsp-stub.py
 *   UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/litefile-appeal-e2e.sqlite3 EFSP_URL=http://127.0.0.1:8999 uv run python manage.py migrate
 *   UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/litefile-appeal-e2e.sqlite3 EFSP_URL=http://127.0.0.1:8999 uv run python manage.py seed_accessibility_session --appeal --jurisdiction illinois --output /tmp/litefile-il-e2e.json --origin http://127.0.0.1:8001
 *   # Seed Massachusetts in the same database using --jurisdiction massachusetts and a second output path.
 *   UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/litefile-appeal-e2e.sqlite3 EFSP_URL=http://127.0.0.1:8999 uv run python manage.py runserver 127.0.0.1:8001 --noreload
 *
 * Then run against that local session and stub:
 *   APPEAL_TEST_STORAGE_STATE=/tmp/litefile-il-e2e.json APPEAL_TEST_JURISDICTION=illinois \
 *   E2E_TEST_BASE_URL=http://127.0.0.1:8001 \
 *   npx playwright test --config=playwright.appeal.config.js
 *   # Repeat with the Massachusetts storage state and APPEAL_TEST_JURISDICTION=massachusetts.
 *
 * The stub implements no fee or submission endpoint. The test stops at Review
 * and never clicks the submission button.
 */
const {
    test,
    expect
} = require('@playwright/test');

const storageState = process.env.APPEAL_TEST_STORAGE_STATE;
const jurisdiction = process.env.APPEAL_TEST_JURISDICTION || 'illinois';
if (storageState) test.use({
    storageState
});

test.skip(!storageState, 'Set APPEAL_TEST_STORAGE_STATE to a seeded local session.');

test(`new ${jurisdiction} appeal requires a valid lower court and shows it on Review`, async ({
    page
}) => {
    const base = `/jurisdiction/${jurisdiction}`;
    await page.goto(`${base}/parties/`, {
        waitUntil: 'networkidle'
    });

    // Moving on from the people step must route an AppellateCase through the
    // new lower-court questions before fees.
    await expect(page.locator('input[name="filer_party_type"][value="plaintiff"]')).toBeChecked();
    await page.getByRole('button', {
        name: /Continue/i
    }).click();
    await expect(page).toHaveURL(new RegExp(`/jurisdiction/${jurisdiction}/case-questions/`));

    const lowerCourt = page.locator('select[name="lower_court_code"]');
    await expect(lowerCourt).toHaveAttribute('required', '');
    const lowerCourtOptions = await lowerCourt.locator('option').evaluateAll(options =>
        options.filter(option => option.value).map(option => ({
            value: option.value,
            label: option.textContent.trim()
        }))
    );
    if (jurisdiction === 'massachusetts') {
        expect(lowerCourtOptions.length).toBeGreaterThan(100);
        expect(lowerCourtOptions).toContainEqual({
            value: '1764',
            label: 'Attleboro District Court'
        });
        expect(lowerCourtOptions.some(option => /Appeals Court|Supreme Judicial Court/i.test(option.label))).toBe(false);
    } else {
        expect(lowerCourtOptions).toContainEqual({
            value: 'cook:law1',
            label: 'Cook County - Law - District 1 - Chicago'
        });
        expect(lowerCourtOptions).toContainEqual({
            value: 'adams',
            label: 'Adams County'
        });
        expect(lowerCourtOptions.some(option => option.value === 'TAC1' || option.value === 'zdev-test')).toBe(false);
    }

    const selectedCode = jurisdiction === 'massachusetts' ? '1764' : 'cook:law1';
    const selectedLabel = jurisdiction === 'massachusetts' ? 'Attleboro District Court' : 'Cook County - Law - District 1 - Chicago';
    await lowerCourt.selectOption(selectedCode);
    await page.locator('[name="lower_court_docket_number"]').fill('2026-CH-00421');
    await page.locator('[name="lower_court_title"]').fill('Reed v. Sample Company');
    await page.locator('[name="lower_court_judge"]').fill('Hon. Morgan Judge');
    await page.getByRole('button', {
        name: /Continue to fees/i
    }).click();
    await expect(page).toHaveURL(new RegExp(`/jurisdiction/${jurisdiction}/payment/`));

    // This is the final pre-submission screen. Navigate there directly so the
    // test remains independent of payment-provider behavior.
    await page.goto(`${base}/review/`);
    await expect(page.getByRole('heading', {
        name: 'Review your filing'
    })).toBeVisible();
    await expect(page.getByText(selectedLabel)).toBeVisible();
    await expect(page.getByText('2026-CH-00421')).toBeVisible();
    await expect(page.getByText('Reed v. Sample Company')).toBeVisible();
    await expect(page.getByText('Hon. Morgan Judge')).toBeVisible();
    await expect(page.getByRole('button', {
        name: /Submit(?: and pay)?/i
    })).toBeVisible();
    await page.getByRole('link', {
        name: 'Edit case questions'
    }).click();
    await expect(lowerCourt).toHaveValue(selectedCode);
    await expect(page.locator('[name="lower_court_docket_number"]')).toHaveValue('2026-CH-00421');
});