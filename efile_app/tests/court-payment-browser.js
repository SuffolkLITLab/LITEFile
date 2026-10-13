/* Opt-in browser flow driven by test_court_payments.py; only external services are stubbed. */
const fs = require("node:fs");
const path = require("node:path");
const {
    chromium,
    expect
} = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

async function main() {
    const config = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
    const browser = await chromium.launch({
        executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined
    });
    try {
        const context = await browser.newContext({
            viewport: {
                width: 1280,
                height: 1000
            }
        });
        await context.addCookies([{
            name: config.cookieName,
            value: config.cookie,
            url: config.baseUrl
        }]);
        const page = await context.newPage();
        fs.mkdirSync(config.evidence, {
            recursive: true
        });
        const shot = name => page.screenshot({
            path: path.join(config.evidence, `${config.scenario}-${name}.png`),
            fullPage: true
        });
        await page.goto(config.baseUrl + config.paymentUrl);
        await page.locator('input[value="pay"][name="paymentIntent"]').check();
        const bank = page.locator('input[name="paymentMethod"][value="bank-1"]');
        const card = page.locator('input[name="paymentMethod"][value="pay-123"]');
        if (!config.scenario.startsWith("stale")) {
            await expect(bank).toHaveCount(0);
            await expect(card).toBeVisible();
            await expect(page.locator("#bank-payment-notice")).toBeVisible();
            await expect(page.locator("#add-payment-method")).toHaveText("Add credit card");
            await expect(page.locator("#paymentSection")).toBeVisible();
            await shot("fees-desktop");
            const accessibility = await new AxeBuilder({
                page
            }).include("#payment-form").withTags(["wcag2a", "wcag2aa"]).analyze();
            expect(accessibility.violations).toEqual([]);
            await page.setViewportSize({
                width: 390,
                height: 844
            });
            await shot("fees-mobile");
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
            await page.setViewportSize({
                width: 1280,
                height: 1000
            });
            if (config.scenario === "unknown") {
                fs.writeFileSync(config.recoverySignal, "recovered");
                await page.locator("#retry-bank-policy").focus();
                await page.keyboard.press("Enter");
                await expect(bank).toBeVisible();
                await expect(bank).toBeChecked();
                await expect(page.locator("#bank-payment-notice")).toBeHidden();
                await expect(page.locator("#paymentSection")).toBeVisible();
                await shot("retry-restored-bank");
            }
        } else {
            await expect(bank).toBeChecked();
            await expect(page.locator("#paymentSection")).toBeVisible();
            await shot("allowed-bank-quote");
        }
        // The stale scenario changes the court rule just after its bank quote.
        // Save is itself guarded, so first demonstrate that a stale form cannot advance.
        if (config.scenario === "stale") {
            await page.locator("#submitButton").click();
            await expect(page).toHaveURL(/payment/);
            await expect(page.getByText("This court does not accept bank payments.", {
                exact: false
            }).first()).toBeVisible();
            await shot("stale-bank-save-blocked");
            await page.locator('input[value="pay"][name="paymentIntent"]').check();
            await expect(card).toBeChecked();
            await expect(bank).toHaveCount(0);
            await expect(page.locator("#paymentSection")).toBeVisible();
        }
        await page.locator("#submitButton").click();
        await expect(page.locator("#confirm-filing")).toBeVisible();
        await shot("review");
        if (config.scenario === "stale-submit") {
            await page.locator("#confirm-filing").check();
            const blocked = page.waitForResponse(r => r.url().includes("/api/submit-final-filing/"));
            let feeRetries = 0;
            page.on("request", request => {
                if (request.url().includes("/api/payment-fees/")) feeRetries++;
            });
            await page.locator("#submitButton").click();
            expect((await blocked).status()).toBe(412);
            await expect(page.locator("#errorMessage")).toContainText("This court does not accept bank payments.");
            expect(feeRetries).toBe(0);
            await shot("submission-blocked");
            await page.getByRole("link", {
                name: "Choose payment method"
            }).click();
            await page.locator('input[value="pay"][name="paymentIntent"]').check();
            await expect(card).toBeChecked();
            await expect(bank).toHaveCount(0);
            await expect(page.locator("#paymentSection")).toBeVisible();
            await page.locator("#submitButton").click();
            await expect(page.locator("#confirm-filing")).toBeVisible();
            await shot("recovered-review");
        }
        await page.locator("#confirm-filing").check();
        const submitted = page.waitForResponse(r => r.url().includes("/api/submit-final-filing/"));
        await page.locator("#submitButton").click();
        const response = await submitted;
        expect(response.status(), await response.text()).toBe(200);
        await expect(page).toHaveURL(/filing-confirmation/);
        await shot("confirmation");
        console.log(`${config.scenario}: real Fees → Review → synthetic submission passed; screenshot evidence saved`);
    } finally {
        await browser.close();
    }
}
main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});