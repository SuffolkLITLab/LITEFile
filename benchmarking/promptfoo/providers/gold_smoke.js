'use strict';

module.exports = class GoldSmokeProvider {
  id() {
    return 'gold-smoke';
  }

  async callApi(prompt, context) {
    if (String(prompt).includes('file://../synthetic/')) {
      return { error: 'PDF variable was not resolved to document text' };
    }
    const expected = context.vars.expected || {};
    const output = Object.fromEntries(
      Object.entries(expected).map(([key, target]) => [key, target.accepted[0]]),
    );
    return { output: JSON.stringify(output) };
  }
};
