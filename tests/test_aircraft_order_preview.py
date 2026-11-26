"""Planned cabins pass through the native preview without opening a purchase."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import aircraft_order_hub
import aircraft_order_preview
import engine_selection
import fleet


PRICE = 216_079_503
DELIVERY_HUB = "24323457"
CABIN = {"y": 443, "j": 42, "f": 24}
MODEL = fleet.AircraftModel("2", "A380-800", 14500, 945, 600, 22, 215_629_503)


def plan(cabin=CABIN):
    route_fee = 1_063_229
    return {
        "plan_id": "test-lax-tun", "snapshot_id": "sha256:" + "a" * 64,
        "kind": "aircraft", "hub_id": "1440", "origin_id": "1440",
        "destination_id": "432", "model_id": "2", "engine_id": "7",
        "configuration_yjf": cabin, "checkout_cost": PRICE,
        "estimated_cost": PRICE + route_fee,
        "capital_costs": {
            "aircraft_cost": PRICE, "engine_delta_cost": 0, "hub_cost": 0,
            "route_fee": route_fee, "hangar_cost": 0, "other_fees": 0,
            "total_investment": PRICE + route_fee,
        },
    }


class NativePreview:
    def __init__(self, *, drift=None):
        self.driver = self
        self.config = SimpleNamespace(get=lambda *args: args[-1])
        self.dry_run = True
        self.opened = False
        self.hub = "101"
        self.engine = "5"
        self.positions = [600, 600]
        self.actions = []
        self.messages = []
        self.drift = drift or {}
        self.handles = [SimpleNamespace(send_keys=lambda keys, i=i: self.move(i, keys)) for i in range(2)]

    def ajax(self, url, target):
        assert (url, target) == ("ac_orders.php?mode=detail&id=2&charter=0", "acModel")
        self.actions.append("detail")
        return self

    def find_element(self, by, selector):
        assert (by, selector) == (By.ID, "acModel")
        return self

    def find_elements(self, by, selector):
        assert by == By.CSS_SELECTOR
        button = {"button#newAcNext": "Configuration", "button#newAcBack": "Back"}[selector]
        return [SimpleNamespace(
            is_displayed=lambda: self.opened == (button == "Back"),
            is_enabled=lambda: True,
            click=lambda: self.toggle(button),
        )]

    def toggle(self, button):
        self.actions.append(button)
        self.opened = button == "Configuration"

    def move(self, index, keys):
        self.actions.append(("slider", index))
        delta = {Keys.ARROW_LEFT: -1, Keys.ARROW_RIGHT: 1, Keys.PAGE_DOWN: -120, Keys.PAGE_UP: 120}
        for key in keys:
            low = self.positions[0] if index == 1 else 0
            high = self.positions[1] if index == 0 else 600
            self.positions[index] = min(high, max(low, self.positions[index] + delta[key]))

    def js(self, script, *args):
        if script == aircraft_order_hub._ORDER_HUB_STATE_JS:
            return {
                "selector_count": 1, "selector_disabled": False, "value": self.hub,
                "selected_values": [self.hub], "options": [
                    {"id": hub, "disabled": False} for hub in ("101", DELIVERY_HUB)
                ],
            }
        if script == aircraft_order_hub._SELECT_ORDER_HUB_JS:
            self.hub, = args
            self.actions.append(("hub", self.hub))
            return True
        if script == engine_selection._ENGINE_OPTIONS_JS:
            return [{"type": "select", "id": "engSelection", "name": "", "options": [
                {"label": label, "value": engine, "selected": self.engine == engine, "disabled": False}
                for engine, label in (("5", "GP7270"), ("7", "RR Trent 972"))
            ]}]
        if script == engine_selection._SET_ENGINE_JS:
            assert args[:2] == ("select", "engSelection")
            self.engine = args[2]
            self.actions.append(("engine", self.engine))
            return True
        assert script == aircraft_order_preview._FORM_STATE_JS and args == (self,)
        state = {"model_id": "2", "hub_id": self.hub, "engine_id": self.engine, "low_balance": False}
        base = MODEL.price
        if self.opened:
            left, right = self.positions
            seats = {"y": left, "j": (right - left) // 2, "f": (600 - right) // 3}
            base += 5000 * seats["j"] + 10000 * seats["f"]
            state.update(capacity=600, positions=self.positions.copy(), seats=seats, handles=self.handles)
        state["price"] = f"${base:,}"
        if self.opened and self.positions == [443, 528]:
            state.update(self.drift)
        return state

    def pause(self, *_):
        pass

    def notify(self, message, **_):
        self.messages.append(message)


def test_worker_stages_route_layout_and_confirms_single_aircraft_quote():
    bot = NativePreview()

    assert fleet.order_aircraft(bot, MODEL, hub_id=DELIVERY_HUB, investment_plan=plan())
    assert bot.positions == [443, 528]
    assert bot.actions == [
        "detail", ("hub", DELIVERY_HUB), ("engine", "7"), "Configuration",
        ("slider", 0), ("slider", 1), "Back",
    ]
    assert not bot.opened
    assert "443/42/24" in bot.messages[0]


@pytest.mark.parametrize(("drift", "reason"), [
    ({"price": "$216,079,504"}, "total exibido"),
    ({"seats": {"y": 442, "j": 42, "f": 24}}, "cabine exata"),
    ({"hub_id": "101"}, "etapa divergente"),
    ({"engine_id": "5"}, "etapa divergente"),
    ({"low_balance": True}, "saldo insuficiente"),
])
def test_preview_closes_after_divergent_form_and_blocks_order(drift, reason, caplog):
    bot = NativePreview(drift=drift)

    assert not fleet.order_aircraft(bot, MODEL, hub_id=DELIVERY_HUB, investment_plan=plan())
    assert reason in caplog.text
    assert bot.actions[-1] == "Back"
    assert not bot.opened and not bot.messages


def test_real_planned_call_stops_before_opening_the_order_detail():
    bot = NativePreview()
    bot.dry_run = False

    assert not fleet.order_aircraft(bot, MODEL, hub_id=DELIVERY_HUB, investment_plan=plan())
    assert bot.actions == []


def test_unrepresentable_layout_closes_preview_without_changing_seats():
    bot = NativePreview()
    layout = {"y": 440, "j": 42, "f": 24}

    assert not fleet.order_aircraft(bot, MODEL, hub_id=DELIVERY_HUB, investment_plan=plan(layout))
    assert bot.positions == [600, 600]
    assert bot.actions[-2:] == ["Configuration", "Back"]
