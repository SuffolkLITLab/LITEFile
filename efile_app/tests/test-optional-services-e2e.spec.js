const {
    test,
    expect
} = require('@playwright/test');
const path = require('path');
const {
    getTestConfig,
    loginViaLoginPage
} = require('./test-utils');

const SAMPLE_PDF = path.resolve(__dirname, '../../testing/sample_test.pdf');

async function selectAfterLoad(page, selector, value) {
    await expect(page.locator(`${selector} option[value="${value}"]`)).toHaveCount(1, {
        timeout: 120000,
    });
    await page.locator(selector).selectOption(value);
}

async function fillRequiredInputs(page, values) {
    for (const [name, value] of Object.entries(values)) {
        const field = page.locator(`[name="${name}"]`);
        if (await field.count()) await field.fill(value);
    }
    const required = page.locator('input[required]:visible');
    for (let index = 0; index < (await required.count()); index += 1) {
        const input = required.nth(index);
        if (await input.inputValue()) continue;
        const type = await input.getAttribute('type');
        if (type === 'radio' || type === 'checkbox') continue;
        await input.fill(
            type === 'email' ? 'efile-test@example.com' : type === 'number' ? '1' : 'Test value'
        );
    }
}

async function completeParty(page, ordinal) {
    const roleRadios = page.locator('input[name="party_type"]');
    await expect(roleRadios).not.toHaveCount(0, {
        timeout: 120000
    });
    if (!(await page.locator('input[name="party_type"]:checked').count())) {
        await roleRadios.first().check();
    }
    await page.locator('input[name="party_kind"][value="person"]').check();
    await fillRequiredInputs(page, {
        first_name: `Alex${ordinal}`,
        last_name: `Respondent${ordinal}`,
        address_line_1: `${100 + ordinal} Test Avenue`,
        city: 'Quincy',
        state: 'IL',
        zip_code: '62301',
        email: `party${ordinal}@example.com`,
        phone: '2175550100',
    });
    await Promise.all([
        page.waitForURL(/\/(party-details|case-questions|payment)\//, {
            timeout: 120000,
        }),
        page.getByRole('button', {
            name: /Save and continue/i
        }).click(),
    ]);
}

test('adding and removing optional services dynamically updates calculated fees on payment and review pages', async ({
    page
}) => {
    test.setTimeout(480000);

    console.log('Step 1: Logging in...');
    await loginViaLoginPage(page, getTestConfig());

    console.log('Step 2: Starting a new filing...');
    await page.goto('/jurisdiction/illinois/options/');
    const start = page.locator('form[action$="/start-filing/"]:has(input[name="existing_case"][value="new"])');
    await Promise.all([
        page.waitForURL(/\/upload-documents\//),
        start.getByRole('button', {
            name: /^Begin/
        }).click(),
    ]);

    console.log('Step 3: Uploading sample PDF...');
    await page.locator('#documents-input').setInputFiles(SAMPLE_PDF);
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

    console.log('Step 4: Selecting case codes (Adams County - Small Claims)...');
    const reviewedCheckbox = page.locator('input[name="reviewed_extraction"]');
    if (await reviewedCheckbox.count()) {
        await reviewedCheckbox.check();
    }
    await selectAfterLoad(page, '#court_code', 'adams');
    await selectAfterLoad(page, '#case_category_code', '6198'); // Small Claims
    await selectAfterLoad(page, '#case_type_code', '183541'); // Contract
    await selectAfterLoad(page, '#filing_type_code', '143132'); // Amended Complaint
    const radioNew = page.locator('input[type="radio"][name="existing_case"][value="new"]');
    if (await radioNew.count()) {
        await radioNew.check();
    }
    await Promise.all([
        page.waitForURL(/\/document-checklist\//, {
            timeout: 120000
        }),
        page.getByRole('button', {
            name: /Confirm and continue/i
        }).click(),
    ]);

    console.log('Step 5: Confirming checklist...');
    await page.locator('input[name="documents_complete"]').check();
    await Promise.all([
        page.waitForURL(/\/organize-documents\//),
        page.getByRole('button', {
            name: /Continue to organize/i
        }).click(),
    ]);

    console.log('Step 6: Organizing document with Optional Service (Certification with Seal - $6.00)...');
    const filingType = page.locator('.organize-card .filing-type');
    await expect(filingType.locator('option[value="143132"]')).toHaveCount(1, {
        timeout: 120000
    });
    if ((await filingType.inputValue()) !== '143132') {
        await filingType.selectOption('143132');
    }

    const docType = page.locator('.organize-card .document-type-options input');
    await expect(docType).not.toHaveCount(0, {
        timeout: 120000
    });
    if (!(await page.locator('.organize-card .document-type-options input:checked').count())) {
        await docType.first().check();
    }

    const component = page.locator('.organize-card .filing-component-options input');
    await expect(component).not.toHaveCount(0, {
        timeout: 120000
    });
    if (!(await page.locator('.organize-card .filing-component-options input:checked').count())) {
        await component.first().check();
    }

    // Open optional services details
    const details = page.locator('.organize-card .certified-copy-details');
    await expect(details).toBeVisible({
        timeout: 120000
    });
    const isDetailsOpen = await details.evaluate((el) => el.open);
    if (!isDetailsOpen) {
        await details.locator('summary').click();
    }

    // Expand additional options if toggle exists
    const toggle = page.locator('.organize-card .optional-services-toggle');
    if (await toggle.isVisible()) {
        await toggle.click();
    }

    // Select optional service (143487: Certification or Authentication with Seal $6.00)
    const optCheckbox = page.locator('.organize-card input.optional-service[value="143487"]');
    await expect(optCheckbox).toBeAttached({
        timeout: 120000
    });
    console.log('Checking optional service 143487 (Certification or Authentication with Seal $6.00)...');
    await optCheckbox.check();
    await expect(optCheckbox).toBeChecked();

    await Promise.all([
        page.waitForURL(/\/your-information\//, {
            timeout: 120000
        }),
        page.getByRole('button', {
            name: /Save and continue/i
        }).click(),
    ]);

    console.log('Step 7: Filling filer information...');
    await fillRequiredInputs(page, {
        first_name: 'Jane',
        last_name: 'Doe',
        address_line_1: '123 Main Street',
        city: 'Quincy',
        state: 'IL',
        zip_code: '62301',
        email: 'efile-test@example.com',
        phone: '2175550100',
    });
    await Promise.all([
        page.waitForURL(/\/parties\//),
        page.getByRole('button', {
            name: /Continue to parties/i
        }).click(),
    ]);

    console.log('Step 8: Completing parties...');
    const filerRoles = page.locator('input[name="filer_party_type"]');
    await expect(filerRoles).not.toHaveCount(0, {
        timeout: 120000
    });
    await filerRoles.first().check();
    await page.getByRole('button', {
        name: /Save role and check required parties/i
    }).click();

    let partyOrdinal = 1;
    while (/\/party-details\//.test(page.url())) {
        await completeParty(page, partyOrdinal);
        partyOrdinal += 1;
        if (partyOrdinal > 12) throw new Error('Unexpected number of required parties');
    }

    if (/\/case-questions\//.test(page.url())) {
        const requiredRadios = page.locator('.question-card input[type="radio"][required]');
        const names = await requiredRadios.evaluateAll((inputs) => [...new Set(inputs.map((input) => input.name))]);
        for (const name of names) await page.locator(`input[name="${name}"]`).first().check();
        await fillRequiredInputs(page, {
            amount_in_controversy: '1250.00'
        });
        await Promise.all([
            page.waitForURL(/\/payment\//, {
                timeout: 120000
            }),
            page.getByRole('button', {
                name: /Continue to fees/i
            }).click(),
        ]);
    }

    console.log('Step 9: Verifying fee calculation on Payment page WITH optional service...');
    await expect(page).toHaveURL(/\/payment\//);

    // Select the active BankAccount payment option
    const bankAccount = page.locator('input[name="paymentMethod"][data-type="BankAccount"], input[name="paymentMethod"][value="d44fd7ed-6683-48e1-a670-f7964e5bba4d"]');
    await expect(bankAccount.first()).toBeAttached({
        timeout: 120000
    });
    await bankAccount.first().check();

    const paymentInfo = page.locator('#paymentInfo');
    // Verify optional service line item and total fee are displayed
    await expect(paymentInfo).toContainText('Optional Service Fee', {
        timeout: 180000
    });
    await expect(paymentInfo).toContainText('262.25');
    await expect(paymentInfo).toContainText('6');

    const paymentInfoWithService = await paymentInfo.innerText();
    console.log('Payment Info WITH Optional Service ($6.00):\n' + paymentInfoWithService);
    console.log('✓ Verified: Fee with optional service is $262.25 ($256 initiation + $6 optional service + $0.25 convenience fee)');

    // Step 10: Continue to Review page and verify fee carries over
    console.log('Step 10: Proceeding to Review page...');
    await Promise.all([
        page.waitForURL(/\/review\//, {
            timeout: 120000
        }),
        page.locator('#submitButton').click(),
    ]);

    await expect(page.locator('.review-fee-total')).toBeVisible({
        timeout: 120000
    });
    const reviewTotalWithService = await page.locator('.review-fee-total').innerText();
    console.log('Review Total WITH Optional Service:\n' + reviewTotalWithService);
    expect(reviewTotalWithService).toContain('262.25');
    await expect(page.locator('.review-fee-breakdown')).toContainText('Optional Service Fee');
    console.log('✓ Verified: Review page shows $262.25 total and Optional Service Fee breakdown item.');

    // Step 11: Edit documents from Review page to UNCHECK the optional service
    console.log('Step 11: Clicking Edit on Documents from Review to remove optional service...');
    const editDocsLink = page.locator('a[aria-label="Edit documents"], a[href*="organize-documents"]');
    await Promise.all([
        page.waitForURL(/\/organize-documents\//, {
            timeout: 120000
        }),
        editDocsLink.first().click(),
    ]);

    const optCheckboxEdit = page.locator('.organize-card input.optional-service[value="143487"]');
    await expect(optCheckboxEdit).toBeAttached({
        timeout: 120000
    });
    await optCheckboxEdit.uncheck();
    await expect(optCheckboxEdit).not.toBeChecked();
    console.log('Unchecked optional service 143487.');

    // Save and continue back to Review (due to return_to=review)
    await Promise.all([
        page.waitForURL(/\/review\//, {
            timeout: 120000
        }),
        page.locator('#save-document-details').click(),
    ]);

    // Step 12: Navigate to Payment page to recalculate fee without optional service
    console.log('Step 12: Re-checking Payment page fee WITHOUT optional service...');
    const editPaymentLink = page.locator('a[aria-label="Edit payment"], a[href$="/payment/"]');
    await Promise.all([
        page.waitForURL(/\/payment\//, {
            timeout: 120000
        }),
        editPaymentLink.first().click(),
    ]);

    const bankAccountAgain = page.locator('input[name="paymentMethod"][data-type="BankAccount"], input[name="paymentMethod"][value="d44fd7ed-6683-48e1-a670-f7964e5bba4d"]');
    await expect(bankAccountAgain.first()).toBeAttached({
        timeout: 120000
    });
    await bankAccountAgain.first().check();

    await expect(paymentInfo).toContainText('256.25', {
        timeout: 180000
    });
    await expect(paymentInfo).not.toContainText('Optional Service Fee');

    const paymentInfoWithoutService = await paymentInfo.innerText();
    console.log('Payment Info WITHOUT Optional Service:\n' + paymentInfoWithoutService);
    console.log('✓ Verified: Fee without optional service reduced by $6.00 to $256.25 ($256 initiation + $0.25 convenience fee)!');

    // Step 13: Proceed back to Review page and verify updated lower fee
    console.log('Step 13: Proceeding to Review page to verify updated fee quote...');
    await Promise.all([
        page.waitForURL(/\/review\//, {
            timeout: 120000
        }),
        page.locator('#submitButton').click(),
    ]);

    await expect(page.locator('.review-fee-total')).toBeVisible({
        timeout: 120000
    });
    const reviewTotalWithoutService = await page.locator('.review-fee-total').innerText();
    console.log('Review Total WITHOUT Optional Service:\n' + reviewTotalWithoutService);
    expect(reviewTotalWithoutService).toContain('256.25');
    await expect(page.locator('.review-fee-breakdown')).not.toContainText('Optional Service Fee');
    console.log('✓ Verified: Review page updated to $256.25 total with Optional Service Fee removed.');
});