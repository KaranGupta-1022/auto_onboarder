# api/intent.py
"""Decide whether a kubectl-shaped command warrants a Ghost Note at all - not
every `kubectl get pods` deserves an interruption. Rule baseline (verb
allowlist) first; a trained checkpoint (scripts/train_intent.py) is preferred
once one exists under Config.INTENT_MODEL_DIR, same "measure it, keep the
baseline as fallback" pattern as the Groq reranker over the bi-encoder.
"""
import logging

from .config import Config

logger = logging.getLogger(__name__)

HIGH_RISK_VERBS = {"delete", "drain", "scale", "apply"}
NO_NOTE_VERBS = {"get", "describe", "logs"}

_tokenizer = None
_model = None


def _try_load_model():
    """Best-effort: load a fine-tuned checkpoint if one exists AND it has been
    measured to beat the rule baseline (Config.INTENT_MODEL_ENABLED). Missing
    directory, disabled flag, missing torch/transformers, or a corrupt
    checkpoint all fall back to the rule baseline silently - classifying
    intent must never crash a request over a model that isn't trained yet,
    and a checkpoint merely existing is not evidence it should be served (see
    GhostKube_Guide.md Phase 13.3: a fine-tuned DistilBERT checkpoint lost
    decisively to the rule baseline under a family-holdout split).
    """
    global _tokenizer, _model
    import os
    if not Config.INTENT_MODEL_ENABLED or not os.path.isdir(Config.INTENT_MODEL_DIR):
        return
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained(Config.INTENT_MODEL_DIR)
        _model = AutoModelForSequenceClassification.from_pretrained(Config.INTENT_MODEL_DIR)
        _model.eval()
        logger.info("Loaded intent classifier checkpoint from %s", Config.INTENT_MODEL_DIR)
    except Exception as e:
        logger.warning(
            "Could not load intent checkpoint from %s, using rule baseline: %s",
            Config.INTENT_MODEL_DIR, e,
        )
        _tokenizer, _model = None, None


_try_load_model()


def _extract_verb(command: str) -> str | None:
    """Pull the operative verb out of a raw command string. Handles both
    "kubectl delete pod x" and "delete pod x" - kubectl-ghost's own delete
    path never types the leading "kubectl" - and strips a leading
    "kubectl-ghost"/"ghost" the same way.
    """
    for tok in command.strip().split():
        low = tok.lower()
        if low in ("kubectl", "kubectl-ghost", "ghost"):
            continue
        return low
    return None


def classify_rules(command: str) -> str:
    verb = _extract_verb(command)
    if verb in HIGH_RISK_VERBS:
        return "high_risk"
    if verb in NO_NOTE_VERBS:
        return "no_note"
    return "low_risk"


def classify_model(command: str) -> str:
    import torch
    inputs = _tokenizer(command, return_tensors="pt", truncation=True)
    with torch.no_grad():
        logits = _model(**inputs).logits
    return _model.config.id2label[int(logits.argmax(dim=-1))]


def classify(command: str) -> dict:
    if _model is not None:
        try:
            return {"label": classify_model(command), "source": "model"}
        except Exception as e:
            logger.warning("Intent model inference failed, falling back to rules: %s", e)
    return {"label": classify_rules(command), "source": "rules"}
