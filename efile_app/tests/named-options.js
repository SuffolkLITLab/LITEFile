// Provider codes are transport values, not stable identities for E2E fixtures.
function choiceName(text) {
    const normalized = String(text).trim().replace(/\s+/g, ' ').toLowerCase();
    return normalized.endsWith(' *') ? normalized.slice(0, -2) : normalized;
}

function resolveNamedOption(options, name, context) {
    const available = options.filter(option => option.value && !option.disabled);
    const matches = available.filter(option => choiceName(option.text) === choiceName(name));
    if (matches.length !== 1) {
        throw new Error(`Expected one choice named "${name}" in ${context}, found ${matches.length}. Available names: ${available.map(option => option.text).join('; ')}`);
    }
    return matches[0];
}

module.exports = {
    resolveNamedOption
};