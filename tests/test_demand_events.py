import json
import shutil
import subprocess
from unittest.mock import Mock, call

import pytest
from selenium.common.exceptions import TimeoutException

from demand_events import _DEMAND_EVENTS_JS, collect_demand_events


def test_native_event_panels_are_independent_after_timeout():
    bot = Mock(stopping=False)
    bot.ajax.side_effect = [TimeoutException, None]
    bot.js.return_value = {"reported_count": 0, "events": []}

    panel, = collect_demand_events(bot)

    assert panel["source"] == "game_route_events"
    assert panel["observed_at"] > 0
    assert panel["reported_count"] == 0
    assert panel["events"] == []
    assert bot.mock_calls == [
        call.open_popup("events_main.php", "Events", "nav_events"),
        call.ajax("specialEvents.php", "eventAction", timeout=8),
        call.ajax("events.php", "eventAction", timeout=8),
        call.js(_DEMAND_EVENTS_JS, "game_route_events"),
        call.close_popup(quiet=True),
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for DOM contract")
def test_native_event_lists_require_matching_cards_and_countdowns(tmp_path):
    script = tmp_path / "demand_events.js"
    script.write_text("""
const assert = require('node:assert/strict');
const collect = new Function(""" + json.dumps(_DEMAND_EVENTS_JS) + r""");
const text = innerText => ({innerText});
let specialHeader = 'Special events available: 1';
let routeHeader = 'Events available 1';
let specialTimer = '3d 16:23:45';
const special = {querySelector: key => ({
  '.hasCountdown': text(specialTimer), '.feature-name': text('BLACK FRIDAY CARGO RUSH'),
  'td.feature-description': text('50% increased cargo demand worldwide'),
})[key]};
const route = {
  innerText: 'YYZToronto intl, Canada\nBusiness class8,051km\nVAGVarginha, Brazil\nUp by\n863\nA/C at location0',
  querySelector: key => key === '.hasCountdown' ? text('3d 22:00:33') : null,
  querySelectorAll: key => key === 'span.xl-text' ? [text('YYZ'), text('VAG')] : [],
  classList: {contains: name => name === 'list-business'},
  getAttribute: key => key === 'onclick' ?
    "$('#event-list').hide();Ajax('route_research_route.php?type=events&dep=305&arr=3016','eventDetails');" : null,
};
let specialCards = [special];
const panel = {
  getClientRects: () => [1],
  querySelector: key => ({
    ':scope > .row:first-child': text(specialHeader), '#eventCount': {parentElement: text(routeHeader)},
  })[key],
  querySelectorAll: key => ({':scope > .row.border': specialCards, '#event-list > .list-list': [route]})[key],
};
global.document = {querySelector: key => key === '#popup #eventAction' ? panel : null};
assert.deepEqual(collect('game_special_events'), {reported_count: 1, events: [{
  title: 'BLACK FRIDAY CARGO RUSH', description: '50% increased cargo demand worldwide', seconds_remaining: 318225,
}]});
assert.deepEqual(collect('game_route_events'), {reported_count: 1, events: [{
  origin_id: '305', destination_id: '3016', origin_code: 'YYZ', destination_code: 'VAG',
  cabin: 'business', demand_change: 863, seconds_remaining: 338433,
}]});
route.innerText = 'Down by 1,863\nA/C at location0';
assert.equal(collect('game_route_events').events[0].demand_change, -1863);
route.innerText = 'Up by 86,3\nA/C at location0';
assert.equal(collect('game_route_events'), null);
specialTimer = 'Expired';
assert.equal(collect('game_special_events'), null);
specialCards = [];
assert.equal(collect('game_special_events'), null);
specialHeader = 'Special events available: 0';
assert.deepEqual(collect('game_special_events'), {reported_count: 0, events: []});
specialHeader = 'Loading';
assert.equal(collect('game_special_events'), null);
""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
