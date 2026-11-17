"""Use the native landed sentinel when scheduling duplicate corrections."""
import json
import shutil
import subprocess

import pytest

from fleet import _LANDED_DUPLICATES_JS


def test_zero_arrival_is_landed_and_future_arrival_is_inflight():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to run the game's scheduling JavaScript")
    script = """
global.window = {statusData: {
    landed: {routeId: 1, arrived: 0, grounded: 0},
    inflight: {routeId: 2, arrived: Date.now()/1000 + 3600, grounded: 0},
    paused: {routeId: 3, arrived: 0, grounded: 1},
    unknown: {routeId: 4, grounded: 0},
    noRoute: {routeId: 0, arrived: 0, grounded: 0}
}};
const choose = new Function(JSON.parse(process.argv[1]));
console.log(JSON.stringify(choose(Object.keys(window.statusData))));
"""
    result = subprocess.run([node, "-e", script, json.dumps(_LANDED_DUPLICATES_JS)],
                            capture_output=True, text=True, check=True, timeout=10)
    assert json.loads(result.stdout) == ["landed"]
