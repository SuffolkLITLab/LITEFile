'use strict';

const KEY_ALIASES = {
  'court name': 'court',
  'court unit': 'court',
  'court or county': 'court',
  'case number': 'docket number',
  'docker number': 'docket number',
};

const MULTI_VALUE_FIELDS = new Set([
  'plaintiff or petitioner names',
  'defendant or respondent names',
  'other party names',
]);

function normalize(value) {
  return String(value ?? '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('en-US')
    .replace(/\b(circuit court|court department)\b/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function normalizeKey(key) {
  const normalized = String(key).trim().toLocaleLowerCase('en-US');
  return KEY_ALIASES[normalized] || normalized;
}

function parseOutput(output) {
  if (output && typeof output === 'object' && !Array.isArray(output)) return output;
  const text = String(output ?? '').trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  return JSON.parse(text);
}

function normalizedSet(value) {
  const values = Array.isArray(value) ? value : String(value ?? '').split(/[;\n]+/);
  return [...new Set(values.map(normalize).filter(Boolean))].sort();
}

function setsEqual(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function valuesMatch(actual, accepted, key) {
  if (MULTI_VALUE_FIELDS.has(key)) {
    const got = normalizedSet(actual);
    return got.length > 0 && accepted.some((candidate) => setsEqual(got, normalizedSet(candidate)));
  }
  const got = normalize(actual);
  if (!got) return false;
  return accepted.some((candidate) => {
    const wanted = normalize(candidate);
    return got === wanted || (wanted.length >= 8 && (got.includes(wanted) || wanted.includes(got)));
  });
}

module.exports = (output, { vars }) => {
  let parsed;
  try {
    parsed = parseOutput(output);
  } catch (error) {
    return { pass: false, score: 0, reason: `Output is not a JSON object: ${error.message}` };
  }

  const predicted = {};
  for (const [rawKey, value] of Object.entries(parsed)) {
    if (value !== null && value !== '' && !(Array.isArray(value) && value.length === 0)) {
      predicted[normalizeKey(rawKey)] = value;
    }
  }

  const expected = vars.expected || {};
  const abstain = new Set((vars.abstain || []).map(normalizeKey));
  const allowed = Object.fromEntries(
    Object.entries(vars.allowed_inferences || {}).map(([key, value]) => [
      normalizeKey(key),
      Array.isArray(value) ? value : [value],
    ]),
  );
  let truePositive = 0;
  let falsePositive = 0;
  let falseNegative = 0;
  let weightedIntersection = 0;
  let weightedUnion = 0;
  const details = [];

  for (const [rawKey, target] of Object.entries(expected)) {
    const key = normalizeKey(rawKey);
    const confidence = Number(target.confidence ?? 1);
    const present = Object.hasOwn(predicted, key);
    const matched = present && valuesMatch(predicted[key], target.accepted || [], key);
    weightedUnion += confidence;
    if (matched) {
      truePositive += 1;
      weightedIntersection += confidence;
    } else {
      falseNegative += 1;
      if (present) falsePositive += 1;
    }
    details.push({
      pass: matched,
      score: matched ? 1 : 0,
      reason: `${key}: ${matched ? 'matched' : present ? `unexpected value ${JSON.stringify(predicted[key])}` : 'missing'} (${target.review_status}, confidence ${confidence.toFixed(2)})`,
    });
  }

  for (const [key, value] of Object.entries(predicted)) {
    if (Object.hasOwn(expected, key)) continue;
    if (Object.hasOwn(allowed, key) && valuesMatch(value, allowed[key], key)) {
      details.push({ pass: true, score: 1, reason: `${key}: permitted optional inference` });
      continue;
    }
    falsePositive += 1;
    const abstentionViolation = abstain.has(key);
    details.push({
      pass: false,
      score: 0,
      reason: `${key}: ${abstentionViolation ? 'should have been omitted' : 'unexpected field'} ${JSON.stringify(value)}`,
    });
    weightedUnion += abstentionViolation ? 1 : 0.5;
  }

  const denominator = truePositive + falsePositive + falseNegative;
  const jaccard = denominator ? truePositive / denominator : 1;
  const weightedJaccard = weightedUnion ? weightedIntersection / weightedUnion : 1;
  const score = (jaccard + weightedJaccard) / 2;

  return {
    pass: score >= 0.6,
    score,
    reason: `Jaccard ${jaccard.toFixed(3)}; confidence-weighted Jaccard ${weightedJaccard.toFixed(3)}; TP ${truePositive}, FP ${falsePositive}, FN ${falseNegative}`,
    componentResults: details,
  };
};
