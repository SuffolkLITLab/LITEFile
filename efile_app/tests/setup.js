/**
 * Playwright Test Setup File
 * 
 * This file contains global setup configuration for Playwright tests.
 * It loads environment variables and validates required test credentials.
 */

require('dotenv').config({
    path:


        '.env'
});







async function globalSetup(_config) {
    // Validate required environment variables
    const requiredEnvVars = ['TESTS_TYLER_USERNAME', 'TESTS_TYLER_PASSWORD'];
    const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);

    if (missingVars.length > 0) {
        throw new Error(`Missing required environment variables: ${missingVars.join(', ')}. Please set them in .env file`);
    }

    console.log('✓ Environment variables loaded successfully');
    console.log(`✓ Test base URL: ${process.env.E2E_TEST_BASE_URL || 'http://localhost:8000'}`);
    console.log(`✓ Test username: ${process.env.TESTS_TYLER_USERNAME}`);

    // You can add more global setup here:
    // - Database setup/cleanup
    // - Authentication token generation
    // - Test data preparation
}

module.exports = globalSetup;