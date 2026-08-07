# data/generate_intent_commands.py
"""Generates data/intent_commands.jsonl for Phase 13.3's intent classifier.

Labels mirror api/intent.py's rule baseline at the verb level - delete/drain/
scale/apply -> high_risk, get/describe/logs -> no_note, everything else ->
low_risk - but generates surface variation the rule baseline cannot handle
(the "k" alias, flags placed before the verb, varied resources/names/
namespaces) so a trained classifier has real signal to beat the heuristic on
instead of just re-deriving it.

Each row carries "family": the verb, used by scripts/train_intent.py to split
train/val/test by command family rather than randomly - a random split would
scatter near-identical commands across the split and inflate the reported
numbers.

Run from the repo root:
    python data/generate_intent_commands.py
"""
import json
import random

random.seed(13)

RESOURCES = [
    "pod", "deployment", "service", "configmap", "secret", "statefulset",
    "daemonset", "job", "cronjob", "ingress", "pvc", "node",
]
NAMES = [
    "auth-api", "payment-gateway", "checkout-worker", "auth-api-7d9f4b",
    "web-frontend-6c8d9", "redis-cache", "postgres-primary",
    "notification-svc", "billing-worker-x2k1", "user-service",
]
NAMESPACES = ["default", "prod", "staging", "ghostkube", "payments", "auth"]


def sample(seq, n):
    return random.sample(seq, min(n, len(seq)))


def prefixed(verb_and_args):
    """Yield the plain and "k"-aliased forms, and occasionally a
    flag-before-verb form - surface variation the rule baseline's naive
    first-token check cannot handle.
    """
    out = [f"kubectl {verb_and_args}", f"k {verb_and_args}"]
    if random.random() < 0.15:
        ns = random.choice(NAMESPACES)
        out.append(f"kubectl -n {ns} {verb_and_args}")
    return out


def rows_for(verb, label, arg_templates):
    rows = []
    for template in arg_templates:
        for res in sample(RESOURCES, 2):
            for name in sample(NAMES, 2):
                ns = random.choice(NAMESPACES)
                args = template.format(res=res, name=name, ns=ns)
                for command in prefixed(f"{verb} {args}"):
                    rows.append({"command": command, "label": label, "family": verb})
    return rows


FAMILIES = [
    ("delete",   "high_risk", ["{res} {name}", "{res}/{name}", "{res} {name} --grace-period=0 --force", "{res} {name} -n {ns}"]),
    ("drain",    "high_risk", ["{name}", "{name} --ignore-daemonsets", "{name} --ignore-daemonsets --delete-emptydir-data", "{name} --force"]),
    ("scale",    "high_risk", ["{res} {name} --replicas=0", "{res} {name} --replicas=5", "{res}/{name} --replicas=1 -n {ns}"]),
    ("apply",    "high_risk", ["-f {name}.yaml", "-f {name}.yaml -n {ns}", "-k ./overlays/{ns}"]),

    ("get",      "no_note", ["{res}", "{res} {name}", "{res} -n {ns}", "{res} -o wide", "{res} --all-namespaces"]),
    ("describe", "no_note", ["{res} {name}", "{res} {name} -n {ns}", "{res}/{name}"]),
    ("logs",     "no_note", ["{name}", "{name} -f", "{name} -n {ns}", "{name} --previous"]),
    ("version",      "no_note", ["--client", "--short", "-o=json"]),
    ("cluster-info", "no_note", ["dump"]),

    ("create",       "low_risk", ["{res} {name} --image=nginx", "-f {name}.yaml"]),
    ("edit",         "low_risk", ["{res} {name}", "{res}/{name} -n {ns}"]),
    ("patch",        "low_risk", ["{res} {name} --type=merge -p patch.json"]),
    ("replace",      "low_risk", ["-f {name}.yaml"]),
    ("rollout",      "low_risk", ["restart {res}/{name}", "status {res}/{name}", "undo {res}/{name}"]),
    ("exec",         "low_risk", ["-it {name} -- /bin/bash", "{name} -n {ns} -- env"]),
    ("port-forward", "low_risk", ["{name} 8080:80", "svc/{name} 5432:5432"]),
    ("cp",           "low_risk", ["{name}:/tmp/log.txt ./log.txt"]),
    ("label",        "low_risk", ["{res} {name} team=platform", "{res} {name} tier=backend --overwrite"]),
    ("annotate",     "low_risk", ["{res} {name} owner=platform-team"]),
    ("cordon",       "low_risk", ["{name}"]),
    ("uncordon",     "low_risk", ["{name}"]),
    ("expose",       "low_risk", ["{res} {name} --port=80 --target-port=8080"]),
    ("run",          "low_risk", ["{name} --image=busybox --restart=Never"]),
    ("top",          "low_risk", ["pods", "nodes"]),
    ("explain",      "low_risk", ["{res}"]),
    ("diff",         "low_risk", ["-f {name}.yaml"]),
    ("wait",         "low_risk", ["{res}/{name} --for=condition=Ready"]),
]


def main():
    rows = []
    for verb, label, templates in FAMILIES:
        rows += rows_for(verb, label, templates)
    random.shuffle(rows)

    with open("data/intent_commands.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    print(f"wrote {len(rows)} rows to data/intent_commands.jsonl")


if __name__ == "__main__":
    main()
