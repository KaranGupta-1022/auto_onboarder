# api/pr_ingest.py
"""PR and issue ingestion for Phase 8.5 - index the "why", not just the code.

Walks closed-and-merged PRs from the last N months (Config.PR_LOOKBACK_MONTHS)
for a GitHub repo and assembles one repo_content.md-style document out of
each PR's title, body, review comments (/pulls/{n}/comments, which carry
file/line context) and discussion comments (/issues/{n}/comments), keyed to a
stable synthetic path `pull/{n}` so api/chunking.py's path-based pooling and
metadata plumbing work unchanged.

Reuses scrape_repo's auth headers and 403 handling rather than a second
client - see scrape_repo.HEADERS / RateLimitError / rate_limit_message. The
import is lazy (inside functions, not at module level): scrape_repo imports
crawl4ai at its own module level, which pulls in Playwright and costs ~25s,
so importing api.pr_ingest itself must not pay that cost - only an actual
network call does, same spirit as api/pipeline.py::_fetch_repo_document.

API JSON comments are the primary indexable text. Crawl4AI - the dependency
kept around since Phase 2 specifically for JS-rendered content - is used only
as an opt-in second pass (`enrich_with_crawl4ai=True`) to catch thread
content the API misses; it is off by default so ingestion never depends on a
working headless browser.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import requests

from .chunking import FILE_HEADER
from .config import Config

logger = logging.getLogger(__name__)

PER_PAGE = 50
# Hard cap on pages walked per list call, regardless of month lookback - an
# unbounded walk on a very active repo is exactly what Config.PR_LOOKBACK_MONTHS
# is meant to prevent, but this is the belt-and-suspenders backstop.
MAX_PAGES = 10
# Bounds concurrent per-PR comment fetches so a large PR set doesn't fan out
# into a burst that trips GitHub's rate limiter faster than necessary.
MAX_CONCURRENT_PR_FETCHES = 5


def _parse_ts(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _build_headers():
    import scrape_repo  # noqa: local import, see module docstring
    headers = dict(scrape_repo.HEADERS)
    if Config.GITHUB_TOKEN and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {Config.GITHUB_TOKEN}"
    return headers


async def _get_json(url: str, headers: dict, params: dict | None = None):
    import scrape_repo  # noqa: local import, see module docstring
    response = await asyncio.to_thread(
        requests.get, url, headers=headers, params=params, timeout=30
    )
    if response.status_code == 403:
        raise scrape_repo.RateLimitError(scrape_repo.rate_limit_message(response))
    response.raise_for_status()
    return response.json()


async def list_merged_prs(owner: str, repo: str, months: int | None = None) -> list[dict]:
    """Closed-and-merged PRs from the last `months` months, newest first.

    Paginates state=closed&sort=updated&direction=desc and stops as soon as a
    whole page has no PR updated within the window - correct because
    merged_at <= updated_at, so once a page's updated_at values are all older
    than the cutoff nothing on a later (older) page can be in scope either.
    """
    months = months if months is not None else Config.PR_LOOKBACK_MONTHS
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    headers = _build_headers()
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"

    merged = []
    for page in range(1, MAX_PAGES + 1):
        items = await _get_json(url, headers, params={
            "state": "closed", "sort": "updated", "direction": "desc",
            "per_page": PER_PAGE, "page": page,
        })
        if not items:
            break

        page_has_recent = False
        for pr in items:
            updated_at = _parse_ts(pr.get("updated_at"))
            if updated_at and updated_at >= cutoff:
                page_has_recent = True
            merged_at = _parse_ts(pr.get("merged_at"))
            if merged_at and merged_at >= cutoff:
                merged.append(pr)

        if not page_has_recent or len(items) < PER_PAGE:
            break

    logger.info(
        "Found %d merged PR(s) in the last %d month(s) for %s/%s",
        len(merged), months, owner, repo,
    )
    return merged


async def fetch_pr_comments(owner: str, repo: str, number: int, headers: dict | None = None):
    """Return (review_comments, issue_comments) for one PR number."""
    headers = headers or _build_headers()
    review_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/comments"
    issue_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments"
    review_comments, issue_comments = await asyncio.gather(
        _get_json(review_url, headers, params={"per_page": 100}),
        _get_json(issue_url, headers, params={"per_page": 100}),
    )
    return review_comments, issue_comments


async def crawl_pr_thread(pr_url: str) -> str | None:
    """Second-pass enrichment only: render the PR's HTML conversation thread
    with Crawl4AI and return its markdown, or None on any failure.

    This is where the retained Crawl4AI dependency earns its keep - the
    rendered thread is JS-heavy HTML, unlike the plain-text raw files Phase 2
    correctly moved to `requests`. Never raises: enrichment is additive, and a
    Crawl4AI/Playwright failure must not take down the primary API-comments
    ingestion path above.
    """
    try:
        from crawl4ai import AsyncWebCrawler
    except Exception as e:
        logger.warning("Crawl4AI unavailable, skipping PR thread enrichment for %s: %s", pr_url, e)
        return None

    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=pr_url)
            return result.markdown if result and result.success else None
    except Exception as e:
        logger.warning("Crawl4AI enrichment failed for %s: %s", pr_url, e)
        return None


def format_pr_block(pr: dict, review_comments: list[dict], issue_comments: list[dict],
                     crawled_markdown: str | None = None) -> str:
    """One FILE_HEADER-delimited block for a PR, in the same shape
    chunk_repo_document() expects from a repo file block - path is the
    synthetic `pull/{n}` rather than a real file path.
    """
    number = pr["number"]
    title = pr.get("title") or ""
    body = pr.get("body") or ""

    lines = [f"{FILE_HEADER}pull/{number}", f"TITLE: {title}", "", "BODY:", body or "(no description)"]

    if review_comments:
        lines.append("\nREVIEW COMMENTS:")
        for c in review_comments:
            author = (c.get("user") or {}).get("login", "unknown")
            path = c.get("path", "")
            lines.append(f"- [{author}] ({path}): {c.get('body', '')}")

    if issue_comments:
        lines.append("\nDISCUSSION COMMENTS:")
        for c in issue_comments:
            author = (c.get("user") or {}).get("login", "unknown")
            lines.append(f"- [{author}]: {c.get('body', '')}")

    if crawled_markdown:
        lines.append("\nCRAWLED THREAD (Crawl4AI enrichment):")
        lines.append(crawled_markdown)

    return "\n".join(lines) + "\n\n"


async def build_pr_document(
    owner: str, repo: str, months: int | None = None, enrich_with_crawl4ai: bool = False
) -> tuple[str, dict]:
    """Return (document, extra_metadata_by_path) for every merged PR in scope.

    `document` is one repo_content.md-style string, meant to be chunked by the
    same api.chunking.chunk_repo_document() as everything else.
    `extra_metadata_by_path` maps the synthetic "pull/{n}" path to per-PR
    metadata (pr_number/pr_title/pr_url/source_type) to merge onto matching
    chunks after chunking, since chunk_repo_document() has no way to carry
    caller-supplied per-block metadata through on its own.

    Called from api/pipeline.py::ingest_url() when source_type == "pr" -
    i.e. POST /ingest {"url": "<repo>", "source_type": "pr"}.
    """
    prs = await list_merged_prs(owner, repo, months)
    headers = _build_headers()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PR_FETCHES)

    async def process(pr):
        async with semaphore:
            number = pr["number"]
            try:
                review_comments, issue_comments = await fetch_pr_comments(owner, repo, number, headers)
            except Exception as e:
                logger.warning("Failed to fetch comments for PR #%d: %s", number, e)
                review_comments, issue_comments = [], []
            crawled = await crawl_pr_thread(pr["html_url"]) if enrich_with_crawl4ai else None
            return pr, review_comments, issue_comments, crawled

    results = await asyncio.gather(*(process(pr) for pr in prs))

    document = f"# Pull requests: {owner}/{repo}\n\n"
    metadata_by_path = {}
    for pr, review_comments, issue_comments, crawled in results:
        number = pr["number"]
        path = f"pull/{number}"
        document += format_pr_block(pr, review_comments, issue_comments, crawled)
        metadata_by_path[path] = {
            "pr_number": number,
            "pr_title": pr.get("title") or "",
            "pr_url": pr.get("html_url") or "",
            "source_type": "pr",
        }

    logger.info("Built PR document: %d PR(s), %d chars", len(prs), len(document))
    return document, metadata_by_path
