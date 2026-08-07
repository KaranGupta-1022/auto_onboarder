"""Shared pytest setup.

Sets test-mode env vars at COLLECTION time, before any test module can import
api.config / api.pipeline / api.app - Config reads these once at import, so
setting them inside a fixture would be too late for the module-level Chroma
client pipeline.py creates on import.
"""
import os
import tempfile

os.environ.setdefault("CHROMA_PATH", tempfile.mkdtemp(prefix="ghostkube-test-chroma-"))
os.environ.setdefault("SYNTHESIS_ENABLED", "0")
os.environ.setdefault("GROQ_RERANK_ENABLED", "0")
os.environ.setdefault("RERANK_ENABLED", "0")
os.environ.setdefault("INTENT_MODEL_ENABLED", "0")
