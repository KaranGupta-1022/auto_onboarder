# scripts/train_intent.py
"""Fine-tunes distilbert-base-uncased on data/intent_commands.jsonl (Phase
13.3). Reports the trained model's classification_report on a held-out test
split ONCE, alongside the rule baseline's (api/intent.py::classify_rules) on
the exact same split - the story this is meant to produce is "the model beat
the heuristic by X," not a number with nothing to compare it to.

Split is by command "family" (the verb), not randomly - a random split would
scatter near-identical commands ("kubectl delete pod x", "kubectl delete pod
y") across train and test and inflate the reported numbers. The split is
fixed by hand below rather than computed, so which families land in test is
stable across runs and inspectable.

Run from the repo root (needs data/intent_commands.jsonl - see
data/generate_intent_commands.py):
    python scripts/train_intent.py
"""
import json
import os
import sys

import torch
import torch.nn as nn
from sklearn.metrics import classification_report
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.intent import classify_rules  # noqa: E402

DATA_PATH = "data/intent_commands.jsonl"
CHECKPOINT_DIR = "models/intent"
BASE_MODEL = "distilbert-base-uncased"
LABELS = ["high_risk", "low_risk", "no_note"]
EPOCHS = 4
BATCH_SIZE = 16
LR = 2e-5

# Family -> split. high_risk has 4 families total, no_note has 3 - too few to
# compute a proportional split, so every group is assigned by hand to
# guarantee every label appears in every split.
FAMILY_SPLIT = {
    # high_risk (4 families)
    "delete": "train", "apply": "train", "scale": "val", "drain": "test",
    # no_note (3 families)
    "get": "train", "version": "train", "describe": "val", "logs": "test", "cluster-info": "test",
    # low_risk (18 families)
    "edit": "train", "patch": "train", "replace": "train",
    "port-forward": "train", "cp": "train", "label": "train",
    "annotate": "train", "cordon": "train", "uncordon": "train",
    "expose": "train", "run": "train", "explain": "train",
    "diff": "train", "wait": "train",
    "create": "val", "exec": "val",
    "rollout": "test", "top": "test",
}


class CommandDataset(Dataset):
    def __init__(self, rows, tokenizer, label2id):
        self.encodings = tokenizer(
            [r["command"] for r in rows],
            truncation=True, padding=True, return_tensors="pt",
        )
        self.labels = torch.tensor([label2id[r["label"]] for r in rows])

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = self.labels[idx]
        return item


def load_split():
    rows = []
    with open(DATA_PATH, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    missing = {r["family"] for r in rows} - set(FAMILY_SPLIT)
    if missing:
        raise ValueError(f"FAMILY_SPLIT is missing families present in the data: {missing}")

    splits = {"train": [], "val": [], "test": []}
    for r in rows:
        splits[FAMILY_SPLIT[r["family"]]].append(r)
    return splits


def evaluate(model, loader, device):
    model.eval()
    criterion = nn.CrossEntropyLoss()
    total_loss, correct, n = 0.0, 0, 0
    all_preds, all_labels = [], []
    with torch.no_grad():
        for batch in loader:
            labels = batch.pop("labels").to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(**batch).logits
            loss = criterion(logits, labels)
            total_loss += loss.item() * labels.size(0)
            preds = logits.argmax(dim=-1)
            correct += (preds == labels).sum().item()
            n += labels.size(0)
            all_preds += preds.tolist()
            all_labels += labels.tolist()
    return total_loss / n, correct / n, all_preds, all_labels


def main():
    torch.manual_seed(13)
    splits = load_split()
    print(f"train={len(splits['train'])}  val={len(splits['val'])}  test={len(splits['test'])}\n")

    label2id = {label: i for i, label in enumerate(LABELS)}
    id2label = {i: label for label, i in label2id.items()}

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=len(LABELS), id2label=id2label, label2id=label2id,
    ).to(device)

    # Freeze the pretrained DistilBERT body and train only the classification
    # head. Full fine-tuning has enough capacity to memorize the small set of
    # train-family verbs outright and never transfer to held-out verbs; a
    # frozen backbone forces the head to work from DistilBERT's general
    # pretrained word representations instead, which is the only thing that
    # could plausibly generalize to an unseen verb like "drain" or "scale".
    for param in model.base_model.parameters():
        param.requires_grad = False

    train_loader = DataLoader(CommandDataset(splits["train"], tokenizer, label2id), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(CommandDataset(splits["val"], tokenizer, label2id), batch_size=BATCH_SIZE)
    test_loader = DataLoader(CommandDataset(splits["test"], tokenizer, label2id), batch_size=BATCH_SIZE)

    # Head-only training tolerates (and needs) a much higher LR than full
    # fine-tuning since there are only ~2.3K trainable params left.
    optimizer = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=1e-3
    )
    criterion = nn.CrossEntropyLoss()

    best_val_acc = -1.0
    for epoch in range(1, EPOCHS + 1):
        model.train()
        train_loss, n = 0.0, 0
        for batch in train_loader:
            labels = batch.pop("labels").to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            optimizer.zero_grad()
            logits = model(**batch).logits
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * labels.size(0)
            n += labels.size(0)
        train_loss /= n

        val_loss, val_acc, _, _ = evaluate(model, val_loader, device)
        print(f"epoch {epoch}/{EPOCHS}  train_loss={train_loss:.4f}  val_loss={val_loss:.4f}  val_acc={val_acc:.4f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            os.makedirs(CHECKPOINT_DIR, exist_ok=True)
            model.save_pretrained(CHECKPOINT_DIR)
            tokenizer.save_pretrained(CHECKPOINT_DIR)
            print(f"  -> new best (val_acc={val_acc:.4f}), saved to {CHECKPOINT_DIR}")

    # Final report, ONCE, on the untouched test split - reloaded fresh from
    # the best checkpoint, not whatever the last epoch happened to leave in
    # memory. Never called anywhere above this line.
    print("\n--- held-out test report (best checkpoint) ---")
    best_model = AutoModelForSequenceClassification.from_pretrained(CHECKPOINT_DIR).to(device)
    _, test_acc, test_preds, test_labels = evaluate(best_model, test_loader, device)
    print(f"test_acc={test_acc:.4f}\n")
    print(classification_report(
        [id2label[i] for i in test_labels],
        [id2label[i] for i in test_preds],
        labels=LABELS,
        zero_division=0,
    ))

    print("--- rule baseline on the SAME test split (for comparison) ---")
    rule_preds = [classify_rules(r["command"]) for r in splits["test"]]
    rule_labels = [r["label"] for r in splits["test"]]
    print(classification_report(rule_labels, rule_preds, labels=LABELS, zero_division=0))


if __name__ == "__main__":
    main()
