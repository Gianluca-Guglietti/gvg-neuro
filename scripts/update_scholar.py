"""Scrape Google Scholar and rewrite the auto-generated block in publications.html.

This script is intended to run from a GitHub Action on a weekly cron schedule
(see .github/workflows/scholar-update.yml). It:

  1. Fetches the Scholar profile.
  2. Sorts the publications in reverse-chronological order.
  3. Rewrites the block between the markers
       <!-- BEGIN: auto-generated publications -->
       <!-- END:   auto-generated publications -->
     in publications.html, leaving everything else untouched.

Run locally with:
    python -m pip install scholarly
    python scripts/update_scholar.py

Important caveats:
  - Google Scholar aggressively rate-limits scrapers. The Action may fail
    intermittently; the workflow is set to non-blocking so the site keeps
    deploying. You can re-run the workflow manually from the Actions tab.
  - When a run does succeed, the workflow commits the updated HTML back to main.
"""

from __future__ import annotations

import datetime as dt
import html
import pathlib
import re
import sys

SCHOLAR_USER_ID = "gM86wgoAAAAJ"  # from https://scholar.google.com/citations?user=gM86wgoAAAAJ
ME_FAMILY_NAME = "Guglietti"      # used to bold my name in the author list

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBS_HTML = REPO_ROOT / "publications.html"
BEGIN_MARKER = "<!-- BEGIN: auto-generated publications. Will be overwritten by scripts/update_scholar.py -->"
END_MARKER = "<!-- END: auto-generated publications -->"


def fetch_publications():
    """Return a list of dicts: {title, authors, venue, year, url}."""
    try:
        from scholarly import scholarly
    except ImportError:
        sys.exit("Install scholarly first: pip install scholarly")

    author = scholarly.search_author_id(SCHOLAR_USER_ID)
    author = scholarly.fill(author, sections=["publications"])

    pubs = []
    for p in author["publications"]:
        bib = p.get("bib", {})
        filled = scholarly.fill(p)
        b = filled.get("bib", {})
        year = b.get("pub_year") or b.get("year") or ""
        try:
            year_int = int(str(year)[:4])
        except (TypeError, ValueError):
            year_int = 0
        pubs.append({
            "title": b.get("title", "").strip(),
            "authors": b.get("author", "").replace(" and ", ", ").strip(),
            "venue": (b.get("journal") or b.get("venue") or b.get("conference") or "").strip(),
            "year": year_int,
            "url": filled.get("pub_url") or filled.get("eprint_url") or "",
        })
    pubs.sort(key=lambda p: (-p["year"], p["title"]))
    return pubs


def bold_me(authors: str) -> str:
    return re.sub(
        rf"([A-Z]\.\s*(?:[A-Z]\.\s*)?{re.escape(ME_FAMILY_NAME)}|{re.escape(ME_FAMILY_NAME)},?\s*[A-Z]\.(?:\s*[A-Z]\.)?)",
        r'<span class="me">\1</span>',
        authors,
    )


def render(pubs) -> str:
    lines = [BEGIN_MARKER, '<h2>Peer-reviewed articles &amp; papers</h2>', '<ol class="entry-list" id="articles">']
    for p in pubs:
        if not p["title"]:
            continue
        title = html.escape(p["title"])
        authors = bold_me(html.escape(p["authors"]))
        venue = html.escape(p["venue"])
        year = p["year"] or ""
        url = p["url"]
        link_html = f'<div class="entry__links"><a href="{html.escape(url)}" target="_blank" rel="noopener">Article</a></div>' if url else ''
        lines.append(
            "<li>"
            f'<span class="entry__year">{year}</span>'
            f'<span class="entry__authors">{authors}</span>'
            f'<span class="entry__title"><strong>{title}.</strong></span>'
            f'<span class="entry__venue">{venue}</span>'
            f'{link_html}'
            "</li>"
        )
    lines.append("</ol>")
    lines.append(f'<p class="muted small">Auto-synced from Google Scholar on {dt.date.today().isoformat()}.</p>')
    lines.append(END_MARKER)
    return "\n".join(lines)


def main() -> int:
    pubs = fetch_publications()
    if not pubs:
        print("No publications returned; aborting without writing.")
        return 1
    new_block = render(pubs)
    text = PUBS_HTML.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
        re.DOTALL,
    )
    if not pattern.search(text):
        print("Markers not found in publications.html — aborting.")
        return 2
    new_text = pattern.sub(new_block, text)
    if new_text != text:
        PUBS_HTML.write_text(new_text, encoding="utf-8")
        print(f"Wrote {len(pubs)} publications.")
    else:
        print("No changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
