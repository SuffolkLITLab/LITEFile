const {
    test,
    expect
} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const fs = require('fs');

const findings = [];
const blockingImpacts = new Set(['critical', 'serious']);

// These are stable URLs, not workflow transitions: a change to the order of
// the filing flow should not require changing accessibility coverage.
const publicScreens = [
    ['choose jurisdiction', '/choose-jurisdiction'],
    ['about', '/about/'],
    ['terms of service', '/terms-of-service/'],
    ['sign in', '/jurisdiction/illinois/login/'],
    ['register', '/jurisdiction/illinois/register/'],
    ['password reset', '/jurisdiction/illinois/password_reset/'],
];
const signedInScreens = [
    ['filing options', '/jurisdiction/illinois/options/'],
    ['choose filing path', '/jurisdiction/illinois/filing-path/'],
    ['upload documents', '/jurisdiction/illinois/upload-documents/'],
    ['confirm filing', '/jurisdiction/illinois/extraction-review/'],
    ['check documents', '/jurisdiction/illinois/document-checklist/'],
    ['organize documents', '/jurisdiction/illinois/organize-documents/'],
    ['your information', '/jurisdiction/illinois/your-information/'],
    ['people', '/jurisdiction/illinois/parties/'],
    ['payment', '/jurisdiction/illinois/payment/'],
    ['review', '/jurisdiction/illinois/review/'],
    ['filing plans', '/jurisdiction/illinois/plans/'],
    ['my drafts', '/jurisdiction/illinois/my-drafts/'],
];

async function audit(page, label, scope) {
    await page.waitForLoadState('networkidle');
    const results = await new AxeBuilder({
            page
        })
        .withTags(['wcag2a', 'wcag2aa'])
        .include(scope || 'body')
        .analyze();
    for (const violation of results.violations) {
        findings.push({
            label,
            impact: violation.impact,
            rule: violation.id,
            help: violation.help,
            helpUrl: violation.helpUrl,
            targets: violation.nodes.map(node => node.target),
        });
    }
}

function routePattern(url) {
    return new RegExp(`${url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/?$`);
}

for (const [label, url] of publicScreens) {
    test(`accessible: ${label}`, async ({
        page
    }) => {
        await page.goto(url, {
            waitUntil: 'networkidle'
        });
        await expect(page).toHaveURL(routePattern(url));
        await expect(page.locator('main, [role="main"]').first()).toBeVisible();
        await audit(page, label);
    });
}

for (const [label, url] of signedInScreens) {
    test(`accessible: ${label}`, async ({
        page
    }) => {
        await page.goto(url, {
            waitUntil: 'networkidle'
        });
        await expect(page).toHaveURL(routePattern(url));
        await expect(page.locator('main, [role="main"]').first()).toBeVisible();
        await audit(page, label);
    });
}

test('accessible: claim-party dialog', async ({
    page
}) => {
    await page.goto('/jurisdiction/illinois/parties/', {
        waitUntil: 'networkidle'
    });
    const dialog = page.locator('#claim-party-dialog');
    await expect(dialog).toBeAttached();
    // Dialog copy and its triggering suggestion vary with the filing data, so
    // open the native dialog independently of either to keep this check stable.
    await dialog.evaluate(element => element.showModal());
    await expect(dialog).toBeVisible();
    await audit(page, 'claim-party dialog', '#claim-party-dialog');
    await dialog.evaluate(element => element.close());
    await expect(dialog).toBeHidden();
});

test.afterAll(() => {
    const report = {
        findings
    };
    fs.mkdirSync('test-results', {
        recursive: true
    });
    fs.writeFileSync('test-results/axe-results.json', JSON.stringify(report, null, 2));
    const blocking = findings.filter(finding => blockingImpacts.has(finding.impact));
    if (blocking.length) {
        throw new Error(`${blocking.length} serious or critical Axe accessibility finding(s); see test-results/axe-results.json.`);
    }
});