"""Native price timers and range checks must finish before a route can be submitted."""
from types import SimpleNamespace

import pytest

import reroute
from airport_catalog import by_code
from route_registry import endpoint


@pytest.mark.parametrize("distance,expected", [(1000, True), (6000, False), (None, False)])
def test_form_waits_for_all_classes_and_checks_native_range(distance, expected):
    button, auto = object(), object()
    reads, clicks = [], []

    def price_read(script):
        reads.append(True)
        return len(reads) > 1

    panel = SimpleNamespace(find_elements=lambda by, selector: [auto] if selector == "introAuto" else [button])
    bot = SimpleNamespace(
        ajax=lambda *_: panel,
        js=lambda *_: dict(codes=["LAX", "MIA"], bound=True, existing="0", fee="100",
                           range="5500", distance=distance),
        read_money=lambda: 1000,
        config=SimpleNamespace(get_int=lambda *_: 100),
        click_element=lambda element: clicks.append(element),
        driver=SimpleNamespace(execute_script=price_read),
    )
    result = reroute._prepare_form(bot, "5", endpoint(code="LAX"), endpoint(by_code("MIA").game_id, code="MIA"))
    assert bool(result) == expected
    assert clicks == ([auto] if expected else [])
    if expected:
        assert result == (button, 100)
        assert len(reads) >= 2
