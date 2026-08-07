import pytest

from webhook.webhook import make_patch_for_pod, SHADOW_SIDECAR_NAME

GHOST_VALUE = "svc:auth-service"


def _pod(labels=None, containers=None):
    return {
        "metadata": {"labels": labels or {}},
        "spec": {"containers": containers or [{"name": "app"}]},
    }


def test_no_label_produces_no_patches():
    pod = _pod(labels={}, containers=[{"name": "app"}])

    assert make_patch_for_pod(pod) == []


@pytest.mark.parametrize(
    "container, expected_op, expected_path, expected_value",
    [
        (
            {"name": "app"},
            "add",
            "/spec/containers/0/env",
            [{"name": "GHOST_NOTE_ID", "value": GHOST_VALUE}],
        ),
        (
            {"name": "app", "env": [{"name": "EXISTING", "value": "1"}]},
            "add",
            "/spec/containers/0/env/-",
            {"name": "GHOST_NOTE_ID", "value": GHOST_VALUE},
        ),
    ],
    ids=["no-env", "existing-env"],
)
def test_label_patches_env(container, expected_op, expected_path, expected_value):
    pod = _pod(labels={"ghostkube.io/service": "auth-service"}, containers=[container])

    env_patch = make_patch_for_pod(pod)[0]

    assert env_patch == {"op": expected_op, "path": expected_path, "value": expected_value}


def test_multi_container_pod_gets_one_env_patch_per_container():
    pod = _pod(
        labels={"ghostkube.io/service": "auth-service"},
        containers=[{"name": "app"}, {"name": "worker", "env": [{"name": "X", "value": "1"}]}],
    )

    patches = make_patch_for_pod(pod)
    env_patches = [p for p in patches if "env" in p["path"]]

    assert len(env_patches) == 2
    assert env_patches[0]["path"] == "/spec/containers/0/env"
    assert env_patches[1]["path"] == "/spec/containers/1/env/-"


def test_shadow_sidecar_is_appended_once():
    pod = _pod(labels={"ghostkube.io/service": "auth-service"}, containers=[{"name": "app"}])

    patches = make_patch_for_pod(pod)
    sidecar_patches = [
        p for p in patches
        if p["path"] == "/spec/containers/-" and p["value"].get("name") == SHADOW_SIDECAR_NAME
    ]

    assert len(sidecar_patches) == 1


def test_shadow_sidecar_not_duplicated_if_already_present():
    pod = _pod(
        labels={"ghostkube.io/service": "auth-service"},
        containers=[{"name": "app"}, {"name": SHADOW_SIDECAR_NAME}],
    )

    patches = make_patch_for_pod(pod)

    assert [p for p in patches if p["path"] == "/spec/containers/-"] == []
