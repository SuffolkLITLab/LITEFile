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

test.describe('filing code search', () => {
    const result = {
        id: 101,
        initial: true,
        court: {
            code: 'vt:orange',
            name: 'Orange Unit'
        },
        case_category: {
            code: '7000',
            name: 'Civil'
        },
        case_type: {
            code: '7100',
            name: 'Landlord tenant'
        },
        filing_type: {
            code: '143132',
            name: 'Complaint'
        },
        explanation: '',
        explanation_source: '',
        unavailable: '',
    };
    const options = {
        court: Object.entries(UNITS).map(([code, name]) => ({
            code,
            name
        })),
        case_category: [{
            code: '7000',
            name: 'Civil'
        }],
        case_type: [{
            code: '7100',
            name: 'Landlord tenant'
        }],
        filing_type: [{
            code: '143132',
            name: 'Complaint'
        }],
    };

    async function mockSearch(page, {
        reject = false,
        unavailable = false
    } = {}) {
        const queries = [];
        await page.route('**/api/filing-code-search/**', async route => {
            const params = new URL(route.request().url()).searchParams;
            queries.push(Object.fromEntries(params));
            if (params.has('path_id')) {
                return route.fulfill(reject ? {
                    status: 409,
                    json: {
                        error: 'The code list has changed. Search again.'
                    },
                } : {
                    json: {
                        path: {
                            ...result,
                            options
                        }
                    }
                });
            }
            return route.fulfill({
                json: {
                    results: [{
                        ...result,
                        unavailable: unavailable ? 'Temporarily unavailable' : ''
                    }],
                    total: 1,
                    corrected_terms: [],
                    stale: false,
                }
            });
        });
        return queries;
    }

    test('empty search offers common types, clears back to them, and accepts one character', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        const queries = await mockSearch(page);
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        const dialog = page.getByRole('dialog');
        await expect(dialog.getByRole('heading', {
            name: 'Common filing types'
        })).toBeVisible();
        expect(queries).toEqual([]);
        await dialog.getByRole('button', {
            name: 'Complaint',
            exact: true
        }).click();
        await expect(dialog.getByRole('radio', {
            name: 'Complaint'
        })).toBeVisible();
        expect(queries[0].q).toBe('complaint');
        await dialog.getByRole('radio').check();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('');
        await expect(dialog.getByRole('heading', {
            name: 'Common filing types'
        })).toBeVisible();
        await expect(dialog.getByRole('radio')).toHaveCount(0);
        await expect(dialog.getByRole('button', {
            name: 'Use this path'
        })).toBeDisabled();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('m');
        await expect(dialog.getByRole('radio')).toBeVisible();
        expect(queries.at(-1).q).toBe('m');
    });

    test('an HTML server error gives a readable message and search can be retried', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        await mockSearch(page);
        await page.route('**/api/filing-code-search/**', route => route.fulfill({
            status: 503,
            contentType: 'text/html',
            body: '<!DOCTYPE html><title>Unavailable</title>',
        }), {
            times: 1
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('button', {
            name: 'Complaint',
            exact: true
        }).click();
        await expect(page.locator('#code-search-status')).toContainText('Code search could not be loaded');
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).press('Enter');
        await expect(page.getByRole('dialog').getByRole('radio')).toBeVisible();
    });

    test('search becomes usable when the first index finishes without reopening the dialog', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        await mockSearch(page);
        await page.clock.install();
        await page.route('**/api/filing-code-search/**', route => route.fulfill({
            status: 503,
            json: {
                error: 'Code search is not available yet.'
            },
        }), {
            times: 1
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('button', {
            name: 'Complaint',
            exact: true
        }).click();
        await expect(page.locator('#code-search-status')).toContainText('We will try again shortly.');
        await page.clock.fastForward(10000);
        await expect(page.getByRole('dialog').getByRole('radio')).toBeVisible();
    });

    for (const flat of [true, false]) {
        test(`applies all four facets across courts (${flat ? 'flat' : 'guided'})`, async ({
            page
        }) => {
            await mockCourtLists(page, {
                flat
            });
            const queries = await mockSearch(page);
            await openSavedDraft(page);
            const open = page.getByRole('button', {
                name: 'Find the right filing code'
            });
            await open.click();
            const dialog = page.getByRole('dialog');
            await expect(page.getByRole('searchbox', {
                name: 'Search filing codes'
            })).toBeFocused();
            await page.getByRole('searchbox', {
                name: 'Search filing codes'
            }).fill('eviction');
            await expect(dialog).not.toContainText('No plain-language explanation');
            await dialog.getByRole('radio', {
                name: 'Complaint'
            }).check();
            await expect(dialog.locator('details')).toHaveAttribute('open', '');
            await expect(dialog).toContainText('Case type: Landlord tenant');
            await dialog.getByRole('button', {
                name: 'Use this path'
            }).click();
            await expect(dialog).not.toBeVisible();
            await expect(open).toBeFocused();
            await expect(page.locator('#court_code')).toHaveValue('vt:orange');
            await expect(field(page, 'case_category').value).toHaveText('Civil');
            await expect(field(page, 'case_type').value).toHaveText('Landlord tenant');
            await expect(field(page, 'filing_type').value).toHaveText('Complaint');
            if (!flat) await expect(page.locator('.court-selector__result')).toContainText('Orange Unit');
            expect(queries[0]).toMatchObject({
                jurisdiction: 'illinois',
                existing_case: 'no',
                q: 'eviction',
                offset: '0'
            });
            expect(queries[0]).not.toHaveProperty('court');
            expect(queries[1].path_id).toBe('101');
        });
    }

    for (const hasCourt of [false, true]) {
        test(`groups repeated court codes with ${hasCourt ? 'a current court' : 'no court selected'}`, async ({
            page
        }) => {
            await mockCourtLists(page, {
                flat: true
            });
            await mockSearch(page);
            await page.route('**/api/filing-code-search/**', route => {
                const params = new URL(route.request().url()).searchParams;
                if (params.has('path_id')) return route.fallback();
                if (params.has('court')) return route.fulfill({
                    json: {
                        results: [{
                            ...result,
                            court: {
                                code: params.get('court'),
                                name: UNITS[params.get('court')]
                            }
                        }],
                        total: 1,
                        corrected_terms: [],
                        stale: false,
                    }
                });
                if (params.has('group')) return route.fulfill({
                    json: {
                        courts: [{
                            code: 'vt:orange',
                            name: 'Orange Unit'
                        }, {
                            code: 'cook:cvd1',
                            name: 'Chittenden Unit'
                        }],
                        corrected_terms: [],
                    }
                });
                return route.fulfill({
                    json: {
                        groups: [{
                            key: 'eviction',
                            name: 'Eviction Complaint',
                            variants: ['Eviction Complaint', 'Summary Process Complaint'],
                            path_count: 100
                        }],
                        total: 1,
                        corrected_terms: [],
                        stale: false,
                    }
                });
            });
            await openSavedDraft(page);
            if (!hasCourt) await page.locator('#court_code').evaluate(input => input.value = '');
            await page.getByRole('button', {
                name: 'Find the right filing code'
            }).click();
            await page.getByRole('searchbox', {
                name: 'Search filing codes'
            }).fill('eviction');
            const dialog = page.getByRole('dialog');
            await expect(dialog.locator('.code-search__group')).toHaveCount(1);
            await expect(dialog.getByRole('radio')).toHaveCount(0);
            await expect(dialog).toContainText('Also listed as: Summary Process Complaint');
            await dialog.getByRole('button', {
                name: 'Choose a court for Eviction Complaint'
            }).click();
            const court = dialog.getByLabel('Court', {
                exact: true
            });
            await expect(court).toHaveValue(hasCourt ? 'cook:cvd1' : '');
            if (hasCourt) {
                await expect(court.locator('option').nth(1)).toHaveText('Chittenden Unit');
                await expect(dialog.getByRole('radio')).toHaveCount(1);
                await dialog.getByRole('radio').check();
            } else {
                await expect(dialog.getByRole('radio')).toHaveCount(0);
            }
            await court.selectOption('vt:orange');
            await expect(dialog.getByRole('button', {
                name: 'Use this path'
            })).toBeDisabled();
            await expect(dialog.locator('.code-search__result label')).toHaveCount(2);
            await dialog.getByRole('radio').check();
            await dialog.getByRole('button', {
                name: 'Use this path'
            }).click();
            await expect(dialog).not.toBeVisible();
            await expect(page.locator('#court_code')).toHaveValue('vt:orange');
            await expect(page.locator('#case_type_code')).toHaveValue('7100');
        });
    }

    test('synonym results explain their concepts and show local meanings after court selection', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        const meaning = {
            key: 'eviction',
            label: 'Eviction',
            text: 'Statewide eviction meaning.',
            scope: 'state',
            scope_name: 'Vermont',
            source: 'https://www.vtcourts.gov/civil/eviction-process',
        };
        await page.route('**/api/filing-code-search/**', route => {
            const params = new URL(route.request().url()).searchParams;
            const match_reason = params.get('q') === 'eviction' ? null : {
                kind: 'related_concept',
                query: params.get('q'),
                concepts: ['eviction'],
                corrected_terms: [],
            };
            if (params.has('court')) {
                const county = params.get('court') === 'vt:orange' ? 'Orange' : 'Chittenden';
                return route.fulfill({
                    json: {
                        results: [{
                            ...result,
                            case_description: `${county} local meaning.`,
                            match_reason,
                            concepts: [{
                                ...meaning,
                                scope: 'county',
                                scope_name: county,
                                text: `${county} local meaning.`
                            }]
                        }],
                        total: 1,
                        corrected_terms: [],
                    }
                });
            }
            if (params.has('group')) return route.fulfill({
                json: {
                    courts: [{
                        code: 'vt:orange',
                        name: 'Orange Unit'
                    }, {
                        code: 'cook:cvd1',
                        name: 'Chittenden Unit'
                    }],
                }
            });
            return route.fulfill({
                json: {
                    groups: [{
                        key: 'eviction',
                        name: 'Eviction complaint',
                        variants: ['Eviction complaint'],
                        concepts: [meaning],
                        match_reason
                    }],
                    total: 1,
                    corrected_terms: [],
                }
            });
        });
        await openSavedDraft(page);
        await page.locator('#court_code').evaluate(input => input.value = '');
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('unlawful detainer');
        const group = page.locator('.code-search__group');
        await expect(group).toContainText('Meaning in Vermont: Statewide eviction meaning.');
        const why = group.locator('.code-search__match-reason');
        await expect(why.locator('p').first()).not.toBeVisible();
        await why.locator('summary').focus();
        await page.keyboard.press('Enter');
        await expect(why.locator('p').first()).toBeVisible();
        await expect(why).toContainText('Your search for “unlawful detainer” relates to Eviction');
        await expect(group.getByRole('link', {
            name: 'About this concept'
        })).toHaveAttribute('href', meaning.source);
        await group.getByRole('button', {
            name: 'Choose a court for Eviction complaint'
        }).click();
        await group.getByLabel('Court', {
            exact: true
        }).selectOption('vt:orange');
        await expect(group).toContainText('Orange local meaning.');
        await group.getByLabel('Court', {
            exact: true
        }).selectOption('cook:cvd1');
        await expect(group).toContainText('Chittenden local meaning.');
        await expect(group).not.toContainText('Orange local meaning.');
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('eviction');
        await expect(group.locator('.code-search__match-reason')).toHaveCount(0);
        await expect(group).toContainText('Statewide eviction meaning.');
    });

    test('contextual radios and claim amount dropdown reset when the case area changes', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        const queries = [];
        await page.route('**/api/filing-code-search/**', route => {
            const params = new URL(route.request().url()).searchParams;
            queries.push({
                ...Object.fromEntries(params),
                choices: JSON.parse(params.get('case_filters') || '{}')
            });
            const topic = params.get('case_topic') || (params.get('q') === 'eviction' ? 'eviction' : 'small_claims');
            const case_facets = topic === 'eviction' ? [{
                key: 'role',
                label: 'Your role',
                options: [{
                    value: 'tenant',
                    label: 'Tenant / occupant'
                }, {
                    value: 'landlord',
                    label: 'Landlord / owner'
                }]
            }, {
                key: 'property',
                label: 'Property',
                options: [{
                    value: 'residential',
                    label: 'Home'
                }, {
                    value: 'commercial',
                    label: 'Business'
                }]
            }, ] : [{
                key: 'amount',
                label: 'Claim amount',
                control: 'select',
                options: [{
                    value: '0:250000',
                    label: 'Up to $2,500'
                }, {
                    value: '250001:1000000',
                    label: '$2,500.01–$10,000'
                }, ],
                help: 'State-specific limits and exceptions.',
                source: 'https://www.illinoiscourts.gov/'
            }];
            return route.fulfill({
                json: {
                    groups: [{
                        key: 'answer',
                        name: 'Answer',
                        variants: ['Answer']
                    }],
                    total: 1,
                    corrected_terms: [],
                    case_topic: topic,
                    case_facets,
                    case_topics: [{
                        value: 'eviction',
                        label: 'Eviction'
                    }, {
                        value: 'small_claims',
                        label: 'Small claims'
                    }]
                }
            });
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('eviction');
        const facets = page.locator('#code-search-case-filters');
        await expect(facets).toBeVisible();
        await facets.getByRole('radio', {
            name: 'Tenant / occupant',
            exact: true
        }).check();
        await expect.poll(() => queries.at(-1)?.choices.role).toBe('tenant');
        await facets.getByRole('radio', {
            name: 'Home',
            exact: true
        }).check();
        await expect.poll(() => queries.at(-1)?.choices.property).toBe('residential');
        await expect(facets.getByRole('radio', {
            name: 'Business',
            exact: true
        })).not.toBeChecked();
        await facets.getByLabel('Case area', {
            exact: true
        }).selectOption('small_claims');
        await expect(facets.getByLabel('Claim amount', {
            exact: true
        })).toBeVisible();
        expect(queries.at(-1).choices).toEqual({});
        await facets.getByLabel('Claim amount', {
            exact: true
        }).selectOption('250001:1000000');
        await expect.poll(() => queries.at(-1)?.choices.amount).toBe('250001:1000000');
        await expect(facets.getByLabel('Claim amount', {
            exact: true
        })).toHaveValue('250001:1000000');
        await facets.getByText('About claim amounts', {
            exact: true
        }).click();
        await expect(facets.getByText('State-specific limits and exceptions.')).toBeVisible();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('small claims');
        await expect.poll(() => queries.at(-1)?.q).toBe('small claims');
        expect(queries.at(-1).choices).toEqual({});
    });

    test('court paths emphasize case types without repeating shared filing information', async ({
        page
    }) => {
        await page.setViewportSize({
            width: 1366,
            height: 768
        });
        await mockCourtLists(page, {
            flat: true
        });
        const filingName = 'Answer/Response to Complaint/Petition';
        const caseTypes = ['Commercial', 'Commercial - Possession Only', 'Ejectment', 'Residential - Eviction', 'Residential - Eviction Possession Only'];
        await page.route('**/api/filing-code-search/**', route => {
            const params = new URL(route.request().url()).searchParams;
            if (params.has('court')) return route.fulfill({
                json: {
                    results: caseTypes.map((name, i) => ({
                        ...result,
                        id: i + 100,
                        filing_type: {
                            ...result.filing_type,
                            name: filingName
                        },
                        case_type: {
                            code: `case-${i}`,
                            name
                        },
                        case_context: `Eviction › ${name}`,
                        case_description: "An existing plain-language case description.",
                        facets: {
                            purpose: 'responding',
                            document: 'main'
                        },
                    })),
                    total: caseTypes.length,
                    corrected_terms: [],
                }
            });
            if (params.has('group')) return route.fulfill({
                json: {
                    courts: [{
                        code: 'vt:orange',
                        name: 'Orange Unit'
                    }]
                }
            });
            return route.fulfill({
                json: {
                    groups: [{
                        key: 'answer',
                        name: filingName,
                        variants: [filingName]
                    }],
                    total: 1,
                    corrected_terms: [],
                    case_topic: 'eviction',
                    case_topics: [{
                        value: 'eviction',
                        label: 'Eviction'
                    }],
                    case_facets: [{
                        key: 'role',
                        label: 'Your role',
                        options: [{
                            value: 'tenant',
                            label: 'Tenant / occupant'
                        }, {
                            value: 'landlord',
                            label: 'Landlord / owner'
                        }]
                    }, {
                        key: 'property',
                        label: 'Property',
                        options: [{
                            value: 'residential',
                            label: 'Home'
                        }, {
                            value: 'commercial',
                            label: 'Business'
                        }]
                    }, {
                        key: 'relief',
                        label: 'What the landlord is asking for',
                        options: [{
                            value: 'possession',
                            label: 'Property back only'
                        }, {
                            value: 'money',
                            label: 'Money too'
                        }]
                    }, ]
                }
            });
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('answer');
        await page.getByRole('button', {
            name: `Choose a court for ${filingName}`
        }).click();
        await page.getByLabel('Court', {
            exact: true
        }).selectOption('vt:orange');
        const choices = page.locator('.code-search__path-choice');
        await expect(choices).toHaveCount(5);
        for (const name of caseTypes) await expect(page.getByRole('radio', {
            name: `Eviction › ${name}`,
            exact: true
        })).toBeVisible();
        await expect(choices.locator('label')).not.toContainText([filingName, filingName, filingName, filingName, filingName]);
        expect(await choices.evaluateAll(rows => rows.every(row => row.getBoundingClientRect().height < 65))).toBe(true);
        await page.getByRole('radio', {
            name: 'Eviction › Residential - Eviction',
            exact: true
        }).check();
        await expect(choices.locator('details[open]')).toHaveCount(0);
        const visible = await choices.evaluateAll(rows => {
            const bounds = document.getElementById('code-search-results').getBoundingClientRect();
            return rows.filter(row => row.getBoundingClientRect().top >= bounds.top && row.getBoundingClientRect().bottom <= bounds.bottom).length;
        });
        expect(visible).toBeGreaterThanOrEqual(3);
        const toggle = choices.nth(3).getByText('Details', {
            exact: true
        });
        const before = await toggle.boundingBox();
        await expect(choices.nth(3).getByText('An existing plain-language case description.')).toBeVisible();
        await toggle.click();
        expect(await toggle.boundingBox()).toEqual(before);
        await expect(choices.nth(3).locator('ol')).not.toContainText('case-3');
        await expect(choices.locator('.code-search__match-reason')).toHaveCount(0);
        await expect(choices.nth(3).locator('ol')).toContainText(filingName);
        await toggle.click();
        await expect(choices.nth(3).locator('ol')).not.toBeVisible();
        await expect(page.getByRole('button', {
            name: 'Use this path'
        })).toBeEnabled();
    });

    test('compact filters keep four results visible and apply case stage only with a path', async ({
        page
    }) => {
        await page.setViewportSize({
            width: 1366,
            height: 768
        });
        await mockCourtLists(page, {
            flat: true
        });
        const queries = [];
        await page.route('**/api/filing-code-search/**', route => {
            const params = new URL(route.request().url()).searchParams;
            queries.push(Object.fromEntries(params));
            const path = {
                ...result,
                initial: params.get('existing_case') !== 'yes'
            };
            if (params.has('path_id')) return route.fulfill({
                json: {
                    path: {
                        ...path,
                        options
                    }
                }
            });
            if (params.has('court')) return route.fulfill({
                json: {
                    results: [path],
                    total: 1,
                    corrected_terms: []
                }
            });
            if (params.has('group')) return route.fulfill({
                json: {
                    courts: [{
                        code: 'vt:orange',
                        name: 'Orange Unit'
                    }]
                }
            });
            const groups = Array.from({
                length: 6
            }, (_, i) => ({
                key: `type-${i}`,
                name: `Complaint / Petition - Eviction - Residential - Possession Only - Fee ${i}`,
                variants: ['Complaint', 'Petition'],
                facets: {
                    purpose: 'starting',
                    document: 'main'
                },
                case_contexts: ['Small claims', 'Civil › Eviction'],
                case_context_count: 2,
                concepts: [{
                    key: 'eviction',
                    label: 'Eviction',
                    text: 'A short explanation of this concept.',
                    scope: 'general'
                }],
            }));
            return route.fulfill({
                json: {
                    groups,
                    total: 6,
                    corrected_terms: []
                }
            });
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('eviction');
        await expect(page.locator('.code-search__group')).toHaveCount(6);
        await expect(page.locator('.code-search__group').first().locator('.code-search__meta')).toContainText('2 case types, including Small claims');
        const visible = await page.locator('#code-search-results').evaluate(container => {
            const bounds = container.getBoundingClientRect();
            return Array.from(container.querySelectorAll('.code-search__group')).filter(row => {
                const rect = row.getBoundingClientRect();
                return rect.top >= bounds.top && rect.bottom <= bounds.bottom;
            }).length;
        });
        expect(visible).toBeGreaterThanOrEqual(4);
        const before = await page.locator('input[name="existing_case"]:checked').inputValue();
        await page.getByLabel('Case stage', {
            exact: true
        }).selectOption('yes');
        await expect.poll(() => queries.at(-1)?.existing_case).toBe('yes');
        await page.getByLabel('Your task', {
            exact: true
        }).selectOption('responding');
        await expect.poll(() => queries.at(-1)?.purpose).toBe('responding');
        await page.getByLabel('Document', {
            exact: true
        }).selectOption('main');
        await expect.poll(() => queries.at(-1)?.document).toBe('main');
        await expect(page.locator('input[name="existing_case"]:checked')).toHaveValue(before);
        const first = page.locator('.code-search__group').first();
        await first.getByRole('button', {
            name: /Choose a court/
        }).click();
        await first.getByLabel('Court', {
            exact: true
        }).selectOption('vt:orange');
        await first.getByRole('radio').check();
        await page.getByRole('button', {
            name: 'Use this path'
        }).click();
        await expect(page.getByRole('dialog')).not.toBeVisible();
        await expect(page.locator('input[name="existing_case"]:checked')).toHaveValue('existing');
        await expect(page.locator('#case_type_code')).toHaveValue('7100');
    });

    test('ZIP filter updates the search and clearing it restores all counties', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        const queries = [];
        await page.route('**/api/filing-code-search/**', route => {
            const params = new URL(route.request().url()).searchParams;
            queries.push(Object.fromEntries(params));
            return route.fulfill({
                json: {
                    groups: [{
                        key: 'petition',
                        name: 'Petition',
                        variants: ['Petition']
                    }],
                    total: 1,
                    corrected_terms: [],
                    location_counties: params.get('zip') ? ['Cook'] : [],
                }
            });
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('eviction');
        await expect(page.locator('.code-search__group')).toHaveCount(1);
        await page.getByLabel('Case location ZIP', {
            exact: true
        }).fill('60601');
        await expect(page.locator('#code-search-status')).toContainText('Counties: Cook.');
        expect(queries.at(-1).zip).toBe('60601');
        await page.getByLabel('Case location ZIP', {
            exact: true
        }).fill('');
        await expect(page.locator('#code-search-status')).not.toContainText('Counties:');
        await expect.poll(() => queries.at(-1)?.zip).toBe('');
    });

    test('case-type links narrow courts and paths and can be cleared', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        const queries = [];
        await page.route('**/api/filing-code-search/**', async route => {
            const params = new URL(route.request().url()).searchParams;
            queries.push(Object.fromEntries(params));
            const context = params.get('context');
            if (params.has('court')) return route.fulfill({
                json: {
                    results: [{
                        ...result,
                        case_type: {
                            code: context || 'all',
                            name: context === 'small' ? 'Small claims' : 'Eviction'
                        }
                    }],
                    total: 1,
                    corrected_terms: [],
                }
            });
            if (params.has('group')) {
                if (context === 'eviction') await new Promise(resolve => setTimeout(resolve, 150));
                const courts = [{
                    code: 'vt:orange',
                    name: 'Orange Unit'
                }, {
                    code: 'cook:cvd1',
                    name: 'Chittenden Unit'
                }];
                return route.fulfill({
                    json: {
                        courts: context === 'small' ? courts.slice(0, 1) : context === 'eviction' ? courts.slice(1) : courts
                    }
                });
            }
            return route.fulfill({
                json: {
                    groups: [{
                        key: 'petition',
                        name: 'Petition',
                        variants: ['Petition'],
                        case_contexts: ['Small claims', 'Civil › Eviction'],
                        case_context_count: 2,
                        case_context_options: [{
                            key: 'small',
                            label: 'Small claims'
                        }, {
                            key: 'eviction',
                            label: 'Civil › Eviction'
                        }]
                    }],
                    total: 1,
                    corrected_terms: [],
                }
            });
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('petition');
        const group = page.locator('.code-search__group');
        await group.locator('summary').click();
        const small = group.getByRole('button', {
            name: 'Small claims',
            exact: true
        });
        await small.focus();
        await page.keyboard.press('Enter');
        const court = group.getByLabel('Court', {
            exact: true
        });
        await expect(court).toBeEnabled();
        await expect(court.locator('option')).toHaveText(['Choose a court', 'Orange Unit']);
        await court.selectOption('vt:orange');
        await group.getByRole('radio').check();
        await expect(page.getByRole('button', {
            name: 'Use this path'
        })).toBeEnabled();
        await group.locator('summary').first().click();
        await group.getByRole('button', {
            name: 'Civil › Eviction',
            exact: true
        }).click();
        await expect(page.getByRole('button', {
            name: 'Use this path'
        })).toBeDisabled();
        await expect(court).toBeEnabled();
        await expect(court.locator('option')).toHaveText(['Choose a court', 'Chittenden Unit']);
        await court.selectOption('cook:cvd1');
        await expect(group.getByRole('radio')).toHaveCount(1);
        expect(queries.filter(item => item.court).at(-1).context).toBe('eviction');
        await group.getByRole('button', {
            name: 'Show all case types'
        }).click();
        await expect(court.locator('option')).toHaveCount(3);
        await expect.poll(() => queries.at(-1)?.context).toBe('');
    });

    test('earlier groups remain usable after loading another page of groups', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        await page.route('**/api/filing-code-search/**', route => {
            const params = new URL(route.request().url()).searchParams;
            if (params.has('court')) return route.fulfill({
                json: {
                    results: [result],
                    total: 1,
                    corrected_terms: []
                }
            });
            if (params.has('group')) return route.fulfill({
                json: {
                    courts: [{
                        code: 'vt:orange',
                        name: 'Orange Unit'
                    }]
                }
            });
            const offset = Number(params.get('offset'));
            const groups = Array.from({
                length: offset ? 1 : 20
            }, (_, i) => ({
                key: `type-${offset + i}`,
                name: `Filing ${offset + i}`,
                variants: [`Filing ${offset + i}`],
                path_count: 100,
            }));
            return route.fulfill({
                json: {
                    groups,
                    total: 21,
                    corrected_terms: [],
                    stale: false
                }
            });
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('button', {
            name: 'Complaint',
            exact: true
        }).click();
        await expect(page.locator('.code-search__group')).toHaveCount(20);
        await page.getByRole('button', {
            name: 'Show more results',
            exact: true
        }).click();
        await expect(page.locator('.code-search__group')).toHaveCount(21);
        await page.getByRole('button', {
            name: 'Choose a court for Filing 0',
            exact: true
        }).click();
        await page.locator('.code-search__group').first().getByLabel('Court', {
            exact: true
        }).selectOption('vt:orange');
        await page.getByRole('dialog').getByRole('radio').check();
        await expect(page.getByRole('button', {
            name: 'Use this path'
        })).toBeEnabled();
    });

    test('rejects a retired path without changing form choices and restores focus on Escape', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        await mockSearch(page, {
            reject: true
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('eviction');
        await page.getByRole('dialog').getByRole('radio').check();
        await page.getByRole('button', {
            name: 'Use this path'
        }).click();
        await expect(page.getByRole('dialog')).toContainText('The code list has changed');
        await expect(page.locator('#court_code')).toHaveValue('cook:cvd1');
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog')).not.toBeVisible();
        await expect(page.getByRole('button', {
            name: 'Find the right filing code'
        })).toBeFocused();
    });

    test('a late search cannot replace a newer query or leave an old selection active', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        await mockSearch(page);
        let delivered = false;
        await page.route('**/api/filing-code-search/**', async route => {
            const params = new URL(route.request().url()).searchParams;
            if (params.get('q') !== 'delayed') return route.fallback();
            await new Promise(resolve => setTimeout(resolve, 800));
            await route.fulfill({
                json: {
                    results: [{
                        ...result,
                        filing_type: {
                            code: 'old',
                            name: 'Outdated result'
                        }
                    }],
                    total: 1,
                    corrected_terms: [],
                    stale: false,
                }
            }).catch(() => {});
            delivered = true;
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('eviction');
        await page.getByRole('dialog').getByRole('radio').check();
        const waiting = page.waitForRequest(request => new URL(request.url()).searchParams.get('q') === 'delayed');
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('delayed');
        await expect(page.getByRole('button', {
            name: 'Use this path'
        })).toBeDisabled();
        await waiting;
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('eviction');
        await expect(page.getByRole('dialog').getByRole('radio', {
            name: 'Complaint'
        })).toBeVisible();
        await expect.poll(() => delivered).toBe(true);
        await expect(page.getByRole('dialog')).not.toContainText('Outdated result');
        await expect(page.getByRole('button', {
            name: 'Use this path'
        })).toBeDisabled();
    });

    test('shows unavailable paths without allowing selection, and keeps focus in the modal', async ({
        page
    }) => {
        await mockCourtLists(page, {
            flat: true
        });
        await mockSearch(page, {
            unavailable: true
        });
        await openSavedDraft(page);
        await page.getByRole('button', {
            name: 'Find the right filing code'
        }).click();
        await page.getByRole('searchbox', {
            name: 'Search filing codes'
        }).fill('eviction');
        await expect(page.getByRole('dialog').getByRole('radio')).toBeDisabled();
        await expect(page.getByRole('button', {
            name: 'Use this path'
        })).toBeDisabled();
        for (let i = 0; i < 8; i++) {
            await page.keyboard.press('Tab');
            expect(await page.evaluate(() => document.querySelector('#code-search-dialog').contains(document.activeElement))).toBe(true);
        }
        await page.setViewportSize({
            width: 375,
            height: 740
        });
        expect(await page.getByRole('dialog').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
        const {
            default: AxeBuilder
        } = require('@axe-core/playwright');
        const accessibility = await new AxeBuilder({
            page
        }).include('#code-search-dialog').analyze();
        expect(accessibility.violations).toEqual([]);
    });
});

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