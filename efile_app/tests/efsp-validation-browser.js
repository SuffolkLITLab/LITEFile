// Run with: node tests/efsp-validation-browser.js
const {
    chromium
} = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const staticDirectory = path.join(__dirname, '../efile/static/js');
const assert = require('node:assert/strict');
const samples = require('../efile/tests/fixtures/efsp_validation_2026-10-02.json');
const phoneRule = samples.responses.find(row => row.path === 'massachusetts/codes/courts/0705:LA/datafields/PartyPhone').body;
(async () => {
    const browser = await chromium.launch({
        headless: true
    });
    const page = await browser.newPage();
    await page.route('https://test.local/**', async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/party') return route.fulfill({
            contentType: 'text/html',
            body: html
        });
        const name = url.pathname.split('/').pop();
        return route.fulfill({
            contentType: 'application/javascript',
            body: fs.readFileSync(path.join(staticDirectory, name), 'utf8')
        });
    });
    const rules = {
        first_name: {
            regex: '^.{0,50}$',
            message: 'First name must be 50 characters or fewer.'
        },
        phone: {
            regex: phoneRule.regularexpression.replaceAll("\\s", "[ \\t\\n\\x0B\\f\\r]"),
            message: 'Enter ten digits.'
        }
    };
    const html = `<!doctype html><html lang="en"><body><form id="party-details-form"><label><input type="radio" name="party_kind" value="person" checked>Person</label><label><input type="radio" name="party_kind" value="organization">Organization</label><section class="person-fields"><label>First name<input id="id_first_name" name="first_name" value="${'a'.repeat(51)}"><span id="error_first_name" hidden></span></label><input name="last_name" value="Lee"></section><section class="organization-fields" hidden><input name="organization_name" value="Legal Aid"></section><input id="id_phone" name="phone" value="123"><span id="error_phone" hidden></span><input id="add-party-address" type="checkbox"><section id="party-address-fields" hidden><input id="id_address_line_1" name="address_line_1"><input id="id_city" name="city"><select id="id_state" name="state"><option value="">Select a state</option><option value="MA">Massachusetts</option></select><input id="id_zip_code" name="zip_code"></section><button>Save</button></form><ul id="links"></ul><script id="party-validation-rules" type="application/json">${JSON.stringify(rules)}</script><script>window.apiUtils={getCurrentJurisdiction:()=>"massachusetts",getCSRFToken:()=>""};window.gettext=s=>s;</script><script src="/party-details.js"></script><script src="/party-validation.js"></script><script src="/filing-error-actions.js"></script></body></html>`;
    await page.goto('https://test.local/party?focus=state');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'id_state');
    assert.equal(await page.locator('#party-address-fields').evaluate(e => e.hidden), false);
    assert.equal(await page.locator('#id_first_name').evaluate(e => e.validity.customError), true);
    assert.equal(await page.locator('#id_phone').evaluate(e => e.validity.customError), true);
    await page.locator('#id_phone').fill('(123) 456-7890');
    assert.equal(await page.locator('#id_phone').evaluate(e => e.validity.valid), true);
    await page.locator('input[value="organization"]').check();
    assert.equal(await page.locator('#id_first_name').evaluate(e => e.validity.customError), false);
    await page.evaluate(() => window.FilingErrorActions.render('links', [{
        url: '/jurisdiction/massachusetts/party-details/?draft=8&party=3&focus=phone&return_to=review',
        label: 'Edit <script>bad</script>',
        message: '<img src=x onerror=alert(1)>'
    }, {
        url: 'https://evil.example',
        label: 'unsafe'
    }]));
    assert.equal(await page.locator('#links a').count(), 1);
    assert.equal(await page.locator('#links img').count(), 0);
    assert.equal(await page.locator('#links script').count(), 0);
    assert.equal(await page.evaluate(() => location.pathname), '/party');
    console.log('Browser checks passed: field focus, optional address reveal, validation, organization switch, safe clickable error links.');
    await browser.close();
})().catch(error => {
    console.error(error);
    process.exit(1);
});