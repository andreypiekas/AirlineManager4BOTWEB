from __future__ import annotations

import time
from types import SimpleNamespace

import investment_events
from investment_events import InvestmentEventDelivery
from investment_journal import InvestmentJournal


SNAPSHOT = "sha256:" + "a" * 64


class Config:
    def __init__(self, path, *, profile="principal", enabled=True):
        self.profile = SimpleNamespace(label=profile, is_main=profile == "principal", data=path)
        self.flags = {
            ("options", "telegram_investment_events"): enabled,
            ("options", "telegram"): True,
        }

    def get_bool(self, section, key, default=False):
        return self.flags.get((section, key), default)


class Client:
    enabled = True

    def __init__(self, *results):
        self.calls = []
        self.results = list(results)

    def send_now(self, message):
        self.calls.append(message)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result, "mock"


def prepare(monkeypatch, path, *, profile="principal", enabled=True,
            results=(True,), dry_run=False):
    monkeypatch.setattr(investment_events, "InvestmentJournal", InvestmentJournal)
    return SimpleNamespace(
        config=Config(path, profile=profile, enabled=enabled),
        telegram=Client(*results),
        dry_run=dry_run,
    )


def register(journal, *, destination="456", plan_id="candidate-123"):
    return journal.register({
        "plan_id": plan_id,
        "snapshot_id": SNAPSHOT,
        "kind": "aircraft",
        "hub_id": "123",
        "origin_id": "123",
        "destination_id": destination,
        "model_id": "A320",
        "engine_id": "motor-2",
        "estimated_cost": 125000,
    })


def test_initialization_skips_history_then_delivers_new_events_in_order(monkeypatch, tmp_path):
    journal = InvestmentJournal(tmp_path / "investment_journal.sqlite3", profile_id="principal")
    register(journal)
    bot = prepare(monkeypatch, tmp_path, results=(True, True))
    now = time.time()

    assert investment_events.publish_investment_event(bot, now=now) == "initialized"
    assert bot.telegram.calls == []

    intent, created = register(journal, destination="789", plan_id="candidate-789")
    assert created
    assert investment_events.publish_investment_event(bot, now=now + 1) == "delivered"
    first_message = bot.telegram.calls[-1]
    assert "Proposta registrada" in first_message
    assert "Hub: 123" in first_message
    assert "Rota: 123 → 789" in first_message
    assert "Aeronave: A320 | Motor: motor-2" in first_message
    assert "Valor previsto no plano: $125,000" in first_message
    assert "não representa gasto observado" in first_message

    assert journal.transition(intent["intent_key"], "PROPOSED", "APPROVED")
    assert investment_events.publish_investment_event(bot, now=now + 2) == "delivered"
    assert "Aprovação registrada" in bot.telegram.calls[-1]
    assert investment_events.publish_investment_event(bot, now=now + 3) == "idle"
    assert len(bot.telegram.calls) == 2


def test_failed_send_retries_same_event_after_restart(monkeypatch, tmp_path, caplog):
    journal = InvestmentJournal(tmp_path / "investment_journal.sqlite3", profile_id="principal")
    bot = prepare(monkeypatch, tmp_path, results=(False, RuntimeError("private-token"), True))
    now = time.time()
    assert investment_events.publish_investment_event(bot, now=now) == "initialized"
    register(journal)

    assert investment_events.publish_investment_event(bot, now=now + 1) == "failed"
    restarted = prepare(monkeypatch, tmp_path, results=(RuntimeError("private-token"), True))
    assert investment_events.publish_investment_event(restarted, now=now + 2) == "failed"
    assert "private-token" not in caplog.text
    assert investment_events.publish_investment_event(restarted, now=now + 3) == "delivered"
    assert restarted.telegram.calls[0] == restarted.telegram.calls[1]
    assert investment_events.publish_investment_event(restarted, now=now + 4) == "idle"


def test_delivery_claim_is_profile_scoped_and_recovers_expired_lease(tmp_path):
    delivery = InvestmentEventDelivery(tmp_path / "delivery.sqlite3")
    assert delivery.initialize("principal", 10, now=1000)
    assert delivery.initialize("filial", 20, now=1000)
    principal_claim = delivery.claim("principal", 11, now=1001)
    filial_claim = delivery.claim("filial", 21, now=1001)
    assert principal_claim is not None
    assert filial_claim is not None
    assert delivery.claim("principal", 11, now=1002) is None

    recovered = delivery.claim("principal", 12, now=1302)
    assert recovered is not None
    assert recovered[0] == 11
    assert recovered[1] != principal_claim[1]
    assert not delivery.acknowledge(
        "principal", 11, principal_claim[1], delivered=True, now=1303,
    )
    assert delivery.acknowledge("principal", 11, recovered[1], delivered=True, now=1304)
    assert delivery.last_event_id("principal") == 11
    assert delivery.last_event_id("filial") == 20
    assert delivery.acknowledge(
        "filial", 21, filial_claim[1], delivered=False, now=1304,
    )


def test_simulation_uses_isolated_journal_and_labels_notification(monkeypatch, tmp_path):
    bot = prepare(monkeypatch, tmp_path, dry_run=True)
    now = time.time()
    assert investment_events.publish_investment_event(bot, now=now) == "initialized"
    simulation = InvestmentJournal(
        tmp_path / "investment_simulation.sqlite3", profile_id="principal", simulation=True,
    )
    register(simulation)

    assert investment_events.publish_investment_event(bot, now=now + 1) == "delivered"
    assert bot.telegram.calls[0].startswith("🧪 Simulação")
    assert (tmp_path / "investment_simulation.sqlite3").exists()
    assert not (tmp_path / "investment_journal.sqlite3").exists()


def test_switching_real_and_simulation_keeps_independent_cursors(monkeypatch, tmp_path):
    real = InvestmentJournal(tmp_path / "investment_journal.sqlite3", profile_id="principal")
    simulated = InvestmentJournal(
        tmp_path / "investment_simulation.sqlite3", profile_id="principal", simulation=True,
    )
    register(real, plan_id="existing-real")
    register(simulated, plan_id="existing-sim")
    bot = prepare(monkeypatch, tmp_path, results=(True, True))
    now = time.time()

    assert investment_events.publish_investment_event(bot, now=now) == "initialized"
    bot.dry_run = True
    assert investment_events.publish_investment_event(bot, now=now + 1) == "initialized"
    assert bot.telegram.calls == []

    register(simulated, destination="789", plan_id="new-sim")
    assert investment_events.publish_investment_event(bot, now=now + 2) == "delivered"
    bot.dry_run = False
    register(real, destination="789", plan_id="new-real")
    assert investment_events.publish_investment_event(bot, now=now + 3) == "delivered"
    assert "new-sim" in bot.telegram.calls[0]
    assert bot.telegram.calls[0].startswith("🧪 Simulação")
    assert "new-real" in bot.telegram.calls[1]
    assert not bot.telegram.calls[1].startswith("🧪 Simulação")

    bot.dry_run = True
    assert investment_events.publish_investment_event(bot, now=now + 4) == "idle"
    bot.dry_run = False
    assert investment_events.publish_investment_event(bot, now=now + 5) == "idle"


def test_claims_are_isolated_between_modes(tmp_path):
    delivery = InvestmentEventDelivery(tmp_path / "delivery.sqlite3")
    assert delivery.initialize("principal", 1, now=100, simulation=False)
    assert delivery.initialize("principal", 10, now=100, simulation=True)
    real_claim = delivery.claim("principal", 2, now=101, simulation=False)
    sim_claim = delivery.claim("principal", 11, now=102, simulation=True)
    assert real_claim is not None and sim_claim is not None
    assert not delivery.acknowledge("principal", 2, real_claim[1],
                                    delivered=True, now=103, simulation=True)
    assert delivery.acknowledge("principal", 11, sim_claim[1],
                                delivered=True, now=104, simulation=True)
    assert delivery.last_event_id("principal", simulation=True) == 11
    assert delivery.last_event_id("principal", simulation=False) == 1
    assert delivery.acknowledge("principal", 2, real_claim[1],
                                delivered=True, now=105, simulation=False)


def test_disabled_event_notifications_do_not_create_delivery_state(monkeypatch, tmp_path):
    bot = prepare(monkeypatch, tmp_path, enabled=False)
    assert investment_events.publish_investment_event(bot, now=time.time()) == "disabled"
    assert bot.telegram.calls == []
    assert not list(tmp_path.glob("*.sqlite3"))


def test_event_reader_is_ordered_and_profile_scoped(tmp_path):
    path = tmp_path / "investment_journal.sqlite3"
    principal = InvestmentJournal(path, profile_id="principal")
    filial = InvestmentJournal(path, profile_id="filial")
    own, _ = register(principal)
    other, _ = register(filial, destination="789", plan_id="filial-789")

    assert principal.latest_event_id() < filial.latest_event_id()
    events = principal.events_after(0, limit=10)
    assert len(events) == 1
    assert events[0]["intent_key"] == own["intent_key"]
    assert principal.event(events[0]["event_id"]) == events[0]
    assert filial.events_after(0, limit=10)[0]["intent_key"] == other["intent_key"]
    assert principal.event(filial.latest_event_id()) is None
