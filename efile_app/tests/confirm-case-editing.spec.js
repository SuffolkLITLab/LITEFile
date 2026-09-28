/**
 * Confirm case: changing the court, category, type and filing type (#230).
 *
 * Runs the real page against the seeded accessibility session, with the court
 * lists mocked in the browser so each test controls what the court "offers"
 * and how slowly. Vermont-shaped guided court questions (level, division,
 * unit) and a flat court list stand in for the two ways states choose a court.
 *
 *   uv run python manage.py seed_accessibility_session --output playwright/.auth/a11y.json
 *   uv run python manage.py runserver 127.0.0.1:8000
 *   A11Y_STORAGE_STATE=playwright/.auth/a11y.json npm run test:confirm-case
 */
const {
    test,
    expect
} = require('@playwright/test');

const PAGE = '/jurisdiction/illinois/extraction-review/';

// The seeded draft is filed in "cook:cvd1", Small Claims (6198), Contract
// (183541), Complaint (143132); here that court is Vermont's Chittenden Unit.
const UNITS = {
    'cook:cvd1': 'Chittenden Unit',
    'vt:washington': 'Washington Unit',
    'vt:orange': 'Orange Unit',
};
const CATEGORIES = {
    'cook:cvd1': [{
        value: '6198',
        text: 'Small Claims'
    }, {
        value: '7000',
        text: 'Civil'
    }],
    'vt:washington': [{
        value: '6198',
        text: 'Small Claims'
    }, {
        value: '7000',
        text: 'Civil'
    }],
    'vt:orange': [{
        value: '7000',
        text: 'Civil'
    }],
};
const TYPES = {
    6198: [{
        value: '183541',
        text: 'Contract'
    }, {
        value: '183542',
        text: 'Tort'
    }],
    7000: [{
        value: '183541',
        text: 'Contract'
    }, {
        value: '7100',
        text: 'Landlord tenant'
    }],
};
const FILINGS = [{
    value: '143132',
    text: 'Complaint'
}, {
    value: '143133',
    text: 'Answer'
}];

function vermontSelector(answers) {
    const unit = answers.unit || '';
    const selected = unit ? {
        value: unit,
        text: UNITS[unit]
    } : null;
    return {
        available: true,
        lede: 'Start with the court shown on your paperwork.',
        steps: [{
            id: 'level',
            type: 'choice',
            label: 'What Vermont court is this filing for?',
            short_label: 'Court',
            answer: 'superior',
            options: [{
                value: 'superior',
                label: 'Superior Court'
            }],
        }, {
            id: 'division',
            type: 'select',
            label: 'Which Superior Court division?',
            short_label: 'Division',
            answer: answers.division || 'civil',
            options: [{
                value: 'civil',
                label: 'Civil Division'
            }, {
                value: 'family',
                label: 'Family Division'
            }],
        }, {
            id: 'unit',
            type: 'select',
            label: 'Which unit?',
            short_label: 'Unit',
            placeholder: 'Choose a unit…',
            answer: unit,
            options: Object.entries(UNITS).map(([value, label]) => ({
                value,
                label
            })),
        }, ],
        path: ['Superior Court', 'Civil Division', selected ? selected.text : ''].filter(Boolean),
        courts: selected ? [selected] : Object.entries(UNITS).map(([value, text]) => ({
            value,
            text
        })),
        location: null,
        waiting: !unit,
        selected,
        complete: Boolean(selected),
    };
}

function respond(url, flat) {
    const params = url.searchParams;
    const path = url.pathname;
    if (path.endsWith('/court-selector/')) {
        if (flat) return {
            available: false
        };
        const answers = params.get('answers') ? JSON.parse(params.get('answers')) : {};
        if (params.get('court')) answers.unit = params.get('court');
        return vermontSelector(answers);
    }
    if (path.endsWith('/courts/')) return Object.entries(UNITS).map(([value, text]) => ({
        value,
        text
    }));
    if (path.endsWith('/case-categories/')) return CATEGORIES[params.get('court')] || [];
    if (path.endsWith('/case-types/')) return TYPES[params.get('parent')] || [];
    if (path.endsWith('/filing-types/')) return FILINGS;
    if (path.endsWith('/filer-roles/')) return [];
    return null;
}

/**
 * Serve the court lists. `delay(url)` holds a response back, in ms; every
 * request is recorded as "endpoint court" for asserting what was asked, and
 * `requests.delivered` collects each URL once its (possibly late) answer has
 * been handed back to the page, so a test can wait for a stale one to land.
 */
async function mockCourtLists(page, {
    flat = false,
    delay = () => 0
} = {}) {
    const requests = [];
    requests.delivered = [];
    await page.route('**/api/**', async (route) => {
        const url = new URL(route.request().url());
        const data = respond(url, flat);
        if (data === null) return route.continue();
        const endpoint = url.pathname.replace('/api/dropdowns/', '').replace('/api/', '').replace(/\/$/, '');
        requests.push(`${endpoint} ${url.searchParams.get('court') || ''}`.trim());
        const wait = delay(url);
        if (wait) await new Promise((resolve) => setTimeout(resolve, wait));
        await route.fulfill({
            json: {
                success: true,
                data
            }
        }).catch(() => {});
        requests.delivered.push(url.href);
    });
    return requests;
}

/** Wait until the page has been handed the answer to a request matching `pattern`. */
async function lateAnswerDelivered(requests, pattern) {
    await expect.poll(() => requests.delivered.some((href) => pattern.test(href))).toBe(true);
}

function field(page, name) {
    const root = page.locator(`.review-field[data-field="${name}"]`);
    return {
        root,
        summary: root.locator('.review-field__display'),
        value: root.locator('.review-field__value'),
        edit: root.locator('.review-field__edit'),
        select: root.locator('select').last(),
        update: root.locator('.review-field__apply'),
        cancel: root.locator('.review-field__cancel'),
        hint: root.locator('.review-field__hint'),
    };
}

async function optionTexts(locator) {
    return locator.locator('option').evaluateAll((options) => options.map((option) => option.textContent.trim()));
}

/** Loaded, with every saved choice shown as a summary. */
async function openSavedDraft(page, path = PAGE) {
    await page.goto(path);
    for (const name of ['case_category', 'case_type', 'filing_type']) {
        await expect(field(page, name).summary).toBeVisible();
    }
    await expect(field(page, 'case_category').value).toHaveText('Small Claims');
    await expect(field(page, 'case_type').value).toHaveText('Contract');
    await expect(field(page, 'filing_type').value).toHaveText('Complaint');
}

/** Record every open/close of a summary panel from here on. */
async function watchPanels(page) {
    await page.evaluate(() => {
        window.panelChanges = [];
        document.querySelectorAll('.review-field__display').forEach((panel) => {
            new MutationObserver(() => window.panelChanges.push(panel.closest('.review-field').dataset.field))
                .observe(panel, {
                    attributes: true,
                    attributeFilter: ['hidden']
                });
        });
    });
}

test.use({
    storageState: process.env.A11Y_STORAGE_STATE
});
test.skip(!process.env.A11Y_STORAGE_STATE, 'Needs the seeded session: run seed_accessibility_session and set A11Y_STORAGE_STATE.');

test.describe('guided court questions (Vermont-shaped)', () => {
    test('rapid unit changes stay open until Update, and a late answer cannot win', async ({
        page
    }) => {
        // Washington's categories arrive long after Orange's are asked for.
        const requests = await mockCourtLists(page, {
            delay: (url) => (url.searchParams.get('court') === 'vt:washington' ? 1500 : 150),
        });
        await openSavedDraft(page);
        await watchPanels(page);
        const before = requests.length;

        await page.locator('[data-change="unit"]').click();
        const unit = page.locator('#court-step-unit');
        await expect(unit).toBeFocused();
        await unit.selectOption('vt:washington');
        await expect(unit).toBeFocused();
        await unit.selectOption('vt:orange');
        await expect(unit).toBeVisible();
        await expect(page.locator('.court-selector__result')).toContainText('Orange Unit');

        // Nothing below the court has moved: it waits for Update.
        expect(requests.slice(before).filter((request) => request.startsWith('case-categories'))).toEqual([]);
        await expect(field(page, 'case_category').value).toHaveText('Small Claims');
        await expect(page.locator('#court_code')).toHaveValue('cook:cvd1');

        await page.getByRole('button', {
            name: 'Update court'
        }).click();
        await expect(page.locator('[data-change="unit"]')).toBeFocused();
        await expect(page.locator('#court_code')).toHaveValue('vt:orange');
        await expect(page.locator('.court-selector__result')).toContainText('Orange Unit');

        // Orange has no Small Claims: cleared, and said so beside the field.
        const category = field(page, 'case_category');
        await expect(category.hint).toContainText('Small Claims is not offered');
        expect(await optionTexts(category.select)).toEqual(['Choose a case category', 'Civil']);
        expect(requests.slice(before).filter((request) => request.startsWith('case-categories'))).toEqual(['case-categories vt:orange']);
        // The category whose choice went away opens, with the two waiting on it;
        // nothing opened or closed before Update.
        expect(await page.evaluate(() => [...new Set(window.panelChanges)])).toEqual(['case_category', 'case_type', 'filing_type']);
    });

    test('a parent change keeps every dependent choice that is still offered', async ({
        page
    }) => {
        await mockCourtLists(page, {
            delay: () => 300
        });
        await openSavedDraft(page);
        await watchPanels(page);

        await page.locator('[data-change="unit"]').click();
        await page.locator('#court-step-unit').selectOption('vt:washington');
        await expect(page.locator('.court-selector__result')).toContainText('Washington Unit');
        await page.getByRole('button', {
            name: 'Update court'
        }).click();

        // While the lists reload, the summaries stay and say they are checking.
        await expect(field(page, 'case_category').root.locator('.review-field__checking')).toBeVisible();
        await expect(field(page, 'filing_type').root.locator('.review-field__checking')).toBeHidden({
            timeout: 5000
        });
        for (const [name, text] of [
                ['case_category', 'Small Claims'],
                ['case_type', 'Contract'],
                ['filing_type', 'Complaint']
            ]) {
            await expect(field(page, name).summary).toBeVisible();
            await expect(field(page, name).value).toHaveText(text);
        }
        await expect(page.locator('#case_category_code')).toHaveValue('6198');
        expect(await page.evaluate(() => window.panelChanges)).toEqual([]);
    });

    test('Update while the answer is still loading says so instead of applying half of it', async ({
        page
    }) => {
        await mockCourtLists(page, {
            delay: (url) => (url.pathname.includes('court-selector') && url.searchParams.get('answers') ? 800 : 0),
        });
        await openSavedDraft(page);

        await page.locator('[data-change="unit"]').click();
        await page.locator('#court-step-unit').selectOption('vt:orange');
        await page.getByRole('button', {
            name: 'Update court'
        }).click();
        await expect(page.locator('.court-selector__actions')).toContainText('Still finding courts');
        await expect(page.locator('#court_code')).toHaveValue('cook:cvd1');

        await expect(page.locator('.court-selector__result')).toContainText('Orange Unit');
        await page.getByRole('button', {
            name: 'Update court'
        }).click();
        await expect(page.locator('#court_code')).toHaveValue('vt:orange');
    });

    test('Change then Update without changing confirms the court and reloads nothing', async ({
        page
    }) => {
        const requests = await mockCourtLists(page);
        await openSavedDraft(page);
        const before = requests.length;

        await page.locator('[data-change="unit"]').click();
        await page.getByRole('button', {
            name: 'Update court'
        }).click();

        await expect(page.locator('#court-step-unit')).toHaveCount(0);
        await expect(page.locator('[data-change="unit"]')).toBeFocused();
        await expect(page.locator('#court_code')).toHaveValue('cook:cvd1');
        expect(requests.slice(before)).toEqual([]);
    });

    test('Cancel puts the court back as it was', async ({
        page
    }) => {
        await mockCourtLists(page);
        await openSavedDraft(page);

        await page.locator('[data-change="unit"]').click();
        await page.locator('#court-step-unit').selectOption('vt:orange');
        await expect(page.locator('.court-selector__result')).toContainText('Orange Unit');
        await page.getByRole('button', {
            name: 'Cancel'
        }).click();

        await expect(page.locator('.court-selector__result')).toContainText('Chittenden Unit');
        await expect(page.locator('[data-change="unit"]')).toBeFocused();
        await expect(page.locator('#court_code')).toHaveValue('cook:cvd1');
        await expect(field(page, 'case_category').value).toHaveText('Small Claims');
    });

    test('continuing with a court change not yet applied is stopped and points at Update', async ({
        page
    }) => {
        await mockCourtLists(page);
        await openSavedDraft(page);
        await page.locator('#reviewed_extraction').check();

        await page.locator('[data-change="unit"]').click();
        await page.locator('#court-step-unit').selectOption('vt:orange');
        await page.getByRole('button', {
            name: /Confirm and continue/
        }).click();

        await expect(page).toHaveURL(new RegExp(`${PAGE}`));
        await expect(page.locator('#extraction-review-error')).toContainText('did not apply it');
        await expect(page.getByRole('button', {
            name: 'Update court'
        })).toBeFocused();
    });
});

test.describe('category, type and filing type', () => {
    test('Edit, change, Cancel restores the choice and the lists below it', async ({
        page
    }) => {
        await mockCourtLists(page, {
            delay: () => 200
        });
        await openSavedDraft(page);
        const category = field(page, 'case_category');
        const caseType = field(page, 'case_type');

        await category.edit.click();
        await expect(category.select).toBeFocused();
        await expect(category.cancel).toBeVisible();
        await category.select.selectOption('7000');
        // Contract is offered under Civil too, so it stays a summary.
        await expect(caseType.root.locator('.review-field__checking')).toBeHidden();
        await expect(caseType.summary).toBeVisible();
        expect(await optionTexts(caseType.select)).toEqual(['Choose a case type', 'Contract', 'Landlord tenant']);

        await category.cancel.click();
        await expect(category.summary).toBeVisible();
        await expect(category.value).toHaveText('Small Claims');
        await expect(category.edit).toBeFocused();
        await expect(page.locator('#case_category_code')).toHaveValue('6198');
        expect(await optionTexts(caseType.select)).toEqual(['Choose a case type', 'Contract', 'Tort']);
        await expect(page.locator('#case_type_code')).toHaveValue('183541');
    });

    test('Cancel while a list is still loading drops the late response', async ({
        page
    }) => {
        const requests = await mockCourtLists(page, {
            delay: (url) => (url.pathname.includes('case-types') && url.searchParams.get('parent') === '7000' ? 1200 : 0),
        });
        await openSavedDraft(page);
        const category = field(page, 'case_category');

        await category.edit.click();
        await category.select.selectOption('7000');
        await category.cancel.click();
        await lateAnswerDelivered(requests, /case-types\/.*parent=7000/);

        expect(await optionTexts(field(page, 'case_type').select)).toEqual(['Choose a case type', 'Contract', 'Tort']);
        await expect(field(page, 'case_type').summary).toBeVisible();
    });

    test('Edit then Update without changing confirms the current value', async ({
        page
    }) => {
        const requests = await mockCourtLists(page);
        await openSavedDraft(page);
        const before = requests.length;
        const caseType = field(page, 'case_type');

        await caseType.edit.click();
        await expect(caseType.update).toBeVisible();
        await caseType.update.click();

        await expect(caseType.summary).toBeVisible();
        await expect(caseType.value).toHaveText('Contract');
        await expect(caseType.edit).toBeFocused();
        await expect(page.locator('#confirm-case-status')).toContainText('Case type updated: Contract.');
        expect(requests.slice(before)).toEqual([]);
    });

    test('changing a type to one that drops the filing type explains it next to the field', async ({
        page
    }) => {
        await mockCourtLists(page);
        await page.route('**/api/dropdowns/filing-types/**', (route) => {
            const url = new URL(route.request().url());
            const data = url.searchParams.get('case_type') === '183542' ? [{
                value: '9',
                text: 'Motion'
            }] : FILINGS;
            return route.fulfill({
                json: {
                    success: true,
                    data
                }
            });
        });
        await openSavedDraft(page);
        const caseType = field(page, 'case_type');
        const filing = field(page, 'filing_type');

        await caseType.edit.click();
        await caseType.select.selectOption('183542');
        await expect(filing.hint).toContainText('Complaint is not offered for the case type you chose');
        await expect(filing.select).toBeVisible();
        await caseType.update.click();
        await expect(caseType.value).toHaveText('Tort');
    });
});

test.describe('flat court list (no guided questions)', () => {
    test('rapid court changes: the list shown is always for the court chosen last', async ({
        page
    }) => {
        const requests = await mockCourtLists(page, {
            flat: true,
            delay: (url) => (url.pathname.includes('case-categories') && url.searchParams.get('court') === 'vt:washington' ? 1200 : 100),
        });
        await openSavedDraft(page);
        const court = field(page, 'court');
        await expect(court.summary).toBeVisible();
        await expect(court.value).toHaveText('Chittenden Unit');

        await court.edit.click();
        await expect(court.select).toBeFocused();
        await court.select.selectOption('vt:washington');
        await court.select.selectOption('vt:orange');
        await expect(court.select).toBeFocused();
        await lateAnswerDelivered(requests, /case-categories\/.*court=vt%3Awashington/);

        expect(await optionTexts(field(page, 'case_category').select)).toEqual(['Choose a case category', 'Civil']);
        await court.update.click();
        await expect(court.value).toHaveText('Orange Unit');
        await expect(court.edit).toBeFocused();
    });
});

test('from Review: the edit controls behave the same and Back returns to Review', async ({
    page
}) => {
    await mockCourtLists(page);
    await openSavedDraft(page, `${PAGE}?return_to=review`);
    const category = field(page, 'case_category');

    await category.edit.click();
    await category.select.selectOption('7000');
    await category.update.click();
    await expect(category.value).toHaveText('Civil');
    await expect(page.getByRole('link', {
        name: /Back to review/
    })).toBeVisible();
});

test('small screens: editing fits without sideways scrolling', async ({
    page
}) => {
    await page.setViewportSize({
        width: 360,
        height: 740
    });
    await mockCourtLists(page);
    await openSavedDraft(page);

    await page.locator('[data-change="unit"]').click();
    await expect(page.getByRole('button', {
        name: 'Update court'
    })).toBeVisible();
    await field(page, 'case_type').edit.click();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
});