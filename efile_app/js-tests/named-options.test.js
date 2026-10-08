const test = require('node:test');
const assert = require('node:assert/strict');
const {
    resolveNamedOption
} = require('../tests/named-options');

test('named fixtures follow re-created provider codes without selecting a different case type', () => {
    for (const value of ['old-code', 'replacement-code']) {
        const options = [{
            value: 'other-code',
            text: 'Adult adoption'
        }, {
            value,
            text: 'Adoption'
        }];
        assert.equal(resolveNamedOption(options, 'Adoption', 'case types').value, value);
    }
});

test('cosmetic whitespace and extraction markers do not change a choice identity', () => {
    const options = [{
        value: 'current-code',
        text: '  Adoption   *  '
    }];
    assert.equal(resolveNamedOption(options, 'adoption', 'case types').value, 'current-code');
});

test('missing names fail with the available choices instead of silently falling back', () => {
    assert.throws(() => resolveNamedOption([{
        value: 'other',
        text: 'Adult adoption'
    }], 'Adoption', 'case types'), /found 0.*Adult adoption/);
});

test('ambiguous names fail even when the matching choices have different codes', () => {
    assert.throws(() => resolveNamedOption([{
        value: 'one',
        text: 'Adoption'
    }, {
        value: 'two',
        text: 'Adoption *'
    }], 'Adoption', 'case types'), /found 2/);
});