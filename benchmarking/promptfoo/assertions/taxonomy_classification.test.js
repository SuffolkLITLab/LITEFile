'use strict';

const assert = require('node:assert/strict');
const score = require('./taxonomy_classification');

let result = score(
  '{"status":"selected","selection":{"code":"7421","name":"Small Claims"}}',
  {
    vars: {
      expected_status: 'selected',
      expected_names: ['Small Claims'],
      available_candidates: [{ code: '7421', name: 'Small Claims' }],
    },
  },
);
assert.equal(result.pass, true);
assert.equal(result.score, 1);

result = score(
  '{"status":"selected","selection":{"code":"297718","name":"Contract - Business Dispute"}}',
  {
    vars: {
      expected_status: 'selected',
      expected_names: ['Contract - Other', 'Contract - Business Dispute'],
      available_candidates: [
        { code: '164987', name: 'Contract - Other' },
        { code: '297718', name: 'Contract - Business Dispute' },
      ],
    },
  },
);
assert.equal(result.pass, true);
assert.equal(result.score, 1);

result = score('{"status":"abstain","selection":null}', {
  vars: { expected_status: 'abstain', expected_selection: null },
});
assert.equal(result.pass, true);
assert.equal(result.score, 1);

result = score('{"status":"selected","selection":{"code":"7","name":"Civil"}}', {
  vars: {
    expected_status: 'selected',
    expected_names: ['Small Claims'],
    available_candidates: [{ code: '7', name: 'Civil' }, { code: '7421', name: 'Small Claims' }],
  },
});
assert.equal(result.pass, false);
assert.ok(result.score < 1);

result = score('{"status":"selected","selection":{"code":"old-key","name":"Small Claims"}}', {
  vars: {
    expected_status: 'selected',
    expected_names: ['Small Claims'],
    available_candidates: [{ code: 'current-key', name: 'Small Claims' }],
  },
});
assert.equal(result.pass, false);
assert.equal(result.score, 0.9);

result = score('{"status":"selected","selection_ref":"C002"}', {
  vars: {
    expected_status: 'selected',
    expected_names: ['Small Claims'],
    available_candidates: [{ code: '7', name: 'Civil' }, { code: 'current-key', name: 'Small Claims' }],
  },
});
assert.equal(result.pass, true);
assert.equal(result.score, 1);

console.log('taxonomy classification scorer tests passed');
