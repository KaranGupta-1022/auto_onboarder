# Testing

## Running the suite

    pip install -r requirements-dev.txt
    pytest

22 tests run by default in a few seconds to ~30s (the embedding model loads
once per session). Two tests are excluded unless you opt in:

- `tests/test_latency.py` - skipped when `CI=1` (or `CI=true`); latency
  budgets are hardware-dependent and unfair to assert on a shared runner.
  Run it locally with plain `pytest`.
- `tests/test_e2e_kind.py` - skipped unless `RUN_KIND_E2E=1`. Creates/uses a
  real kind cluster and builds real Docker images - not something a plain
  `pytest` run should ever do by accident.

      # bash
      RUN_KIND_E2E=1 pytest tests/test_e2e_kind.py -v
      # PowerShell
      $env:RUN_KIND_E2E="1"; pytest tests/test_e2e_kind.py -v

  or run the script directly: `bash scripts/e2e_kind.sh` (needs `kind`,
  `docker`, `kubectl`, `openssl` on PATH). `RUN_KUBECTL_GHOST=1` additionally
  deploys the Brain API/Chroma and checks `kubectl ghost` returns a note.

## What's hermetic vs. not

Everything except `test_e2e_kind.py` runs against a temp Chroma directory
(`tests/conftest.py` sets `CHROMA_PATH` to a fresh `tempfile.mkdtemp()`
before any test imports `api.pipeline`/`api.app`) and a committed fixture
corpus (`tests/fixtures/repo_content.md`, ~20 fake files), never the live
`./chroma_db`. `SYNTHESIS_ENABLED`, `GROQ_RERANK_ENABLED`, `RERANK_ENABLED`,
and `INTENT_MODEL_ENABLED` are all forced off for determinism and speed.

## Retrieval floors are fixture-specific

`tests/test_retrieval.py` asserts hit@1 >= 60% and hit@3 >= 80% against
`eval/queries_fixture.json` (20 positive + 10 negative queries) run over the
fixture corpus above. These numbers describe the fixture, not the product -
they say nothing about retrieval quality on a real, unseen repo. The
historical MeetMe/f1 eval sets in `eval/` are exploratory tooling against
whatever repo is currently in `./chroma_db`; they are not part of this gate
and are not required to be complete.

## Known limitations

- Ingestion is GitHub-only (`api/pipeline.py::_fetch_repo_document`) - no
  GitLab, Bitbucket, or generic Git remotes.
- Retrieval quality is only measured against the fixture corpus here and the
  two small real repos used during development; it is untested on repos
  outside those.
- The mutating webhook's `failurePolicy` is `Ignore` (see
  `k8s/mutatingwebhook.yaml`) - by design, a webhook outage silently produces
  pods with no `GHOST_NOTE_ID` rather than blocking pod creation. This means
  a broken webhook fails silently; nothing pages anyone.
- `Config.GROQ_RERANK_ENABLED`, `Config.RERANK_ENABLED`, and
  `Config.INTENT_MODEL_ENABLED` all default off - each was measured to not
  beat its baseline (see `api/config.py`'s comments). Tests run with them
  off, matching the shipped default.
