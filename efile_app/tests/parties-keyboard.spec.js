const {
    test,
    expect
} = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const script = fs.readFileSync(path.join(__dirname, '../efile/static/js/parties.js'), 'utf8');

async function openRoles(page) {
    const submissions = [];
    await page.route('http://parties.test/**', async route => {
        if (route.request().method() === 'POST') {
            submissions.push(new URLSearchParams(route.request().postData()));
            await route.fulfill({
                contentType: 'text/html',
                body: '<h1>Role saved</h1>'
            });
            return;
        }
        await route.fulfill({
            contentType: 'text/html',
            body: `<!doctype html>
            <form id="your-role" method="post">
                <fieldset><legend>Your role</legend>
                    <label><input type="radio" name="filer_party_type" value="plaintiff" checked> Plaintiff</label>
                    <label><input type="radio" name="filer_party_type" value="defendant"> Defendant</label>
                    <label><input type="radio" name="filer_party_type" value="intervenor"> Intervenor</label>
                    <label><input type="radio" name="filer_party_type" value="other" id="filer-not-a-party"> Not a party</label>
                </fieldset>
                <fieldset id="filing-for" hidden><input type="email" value="invalid-address"></fieldset>
                <button name="action" value="save_role">Save role</button>
            </form>
            <button form="your-role" name="action" value="continue">Continue</button>
            <script>${script}</script>`
        });
    });
    await page.goto('http://parties.test/roles/');
    return submissions;
}

for (const action of ['Save role', 'Continue']) {
    test(`arrow keys traverse roles without navigating before ${action}`, async ({
        page
    }) => {
        const submissions = await openRoles(page);
        await page.keyboard.press('Tab');
        await expect(page.getByRole('radio', {
            name: 'Plaintiff',
            exact: true
        })).toBeFocused();
        await page.keyboard.press('ArrowDown');
        await expect(page.getByRole('radio', {
            name: 'Defendant',
            exact: true
        })).toBeFocused();
        await page.keyboard.press('ArrowDown');
        const selected = page.getByRole('radio', {
            name: 'Intervenor',
            exact: true
        });
        await expect(selected).toBeFocused();
        await expect(selected).toBeChecked();
        expect(submissions).toHaveLength(0);
        await page.keyboard.press('Tab');
        if (action === 'Continue') await page.keyboard.press('Tab');
        await expect(page.getByRole('button', {
            name: action,
            exact: true
        })).toBeFocused();
        await page.keyboard.press('Enter');
        await expect(page.getByRole('heading', {
            name: 'Role saved'
        })).toBeVisible();
        expect(submissions).toHaveLength(1);
        expect(submissions[0].get('filer_party_type')).toBe('intervenor');
        expect(submissions[0].get('action')).toBe(action === 'Continue' ? 'continue' : 'save_role');
    });
}

test('a pointer click saves the selected role immediately', async ({
    page
}) => {
    const submissions = await openRoles(page);
    await page.getByRole('radio', {
        name: 'Defendant',
        exact: true
    }).click();
    await expect(page.getByRole('heading', {
        name: 'Role saved'
    })).toBeVisible();
    expect(submissions).toHaveLength(1);
    expect(submissions[0].get('filer_party_type')).toBe('defendant');
});