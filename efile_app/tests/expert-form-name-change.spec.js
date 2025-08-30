const { test, expect } = require('@playwright/test');

require('dotenv').config({ path: '.env' });

test('expert-form-name-change', async ({ page }) => {
  const username = process.env.E2E_TEST_USERNAME;
  const password = process.env.E2E_TEST_PASSWORD;
  const baseUrl = process.env.E2E_TEST_BASE_URL || 'http://localhost:8000';

  if (!username || !password) {
    throw new Error('E2E_TEST_USERNAME and E2E_TEST_PASSWORD must be set in .env file');
  }

  console.log(`Logging in as ${username} to ${baseUrl}`);
  
  // Navigate to login page
  await page.goto(`${baseUrl}/login`);
  
  // Fill in login credentials
  await page.getByLabel('Email address').fill(username);
  await page.getByLabel('Password').fill(password);
  
  // Submit the form
  await page.getByRole('button', { name: /Sign In/i }).click();
  
  // Wait for navigation to complete
  await page.waitForURL(/\/options\/?$/);
  
  // Ensure the "File a New Case" section is visible
  await page.getByRole('heading', { level: 3, name: /File a New Case/i }).waitFor();

  // Click the Expert Form button under File a New Case (matches onclick)
  await page.locator("button.btn.btn-primary[onclick=\"goToExpertForm('new')\"]").click();
  
  // Wait for the form to be visible
  await page.waitForSelector('form');
  
  // Select Court
  const courtSelect = page.locator('select#court');
  await courtSelect.waitFor({ state: 'visible' });
  await courtSelect.selectOption({ value: 'cook:cd1' });

  await page.waitForTimeout(500);

  // Wait for Case Category to be enabled and select option
  const categorySelect = page.locator('select#case_category');
  await categorySelect.waitFor({ state: 'visible' });

  // Move focus to a different element first to ensure form state is stable
  await page.locator('body').click();
  await page.waitForTimeout(500);
  
  // Focus on the category select before making selection
  await categorySelect.focus();
  await page.waitForTimeout(500);

  const optionToSelect = await categorySelect.locator('option', { hasText: /^Miscellaneous \(/ });
  const optionValue = await optionToSelect.getAttribute('value');
  await categorySelect.selectOption({ value: optionValue });
  
  // Wait for any JavaScript events to complete after category selection
  await page.waitForTimeout(200);
  
  // Verify category selection is still active
  await expect(categorySelect).toHaveValue(optionValue);
  
  // Wait for Case Type to be enabled and select option
  const caseTypeSelect = page.locator('select#case_type');
  await caseTypeSelect.waitFor({ state: 'visible' });
  const caseTypeOptionToSelect = await caseTypeSelect.locator('option', { hasText: /Name Change/ });
  const caseTypeOptionValue = await caseTypeOptionToSelect.getAttribute('value');
  await caseTypeSelect.selectOption({ value: caseTypeOptionValue });
  
  // Wait for any JavaScript events to complete after case type selection
  await page.waitForTimeout(1000);
  
  // Verify both selections are still active
  await expect(categorySelect).toHaveValue(optionValue);
  await expect(caseTypeSelect).toHaveValue(caseTypeOptionValue);
  
  // Wait for the Required Parties section to appear, then fill the fields
  await page.locator('h3:has-text("Required Parties")').waitFor();
  await page.locator('#petitioner_first_name').fill('John');
  await page.locator('#petitioner_last_name').fill('Doe');
  await page.locator('#new_first_name').fill('Jane');
  await page.locator('#new_last_name').fill('Doe');
  
  // Wait briefly for client-side updates, then click Continue
  await page.waitForTimeout(500); // Small delay for safety
  await page.getByRole('button', { name: 'Continue to Documents' }).click();

  // Wait for 10 seconds before taking screenshot
  await page.waitForTimeout(10000);

  // Check that we're on the Upload Your Documents Page.
  // We'll stop here to avoid sending to S3 and filing the case.

  // Check for "Upload Your Documents" heading
  await expect(page.getByRole('heading', { name: /Upload Your Documents/i })).toBeVisible();
  
  // Verify case details are displayed correctly
  await expect(page.locator('text=Case Type: Name Change')).toBeVisible();
  await expect(page.locator('text=County: Cook County - County Division - District 1 - Chicago')).toBeVisible();

  // Take a screenshot
  await page.screenshot({ path: 'screenshots/expert-form-name-change.png', fullPage: true });
  
  console.log('Screenshot saved as expert-form-name-change.png');
});
