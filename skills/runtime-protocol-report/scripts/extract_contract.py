#!/usr/bin/env python3
"""Extract an API contract matrix from captured HTTP traffic.

Input:
  --input capture.mitm   mitmproxy flow dump (requires mitmproxy)
  --input flows.json     list of HTTP records (no extra dependency)

Output:
  <out>/contract.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse as up
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

SENSITIVE_KEY = re.compile(
    r"(token|cookie|session|secret|passw|pwd|auth|key|sign|device|account|phone|mobile|"
    r"idcard|email|openid|unionid)",
    re.I,
)
PHONE = re.compile(r"\b1[3-9]\d{9}\b")
IDCARD = re.compile(r"\b\d{17}[\dXx]\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
OPAQUE = re.compile(r"^[A-Za-z0-9+/=_-]{32,}$")
SIGN_HINT = re.compile(r"^(sign|signature|sig|md5|token|nonce|ts|timestamp|time)$", re.I)


def mask_text(value: str) -> str:
    value = PHONE.sub("1**********", value)
    value = IDCARD.sub("******************", value)
    value = EMAIL.sub("***@***", value)
    if OPAQUE.match(value):
        return value[:8] + "…(" + str(len(value)) + " chars)"
    return value[:120]


def mask_value(key: str, value):
    if isinstance(value, str) and SENSITIVE_KEY.search(key or ""):
        return "<masked>"
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, list):
        return [mask_value(key, v) for v in value[:3]]
    if isinstance(value, dict):
        return {k: mask_value(k, v) for k, v in list(value.items())[:20]}
    return value


def shape(value, depth: int = 0):
    if depth > 3:
        return "…"
    if isinstance(value, dict):
        return {k: shape(v, depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        return [shape(value[0], depth + 1)] if value else []
    if isinstance(value, str):
        if re.fullmatch(r"-?\d+", value):
            return "int-as-str"
        if value in ("true", "false"):
            return "bool-as-str"
        return "str"
    return type(value).__name__


def parse_body(text: str, content_type: str):
    ct = (content_type or "").lower()
    if not text:
        return None
    if "json" in ct:
        try:
            return json.loads(text)
        except Exception:
            return None
    if "x-www-form-urlencoded" in ct:
        try:
            pairs = up.parse_qsl(text, keep_blank_values=True)
            return dict(pairs)
        except Exception:
            return None
    return None


def records_from_mitm(path: Path):
    try:
        from mitmproxy import http, io
    except ImportError:
        sys.exit(
            "mitmproxy is required to read .mitm dumps. Run:\n"
            "  uvx --from mitmproxy python scripts/extract_contract.py --input <dump> --out <dir>\n"
            "or convert the dump to flows.json first."
        )
    records = []
    with open(path, "rb") as fh:
        for flow in io.FlowReader(fh).stream():
            if not isinstance(flow, http.HTTPFlow):
                continue
            req, resp = flow.request, flow.response
            req_text = req.get_text(strict=False) or ""
            resp_text = (resp.get_text(strict=False) or "")[:200000] if resp else ""
            ctype = req.headers.get("content-type", "")
            resp_ctype = resp.headers.get("content-type", "") if resp else ""
            records.append(
                {
                    "method": req.method,
                    "host": req.pretty_host,
                    "path": req.path,
                    "scheme": req.scheme,
                    "status": resp.status_code if resp else None,
                    "req_headers": dict(req.headers),
                    "req_content_type": ctype,
                    "req_fields": parse_body(req_text, ctype),
                    "resp_json": parse_body(resp_text, resp_ctype),
                    "tls_error": flow.error,
                }
            )
    return records


def records_from_json(path: Path):
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    out = []
    for rec in data:
        url = rec.get("url") or ""
        host = rec.get("host")
        p = rec.get("path")
        if url and (not host or not p):
            parts = up.urlsplit(url if "://" in url else "https://" + url)
            host = host or parts.hostname
            p = p or parts.path + (("?" + parts.query) if parts.query else "")
        headers = rec.get("req_headers") or rec.get("request_headers") or rec.get("headers") or {}
        fields = rec.get("req_fields") or rec.get("request_fields")
        if fields is None and isinstance(rec.get("req_body"), str):
            fields = parse_body(rec["req_body"], rec.get("req_content_type") or headers.get("content-type", ""))
        resp_json = rec.get("resp_json")
        if resp_json is None and isinstance(rec.get("resp_body"), str):
            resp_json = parse_body(rec["resp_body"], rec.get("resp_content_type", ""))
        out.append(
            {
                "method": (rec.get("method") or "GET").upper(),
                "host": host or "",
                "path": p or "/",
                "scheme": rec.get("scheme") or "https",
                "status": rec.get("status") or rec.get("status_code"),
                "req_headers": headers,
                "req_content_type": rec.get("req_content_type") or headers.get("content-type", ""),
                "req_fields": fields,
                "resp_json": resp_json,
                "resp_json_shape": rec.get("resp_json_shape") or rec.get("response_shape"),
                "resp_code": rec.get("resp_code"),
                "resp_msg": rec.get("resp_msg"),
                "tls_error": rec.get("tls_error"),
            }
        )
    return out


def build(records, redact: bool):
    groups = OrderedDict()
    for rec in records:
        key = (rec["host"], rec["path"].split("?")[0])
        groups.setdefault(key, []).append(rec)

    endpoints = []
    all_errors = {}
    for (host, path), items in groups.items():
        methods = sorted({i["method"] for i in items})
        with_fields = [i for i in items if isinstance(i.get("req_fields"), dict) and i["req_fields"]]
        field_sets = [set(i["req_fields"]) for i in with_fields]
        common = set.intersection(*field_sets) if field_sets else set()
        union = set.union(*field_sets) if field_sets else set()

        sample = {}
        for i in with_fields:
            for k, v in i["req_fields"].items():
                sample.setdefault(k, v)

        headers = {}
        for i in items:
            for k, v in (i.get("req_headers") or {}).items():
                headers.setdefault(k.lower(), v)

        shape_src = next((i for i in items if i.get("resp_json_shape")), None)
        resp_shape = shape_src["resp_json_shape"] if shape_src else None
        if resp_shape is None:
            json_rec = next((i for i in items if i.get("resp_json") is not None), None)
            resp_shape = shape(json_rec["resp_json"]) if json_rec else None

        codes = {}
        code_pairs = []
        for i in items:
            code = i.get("resp_code")
            msg = i.get("resp_msg")
            if code is None and isinstance(i.get("resp_json"), dict):
                code, msg = i["resp_json"].get("code"), i["resp_json"].get("msg")
            if code is not None:
                codes[str(code)] = msg
                code_pairs.append((i.get("status"), str(code)))
                if str(code) not in ("0", "200") and i.get("status") == 200:
                    all_errors[str(code)] = msg

        flags = []
        if not union:
            flags.append("no_request_body")
        if "sign" in union:
            flags.append("has_sign")
        if any(SIGN_HINT.match(f) for f in union):
            flags.append("auth_like_field")
        if any(code not in ("0", "200") for _, code in code_pairs):
            flags.append("non_zero_code")
        if any(status == 200 and code not in ("0", "200") for status, code in code_pairs):
            flags.append("error_http_200")

        masked_sample = {k: (mask_value(k, v) if redact else v) for k, v in sample.items()}
        endpoints.append(
            {
                "endpoint": path,
                "url": f"https://{host}{path}",
                "host": host,
                "methods": methods,
                "observed": len(items),
                "common_fields": sorted(common),
                "business_fields": sorted(union - common),
                "request_sample": masked_sample,
                "request_shape": shape(sample) if sample else None,
                "request_content_type": next((i["req_content_type"] for i in items if i.get("req_content_type")), ""),
                "request_headers": {k: (mask_value(k, v) if redact else v) for k, v in headers.items()},
                "response_shape": resp_shape,
                "business_codes": codes,
                "flags": sorted(set(flags)),
                "response_statuses": sorted({i["status"] for i in items if i.get("status") is not None}),
            }
        )

    endpoints.sort(key=lambda e: (e["host"], e["endpoint"]))
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "redacted": redact,
        "flow_count": len(records),
        "hosts": sorted({e["host"] for e in endpoints}),
        "endpoints": endpoints,
        "business_codes": dict(sorted(all_errors.items())),
        "signature_candidates": sorted(
            {f for e in endpoints for f in e["business_fields"] + e["common_fields"] if SIGN_HINT.match(f)}
        ),
    }


def main():
    ap = argparse.ArgumentParser(description="Extract an API contract from captured traffic")
    ap.add_argument("--input", required=True, help="capture.mitm or flows.json")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--no-redact", action="store_true", help="keep raw values (contains PII)")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"input not found: {src}")

    if src.suffix in (".mitm", ".mitmproxy"):
        records = records_from_mitm(src)
    elif src.suffix == ".json":
        records = records_from_json(src)
    else:
        sys.exit("unsupported input: use a .mitm dump or a .json flows file")

    contract = build(records, redact=not args.no_redact)
    contract["source"] = src.name

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2))

    print(f"flows     : {contract['flow_count']}")
    print(f"endpoints : {len(contract['endpoints'])} across {len(contract['hosts'])} host(s)")
    print(f"redacted  : {contract['redacted']}")
    print(f"written   : {out / 'contract.json'}")
    for e in contract["endpoints"][:10]:
        print(f"  {'/'.join(e['methods']):6} {e['endpoint']}")


if __name__ == "__main__":
    main()
