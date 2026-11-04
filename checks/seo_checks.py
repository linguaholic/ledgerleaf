#!/usr/bin/env python3
"""LedgerLeaf SEO quality checks.

Hard rules that must never depend on judgement. Runs on every pull request.

Usage:
    python3 checks/seo_checks.py                    # check every page in site/
    python3 checks/seo_checks.py site/pricing.html  # check only these pages
    python3 checks/seo_checks.py --changed-only     # check nothing (no pages changed)

Exit code 0 = all checks pass, 1 = at least one error.
"""
import datetime
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
BASE_URL = "https://linguaholic.github.io/ledgerleaf/"


class Page(HTMLParser):
    """Collects the few things the checks need from one HTML file."""

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.lang = None
        self.title = ""
        self.jsonld = []           # raw text of each JSON-LD block
        self.alternates = {}       # hreflang -> href
        self.visible_prices = {}   # plan name -> visible text
        self._in_title = False
        self._in_jsonld = False
        self._plan = None
        self._plan_depth = 0
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld = True
            self.jsonld.append("")
        elif tag == "link" and a.get("rel") == "alternate" and "hreflang" in a:
            self.alternates[a["hreflang"]] = a.get("href", "")
        if self._plan:
            self._plan_depth += 1
        elif "data-plan" in a:
            self._plan, self._plan_depth = a["data-plan"], 1
            self.visible_prices[self._plan] = ""

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_jsonld = False
        if self._plan:
            self._plan_depth -= 1
            if self._plan_depth == 0:
                self._plan = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_jsonld:
            self.jsonld[-1] += data
        if self._plan:
            self.visible_prices[self._plan] += data


def url_of(path):
    return BASE_URL + path.relative_to(SITE).as_posix()


def path_of(url):
    if not url.startswith(BASE_URL):
        return None
    return SITE / url[len(BASE_URL):]


def find_offers(node):
    """Yield every schema.org Offer anywhere inside a JSON-LD structure."""
    if isinstance(node, dict):
        if node.get("@type") == "Offer":
            yield node
        for value in node.values():
            yield from find_offers(value)
    elif isinstance(node, list):
        for item in node:
            yield from find_offers(item)


def to_number(text):
    match = re.search(r"\d+(?:[.,]\d{1,2})?", text)
    return float(match.group().replace(",", ".")) if match else None


# --- The five checks. Each returns a list of error messages. ---

def check_jsonld_parses(page):
    errors = []
    for i, block in enumerate(page.jsonld, 1):
        try:
            json.loads(block)
        except json.JSONDecodeError as e:
            errors.append(f"JSON-LD block {i} does not parse: {e.msg} (line {e.lineno} of the block)")
    return errors


def check_prices_match(page):
    errors = []
    for block in page.jsonld:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue  # already reported by check_jsonld_parses
        for offer in find_offers(data):
            name, price = offer.get("name"), offer.get("price")
            if name not in page.visible_prices:
                errors.append(f'Schema Offer "{name}" has no visible price element with data-plan="{name}"')
                continue
            visible = to_number(page.visible_prices[name])
            if visible is None or abs(visible - float(price)) > 0.001:
                errors.append(f'Schema Offer "{name}" says {price} but the page shows "{page.visible_prices[name].strip()}"')
    return errors


def check_lang(page):
    expected = "de" if page.path.relative_to(SITE).parts[0] == "de" else "en"
    actual = (page.lang or "").split("-")[0].lower()
    if actual != expected:
        return [f'<html lang="{page.lang}"> but pages in this folder must be lang="{expected}"']
    return []


def check_hreflang_return(page):
    errors = []
    own_url = url_of(page.path)
    for lang, href in page.alternates.items():
        if href == own_url:
            continue
        target = path_of(href)
        if target is None or not target.exists():
            errors.append(f"hreflang={lang} points to {href}, which is not a page on this site")
            continue
        if own_url not in Page(target).alternates.values():
            errors.append(f"hreflang={lang} points to {target.relative_to(ROOT)}, but that page has no hreflang link back")
    return errors


def check_title_year(page, this_year=None):
    this_year = this_year or datetime.date.today().year
    old = [y for y in re.findall(r"\b(20\d\d)\b", page.title) if int(y) < this_year]
    if old:
        return [f'Title mentions past year {", ".join(old)}: "{page.title.strip()}"']
    return []


CHECKS = [
    ("JSON-LD parses", check_jsonld_parses),
    ("Schema prices match visible prices", check_prices_match),
    ("lang matches page language", check_lang),
    ("hreflang return links exist", check_hreflang_return),
    ("No past years in titles", check_title_year),
]


def main(args):
    # --changed-only: check exactly the listed files, even if the list is empty
    # (used by pull requests, so an unchanged legacy page never blocks a PR).
    changed_only = "--changed-only" in args
    args = [a for a in args if a != "--changed-only"]
    if args or changed_only:
        files = [ROOT / a for a in args if a.endswith(".html")]
    else:
        files = sorted(SITE.rglob("*.html"))
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    failed = 0
    for path in files:
        if not path.exists():
            continue  # file was deleted in this pull request
        page = Page(path)
        rel = path.relative_to(ROOT)
        for name, check in CHECKS:
            for message in check(page):
                failed += 1
                print(f"FAIL  {rel}  [{name}]  {message}")
                if in_actions:
                    # Shows the error inline on the pull request's "Files changed" tab.
                    print(f"::error file={rel},title={name}::{message}")
    print(f"\nChecked {len(files)} page(s): {failed} error(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
