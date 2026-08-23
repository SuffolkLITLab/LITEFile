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
    const noSelection = (result.selection === null || result.selection === undefined)
      && (result.selection_ref === null || result.selection_ref === undefined);
    const score = (statusMatches ? 0.7 : 0) + (noSelection ? 0.3 : 0);
    return {
      pass: statusMatches && noSelection,
      score,
      reason: statusMatches && noSelection
        ? 'Correctly abstained without inventing a taxonomy value.'
        : `Expected abstain with no selection; got ${JSON.stringify(result)}`,
    };
  }

  const expectedNames = context.vars.expected_names || [];
  let selection = result.selection || {};
  let selectedByReference = false;
  const referenceMatch = String(result.selection_ref || '').match(/^C(\d{3})$/);
  if (referenceMatch) {
    const candidate = (context.vars.available_candidates || [])[Number(referenceMatch[1]) - 1];
    if (candidate) {
      selection = candidate;
      selectedByReference = true;
    }
  }
  const selectedName = String(selection.name || '').trim();
  const nameMatches = expectedNames.some((name) => String(name).trim() === selectedName);
  const offered = (context.vars.available_candidates || []).find(
    (candidate) => String(candidate.name).trim() === selectedName,
  );
  // The name is the durable gold identity. A current numeric key is checked only
  // for response integrity against this run's frozen candidate list.
  const routeKeyConsistent = Boolean(offered)
    && (selectedByReference || String(offered.code) === String(selection.code));
  const score = Number(((statusMatches ? 0.2 : 0) + (nameMatches ? 0.7 : 0)
    + (routeKeyConsistent ? 0.1 : 0)).toFixed(6));
  return {
    pass: statusMatches && nameMatches && routeKeyConsistent,
    score,
    reason: statusMatches && nameMatches && routeKeyConsistent
      ? `Selected durable taxonomy name ${selectedName}; route key is consistent with this snapshot.`
      : `Expected one of the durable names ${JSON.stringify(expectedNames)} with its offered route key; got ${JSON.stringify(result)}`,
  };
};
