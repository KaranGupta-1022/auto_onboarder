import sys

# Crawl4AI's rich-based logger prints U+2192 at startup. When stdout is a pipe,
# a redirect, CI, or a subprocess call from pipeline.py, Python falls back to the
# ANSI codepage (cp1252 on Windows) and the whole scrape dies before fetching a
# single file. Force UTF-8 here so behaviour never depends on the caller.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import os
import time

import requests

# Kept available for the future PR/issue HTML path, where the discussion thread
# is JS-rendered and a headless browser genuinely earns its keep. Deliberately
# NOT used for raw file fetches below - raw.githubusercontent.com serves plain
# text, so the browser adds nothing but runtime.
from crawl4ai import *  # noqa: F401,F403

# Applied before anything is FETCHED. Lockfiles and vendored trees are the bulk
# of a typical repo by bytes and are pure noise once embedded: package-lock.json
# alone was 72% of the previous corpus, downloaded in full only to be discarded
# at embed time.
#
# Shared with the chunker rather than duplicated. The local copy this replaces
# was a substring test, which silently dropped real source - a bare 'dist'
# pattern matches distance.py and 'bin' matches combine.ts and binary_search.py,
# and because this filter runs at fetch time those files were never downloaded at
# all, so nothing downstream could recover them. api/chunking.is_ignored matches
# structurally (exact filename, whole path segment, or suffix) and covers every
# pattern that used to live here plus caches, generated code and build output.
#
# The extension allowlist lives there too - it is the complement of the same
# filter, and splitting the pair across two files is how they drift apart.
#
# Resolves because this script is run from the repo root; `api/` has no
# __init__.py and relies on namespace packages.
from api.chunking import ALLOWED_EXTENSIONS, is_ignored  # noqa: E402

MAX_CONCURRENT_FETCHES = 10

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# Unauthenticated: 60 req/hr, and a recursive walk spends one request per
# directory. Authenticated: 5,000 req/hr.
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


class RateLimitError(RuntimeError):
    """Raised loudly on a 403 so a truncated scrape is never mistaken for a complete one."""


def rate_limit_message(response) -> str:
    remaining = response.headers.get("X-RateLimit-Remaining")
    reset = response.headers.get("X-RateLimit-Reset")
    detail = f"GitHub returned 403 (remaining={remaining})."
    if reset:
        try:
            reset_ts = int(reset)
            wait_s = max(0, reset_ts - int(time.time()))
            reset_at = time.strftime("%H:%M:%S", time.localtime(reset_ts))
            detail += f" Rate limit resets at {reset_at} (in {wait_s // 60}m {wait_s % 60}s)."
        except ValueError:
            detail += f" Rate limit resets at {reset}."
    if not GITHUB_TOKEN:
        detail += " Set GITHUB_TOKEN to raise the limit from 60 to 5000 requests/hour."
    return detail


async def main():
    url = input("Enter the Github repo URL to scrape: ").rstrip('/').split('/tree')[0]
    blocks = url.strip('/').split('/')
    owner, repo = blocks[-2], blocks[-1]

    important_files = []  # Stores (download_url, full_path)
    skipped = []

    async def fetch_all_files(path=""):
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        response = await asyncio.to_thread(requests.get, api_url, headers=HEADERS, timeout=30)

        # A 403 here means rate limiting. The old code returned silently, which
        # truncated an entire subtree and produced a quietly incomplete corpus.
        if response.status_code == 403:
            raise RateLimitError(rate_limit_message(response))
        if response.status_code != 200:
            print(
                f"WARNING: skipping '{path or '/'}' - GitHub returned "
                f"{response.status_code} {response.reason}"
            )
            return

        items = response.json()
        if isinstance(items, dict):  # a file path was passed instead of a directory
            items = [items]

        subdirs = []
        for item in items:
            full_path = item['path']
            if is_ignored(full_path):
                skipped.append(full_path)
                continue
            if item['type'] == 'file':
                if item['name'].endswith(ALLOWED_EXTENSIONS):
                    # Full path, not just the filename - this is what makes the
                    # contextual chunking in embed_and_store.py work.
                    important_files.append((item['download_url'], full_path))
            elif item['type'] == 'dir':
                subdirs.append(full_path)

        for subdir in subdirs:
            await fetch_all_files(path=subdir)

    print("Fetching file list...")
    try:
        await fetch_all_files()
    except RateLimitError as e:
        print(f"ERROR: {e}")
        print("Aborting: a partial scrape would silently produce an incomplete corpus.")
        sys.exit(1)

    if skipped:
        print(f"Skipped {len(skipped)} ignored path(s) before fetching: {', '.join(skipped[:5])}"
              + (f" (+{len(skipped) - 5} more)" if len(skipped) > 5 else ""))

    total = len(important_files)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)
    results = [None] * total
    counter = {"done": 0}

    async def fetch_one(index, file_url, full_path):
        async with semaphore:
            try:
                # Plain requests, not Crawl4AI: these are raw text files, so a
                # headless browser contributes nothing but latency.
                response = await asyncio.to_thread(requests.get, file_url, timeout=30)
                response.raise_for_status()
                results[index] = (full_path, response.text)
            except Exception as e:
                print(f"Error scraping {full_path}: {e}")
            finally:
                counter["done"] += 1
                print(f"Scraping {counter['done']}/{total}: {full_path}...")

    await asyncio.gather(*(
        fetch_one(i, file_url, full_path)
        for i, (file_url, full_path) in enumerate(important_files)
    ))

    all_content = f"# Repository: {owner}/{repo}\n\n"
    for entry in results:
        if entry is None:
            continue
        full_path, text = entry
        # This exact header string is the delimiter embed_and_store.py splits on.
        all_content += f"\n## File Path: {full_path}\n"
        all_content += text + "\n\n"

    with open("repo_content.md", "w", encoding="utf-8") as f:
        f.write(all_content)
    print(f"Saved to repo_content.md")


if __name__ == "__main__":
    asyncio.run(main())
