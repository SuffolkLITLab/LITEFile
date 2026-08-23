'use strict';

const assert = require('node:assert/strict');
const score = require('./set_jaccard');

const variables = {
  expected: {
    court: {
      accepted: ['Kane County Circuit Court'],
      confidence: 0.99,
      review_status: 'synthetic_document_ground_truth',
    },
    'case category': {
      accepted: ['Small Claims'],
      confidence: 0.99,
      review_status: 'verified_live',
    },
  },
  abstain: ['case type'],
  allowed_inferences: { 'filing type': ['Complaint'] },
};

const exact = score('{"court name":"Kane County","case category":"Small Claims","filing type":"Complaint"}', {
  vars: variables,
});
assert.equal(exact.pass, true);
assert.equal(exact.score, 1);

const reversedFields = score('{"case category":"Small Claims","court":"Kane County","filing type":"Complaint"}', {
  vars: variables,
});
assert.equal(reversedFields.score, 1, 'JSON field order should not affect a set score');

const parties = {
  expected: {
    'plaintiff or petitioner names': {
      accepted: ['Jamie Ortiz; Riley Ortiz'],
      confidence: 0.99,
      review_status: 'synthetic_document_ground_truth',
    },
  },
  abstain: [],
  allowed_inferences: {},
};
const reversedParties = score('{"plaintiff or petitioner names":["Riley Ortiz","Jamie Ortiz"]}', {
  vars: parties,
});
assert.equal(reversedParties.score, 1, 'multi-valued party fields should be order-independent');

const missingParty = score('{"plaintiff or petitioner names":"Jamie Ortiz"}', { vars: parties });
assert.equal(missingParty.pass, false, 'multi-valued fields still require the complete set');

const reorderedCourtWords = score('{"court":"County Kane"}', { vars: variables });
assert.ok(reorderedCourtWords.score < 1, 'word order inside scalar values remains meaningful');

const hallucinated = score('{"court":"Kane County","case category":"Small Claims","case type":"Contract"}', {
  vars: variables,
});
assert.equal(hallucinated.pass, true);
assert.ok(hallucinated.score < 1);
assert.match(hallucinated.reason, /FP 1/);

const invalid = score('not json', { vars: variables });
assert.equal(invalid.pass, false);
assert.equal(invalid.score, 0);
