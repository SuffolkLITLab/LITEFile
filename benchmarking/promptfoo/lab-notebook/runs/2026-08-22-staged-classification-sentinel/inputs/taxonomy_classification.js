'use strict';

function parseOutput(output) {
  if (typeof output === 'object' && output !== null) return output;
  const text = String(output || '').trim();
  const fenced = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return JSON.parse(fenced ? fenced[1] : text);
}

module.exports = (output, context) => {
  let result;
  try {
    result = parseOutput(output);
  } catch (error) {
    return { pass: false, score: 0, reason: `Invalid JSON: ${error.message}` };
  }

  const expectedStatus = context.vars.expected_status;
  const statusMatches = result.status === expectedStatus;
  if (expectedStatus === 'abstain') {
    const noSelection = result.selection === null || result.selection === undefined;
    const score = (statusMatches ? 0.7 : 0) + (noSelection ? 0.3 : 0);
    return {
      pass: statusMatches && noSelection,
      score,
      reason: statusMatches && noSelection
        ? 'Correctly abstained without inventing a taxonomy value.'
        : `Expected abstain with no selection; got ${JSON.stringify(result)}`,
    };
  }

  const expected = context.vars.expected_selection;
  const selection = result.selection || {};
  const codeMatches = String(selection.code) === String(expected.code);
  const nameMatches = selection.name === expected.name;
  const score = (statusMatches ? 0.4 : 0) + (codeMatches ? 0.3 : 0) + (nameMatches ? 0.3 : 0);
  return {
    pass: statusMatches && codeMatches && nameMatches,
    score,
    reason: statusMatches && codeMatches && nameMatches
      ? `Selected exact taxonomy value ${expected.code}: ${expected.name}.`
      : `Expected selected ${expected.code}: ${expected.name}; got ${JSON.stringify(result)}`,
  };
};
