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

test.skip(!process.env.RUN_FILING_MATRIX, 'Set RUN_FILING_MATRIX=1 to create filings in the test EFSP.');

const scenarios = [{
    label: 'Adams adoption complaint',
    court: 'adams',
    category: '7306',
    caseType: '25361',
    filingType: '27959'
}, {
    label: 'Bond adoption application',
    court: 'bond',
    category: '7306',
    caseType: '25361',
    filingType: '29730'
}, {
    label: 'Cass adoption affidavit',
    court: 'cass',
    category: '7306',
    caseType: '25361',
    filingType: '29670'
}, {
    label: 'Champaign adoption appearance',
    court: 'champaign',
    category: '7306',
    caseType: '159407',
    filingType: '40376'
}, {
    label: 'Christian adoption complaint',
    court: 'christian',
    category: '7306',
    caseType: '25361',
    filingType: '28106'
}, {
    label: 'Cook chancery accounting petition',
    court: 'cook:chd1',
    category: '173185',
    caseType: '173191',
    filingType: '173741'
}, {
    label: 'Cook domestic relations transfer certification',
    court: 'cook:dr1',
    category: '172833',
    caseType: '186545',
    filingType: '172974'
}, {
    label: 'Cook municipal administrative review petition',
    court: 'cook:cvd1',
    category: '174140',
    caseType: '174188',
    filingType: '174592'
}, {
    label: 'DuPage adoption foreign judgment',
    court: 'dupage',
    category: '7306',
    caseType: '129482',
    filingType: '148587'
}, {
    label: 'Edgar adoption amended complaint',
    court: 'edgar',
    category: '7306',
    caseType: '25361',
    filingType: '143017'
}, {
    label: 'Fulton adoption foreign judgment',
    court: 'fulton',
    category: '7306',
    caseType: '25361',
    filingType: '122841'
}, {
    label: 'Kane adoption complaint',
    court: 'kane',
    category: '7405',
    caseType: '10663',
    filingType: '26571'
}, {
    label: 'Kankakee abandoned mobile home application',
    court: 'KankakeeCV',
    category: '7406',
    caseType: '257879',
    filingType: '8201'
}, {
    label: 'Lake adoption affidavit',
    court: 'lake',
    category: '7306',
    caseType: '242427',
    filingType: '55469'
}, {
    label: 'McLean adoption complaint',
    court: 'mclean',
    category: '6187',
    caseType: '324985',
    filingType: '5905'
}, {
    label: 'Peoria adoption complaint',
    court: 'peoria',
    category: '7405',
    caseType: '5892',
    filingType: '127173'
}, {
    label: 'Sangamon adoption appearance',
    court: 'sangamon',
    category: '7306',
    caseType: '154869',
    filingType: '58129'
}, {
    label: 'St Clair adoption complaint',
    court: 'stclair',
    category: '7306',
    caseType: '312761',
    filingType: '314512'
}, {
    label: 'Will adoption application',
    court: 'will',
    category: '7306',
    caseType: '184409',
    filingType: '48969'
}, {
    label: 'Winnebago adoption complaint',
    court: 'winnebago',
    category: '7306',
    caseType: '76969',
    filingType: '6618'
}, ];

const existingCaseScenarios = [{
    label: 'Existing Sangamon small-claims case',
    court: 'sangamon',
    caseNumber: '2019SC999999'
}, {
    label: 'Existing Kankakee civil case',
    court: 'KankakeeCV',
    caseNumber: '20250527-ITK-IL-2'
}, ];

async function selectAfterLoad(page, selector, value) {
    await expect(page.locator(`${selector} option[value="${value}"]`)).toHaveCount(1, {
        timeout: 120000
    });
    await page.locator(selector).selectOption(value);
}

async function fillRequiredInputs(page, values) {
    for (const [name, value] of Object.entries(values)) {
        const field = page.locator(`[name="${name}"]`);
        if (await field.count()) await field.fill(value);
    }
    const required = page.locator('input[required]:visible');
    for (let index = 0; index < await required.count(); index += 1) {
        const input = required.nth(index);
        if (await input.inputValue()) continue;
        const type = await input.getAttribute('type');
        if (type === 'radio' || type === 'checkbox') continue;
        await input.fill(type === 'email' ? 'efile-test@example.com' : type === 'number' ? '1' : 'Test value');
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
    await page.locator('input[name="documents_complete"]').check();
    await Promise.all([
        page.waitForURL(/\/organize-documents\//),
        page.getByRole('button', {
            name: /Continue to organize/i
        }).click(),
    ]);
    console.log(`${scenario.label}: organizing document`);
    const filingType = page.locator('.organize-card .filing-type');
    if (scenario.filingType) {
        await expect(filingType).toHaveValue(scenario.filingType, {
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
        scenario.filingType = firstAvailable;
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
    await page.getByRole('button', {
        name: /Save role and check required parties/i
    }).click();

    let partyOrdinal = 1;
    while (/\/party-details\//.test(page.url())) {
        await completeParty(page, partyOrdinal);
        partyOrdinal += 1;
        if (partyOrdinal > 12) throw new Error('Unexpected number of required parties');
    }
    if (/\/case-questions\//.test(page.url())) await completeQuestions(page);
    await expect(page).toHaveURL(/\/payment\//);

    console.log(`${scenario.label}: quoting fees`);
    await expect(page.locator('input[name="paymentMethod"]')).not.toHaveCount(0, {
        timeout: 120000
    });
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
    await Promise.all([
        page.waitForURL(/\/extraction-review\//),
        page.locator('#continue-to-analysis').click(),
    ]);

    console.log(`${scenario.label}: selecting case codes`);
    await selectAfterLoad(page, '#court_code', scenario.court);
    await selectAfterLoad(page, '#case_category_code', scenario.category);
    await selectAfterLoad(page, '#case_type_code', scenario.caseType);
    await selectAfterLoad(page, '#filing_type_code', scenario.filingType);
    await page.locator('input[name="existing_case"][value="new"]').check();
    await Promise.all([
        page.waitForURL(/\/document-checklist\//, {
            timeout: 120000
        }),
        page.getByRole('button', {
            name: /Confirm and continue/i
        }).click(),
    ]);

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
    await Promise.all([
        page.waitForURL(/\/extraction-review\//),
        page.locator('#continue-to-analysis').click(),
    ]);

    await selectAfterLoad(page, '#court_code', scenario.court);
    await page.locator('input[name="existing_case"][value="existing"]').check();
    await Promise.all([
        page.waitForURL(/\/case-lookup\//, {
            timeout: 120000
        }),
        page.getByRole('button', {
            name: /Confirm and continue/i
        }).click(),
    ]);
    await selectAfterLoad(page, '#court', scenario.court);
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