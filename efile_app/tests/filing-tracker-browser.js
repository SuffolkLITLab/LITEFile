const {
    chromium,
    expect
} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

async function main() {
    const config = JSON.parse(process.env.FILING_TRACKER_BROWSER_CONFIG);
    const screenshotDir = fs.mkdtempSync(path.join(os.tmpdir(), 'litefile-filing-tracker-'));
    const browser = await chromium.launch({
        headless: true
    });
    const context = await browser.newContext({
        viewport: {
            width: 390,
            height: 844
        }
    });
    const page = await context.newPage();
    try {
        const detailUrl = (id) => `${config.base}/jurisdiction/illinois/filings/kane/${id}/`;
        const trackerUrl = config.emailContents.match(/https?:\/\/[^\s"'<>]*\/submissions\/[0-9a-f-]{36}\//)?.[0];
        expect(trackerUrl).toBeTruthy();
        await page.goto(trackerUrl);
        await expect(page.getByLabel('Email address')).toBeVisible();
        const submissionId = trackerUrl.match(/\/submissions\/([0-9a-f-]{36})\//)?.[1];
        expect(submissionId).toBeTruthy();
        expect(new URL(page.url()).searchParams.get('next')).toBe(`/submissions/${submissionId}/`);
        await page.reload();
        await page.reload();
        await expect(page.getByLabel('Email address')).toBeVisible();
        await page.getByLabel('Email address').fill('tracker@example.test');
        await page.getByLabel('Password').fill('synthetic-password');
        await page.getByRole('button', {
            name: 'Sign in'
        }).click();
        await expect(page.getByRole('heading', {
            name: 'Your filing'
        })).toBeVisible();
        await expect(page.getByRole('link', {
            name: 'View filing returned-1'
        })).toBeVisible();
        await expect(page.getByRole('link', {
            name: 'View filing accepted-1'
        })).toBeVisible();

        await page.getByRole('link', {
            name: 'View filing returned-1'
        }).click();
        await expect(page.getByRole('status')).toContainText('Returned for changes');
        await expect(page.getByText('Please refile with the case number on page 1.', {
            exact: true
        })).toBeVisible();
        await expect(page.getByRole('link', {
            name: 'Correct and resubmit'
        })).toBeVisible();
        await page.goto(trackerUrl);
        await page.getByRole('link', {
            name: 'View filing accepted-1'
        }).click();
        await expect(page.getByRole('status')).toContainText('Accepted');
        await expect(page.getByRole('link', {
            name: "The court's file-stamped copy"
        })).toHaveAttribute('href', 'https://example.test/stamped.pdf');
        await expect(page.getByRole('link', {
            name: 'Correct and resubmit'
        })).toHaveCount(0);
        await expect(page.locator('.filing-tracker__stages li[aria-current="step"]')).toContainText('Accepted');
        await expect(page.locator('.filing-tracker__stages time')).toHaveCount(2);
        await expect(page.locator('.filing-tracker__stages time').first()).toContainText('CST');
        const acceptedOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
        expect(acceptedOverflow).toBe(false);
        await page.setViewportSize({
            width: 320,
            height: 720
        });
        expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
        await page.setViewportSize({
            width: 390,
            height: 844
        });
        const acceptedA11y = await new AxeBuilder({
            page
        }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
        expect(acceptedA11y.violations.map((item) => `${item.id}: ${item.help} (${item.nodes.map((node) => node.target.join(' ')).join('; ')})`)).toEqual([]);
        await page.screenshot({
            path: path.join(screenshotDir, 'accepted-mobile.png'),
            fullPage: true
        });

        await page.goto(detailUrl('returned-1'));
        await expect(page.getByRole('status')).toContainText('Returned for changes');
        await expect(page.getByText('Please refile with the case number on page 1.', {
            exact: true
        })).toBeVisible();
        await expect(page.getByRole('link', {
            name: 'Correct and resubmit'
        })).toBeVisible();
        await expect(page.locator('.filing-tracker__stages li[aria-current="step"]')).toContainText('Returned for changes');
        await expect(page.getByRole('status')).not.toContainText('Accepted');

        await page.goto(detailUrl('failed-1'));
        await expect(page.getByRole('status')).toContainText('This filing did not go through.');
        await expect(page.getByRole('link', {
            name: 'Correct and resubmit'
        })).toHaveCount(0);
        await expect(page.locator('.filing-tracker__stages')).toHaveCount(0);

        for (const status of config.pendingStatuses) {
            await page.goto(detailUrl(status));
            await expect(page.getByRole('status')).toContainText('No action is needed');
            await expect(page.locator('.filing-tracker__stages')).toContainText('1–2 days');
            await expect(page.locator('.filing-tracker__stages li[aria-current="step"]')).toHaveCount(1);
            await expect(page.getByRole('link', {
                name: 'Correct and resubmit'
            })).toHaveCount(0);
        }

        await page.goto(detailUrl('accepted-1'));
        await page.getByRole('heading', {
            level: 1
        }).click();
        let backFocused = false;
        for (let i = 0; i < 60; i += 1) {
            await page.keyboard.press('Tab');
            backFocused = await page.evaluate(() => document.activeElement?.getAttribute('href')?.includes('filing_statuses'));
            if (backFocused) break;
        }
        expect(backFocused).toBe(true);
        await expect(page.getByRole('link', {
            name: 'Back to my cases'
        })).toBeFocused();
        await page.keyboard.press('Enter');
        await expect(page).toHaveURL(/\/jurisdiction\/illinois\/filing_statuses\/?$/);
        console.log('Synthetic proxy email content → signed-out tracker link → login POST → multi-filing tracker and detail browser checks passed. No email was delivered.');
    } finally {
        await browser.close();
    }
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});