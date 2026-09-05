const {
    test,
    expect
} = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

const script = fs.readFileSync(path.join(__dirname, '../efile/static/js/draft-scope.js'), 'utf8');
const base = 'http://draft-scope.test';
const uploadPath = '/jurisdiction/illinois/upload-documents/';
const reviewPath = '/jurisdiction/illinois/review/';

async function serveWorkflow(context) {
    await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.pathname.startsWith('/api/')) {
            await route.fulfill({
                json: {
                    draft: url.searchParams.get('draft') || route.request().headers()['x-filing-draft'],
                    body: route.request().postData(),
                }
            });
            return;
        }
        const id = Number(url.searchParams.get('draft') || url.searchParams.get('fixture'));
        await route.fulfill({
            contentType: 'text/html',
            body: `
            <!doctype html><html><head>
            <script type="application/json" id="draft-scope">${JSON.stringify({id, paths: [uploadPath, reviewPath]})}</script>
            <script>${script}</script>
            </head><body>
            <a id="next" href="${reviewPath}?return_to=review#details">Next</a>
            <a id="resume" href="${uploadPath}?draft=3">Resume a third filing</a>
            <form id="save" method="post" action="${reviewPath}"><button>Save</button></form>
            <form id="search" method="get" action="${uploadPath}"><button>Search</button></form>
            <form id="start" method="post" action="/jurisdiction/illinois/start-filing/"><button>Start</button></form>
            <div id="dynamic"></div>
            </body></html>
        `
        });
    });
}

for (const sharedSession of [false, true]) {
    test(`draft identity survives concurrent ${sharedSession ? 'tabs' : 'browser contexts'}`, async ({
        browser
    }) => {
        const firstContext = await browser.newContext();
        const secondContext = sharedSession ? firstContext : await browser.newContext();
        try {
            await serveWorkflow(firstContext);
            if (!sharedSession) await serveWorkflow(secondContext);
            const first = await firstContext.newPage();
            const second = await secondContext.newPage();
            await Promise.all([
                first.goto(base + uploadPath + '?fixture=1'),
                second.goto(base + uploadPath + '?fixture=2'),
            ]);
            for (const [page, id] of [
                    [first, '1'],
                    [second, '2']
                ]) {
                expect(new URL(page.url()).searchParams.get('draft')).toBe(id);
                await expect(page.locator('#next')).toHaveAttribute('href', base + reviewPath + '?return_to=review&draft=' + id + '#details');
                await expect(page.locator('#resume')).toHaveAttribute('href', base + uploadPath + '?draft=3');
                await expect(page.locator('#save input[name="draft"]')).toHaveValue(id);
                await expect(page.locator('#search input[name="draft"]')).toHaveValue(id);
                await expect(page.locator('#start')).toHaveAttribute('action', '/jurisdiction/illinois/start-filing/');
                await expect(page.locator('#start input[name="draft"]')).toHaveCount(0);
                const result = await page.evaluate(async () => {
                    const response = await fetch(new Request(location.origin + '/api/save-case-data/', {
                        method: 'POST',
                        body: JSON.stringify({
                            case_title: 'My filing'
                        }),
                    }));
                    return response.json();
                });
                expect(result).toEqual({
                    draft: id,
                    body: JSON.stringify({
                        case_title: 'My filing'
                    })
                });
                const external = await page.evaluate(() => window.withFilingDraft('https://court.example/api/upload', true));
                expect(external).toBe('https://court.example/api/upload');
            }

            // A resume action in the second page cannot change the first.
            await second.locator('#resume').click();
            await first.locator('#next').click();
            expect(new URL(first.url()).searchParams.get('draft')).toBe('1');
            expect(new URL(second.url()).searchParams.get('draft')).toBe('3');
            await first.reload();
            expect(new URL(first.url()).searchParams.get('draft')).toBe('1');
            await first.evaluate(() => {
                const link = document.createElement('a');
                link.id = 'inserted';
                link.href = '/jurisdiction/illinois/upload-documents/';
                document.getElementById('dynamic').append(link);
            });
            await expect(first.locator('#inserted')).toHaveAttribute('href', base + uploadPath + '?draft=1');
            await first.locator('#save button').click();
            expect(new URL(first.url()).searchParams.get('draft')).toBe('1');
        } finally {
            await firstContext.close();
            if (!sharedSession) await secondContext.close();
        }
    });
}