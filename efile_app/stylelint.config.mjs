export default {
    plugins: ['stylelint-plugin-defensive-css'],
    rules: {
        // Keep this deliberately small at first: these rules cover failures
        // Axe cannot see from rendered DOM alone.
        'defensive-css/require-forced-colors-focus': [true, { severity: 'error' }],
        'defensive-css/require-prefers-reduced-motion': [true, { severity: 'warning' }],
        'defensive-css/no-accidental-hover': [true, { severity: 'warning' }],
    },
};
