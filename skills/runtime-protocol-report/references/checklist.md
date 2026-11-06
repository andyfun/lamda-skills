# Contract review checklist

Use this when reading `contract.json` or the rendered report. Every item should be answered
with **observed / not observed**, never with a guess.

## Transport

- [ ] One host or several? List every host — a second host usually means a separate auth model.
- [ ] `application/x-www-form-urlencoded`, JSON, or multipart?
- [ ] POST everywhere, or a mix? GET on a business endpoint is often a caching bug.
- [ ] HTTP or HTTPS only? Any plain-HTTP host is a finding on its own.

## Request shape

- [ ] Which fields appear on **every** request (`common_fields`)? Those are the real envelope.
- [ ] Which fields are per-endpoint (`business_fields`)?
- [ ] Is there pagination? Check whether `page`/`size`/`offset` is 1-based and what the
      server does past the last page.
- [ ] Are empty values sent or omitted? That changes the signature.

## Auth

- [ ] Is there a credential, or is the caller identified by an opaque id?
- [ ] If the credential is absent, what binds the session — cookie, header, device id?
- [ ] Does the response echo an identifier that a different caller could supply?
- [ ] Are there endpoints that work with no auth at all? Those are usually bootstrap/init.

## Signature

- [ ] Is there a `sign` (or `sig`/`hash`) field?
- [ ] Is it a hash of the parameters, or an HMAC with a server-issued key?
- [ ] Does it cover the timestamp? If yes, expect an expiry error code.
- [ ] **Is it actually verified?** Replay the same body with a mutated `sign` and compare.

Never report "signature implemented" from the presence of a field alone.

## Response

- [ ] Shape per endpoint, including the empty-list case.
- [ ] Business code envelope: `{code, msg, data}`? Is `data` an object or a single-element list?
- [ ] Do errors come back as HTTP 4xx/5xx, or as HTTP 200 with `code != 0`?
- [ ] Are IDs strings or numbers? Mixed types break clients silently.
- [ ] Any field returned that the UI never shows (raw ID numbers, tokens, e-mails)?

## Hygiene

- [ ] Was the capture made with a test account? If not, treat every payload as PII.
- [ ] Was the report rendered with `--redact`?
- [ ] Is `out/` excluded from version control?
- [ ] Were any capture certificates removed from the device afterwards?

## Reporting

State three things explicitly:

1. **Confirmed** — reproduced from the capture (byte-for-byte where possible).
2. **Observed** — seen in the capture, not independently verified.
3. **Not captured** — endpoint or behaviour that the session never exercised.

"Might be", "probably", and "should" belong in a follow-up task, not in the contract.
