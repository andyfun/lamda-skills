---
name: runtime-protocol-report
description: Turn captured HTTP/TLS traffic into an API contract matrix and a standalone report — method, path, headers, request fields, signature scheme, response schema and error codes. Use when you need to verify what an app actually sends at runtime, compare a captured contract against static extraction, document an undocumented API, or produce protocol evidence for a test report. Works from a mitmproxy dump or an already-extracted flows JSON; no phone or AI model required.
---

# Runtime Protocol Report

Turn "what the app actually sends" into a readable contract, without hand-copying
requests into a document.

Scope: **read-only analysis of captured traffic**. This skill never drives a device and
never sends requests by itself.

## 1. Inputs

Either of these:

| Input | How you get it |
|---|---|
| `.mitm` flow dump | `mitmdump --mode socks5 -w capture.mitm` (or `--mode regular`, transparent, …) |
| `flows.json` | output of `scripts/extract_contract.py`, or any list of HTTP records |

`flows.json` records are dicts. Both key styles are accepted:

```json
{
  "method": "POST",
  "url": "https://api.example.com/v1/profile",
  "status": 200,
  "req_headers": {"content-type": "application/x-www-form-urlencoded"},
  "req_fields": {"time": "1700000000", "sign": "ab12..."},
  "resp_json_shape": {"code": "int", "data": {"uid": "int"}},
  "resp_code": 0
}
```

## 2. Extract

```bash
# from a mitmproxy dump
uvx --from mitmproxy python scripts/extract_contract.py \
  --input capture.mitm --out out/

# from an existing flows.json (no mitmproxy needed)
python3 scripts/extract_contract.py --input flows.json --out out/
```

Produces `out/contract.json`:

- one entry per `(host, path)`, with the observed method(s)
- union of request field names, split into `common_fields` (present on every call) and
  `business_fields`
- response shape per endpoint, plus all observed `{code, msg}` pairs
- header set, with sensitive headers flagged
- `signature_candidates`: keys that look like signing/auth material (`sign`, `token`,
  `nonce`, `timestamp`, …)
- `flags`: per endpoint, e.g. `no_body`, `auth_like_field`, `error_http_200` (HTTP 200
  carrying a non-zero business code)

### Redaction

Default is `--redact`, which masks values that look like PII or credentials before
anything is written:

- 11-digit phone numbers, 18-digit ID numbers, e-mails
- values of keys matching `token|cookie|session|secret|key|password|device|account|sign`
- long opaque blobs (base64 / hex ≥ 32 chars) are truncated

`--no-redact` keeps raw values. **Any output produced with `--no-redact` contains PII and
must stay local** — do not commit it, do not paste it into a ticket.

## 3. Render

```bash
python3 scripts/render_contract.py --contract out/contract.json --out out/ \
  --title "Runtime protocol" --subtitle "captured 2026-01-01"
```

Produces:

```
out/contract.md      ← paste into a PR / doc
out/index.html       ← dark, self-contained; one card per endpoint
```

`index.html` has no external assets, so it can be opened from disk or served with
`python3 -m http.server`.

## 4. Read the result

When reviewing the matrix, check in this order:

1. **Transport** — form-encoded or JSON, POST or GET, one host or several.
2. **Common fields** — what every request carries (time, device id, version, sign).
3. **Auth** — is there a real credential, or is the caller bound by an opaque id?
4. **Signature** — presence of a `sign` field does not mean it is verified; test it.
5. **Response shape** — the same endpoint returning two shapes is a compatibility bug.
6. **Error model** — business codes inside HTTP 200 hide failures from gateways.

Report what was observed and what was not. "Not captured" is a finding, not a gap to
fill by guessing.

## 5. Verifying a signature (optional)

A captured `sign` can often be reproduced once the algorithm is known. Do it in a scratch
directory, against read-only endpoints only:

```bash
# only replay endpoints that do not mutate state
curl -s -X POST "$BASE/path" -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-raw "$BODY"
```

Record, for each attempt: request, response code, and message. A signature that is
accepted for a mutated body means it is not enforced — that is a contract fact worth
reporting.

Never replay write, payment, logout or account-state endpoints from a report script.

## 6. Boundaries

- No device control, no request generation beyond read-only replay.
- No assumptions about algorithms: a signature is "confirmed" only when a recomputation
  matches a captured value byte for byte.
- Traffic captured from a real account is personal data. Keep `out/` out of git, and use
  `--redact` unless you are debugging locally.
- This skill is standalone. To attach a contract to a UI-evidence report, link the
  generated `contract.md` from that report instead of copying raw payloads.

## Resources

- `scripts/extract_contract.py` — flow dump → `contract.json` (optional mitmproxy import)
- `scripts/render_contract.py` — `contract.json` → `contract.md` + `index.html`
- `references/checklist.md` — what to look for in a captured contract
