const {
    test,
    expect
} = require('@playwright/test');
const path = require('path');
const {
    resolveNamedOption
} = require('./named-options');
const {
    getTestConfig,
    loginViaLoginPage,
    continueFromUpload,
    fillRequiredInputs,
    choosePayByAccount,
    continueFromExtractionReview,
    continueFromDocumentChecklist,
    chooseFilingPath,
    selectGuidedCourt
} = require('./test-utils');

const SAMPLE_PDF = path.resolve(__dirname, '../../testing/sample_test.pdf');

test.skip(!process.env.RUN_FILING_MATRIX, 'Set RUN_FILING_MATRIX=1 to create filings in the test EFSP.');

// Match the names filers see; provider codes may change when a choice is re-created.
const scenarios = [{
    label: 'Adams adoption complaint',
    courtName: 'Adams County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Complaint'
}, {
    label: 'Bond adoption application',
    courtName: 'Bond County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Application'
}, {
    label: 'Cass adoption affidavit',
    courtName: 'Cass County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Affidavit'
}, {
    label: 'Champaign adoption appearance',
    courtName: 'Champaign County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Appearance'
}, {
    label: 'Christian adoption complaint',
    courtName: 'Christian County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Complaint'
}, {
    label: 'Cook chancery accounting petition',
    courtName: 'Cook County - Chancery - District 1 - Chicago',
    categoryName: 'General Chancery',
    caseTypeName: 'Accounting',
    filingTypeName: 'Complaint / Petition - Petition For Accounting Filed'
}, {
    label: 'Cook domestic relations transfer certification',
    courtName: 'Cook County - Domestic Relations - District 1 - Chicago',
    categoryName: 'Domestic Relations - General Proceedings',
    caseTypeName: 'Case Record [Change of Venue]',
    filingTypeName: 'Certification - Out Of County Transfer'
}, {
    label: 'Cook municipal administrative review petition',
    courtName: 'Cook County - Municipal Civil - District 1 - Chicago',
    categoryName: 'Civil',
    caseTypeName: 'Administrative Review - Ordinance Violation - Non-Jury',
    filingTypeName: 'Complaint / Petition - Administrative Review - Ordinance Violation - Fee'
}, {
    label: 'DuPage adoption foreign judgment',
    courtName: 'DuPage County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Foreign Judgment'
}, {
    label: 'Edgar adoption amended complaint',
    courtName: 'Edgar County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Amended Complaint'
}, {
    label: 'Fulton adoption foreign judgment',
    courtName: 'Fulton County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Foreign Judgment'
}, {
    label: 'Kane adoption complaint',
    courtName: 'Kane County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Complaint'
}, {
    label: 'Kankakee abandoned mobile home application',
    courtName: 'Kankakee - Civil',
    categoryName: 'Chancery',
    caseTypeName: 'Abandoned Mobile Home',
    filingTypeName: 'Application'
}, {
    label: 'Lake adoption affidavit',
    courtName: 'Lake County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Affidavit'
}, {
    label: 'McLean adoption complaint',
    courtName: 'McLean',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Complaint'
}, {
    label: 'Peoria adoption complaint',
    courtName: 'Peoria County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Complaint'
}, {
    label: 'Sangamon adoption appearance',
    courtName: 'Sangamon County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Appearance'
}, {
    label: 'St Clair adoption complaint',
    courtName: 'St. Clair County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Complaint'
}, {
    label: 'Will adoption application',
    courtName: 'Will County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Application'
}, {
    label: 'Winnebago adoption complaint',
    courtName: 'Winnebago County',
    categoryName: 'Adoption',
    caseTypeName: 'Adoption',
    filingTypeName: 'Complaint'
}];

const existingCaseScenarios = [{
    label: 'Existing Sangamon small-claims case',
    courtName: 'Sangamon County',
    caseNumber: '2019SC999999'
}, {
    label: 'Existing Kankakee civil case',
    courtName: 'Kankakee - Civil',
    caseNumber: '20250527-ITK-IL-2'
}, ];

async function namedOptionValue(select, name) {
    await expect(select).toBeEnabled({
        timeout: 120000
    });
    await expect.poll(() => select.locator('option').evaluateAll(options =>
        options.some(option => option.value && !option.disabled)
    ), {
        timeout: 120000
    }).toBe(true);
    const options = await select.locator('option').evaluateAll(items => items.map(option => ({
        value: option.value,
        text: option.textContent,
        disabled: option.disabled
    })));
    return resolveNamedOption(options, name, 'dropdown').value;
}

async function selectByName(page, selector, name) {
    const select = page.locator(selector);
    const value = await namedOptionValue(select, name);
    await select.selectOption(value);
    return value;
}

async function selectCourtByName(page, name) {
    const response = await page.request.get('/api/dropdowns/courts/', {
        params: {
            jurisdiction: 'illinois'
        }
    });
    expect(response.ok()).toBe(true);
    const payload = await response.json();
    expect(payload.success).toBe(true);
    const court = resolveNamedOption(payload.data, name, 'Illinois courts');
    await selectGuidedCourt(page, 'illinois', court.value);
    return court.value;
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
    const addressToggle = page.locator('#add-party-address');
    if (await addressToggle.count()) await addressToggle.check();
    await fillRequiredInputs(page, {
        first_name: `Alex${ordinal}`,
        last_name: `Respondent${ordinal}`,
        address_line_1: `${100 + ordinal} Test Avenue`,
        city: 'Springfield',
        state: 'IL',
        zip_code: '62701',
        email: `party${ordinal}@example.com`,
        phone: '2175550100',
    });
    await Promise.all([
        page.waitForURL(/\/(party-details|case-questions|payment)\//, {
            timeout: 120000
        }),
        page.getByRole('button', {
            name: /Save and continue/i
        }).click(),
    ]);
}

async function completeQuestions(page) {
    const requiredRadios = page.locator('.question-card input[type="radio"][required]');
    const names = await requiredRadios.evaluateAll(inputs => [...new Set(inputs.map(input => input.name))]);
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

async function finishFiling(page, scenario, ordinal) {
    console.log(`${scenario.label}: confirming checklist`);
    await continueFromDocumentChecklist(page);
    console.log(`${scenario.label}: organizing document`);
    const filingType = page.locator('.organize-card .filing-type');
    if (scenario.filingTypeName) {
        const expected = await namedOptionValue(filingType, scenario.filingTypeName);
        await expect(filingType).toHaveValue(expected, {
            timeout: 120000
        });
    } else {
        await page.waitForFunction(
            () => document.querySelector('.organize-card .filing-type')?.options.length > 1,
            null, {
                timeout: 120000
            },
        );
        const firstAvailable = await filingType.locator('option').nth(1).getAttribute('value');
        await filingType.selectOption(firstAvailable);
    }
    await expect(page.locator('.organize-card .document-type-options input')).not.toHaveCount(0, {
        timeout: 120000
    });
    const docType = page.locator('.organize-card .document-type-options input');
    if (!(await page.locator('.organize-card .document-type-options input:checked').count())) await docType.first().check();
    const component = page.locator('.organize-card .filing-component-options input');
    await expect(component).not.toHaveCount(0, {
        timeout: 120000
    });
    if (!(await page.locator('.organize-card .filing-component-options input:checked').count())) await component.first().check();
    await Promise.all([
        page.waitForURL(/\/your-information\//, {
            timeout: 120000
        }),
        page.getByRole('button', {
            name: /Save and continue/i
        }).click(),
    ]);

    console.log(`${scenario.label}: filling filer information`);
    await fillRequiredInputs(page, {
        first_name: 'Quinn',
        last_name: `Matrix${ordinal}`,
        address_line_1: `${ordinal} Regular Street`,
        city: 'Springfield',
        state: 'IL',
        zip_code: '62701',
        email: 'efile-test@example.com',
        phone: '2175550100',
    });
    await Promise.all([
        page.waitForURL(/\/parties\//),
        page.getByRole('button', {
            name: /Continue to parties/i
        }).click(),
    ]);

    console.log(`${scenario.label}: completing parties`);
    const filerRoles = page.locator('input[name="filer_party_type"]');
    await expect(filerRoles).not.toHaveCount(0, {
        timeout: 120000
    });
    await filerRoles.first().check();
    // Save keeps the filer on People to check the party list; only the
    // Continue button after that list moves on.
    await page.getByRole('button', {
        name: /^Save role$/i
    }).click();
    await expect(page).toHaveURL(/\/parties\//);
    await page.locator('.workflow-actions button[value="continue"]').click();

    let partyOrdinal = 1;
    while (/\/party-details\//.test(page.url())) {
        await completeParty(page, partyOrdinal);
        partyOrdinal += 1;
        if (partyOrdinal > 12) throw new Error('Unexpected number of required parties');
    }
    if (/\/case-questions\//.test(page.url())) await completeQuestions(page);
    await expect(page).toHaveURL(/\/payment\//);

    console.log(`${scenario.label}: quoting fees`);
    await page.waitForFunction('typeof PaymentPage !== "undefined" && Array.isArray(PaymentPage.accounts)', null, {
        timeout: 120000
    });
    if (process.env.E2E_PAYMENT_MODE === 'waiver') {
        await page.locator('input[name="paymentIntent"][value="waiver"]').check();
        await page.locator('#add-waiver-document').click();
        await expect(page.locator('#waiver-filing-type option')).not.toHaveCount(0, {
            timeout: 120000
        });
        const confidentiality = page.locator('#waiver-document-type');
        await expect(confidentiality.locator('option')).not.toHaveCount(0, {
            timeout: 120000
        });
        const firstSetting = await confidentiality.locator('option:not([value=""])').first().getAttribute('value');
        await confidentiality.selectOption(firstSetting);
        await page.locator('#waiver-file').setInputFiles(SAMPLE_PDF);
        await page.locator('#upload-waiver-document').click();
        await expect(page.locator('#waiver-upload-confirmation')).toBeVisible({
            timeout: 120000
        });
        // A copy added on Fees is checked here before Review is offered.
        await page.getByRole('button', {
            name: 'This copy looks right'
        }).click();
    } else {
        await choosePayByAccount(page);
    }
    const quoteOutcome = await Promise.race([
        page.locator('#errorMessage:not([hidden])').waitFor({
            state: 'visible',
            timeout: 180000
        }).then(() => 'error'),
        page.waitForFunction(() => !document.getElementById('submitButton').disabled, null, {
            timeout: 180000
        }).then(() => 'ready'),
    ]);
    if (quoteOutcome === 'error') {
        throw new Error(`Fee quote failed: ${await page.locator('#errorMessage').innerText()}`);
    }
    await Promise.all([
        page.waitForURL(/\/review\//, {
            timeout: 120000
        }),
        page.locator('#submitButton').click(),
    ]);
    console.log(`${scenario.label}: submitting filing`);
    await page.locator('#confirm-filing').check();
    await expect(page.locator('#submitButton')).toBeEnabled();
    await page.locator('#submitButton').click();
    const submissionOutcome = await Promise.race([
        page.waitForURL(/\/filing-confirmation\//, {
            timeout: 180000
        }).then(() => 'confirmed'),
        page.locator('#errorMessage:not([hidden])').waitFor({
            state: 'visible',
            timeout: 180000
        }).then(() => 'error'),
    ]);
    if (submissionOutcome === 'error') {
        throw new Error(`Submission failed: ${await page.locator('#errorMessage').innerText()}`);
    }
    await expect(page.getByRole('heading', {
        name: /Your filing was sent to the court/i
    })).toBeVisible();
}

async function startFiling(page, path) {
    // The options screen (and the header menu) start a filing that already
    // knows which kind it is, so there is no filing-path screen to answer.
    await page.goto('/jurisdiction/illinois/options/');
    const form = page.locator(`form[action$="/start-filing/"]:has(input[name="existing_case"][value="${path}"])`);
    await Promise.all([
        page.waitForURL(/\/upload-documents\//),
        form.getByRole('button', {
            name: /^Begin/
        }).click(),
    ]);
}

async function runNewCase(page, scenario, ordinal) {
    console.log(`${scenario.label}: starting a new-case draft`);
    await startFiling(page, 'new');

    console.log(`${scenario.label}: uploading document`);
    await page.locator('#documents-input').setInputFiles(SAMPLE_PDF);
    await page.getByRole('button', {
        name: 'Upload selected files'
    }).click();
    await expect(page.locator('.document-row')).toHaveCount(1, {
        timeout: 180000
    });
    await continueFromUpload(page);

    console.log(`${scenario.label}: selecting case codes`);
    await selectCourtByName(page, scenario.courtName);
    await selectByName(page, '#case_category_code', scenario.categoryName);
    await selectByName(page, '#case_type_code', scenario.caseTypeName);
    await selectByName(page, '#filing_type_code', scenario.filingTypeName);
    await chooseFilingPath(page, 'new');
    await continueFromExtractionReview(page, /\/document-checklist\//);

    await finishFiling(page, scenario, ordinal);
}

async function runExistingCase(page, scenario, ordinal) {
    console.log(`${scenario.label}: starting existing-case draft`);
    await startFiling(page, 'existing');
    await page.locator('#documents-input').setInputFiles(SAMPLE_PDF);
    await page.getByRole('button', {
        name: 'Upload selected files'
    }).click();
    await expect(page.locator('.document-row')).toHaveCount(1, {
        timeout: 180000
    });
    await continueFromUpload(page);

    const courtCode = await selectCourtByName(page, scenario.courtName);
    await chooseFilingPath(page, 'existing');
    await continueFromExtractionReview(page, /\/case-lookup\//);
    // Confirm case already saved the court. The guided picker on Lookup hides
    // its backing select, so wait for the saved value rather than clicking it.
    await expect(page.locator('#court')).toHaveValue(courtCode, {
        timeout: 120000
    });
    await page.locator('#case-number').fill(scenario.caseNumber);
    const lookupOutcome = await Promise.race([
        page.waitForURL(/\/case-confirmation\//, {
            timeout: 180000
        }).then(() => 'found'),
        page.locator('#lookup-error:not([hidden])').waitFor({
            state: 'visible',
            timeout: 180000
        }).then(() => 'error'),
        page.getByRole('button', {
            name: /Find my case/i
        }).click().then(() => 'clicked'),
    ]);
    if (lookupOutcome === 'clicked') {
        const settled = await Promise.race([
            page.waitForURL(/\/case-confirmation\//, {
                timeout: 180000
            }).then(() => 'found'),
            page.locator('#lookup-error:not([hidden])').waitFor({
                state: 'visible',
                timeout: 180000
            }).then(() => 'error'),
        ]);
        if (settled === 'error') throw new Error(`Case lookup failed: ${await page.locator('#lookup-error').innerText()}`);
    } else if (lookupOutcome === 'error') {
        throw new Error(`Case lookup failed: ${await page.locator('#lookup-error').innerText()}`);
    }
    await Promise.all([
        page.waitForURL(/\/document-checklist\//, {
            timeout: 120000
        }),
        page.getByRole('button', {
            name: /Yes, this is my case/i
        }).click(),
    ]);
    await finishFiling(page, scenario, ordinal);
}

test.beforeEach(async ({
    page
}) => {
    test.setTimeout(600000);
    const config = getTestConfig();
    await loginViaLoginPage(page, config);
    page.on('pageerror', error => console.error(`PAGE ERROR: ${error.message}`));
});

for (const [index, scenario] of scenarios.entries()) {
    test(scenario.label, async ({
        page
    }) => {
        await runNewCase(page, scenario, index + 1);
    });
}

for (const [index, scenario] of existingCaseScenarios.entries()) {
    test(scenario.label, async ({
        page
    }) => {
        await runExistingCase(page, scenario, scenarios.length + index + 1);
    });
}