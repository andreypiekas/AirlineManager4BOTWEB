"""Planned cabins pass through the native preview without opening a purchase."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import aircraft_order_hub
import aircraft_order_preview
import assisted_aircraft_order
import engine_selection
import fleet
import paths
from investment_journal import InvestmentJournal
from investment_policy import InvestmentPolicy


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
    _observation_only = False
    _observation_company_id = "101"
    stopping = False

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
        if (url, target) == ("ac_orders.php?first=true", "routeAction"):
            self.actions.append("catalog")
            return self
        assert (url, target) == ("ac_orders.php?mode=detail&id=2&charter=0", "acModel")
        self.actions.append("detail")
        return self

    def open_popup(self, url, title, selector):
        assert (url, title, selector) == ("routes_main.php", "Routes", "nav_routes")
        self.actions.append("Routes")

    def close_popup(self, *, quiet):
        assert quiet
        self.actions.append("close")

    def find_element(self, by, selector):
        assert (by, selector) == (By.ID, "acModel")
        return self

    def find_elements(self, by, selector):
        assert by == By.CSS_SELECTOR
        button = {
            "button#newAcNext": "Configuration", "button#newAcBack": "Back",
            "#btnPurchaseIntroA": "Order",
        }[selector]
        return [SimpleNamespace(
            is_displayed=lambda: self.opened == (button != "Configuration"),
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
            state.update(capacity=600, positions=self.positions.copy(), seats=seats, handles=self.handles,
                         order_available=True)
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


@pytest.mark.parametrize(("expected", "status"), [(PRICE, "matched"), (PRICE + 1, "mismatch")])
def test_order_diagnostic_reports_game_price_independently_of_expected_price(expected, status):
    bot = NativePreview()
    request = aircraft_order_preview.AircraftPreviewRequest("2", DELIVERY_HUB, "7", (443, 42, 24), expected)

    report = aircraft_order_preview.probe_aircraft_order(bot, request)

    assert report["status"] == status and report["displayed_cost_usd"] == PRICE
    assert report["read_only"] and not report["execution_available"]
    if status == "matched":
        assert report["order_control_available"] and not report["price_verified"]
    else:
        assert report["expected_checkout_cost"] == PRICE + 1
    assert bot.actions[:3] == ["close", "Routes", "catalog"]
    assert bot.actions[-2:] == ["Back", "close"]
    assert not bot.opened


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


@pytest.fixture
def assisted(tmp_path, monkeypatch):
    bot = NativePreview()
    bot.dry_run = False
    bot._require_observation_session = lambda: None
    bot._verify_observation_company = lambda: None
    cash = 300_000_000
    bot.read_money = lambda: cash
    def ledger(_, checkout_cost):
        clicked = "Order" in bot.actions
        rows = [ch * 64 for ch in "abc"]
        return {"cash": cash - checkout_cost if clicked else cash, "observed_at": time.time(),
                "first_is_checkout": clicked, "ledger_rows": ["d" * 64, *rows] if clicked else rows}

    monkeypatch.setattr(assisted_aircraft_order, "read_checkout_ledger", ledger)
    profile = paths.current().label
    journal = InvestmentJournal(tmp_path / "investment_journal.sqlite3", profile_id=profile)
    company = bot._observation_company_id
    policy = InvestmentPolicy(
        enabled=True, mode="approval", max_single_investment=cash,
        max_daily_spend=cash, max_cycle_spend=cash, max_acquisitions_per_day=1,
    )
    exact = plan()
    reserve = 20_000_000
    approval = assisted_aircraft_order.aircraft_approval_key(
        exact, profile_id=profile, company_id=company, delivery_hub_id=DELIVERY_HUB, reserve=reserve,
    )
    readiness = {
        "profile_id": profile, "company_id": company, "snapshot_id": exact["snapshot_id"],
        "origin_id": "1440", "destination_id": "432", "cash": cash, "pending_commitments": 500,
        "pending_ids": ["20"], "commitments_verified": True, "observed_at": time.time(),
        "delivery_hub_mapping": {
            "verified": True, "source": "game_owned_hub_crosswalk", "profile_id": profile,
            "snapshot_id": exact["snapshot_id"], "observed_at": time.time(),
            "pairs": [{"airport_id": "1440", "delivery_hub_id": DELIVERY_HUB}],
        },
        **dict.fromkeys(("capacity_available", "model_available", "engine_available", "price_includes_engine",
                         "route_available", "route_feasible", "demand_verified"), True),
    }
    monkeypatch.setattr(assisted_aircraft_order, "read_pilot_pending", lambda bot, baseline: {
        "company_id": company, "profile_id": profile, "observed_at": time.time(),
        "fleet_ids": ["19", "20"], "pending": {"rows": [{"id": "20"}]},
    })
    executor = assisted_aircraft_order.AssistedAircraftOrder(
        journal, policy, bot, read_readiness=lambda _: readiness, read_receipt=lambda *_: None,
    )
    return SimpleNamespace(
        bot=bot, journal=journal, executor=executor, readiness=readiness, plan=exact,
        arguments=dict(company_id=company, delivery_hub_id=DELIVERY_HUB, approval_key=approval, reserve=reserve),
    )


def test_assisted_claim_is_durable_before_one_native_click_and_restart_reconciles(assisted):
    bot, journal, executor = assisted.bot, assisted.journal, assisted.executor
    intent, _ = journal.register(assisted.plan)
    key = intent["intent_key"]
    toggle = bot.toggle

    def click(button):
        toggle(button)
        if button == "Order":
            reopened = InvestmentJournal(journal.path, profile_id=journal.profile_id)
            assert reopened.get(key)["state"] == "SUBMITTED"
            assert reopened.get(key)["submit_attempts"] == 1
            assert reopened.submission_baseline(key)["fleet_ids"] == ["19", "20"]
            assert reopened.submission_baseline(key)["ledger_rows"] == [ch * 64 for ch in "abc"]
            raise TimeoutException()

    bot.toggle = click
    result = executor.run(assisted.plan, **assisted.arguments)
    assert result["state"] == "UNKNOWN" and result["isolated_checkout_debit"] is True
    assert journal.get(key)["observed_checkout_debit_at"] >= journal.submission_baseline(key)["submitted_at"]
    assert executor.run(assisted.plan, **assisted.arguments)["state"] == "UNKNOWN"
    assert bot.actions.count("Order") == 1
    assert "Back" not in bot.actions

    proof = {
        "source": "game_order_list", "profile_id": journal.profile_id, "verified": True,
        "company_id": bot._observation_company_id, "delivery_hub_id": DELIVERY_HUB,
        "observed_at": time.time(), "purchase_id": "4444", "aircraft_id": "20",
        "hub_id": "1440", "origin_id": "1440", "destination_id": "432",
        "model_id": "2", "engine_id": "7", "configuration_yjf": CABIN,
        "charged_checkout_cost": PRICE, "debit_transaction_id": "tx-432",
    }
    restarted = assisted_aircraft_order.AssistedAircraftOrder(
        InvestmentJournal(journal.path, profile_id=journal.profile_id), executor.policy, bot,
        read_readiness=None, read_receipt=lambda *_: proof,
    )
    assert restarted.reconcile(key)["state"] == "UNKNOWN"  # The aircraft was already in the fleet.
    proof["aircraft_id"] = "21"
    proof["charged_checkout_cost"] = PRICE + 1
    assert restarted.reconcile(key)["state"] == "UNKNOWN"
    proof["charged_checkout_cost"] = PRICE
    assert restarted.reconcile(key)["state"] == "CONFIRMED"
    assert restarted.journal.get(key)["submit_attempts"] == 1
    assert bot.actions.count("Order") == 1


def test_worker_recovers_checkout_debit_without_resending(assisted, monkeypatch):
    bot = assisted.bot
    monkeypatch.setattr(paths.Profile, "data", property(lambda _: assisted.journal.path.parent))
    reader = assisted_aircraft_order.read_checkout_ledger
    monkeypatch.setattr(assisted_aircraft_order, "read_checkout_ledger",
                        lambda bot, cost: None if "Order" in bot.actions else reader(bot, cost))
    result = assisted.executor.run(assisted.plan, **assisted.arguments)
    key = result["intent_key"]
    assert result["state"] == "UNKNOWN"
    assert "observed_checkout_debit_at" not in assisted.journal.get(key)
    monkeypatch.setattr(assisted_aircraft_order, "read_checkout_ledger", reader)
    monkeypatch.setattr(InvestmentPolicy, "from_config", lambda _: assisted.executor.policy)
    assisted_aircraft_order.reconcile_submitted_aircraft(bot)
    assert assisted.journal.get(key)["observed_checkout_debit_at"] > 0
    assisted_aircraft_order.reconcile_submitted_aircraft(bot)
    assert assisted.journal.get(key)["state"] == "UNKNOWN"
    assert bot.actions.count("Order") == 1


def test_balance_drift_immediately_before_claim_keeps_zero_attempts(assisted):
    cash = assisted.readiness["cash"]
    readings = iter([cash, cash - 1])
    assisted.bot.read_money = lambda: next(readings)
    result = assisted.executor.run(assisted.plan, **assisted.arguments)
    assert result["state"] == "PRECHECKED" and result["reasons"] == ["submissao_bloqueada"]
    assert assisted.journal.get(result["intent_key"])["submit_attempts"] == 0
    assert "Order" not in assisted.bot.actions


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("commitments_verified", False, "compromissos_pendentes_nao_verificados"),
    ("demand_verified", False, "demanda_nao_verificada"),
    ("pending_ids", [], "frota_ou_compromissos_divergentes"),
    ("cash", 299_999_999, "controle_de_envio_ou_saldo_divergente"),
])
def test_assisted_checkout_blocks_unverified_route_or_cash(assisted, field, value, reason):
    assisted.readiness[field] = value
    result = assisted.executor.run(assisted.plan, **assisted.arguments)
    assert reason in result["reasons"]
    assert "Order" not in assisted.bot.actions
    assert result["state"] == "BLOCKED"
    assert assisted.journal.get(result["intent_key"]) is None


def test_assisted_approval_rejects_a_different_route(assisted):
    other = {**assisted.plan, "destination_id": "433"}
    result = assisted.executor.run(other, **assisted.arguments)
    assert result["reasons"] == ["aprovacao_exata_necessaria"]
    assert assisted.bot.actions == []


def test_assisted_order_requires_live_receipt_reader_and_mutating_mode(assisted):
    assisted.bot._observation_only = True
    assert assisted.executor.run(assisted.plan, **assisted.arguments)["reasons"] == ["modo_assistido_indisponivel"]
    assisted.bot._observation_only = False
    assisted.executor.read_receipt = None
    assert assisted.executor.run(assisted.plan, **assisted.arguments)["reasons"] == ["leitores_do_jogo_indisponiveis"]
    assert assisted.bot.actions == []
