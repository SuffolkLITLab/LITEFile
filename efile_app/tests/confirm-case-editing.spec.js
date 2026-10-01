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
// More units than the selector shows as radios, as in Vermont (14), so the
// unit question stays a dropdown; the division question is a short list.
const UNITS = {
    'cook:cvd1': 'Chittenden Unit',
    'vt:washington': 'Washington Unit',
    'vt:orange': 'Orange Unit',
    'vt:addison': 'Addison Unit',
    'vt:bennington': 'Bennington Unit',
    'vt:caledonia': 'Caledonia Unit',
    'vt:franklin': 'Franklin Unit',
    'vt:rutland': 'Rutland Unit',
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
            },
            // Vermont's other way in: a place lookup beside the unit list. The
            // server leaves it unanswered once the unit is.
            {
                id: 'place',
                type: 'location',
                label: 'Or tell us the town',
                short_label: 'Town',
                alternative_to: 'unit',
                answer: '',
                examples: [],
                options: [],
            },
        ],
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

    test('an older answer returning first does not let Update apply before the newest one lands', async ({
        page
    }) => {
        // Washington's questions come back quickly; Orange's, asked after, are slow.
        const requests = await mockCourtLists(page, {
            delay: (url) => {
                if (!url.pathname.includes('court-selector') || !url.searchParams.get('answers')) return 0;
                return url.searchParams.get('answers').includes('vt:orange') ? 1500 : 100;
            },
        });
        await openSavedDraft(page);

        await page.locator('[data-change="unit"]').click();
        const unit = page.locator('#court-step-unit');
        await unit.selectOption('vt:washington');
        await unit.selectOption('vt:orange');
        await lateAnswerDelivered(requests, /court-selector\/.*washington/);

        await page.getByRole('button', {
            name: 'Update court'
        }).click();
        await expect(page.locator('.court-selector__actions')).toContainText('Still finding courts');
        await expect(page.locator('#court_code')).toHaveValue('cook:cvd1');

        // When Orange's answer does land, it waits for Update like any other.
        await lateAnswerDelivered(requests, /court-selector\/.*orange/);
        await expect(page.locator('.court-selector__result')).toContainText('Orange Unit');
        await expect(page.locator('#court_code')).toHaveValue('cook:cvd1');
        await page.getByRole('button', {
            name: 'Update court'
        }).click();
        await expect(page.locator('#court_code')).toHaveValue('vt:orange');
    });

    test('a reopened question opens in its own place, numbered, with Update under it', async ({
        page
    }) => {
        await mockCourtLists(page);
        await openSavedDraft(page);
        const items = page.locator('.court-selector__item');

        // Settled: the court is stated first, then the route, in order.
        await expect(page.locator('.court-selector__result + .court-selector__steps')).toHaveCount(1);
        expect(await items.evaluateAll((els) => els.map((el) => el.dataset.item))).toEqual(['level', 'division', 'unit']);
        await expect(page.locator('.court-selector__number')).toHaveText(['1', '2', '3']);

        await page.locator('[data-change="division"]').click();

        expect(await items.evaluateAll((els) => els.map((el) => el.dataset.item))).toEqual(['level', 'division', 'unit']);
        const division = page.locator('.court-selector__item[data-item="division"]');
        await expect(division).toHaveClass(/court-selector__item--open/);
        await expect(page.locator('.court-selector__item[data-item="unit"] [data-change="unit"]')).toBeVisible();
        // A short list is radios, and the selected one has focus.
        await expect(division.locator('input[type="radio"][name="court-step-division"]')).toHaveCount(2);
        await expect(division.locator('input[value="civil"]')).toBeFocused();
        await expect(division.locator('[data-court-apply]')).toBeVisible();
        await expect(division.locator('[data-court-cancel]')).toBeVisible();

        await division.locator('input[value="family"]').check();
        await expect(division.locator('input[value="family"]')).toBeFocused();
        await expect(division.locator('[data-court-apply]')).toBeVisible();
        expect(await items.evaluateAll((els) => els.map((el) => el.dataset.item))).toEqual(['level', 'division', 'unit']);
        await division.locator('[data-court-cancel]').click();
        await expect(page.locator('[data-change="division"]')).toBeFocused();
        await expect(page.locator('[data-change="division"]')).toContainText('Civil Division');
    });

    test('the unused place lookup stays out of the way unless the unit is reopened', async ({
        page
    }) => {
        await mockCourtLists(page);
        await openSavedDraft(page);
        const items = page.locator('.court-selector__item');

        await page.locator('[data-change="division"]').click();
        expect(await items.evaluateAll((els) => els.map((el) => el.dataset.item))).toEqual(['level', 'division', 'unit']);
        await expect(page.locator('[data-location-step]')).toHaveCount(0);
        await expect(page.locator('.court-selector__item[data-item="division"] [data-court-apply]')).toBeVisible();
        await page.locator('[data-court-cancel]').click();

        // Reopening the unit is when the other way of naming it is useful.
        await page.locator('[data-change="unit"]').click();
        expect(await items.evaluateAll((els) => els.map((el) => el.dataset.item))).toEqual(['level', 'division', 'unit', 'place']);
        await expect(page.locator('[data-location-step="place"]')).toBeVisible();
    });

    test('a long list stays a dropdown when its question is reopened', async ({
        page
    }) => {
        await mockCourtLists(page);
        await openSavedDraft(page);

        await page.locator('[data-change="unit"]').click();

        await expect(page.locator('select#court-step-unit')).toBeFocused();
        await expect(page.locator('input[name="court-step-unit"]')).toHaveCount(0);
        // Its alternative, the place lookup, opens with it; Update follows both.
        await expect(page.locator('.court-selector__item[data-item="place"] [data-court-apply]')).toBeVisible();
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
    test('Edit opens the dropdown and a choice applies at once, keeping what still fits', async ({
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
        // No Update or Cancel of their own: the choice is the edit.
        await expect(category.root.locator('button:not(.review-field__edit)')).toHaveCount(0);
        await category.select.selectOption('7000');

        await expect(page.locator('#case_category_code')).toHaveValue('7000');
        await expect(page.locator('#case_category_name')).toHaveValue('Civil');
        await expect(category.select).toBeVisible();
        // Contract is offered under Civil too, so it stays a summary.
        await expect(caseType.root.locator('.review-field__checking')).toBeHidden();
        await expect(caseType.summary).toBeVisible();
        expect(await optionTexts(caseType.select)).toEqual(['Choose a case type', 'Contract', 'Landlord tenant']);
        await expect(page.locator('#case_type_code')).toHaveValue('183541');
    });

    test('changing back quickly: a late list for the earlier choice is dropped', async ({
        page
    }) => {
        const requests = await mockCourtLists(page, {
            delay: (url) => (url.pathname.includes('case-types') && url.searchParams.get('parent') === '7000' ? 1200 : 0),
        });
        await openSavedDraft(page);
        const category = field(page, 'case_category');

        await category.edit.click();
        await category.select.selectOption('7000');
        await category.select.selectOption('6198');
        await lateAnswerDelivered(requests, /case-types\/.*parent=7000/);

        expect(await optionTexts(field(page, 'case_type').select)).toEqual(['Choose a case type', 'Contract', 'Tort']);
        await expect(field(page, 'case_type').summary).toBeVisible();
        await expect(page.locator('#case_type_code')).toHaveValue('183541');
    });

    test('opening a field without changing it reloads nothing', async ({
        page
    }) => {
        const requests = await mockCourtLists(page);
        await openSavedDraft(page);
        const before = requests.length;
        const caseType = field(page, 'case_type');

        await caseType.edit.click();

        await expect(caseType.select).toBeFocused();
        await expect(page.locator('#case_type_code')).toHaveValue('183541');
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
        await expect(page.locator('#case_type_code')).toHaveValue('183542');
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
        await expect(page.locator('#court_code')).toHaveValue('vt:orange');
    });
});

test('from Review: editing works the same and Back returns to Review', async ({
    page
}) => {
    await mockCourtLists(page);
    await openSavedDraft(page, `${PAGE}?return_to=review`);
    const category = field(page, 'case_category');

    await category.edit.click();
    await category.select.selectOption('7000');
    await expect(page.locator('#case_category_code')).toHaveValue('7000');
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
// Availability is checked as a choice changes, before the form is submitted.
test.describe('live filing availability', () => {
    const warning = 'Hearing scheduling is not supported for this selection.';
    // Restrict any selection that sends `blockedName` as `parameter`.
    const mockAvailability = (page, parameter, blockedName) => page.route('**/api/filing-availability/**', (route) => {
        const unavailable = new URL(route.request().url()).searchParams.getAll(parameter).includes(blockedName);
        return route.fulfill({
            json: {
                success: true,
                available: !unavailable,
                message: unavailable ? warning : ''
            }
        });
    });
    const choices = [
        ['court', 'court', 'vt:washington', 'cook:cvd1', 'vt:washington'],
        ['case_category', 'case_category_name', '7000', '6198', 'Civil'],
        ['case_type', 'case_type_name', '183542', '183541', 'Tort'],
        ['filing_type', 'filing_type_name', '143133', '143132', 'Answer'],
    ];
    for (const [name, parameter, blocked, allowed, blockedName] of choices) {
        test(`warns immediately for ${name} and clears after correction`, async ({
            page
        }) => {
            await mockCourtLists(page, {
                flat: true
            });
            await mockAvailability(page, parameter, blockedName);
            await openSavedDraft(page);
            const notice = page.locator('#filing-availability-notice');
            const next = page.getByRole('button', {
                name: 'Confirm and continue'
            });
            await expect(notice).toBeHidden();
            await field(page, name).edit.click();
            await field(page, name).select.selectOption(blocked);
            await expect(notice).toHaveText(warning);
            await expect(next).toBeDisabled();
            await field(page, name).select.selectOption(allowed);
            await expect(notice).toBeHidden();
            await expect(next).toBeEnabled();
        });
    }

    test('a changed numeric ID still sends the human-readable name', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        await page.route('**/api/dropdowns/case-types/**', (route) => route.fulfill({
            json: {
                success: true,
                data: [{
                    value: '987654',
                    text: 'Contract'
                }],
            }
        }));
        await mockAvailability(page, 'case_type_name', 'Contract');
        await page.goto(PAGE);
        await expect(field(page, 'case_type').select).toBeEnabled();
        await field(page, 'case_type').select.selectOption('987654');
        await expect(page.locator('#filing-availability-notice')).toHaveText(warning);
        await expect(page.getByRole('button', {
            name: 'Confirm and continue'
        })).toBeDisabled();
    });

    test('a late allowed response cannot clear the current restriction', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        let delayAllowed = false;
        let lateDelivered = false;
        await page.route('**/api/filing-availability/**', async (route) => {
            const blocked = new URL(route.request().url()).searchParams.get('filing_type_name') === 'Answer';
            const delayed = delayAllowed && !blocked;
            if (delayed) await new Promise((resolve) => setTimeout(resolve, 500));
            await route.fulfill({
                json: {
                    success: true,
                    available: !blocked,
                    message: blocked ? warning : ''
                }
            }).catch(() => {});
            if (delayed) lateDelivered = true;
        });
        await openSavedDraft(page);
        await expect(page.locator('#filing-availability-notice')).toBeHidden();
        await field(page, 'filing_type').edit.click();
        // Leave the saved choice first: an unchanged selection is not re-checked.
        await field(page, 'filing_type').select.selectOption('143133');
        await expect(page.locator('#filing-availability-notice')).toHaveText(warning);
        delayAllowed = true;
        const requested = page.waitForRequest('**/api/filing-availability/**');
        await field(page, 'filing_type').select.selectOption('143132');
        await requested;
        await field(page, 'filing_type').select.selectOption('143133');
        await expect(page.locator('#filing-availability-notice')).toHaveText(warning);
        await expect.poll(() => lateDelivered).toBe(true);
        await expect(page.locator('#filing-availability-notice')).toHaveText(warning);
        await expect(page.getByRole('button', {
            name: 'Confirm and continue'
        })).toBeDisabled();
    });

    test('organizing warns on a filing-type change before saving', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        for (const path of ['dropdowns/document-types', 'get-filing-components', 'dropdowns/optional-services']) {
            await page.route(`**/api/${path}/**`, (route) => route.fulfill({
                json: {
                    success: true,
                    data: []
                }
            }));
        }
        await mockAvailability(page, 'filing_type_name', 'Answer');
        await page.goto('/jurisdiction/illinois/organize-documents/');
        const choice = page.locator('.filing-type').first();
        await expect(choice).toBeEnabled();
        await choice.selectOption('143133');
        await expect(page.locator('#filing-availability-notice')).toHaveText(warning);
        await expect(page.locator('#save-document-details')).toBeDisabled();
        await choice.selectOption('143132');
        await expect(page.locator('#filing-availability-notice')).toBeHidden();
        await expect(page.locator('#save-document-details')).toBeEnabled();
    });
});