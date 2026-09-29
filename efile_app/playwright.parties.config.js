// Native keyboard and pointer checks; no server or court account is needed.
const {
    defineConfig
} = require('@playwright/test');

module.exports = defineConfig({
    testDir: './tests',
    testMatch: 'parties-keyboard.spec.js',
    forbidOnly: !!process.env.CI,
    timeout: 30000,
    use: {
        browserName: 'chromium',
        headless: true
    },
});