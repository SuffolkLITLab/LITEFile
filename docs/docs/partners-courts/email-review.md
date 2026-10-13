---
id: email-review
title: Review filing emails and tracker guidance
sidebar_label: Emails and tracker review
---

# Review filing emails and tracker guidance

Customized emails are implemented and **disabled pending sender/copy and release
signoff** in the October 13, 2026 snapshot. This page prepares a partner review;
it does not authorize enabling delivery. Release gates remain in
[#157](https://github.com/SuffolkLITLab/LITEFile/issues/157) and sender work in
[EfileProxyServer #375](https://github.com/SuffolkLITLab/EfileProxyServer/issues/375).
The [filing updates contract](https://github.com/SuffolkLITLab/LITEFile/blob/main/docs/developer-notes/filing-updates-contract.md)
is the technical authority, including inspected proxy behavior and limited live
test evidence. It remains an internal repository note.

## Locate and propose the change

Defaults are inherited from `efile_app/efile/static/config/base-case-types.yaml`.
Merge overrides into `efile_app/efile/static/config/states/<jurisdiction>.yaml`:

```yaml
submission_notifications:
  enabled: false                # keep off while copy and delivery are reviewed
  format: html                  # use plain_text for the current SMTP transport
  templates:
    acceptance_subject: "Filing accepted"
    acceptance_contents: >-
      A filing in your submission was accepted by the court.
      Check its status and next steps here: $tracker_url$help_line
```

All eight template members must be nonblank strings in the **merged** configuration.
If any member is missing or blank, the server omits the entire customized template
set; it does not send a partially customized set. Do not mistake proxy-default or
Tyler mail for proof that these overrides worked. The server also discards
browser-supplied email fields.

Implementation: [submission_notifications.py](https://github.com/SuffolkLITLab/LITEFile/blob/main/efile_app/efile/services/submission_notifications.py).
HTML presentation: [filing_notification.html](https://github.com/SuffolkLITLab/LITEFile/blob/main/efile_app/efile/templates/efile/emails/filing_notification.html)
and [filing_progress.html](https://github.com/SuffolkLITLab/LITEFile/blob/main/efile_app/efile/templates/efile/emails/filing_progress.html).

## Review packet for all four categories

These are the inherited subject/body previews before substitution and the HTML
wrapper. For each category, attach its actual rendered preview at 320px and
600px, plus a real inbox/spam capture from the approved test delivery.

| Category and exact fields | Default subject | Body preview / review concern | Partner approval |
| --- | --- | --- | --- |
| Submission: `email_confirmation_subject`, `email_confirmation_contents` | Your filing was submitted | “The e-filing system received a filing in your submission. This is not court acceptance.” Then `$tracker_url$waiver_line$help_line` | Unassigned; pending |
| Accepted: `acceptance_subject`, `acceptance_contents` | Filing accepted | “A filing in your submission was accepted by the court.” Then `$tracker_url$help_line`; avoid saying every filing was accepted | Unassigned; pending |
| Rejected: `rejected_subject`, `rejected_contents` | Filing returned for changes | “A filing in your submission was returned for changes.” Then “Review the clerk’s comments and next steps here: `$tracker_url$help_line`” | Unassigned; pending |
| Neutral/other: `neutral_subject`, `neutral_contents` | Filing update | Known returned display text gets returned guidance; otherwise “A filing in your submission changed status. Check its status and next steps here: `$tracker_url$help_line`”. Unknown status must not invent progress | Unassigned; pending |

For each row record: jurisdiction/court, complete subject and body after both
rendering stages, sender/domain, recipient-selection case, mobile layout and
accessible stage labels, tracker destination/sign-in, court/help contacts,
waiver-request wording (with and without a request), reviewer/date/decision, and
evidence URL. Use the [maintenance register](./maintenance.md); do not include
real filing data or secrets in a shared packet.

## Two substitution stages and delivery ownership

LITEFile fills `$tracker_url`, `$help_line`, and `$waiver_line` with Python
`string.Template` substitution. Use `$$` for a literal dollar sign. The tracker
URL names the local submission UUID; it does not grant access. Help comes from
court contact settings with jurisdiction fallback. Waiver wording appears only
for a selected waiver account or a document whose filing-type name identifies
a waiver, indigency or in-forma-pauperis request. A configured generic fallback
filing type additionally needs explicit waiver provenance (the waiver checklist
item or an explicit-purpose upload). Include a waiver-named document with no
waiver account in the review packet, as well as a generic fallback with and
without that provenance. The line asks the filer to check the court’s decision;
it does not say that a waiver is approved.

The proxy subsequently renders **bodies** with Jinjava. Its variables include
`name`, `court_name`, `case_type`, `case_title`, `status`, `message_text`,
`transaction_id`, optional `message_url`, and confirmation-only `envelope_id`.
There is no callback `filing_id` variable. Proxy subjects pass through unchanged;
do not put `{{ status }}` in a subject expecting rendering. Inserted configuration
values are escaped to prevent them becoming second-stage template expressions.

LITEFile supplies copy; EFSPProxy sends it. The inspected SendGrid path recognizes
HTML bodies by their doctype. The current SMTP path sends plain text, so choose
`format: plain_text` there. There is no multipart fallback. Tyler can independently
send filing notices and account-activation mail. Sender identity is owned by proxy
operations, not a state `text` setting. The legacy proxy sender fallback is not
evidence of an approved partner sender.

Confirmation recipient selection prefers `users[0].email` when that user is the
form filler; otherwise it uses `lead_contact.email`. Callbacks use the recipient
saved on the proxy transaction. Review both self-filing and filing-for-someone-else
cases with the operations owner.

A raw `rejected` callback selects `REJECTED`; `showreturnonreject` can change its
display wording to returned without changing that category. A literal `returned`
callback selects neutral/other. The display variable `status` is not always the
category. One submission may contain several filings with different outcomes;
the tracker lets the authorized filer choose the filing.

## Timing, office hours and stale guidance

Configure `filing_timing.timezone` in State YAML, with exact court overrides under
`court_specific_requirements.<court>.filing_timing`. Missing/invalid zones fall
back to labeled UTC. Event times come from the court response; unavailable or
date-only times do not become invented timestamps or a complete history.

```yaml
# Illustrative structure; replace with a verified local source before display.
filing_timing:
  timezone: America/New_York
  review:
    label: "Partner-reviewed estimate"
    source_url: "https://court.example.org/review-times"
    checked_on: "2026-10-13"
  office_hours:
    label: "Partner-reviewed office hours"
    source_url: "https://court.example.org/contact"
    checked_on: "2026-10-13"
  business_calendar:
    country: US
    subdivision: MA
    review_days: 2
    closed_weekdays: [5, 6]      # Monday is 0
```

Both a label and valid source URL are needed to display review/hours guidance.
`checked_on` is review metadata, not automatic expiry. Exact court settings
replace the whole `review`, `office_hours` or `business_calendar` block for
that key; they do not merge its individual fields. Restate every required field
in a court block. For example, setting only `business_calendar.review_days` at
court level loses the state’s subdivision and holiday-name overrides.
Review source content, timezone/daylight-saving
behavior, `business_calendar` subdivision, observed holidays, closure weekdays,
and any `holiday_names` overrides before release and after court-calendar changes.
Government holidays are advisory; they do not establish court deadlines.

To withdraw a stale estimate, remove its `review` entry at every applicable
scope or override it with `review: {}` at the court; removing only a court override
can expose the statewide estimate again. Apply the same approach to stale hours.
Record why it was withdrawn and confirm no estimate appears in web/email previews.
The email graphic is a send-time snapshot. The linked tracker is live. The
date-sensitive closure note appears in confirmation and is recalculated on the
web; saved callback templates omit it. Neither estimated intervals nor waiver
requests promise court action or approval.

## Enablement and maintenance checklist

- [ ] Partner approves all four categories, local contacts, waiver language and
  sourced timing; record approver, scope/date and next review.
- [ ] Operations approves sender/domain, credentials and authentication; identify
  which events Tyler and proxy mail each handle.
- [ ] Run configuration and notification/timing regressions; render all categories
  at mobile/desktop widths, including literal returned and unknown status.
- [ ] Verify actual acceptance and rejection callbacks, provider errors,
  missing/invalid recipients, duplicate callbacks, failed-send handling and inbox/spam
  presentation. Existing tests/live confirmation do not establish these gates.
- [ ] Verify signed-out tracker → sign-in → correct filing; test another account
  cannot read it, legitimate remote history and mixed-outcome submissions.
- [ ] Record evidence under #157 and the register, then enable only the approved
  jurisdiction/transport. Revert `enabled` to `false` if necessary; templates
  already stored at submission may still be used by later proxy callbacks.

The inspected proxy can acknowledge callbacks despite failed mail and can send
again for repeated callbacks. Do not promise automatic delivery retries or
deduplication. Review delivery failures weekly and copy/contacts before each
release and source change, subject to assigned owner approval.

```bash
# From efile_app; tests use synthetic data, not live delivery.
uv run python manage.py check --fail-level WARNING
uv run pytest -q efile/tests/test_submission_notifications.py efile/tests/test_filing_timing.py
```

For the real proxy body-rendering harness and its prerequisites, use the existing
contract. Enabling emails or sending a live filing is separate release work.
