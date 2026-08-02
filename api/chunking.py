# api/chunking.py
"""Single source of truth for how repository text becomes indexed chunks.

Both ingestion paths - the CLI pipeline and the API's POST /ingest - must
produce byte-identical chunks and the same metadata shape, or they poison one
another's collection. That is not hypothetical: the previous index held 137
records in a dead schema plus 40 records that were the HTML of a GitHub landing
page, none with a `path` field, which made search raise KeyError outright.

Both `embed_and_store.py` (CLI) and `api/pipeline.py` (HTTP) import from here.
"""
import os

# Bump whenever the metadata shape changes. embed_and_store.py refuses to write
# into a collection whose records carry a different version, which is what stops
# a silent mixed-schema write from destroying the index a second time.
SCHEMA_VERSION = 2

# A file whose body is shorter than this is dropped. The contextual header is
# prepended unconditionally, so an empty backend/__init__.py would otherwise
# embed as pure path text and outrank real files on bare directory-name matches.
MIN_BODY_CHARS = 40

CHUNK_SIZE = 1000


# What is worth indexing at all. The complement of the ignore rules below: this
# is the allowlist ("is this a kind of file we index?"), those are the denylist
# ("is this a copy of one we shouldn't?"). Both are applied at fetch time by the
# scraper and again at chunk time, so they belong together.
ALLOWED_EXTENSIONS = (
    '.md', '.py', '.js', '.ts', '.json', '.yaml', '.yml', '.txt', '.jsx', '.tsx',
)

# Ignore rules are split by HOW they match, not just what they match. The old
# list was a flat substring test, which silently dropped legitimate source: a
# bare "dist" entry matches distance.py and distribution.js, and "bin" matches
# combine.ts, binary_search.py and cabinet.py. Any entry short enough to be
# useful as a directory name is also short enough to appear inside real
# filenames, so matching has to be structural.

# Matched against the exact filename.
IGNORE_FILENAMES = {
    # Lockfiles - huge, machine-generated, and pure noise once embedded.
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "bun.lockb", "poetry.lock", "pipfile.lock", "composer.lock",
    "gemfile.lock", "cargo.lock", "go.sum", "gradle.lockfile",
    # Editor/OS debris that occasionally gets committed.
    ".ds_store", "thumbs.db",
}

# Matched against whole path SEGMENTS, so "dist" hits dist/bundle.js but not
# src/distance.py.
IGNORE_DIRS = {
    # Vendored dependencies
    "node_modules", "bower_components", "vendor", "third_party", "thirdparty",
    "site-packages", "venv", ".venv", "virtualenv",
    # Build output
    "dist", "build", "out", "target", "bin", "obj", "_build",
    ".next", ".nuxt", ".output", ".svelte-kit", ".astro", "_site",
    ".docusaurus", ".vitepress",
    # Caches and tool state
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".cache", ".parcel-cache", ".turbo", ".gradle", ".eggs", ".nox",
    # Coverage and snapshots
    "coverage", "htmlcov", "__snapshots__",
    # VCS and editor metadata
    ".git", ".hg", ".svn", ".idea", ".vscode",
}

# Matched against the end of the filename.
IGNORE_SUFFIXES = (
    # Minified and bundled assets - unreadable, and they blow the chunk budget.
    ".min.js", ".min.css", ".bundle.js", ".chunk.js", ".map",
    # Generated code: the source of truth is the .proto/.graphql, not this.
    "_pb2.py", "_pb2_grpc.py", ".pb.go", ".pb.cc", ".pb.h", ".g.dart",
    ".freezed.dart", ".generated.ts", ".generated.js", "_generated.go",
)

FILE_HEADER = "## File Path: "


def is_ignored(full_path: str) -> bool:
    """Structural ignore test - exact filename, path segment, or suffix.

    Deliberately not a substring match: see the note above IGNORE_FILENAMES.
    """
    lowered = full_path.lower().replace("\\", "/")
    segments = [s for s in lowered.split("/") if s]
    if not segments:
        return False

    filename = segments[-1]
    if filename in IGNORE_FILENAMES:
        return True
    if filename.endswith(IGNORE_SUFFIXES):
        return True

    # Directory components only, so a file that happens to be named "build"
    # is still indexed while build/ contents are not.
    for segment in segments[:-1]:
        if segment in IGNORE_DIRS or segment.endswith(".egg-info"):
            return True
    return False


def chunk_file(full_path: str, block: str):
    """Chunk one file's text. `block` is the path line followed by the content.

    Returns (chunks, metadatas). Empty lists if the file is ignored or too small.
    """
    extension = os.path.splitext(full_path)[1]

    if is_ignored(full_path):
        return [], []

    # Strip the path line off the front so we measure the real body, not the
    # header we are about to re-add.
    body = block[len(full_path):]
    if len(body.strip()) < MIN_BODY_CHARS:
        return [], []

    chunks, metadatas = [], []
    for i in range(0, len(block), CHUNK_SIZE):
        text_segment = block[i:i + CHUNK_SIZE]
        # Contextual chunking: every chunk carries its own file identity, so a
        # chunk from the middle of a file still knows what it belongs to.
        chunks.append(
            f"FILE PATH: {full_path}\nEXTENSION: {extension}\nCODE:\n{text_segment}"
        )
        metadatas.append({
            "path": full_path,
            "extension": extension,
            # Reserved for the Phase 12 Console's code/prose toggle. Deliberately
            # NOT used as a `where=` filter at query time: Phase 4 measured that
            # filtering on is_code alone does not improve retrieval, and the
            # docs-outrank-code problem it was meant to solve was fixed by
            # file-level pooling instead. Kept rather than dropped because
            # removing it means SCHEMA_VERSION 3 and a full reindex.
            "is_code": extension not in ['.md', '.txt'],
            "schema": SCHEMA_VERSION,
        })
    return chunks, metadatas


def chunk_repo_document(content: str):
    """Chunk a whole `repo_content.md`-style document.

    Splits on the `## File Path: ` header, which is the delimiter the scraper
    writes and embed_and_store.py splits on.

    Returns (chunks, metadatas, skipped_paths).
    """
    chunks, metadatas, skipped = [], [], []

    for block in content.split(FILE_HEADER):
        if not block.strip() or "\n" not in block:
            continue
        full_path = block.split('\n')[0].strip()
        c, m = chunk_file(full_path, block)
        if not c:
            skipped.append(full_path)
            continue
        chunks.extend(c)
        metadatas.extend(m)

    return chunks, metadatas, skipped
