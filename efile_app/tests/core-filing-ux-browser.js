const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
    chromium
} = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

async function main() {
    const config = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
    const browser = await chromium.launch();
    fs.mkdirSync(config.evidence, {
        recursive: true
    });
    try {
        for (const scenario of config.scenarios) {
            const context = await browser.newContext({
                viewport: {
                    width: 390,
                    height: 844
                }
            });
            await context.addCookies([{
                name: "sessionid",
                value: scenario.cookie,
                url: config.baseUrl
            }]);
            const page = await context.newPage();
            const errors = [];
            page.on("pageerror", error => errors.push(error.message));
            await page.route("**/api/dropdowns/**", route => {
                const endpoint = new URL(route.request().url()).pathname;
                if (endpoint.endsWith("court-selector/")) return route.fulfill({
                    json: {
                        success: true,
                        data: {
                            available: false
                        }
                    }
                });
                let data = [];
                if (endpoint.endsWith("courts/")) data = [{
                    value: "336",
                    text: "Ayer District Court"
                }];
                if (endpoint.endsWith("document-types/")) data = [{
                    value: "public",
                    text: "Public"
                }];
                return route.fulfill({
                    json: {
                        success: true,
                        data
                    }
                });
            });
            await page.route("**/api/suffolk/lookup-case/**", route => route.fulfill({
                json: {
                    success: true,
                    caseInfo: {
                        caseTrackingID: "verified",
                        caseDocketID: scenario.number,
                        caseTitle: "Synthetic case",
                        caseCategoryCode: "civil",
                        caseCategoryName: "Civil",
                        caseTypeCode: "contract",
                        caseTypeName: "Contract"
                    }
                }
            }));
            await page.route("**/api/filing-availability/**", route => route.fulfill({
                json: {
                    success: true,
                    available: true,
                    message: ""
                }
            }));
            try {
                await page.goto(config.baseUrl + scenario.url);
                assert.equal(await page.locator("#new-case-details").isVisible(), false);
                assert.equal(await page.locator("#review-parties").count(), 0);
                await page.locator("#reviewed_extraction").check();
                await page.locator("#proposed-filing-type").fill(scenario.correction);
                await page.getByRole("button", {
                    name: "Continue",
                    exact: true
                }).click();
                await page.waitForURL(/case-lookup/);
                if (scenario.name === "modern") {
                    await page.locator("#inferred-court:not([hidden])").waitFor();
                    assert.equal(await page.locator("#court").inputValue(), "336");
                    await page.getByRole("button", {
                        name: "Change court"
                    }).click();
                }
                await page.locator("#court").selectOption("336");
                await page.getByRole("button", {
                    name: "Find my case"
                }).click();
                await page.waitForURL(/case-confirmation/);
                assert.match(await page.locator(".case-summary").innerText(), /Synthetic case/);
                assert.equal(await page.locator(".case-summary input").count(), 0);
                await page.getByRole("button", {
                    name: "Yes, this is my case"
                }).click();
                await page.waitForURL(/document-checklist/);
                await page.getByRole("link", {
                    name: "Find my filing type",
                    exact: true
                }).click();
                await page.waitForURL(/organize-documents/);
                await page.locator(".filing-type option[value='motion']").waitFor({
                    state: "attached"
                });
                if (scenario.name === "modern") {
                    assert.match(await page.locator(".filing-suggestion-message").innerText(), /not an exact match/);
                    assert.equal(await page.locator(".filing-type").inputValue(), "");
                } else {
                    assert.equal(await page.locator(".filing-type").inputValue(), "motion");
                }
                await page.locator(".filing-search").fill("motion");
                await page.locator(".filing-search-results").getByRole("button", {
                    name: "Motion",
                    exact: true
                }).click();
                await page.locator(".document-type-options input[value='public']").check();
                const a11y = await new AxeBuilder({
                    page
                }).include(".workflow-card").analyze();
                assert.deepEqual(a11y.violations.map(item => item.id), []);
                assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
                await page.screenshot({
                    path: path.join(config.evidence, `${scenario.name}.png`),
                    fullPage: true
                });
                const saved = page.waitForResponse(response => response.url().includes("organize-documents") && response.request().method() === "POST");
                await page.getByRole("button", {
                    name: "Save and continue"
                }).click();
                assert.equal((await saved).status(), 200);
                assert.deepEqual(errors, []);
                console.log(`${scenario.name} passed`);
            } catch (error) {
                await page.screenshot({
                    path: path.join(config.evidence, `${scenario.name}-failure.png`),
                    fullPage: true
                });
                throw error;
            } finally {
                await context.close();
            }
        }
    } finally {
        await browser.close();
    }
}
main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});