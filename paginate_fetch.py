#!/usr/bin/env python3
"""
paginate_fetch.py

Fetch up to max_items from a paginated REST API and write both JSON and CSV outputs.

Usage:
  export API_KEY="..." && python paginate_fetch.py \
    --url "https://api.example.com/items" \
    --max 500 \
    --per-page 100 \
    --out-prefix "export_1" \
    --params "region=us&status=active"

Notes:
- Adjust items_from_response() to match your API's JSON shape if necessary.
- For APIs that accept pagination via cursor, replace page/per_page loop with cursor logic.
"""
import argparse
import os
import requests
import csv
import json
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

def fetch_page(url: str, params: dict, headers: dict, timeout: int = 30) -> Any:
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    # assume JSON response
    return resp.json()

def items_from_response(resp_json: Any) -> List[Dict[str, Any]]:
    """
    Customize this to match your API response structure.

    Common shapes:
    - {"data": [ ... ] }  -> return resp_json["data"]
    - {"items": [ ... ] } -> return resp_json["items"]
    - [ {...}, {...} ]    -> return resp_json
    """
    if isinstance(resp_json, list):
        return resp_json
    if isinstance(resp_json, dict):
        # common keys
        for k in ("data", "items", "results"):
            if k in resp_json and isinstance(resp_json[k], list):
                return resp_json[k]
        # fallback: look for the first list value
        for v in resp_json.values():
            if isinstance(v, list):
                return v
    raise RuntimeError("Unrecognized response format; update items_from_response()")

def write_json(path: str, items: List[Dict[str, Any]]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def write_csv(path: str, items: List[Dict[str, Any]]):
    if not items:
        open(path, "w").close()
        return
    # build union of all keys across items to avoid missing columns
    keys = sorted({k for it in items for k in it.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for it in items:
            # flatten nested dicts naively by JSON-encoding them
            row = {}
            for k in keys:
                v = it.get(k, "")
                if isinstance(v, (dict, list)):
                    row[k] = json.dumps(v, ensure_ascii=False)
                else:
                    row[k] = v
            writer.writerow(row)

def merge_url_and_params(base_url: str, extra_params: Optional[dict]) -> (str, dict):
    # allow --url to include query params; merge with extra_params
    parsed = urlparse(base_url)
    existing = dict(parse_qsl(parsed.query))
    merged = existing.copy()
    if extra_params:
        merged.update({k: str(v) for k, v in extra_params.items()})
    # rebuild url without query
    url_no_query = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, "", parsed.fragment))
    return url_no_query, merged

def main():
    p = argparse.ArgumentParser(description="Fetch up to max items from a paginated API and write CSV + JSON")
    p.add_argument("--url", required=True, help="Base API url, e.g. https://api.example.com/items")
    p.add_argument("--max", type=int, default=500, help="Maximum items to fetch")
    p.add_argument("--per-page", type=int, default=100, help="Items per page (API max recommended)")
    p.add_argument("--out-prefix", default="export", help="Prefix for output files (export.json / export.csv)")
    p.add_argument("--api-key", default=os.environ.get("API_KEY"), help="API key or token (Bearer)")
    p.add_argument("--params", default="", help="Extra query params encoded like key=val&key2=val2")
    p.add_argument("--page-param", default="page", help="Page parameter name (default: page)")
    p.add_argument("--per-page-param", default="per_page", help="Per-page parameter name (default: per_page)")
    args = p.parse_args()

    headers = {}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    # parse extra params
    extra_params = dict(parse_qsl(args.params)) if args.params else {}

    base_url, initial_params = merge_url_and_params(args.url, extra_params)

    collected: List[Dict[str, Any]] = []
    page = 1
    while len(collected) < args.max:
        params = initial_params.copy()
        params[args.page_param] = page
        params[args.per_page_param] = args.per_page
        print(f"Fetching page {page} (params={{params}}) ...", flush=True)
        resp_json = fetch_page(base_url, params, headers)
        page_items = items_from_response(resp_json)
        if not page_items:
            print("No more items returned by API.")
            break
        collected.extend(page_items)
        if len(page_items) < args.per_page:
            # last page
            break
        page += 1

    collected = collected[: args.max]
    json_path = f"{{args.out_prefix}}.json"
    csv_path = f"{{args.out_prefix}}.csv"
    print(f"Writing {{len(collected)}} items to {{json_path}} and {{csv_path}}")
    write_json(json_path, collected)
    write_csv(csv_path, collected)
    print("Done.")

if __name__ == "__main__":
    main()