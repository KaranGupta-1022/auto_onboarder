import os
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_KIND_E2E") != "1",
    reason="full kind e2e - creates/uses a real cluster and Docker images; opt in with RUN_KIND_E2E=1",
)


def test_kind_e2e_webhook_injects_ghost_note_id():
    script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "e2e_kind.sh")
    result = subprocess.run(["bash", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
