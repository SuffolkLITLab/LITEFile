const {
    test,
    expect
} = require('@playwright/test');
const {
    loginViaLogout
} = require('./test-utils');

test('expert-form-forfeiture-of-seized-property', async ({
    page
}) => {
    // Use the common login utility
    await loginViaLogout(page);

    // Ensure the "Respond" section is visible
    await page.getByRole('heading', {
        level: 3,
        name: /Respond/i
    }).waitFor();

    // Click the Expert Form button under Respond (matches onclick)
    await page.locator("button.btn.btn-primary[onclick=\"goToExpertForm('response')\"]").click();

    // Wait for the form to be visible
    await page.waitForSelector('form');

    // Select Court
    const courtSelect = page.locator('select#court');
    await courtSelect.waitFor({
        state: 'visible'
    });
    await courtSelect.selectOption({
        value: 'winnebago'
    });

    await page.waitForTimeout(500);

    // Find and fill the Case Number input field
    const caseNumberInput = page.locator('input#case_number');
    await caseNumberInput.waitFor({
        state: 'visible'
    });
    await caseNumberInput.fill('2024-MX-50');

    // Wait for "Case Information Found" text to appear
    await page.locator('text=Case Information Found').waitFor({
        state: 'visible'
    });

    // Validate case information fields are displayed
    await expect(page.locator('text=Case Title:')).toBeVisible();
    await expect(page.locator('text=People of the State of Illinois vs. One Thousand Nine Hundred Dollars US Currency')).toBeVisible();
    await expect(page.locator('text=Docket Number:')).toBeVisible();
    await expect(page.locator('text=2024-MX-50')).toBeVisible();
    await expect(page.locator('text=Case Category:')).toBeVisible();
    await expect(page.locator('text=190925')).toBeVisible();
    await expect(page.locator('text=Case Type:')).toBeVisible();
    await expect(page.locator('text=324882')).toBeVisible();

    // Click Continue (this should trigger continueToExpertForm() which sets session storage)
    await page.getByRole('button', {
        name: 'Continue'
    }).click();
    await page.locator('text=Loading your information').waitFor({
        state: 'hidden'
    });

    // Verify that the form automatically populated the dropdowns correctly
    const courtDropdown = page.locator('select#court');
    const caseCategoryDropdown = page.locator('select#case_category');
    const caseTypeDropdown = page.locator('select#case_type');

    // Verify court is pre-selected and disabled
    await expect(courtDropdown).toHaveValue('winnebago');
    await expect(courtDropdown.locator('option:checked')).toContainText('Winnebago County');

    // Verify case category is pre-selected and disabled
    await expect(caseCategoryDropdown.locator('option:checked')).toContainText('Miscellaneous Criminal (190925)');

    // Verify case type is pre-selected and disabled
    await expect(caseTypeDropdown.locator('option:checked')).toContainText('Forfeiture of Seized Property (324882)');

    // Wait briefly for client-side updates, then click Continue
    await page.waitForTimeout(500); // Small delay for safety
    await page.getByRole('button', {
        name: 'Continue to Documents'
    }).click();

    // Check that we're on the Upload Your Documents Page.
    // We'll stop here to avoid sending to S3 and filing the case.

    // Check for "Upload Your Documents" heading
    await expect(page.getByRole('heading', {
        name: /Upload Your Documents/i
    })).toBeVisible();

    // Verify case details are displayed correctly
    await expect(page.locator('text=Case Type: Forfeiture of Seized Property')).toBeVisible();
    await expect(page.locator('text=County: Winnebago')).toBeVisible();

    // Take a screenshot
    await page.screenshot({
        path: 'screenshots/expert-form-forfeiture-of-seized-property.png',
        fullPage: true
    });

    console.log('Screenshot saved as expert-form-forfeiture-of-seized-property.png');
});