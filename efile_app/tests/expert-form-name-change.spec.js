const {
    test,
    expect
} = require('@playwright/test');
const {
    loginViaLoginPage
} = require('./test-utils');

test('expert-form-name-change', async ({
    page
}) => {
    // Use the common login utility
    await loginViaLoginPage(page);

    // Ensure the "File a New Case" section is visible
    await page.getByRole('heading', {
        level: 3,
        name: /File a New Case/i
    }).waitFor();

    // Click the Expert Form button under File a New Case (matches onclick)
    await page.locator("button.btn.btn-primary[onclick=\"goToExpertForm('new')\"]").click();

    // Wait for the form to be visible
    await page.waitForSelector('form');

    // Select Court
    const courtSelect = page.locator('select#court');
    await courtSelect.waitFor({
        state: 'visible'
    });
    await courtSelect.selectOption({
        value: 'cook:cd1'
    });

    await page.waitForTimeout(500);

    // Wait for Case Category to be enabled and select option
    const categorySelect = page.locator('select#case_category');
    await categorySelect.waitFor({
        state: 'visible'
    });

    // Move focus to a different element first to ensure form state is stable
    await page.locator('body').click();
    await page.waitForTimeout(500);

    // Focus on the category select before making selection
    await categorySelect.focus();
    await page.waitForTimeout(500);

    const optionToSelect = await categorySelect.locator('option', {
        hasText: /^Miscellaneous \(/
    });
    const optionValue = await optionToSelect.getAttribute('value');
    await categorySelect.selectOption({
        value: optionValue
    });

    // Wait for any JavaScript events to complete after category selection
    await page.waitForTimeout(200);

    // Verify category selection is still active
    await expect(categorySelect).toHaveValue(optionValue);

    // Wait for Case Type to be enabled and select option
    const caseTypeSelect = page.locator('select#case_type');
    await caseTypeSelect.waitFor({
        state: 'visible'
    });
    const caseTypeOptionToSelect = await caseTypeSelect.locator('option', {
        hasText: /Name Change/
    });
    const caseTypeOptionValue = await caseTypeOptionToSelect.getAttribute('value');
    await caseTypeSelect.selectOption({
        value: caseTypeOptionValue
    });

    // Wait for any JavaScript events to complete after case type selection
    await page.waitForTimeout(1000);

    // Verify both selections are still active
    await expect(categorySelect).toHaveValue(optionValue);
    await expect(caseTypeSelect).toHaveValue(caseTypeOptionValue);

    // Wait for the Required Parties section to appear, then fill the fields
    await page.locator('h3:has-text("Required parties")').waitFor();
    await page.locator('#petitioner_first_name').fill('John');
    await page.locator('#petitioner_last_name').fill('Doe');
    await page.locator('#new_first_name').fill('Jane');
    await page.locator('#new_last_name').fill('Doe');

    // Wait briefly for client-side updates, then click Continue
    await page.waitForTimeout(500); // Small delay for safety
    await page.getByRole('button', {
        name: 'Continue to Documents'
    }).click();

    // Wait for 10 seconds before taking screenshot
    await page.waitForTimeout(10000);

    // Check that we're on the Upload Your Documents Page.
    // We'll stop here to avoid sending to S3 and filing the case.
    // TODO: you can un-comment to have the tests run all the way through to filing the case into Tyler's systems.

    /* 
    // Check for "Upload Your Documents" heading
    await expect(page.getByRole('heading', { name: /Upload Your Documents/i })).toBeVisible();
  
    // Verify case details are displayed correctly
    await expect(page.locator('text=Case Type: Name Change')).toBeVisible();
    await expect(page.locator('text=County: Cook County - County Division - District 1 - Chicago')).toBeVisible();

    // Upload the PDF file to the Lead Document upload area
    const fileInput = page.locator('input[type="file"]').first(); // Target the first file input (Lead Document)
    // NOTE: relies on the test file being in the tmp directory, which isn't checked into git
    await fileInput.setInputFiles('tmp/test-name-change1.pdf');
  
    // Wait for the file to be processed/uploaded
    await page.waitForTimeout(10000);
  
    // Fill in Filing Type with type-ahead search
    const filingTypeInput = page.locator('#leadFilingType_search');
    await filingTypeInput.fill('Petition for Name Change (');
  
    // Wait for type-ahead results and click on the first match containing "Petition for Name Change"
    await page.waitForTimeout(1000);
    await page.locator('.search-dropdown-item').filter({ hasText: 'Petition for Name Change (' }).first().click();
  
    // Fill in Document Type - select first Non-Confidential option
    const documentTypeSelect = page.locator('#leadDocumentType');
    const nonConfidentialOption = await documentTypeSelect.locator('option').filter({ hasText: /Non-Confidential \(/ }).first();
    const documentTypeValue = await nonConfidentialOption.getAttribute('value');
    await documentTypeSelect.selectOption({ value: documentTypeValue });
  
    // Fill in Filing Component - select "Lead Document"
    const filingComponentSelect = page.locator('#leadFilingComponent');
    await filingComponentSelect.selectOption({ label: 'Lead Document' });
  
    // Wait for all selections to be processed
    await page.waitForTimeout(1000);

    // Click "Continue to Review & Pay" button
    await page.getByRole('button', { name: 'Continue to Review & Pay' }).click();
  
    await page.waitForTimeout(5000);
        
    // Wait for the review page to load
    await page.waitForSelector('text=Review Case Details', { timeout: 30000 });
  
    // Click the Continue button
    await page.getByRole('button', { name: 'Continue' }).click();
  
    await page.waitForTimeout(8000);

    // Wait for the e-filing success page to load
    await page.waitForSelector('text=You will receive email confirmation shortly', { timeout: 30000 }); 

    */

    // Take a screenshot
    await page.screenshot({
        path: 'screenshots/expert-form-name-change.png',
        fullPage: true
    });

    console.log('Screenshot saved as expert-form-name-change.png');
});