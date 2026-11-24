"""Independent managed-hub versus order-form coverage; never an airport crosswalk."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import paths
from aircraft_order_hub import _ORDER_HUB_STATE_JS
from engine_detail import MODEL_DETAIL_IDENTITY_JS

SOURCE = "game_managed_hubs_and_order_form"
MAX_AGE = 900
MAX_WINDOW = 120
_ID = re.compile(r"[1-9][0-9]{0,13}")

MANAGED_HUB_IDS_JS = r"""
const lists = document.querySelectorAll('#hubList');
if (lists.length !== 1 || !window.jQuery || window.jQuery.active !== 0) return null;
const list = lists[0];
if (list.querySelector('img[src*="loader"], [aria-busy="true"]')) return null;
const rows = Array.from(list.children);
if (!rows.length || rows.some(row => !row.matches('.row[onclick]'))) return null;
const pattern = /^\s*playSound\('neutral_click'\);\s*Ajax\('hub_details\.php\?id=([1-9][0-9]{0,13})','hubDetail',this,true\);\s*$/;
return rows.map(row => (row.getAttribute('onclick').match(pattern) || [])[1] || null);
"""

ORDER_DELIVERY_IDS_JS = r"""
const panels = document.querySelectorAll('#acModel');
const selectors = document.querySelectorAll('#hubSelection');
if (panels.length !== 1 || selectors.length !== 1 || !panels[0].contains(selectors[0]) ||
    !window.jQuery || window.jQuery.active !== 0 ||
    panels[0].querySelector('img[src*="loader"], [aria-busy="true"]')) return null;
const identity = """ + MODEL_DETAIL_IDENTITY_JS + r"""(panels[0]);
if (!identity) return null;
const state = (() => {
""" + _ORDER_HUB_STATE_JS + r"""
})();
return {model_id: identity.model_id ?? identity.script_model_id, state};
"""


def _ids(values):
    if (not isinstance(values, list) or not values or len(values) > 10000
            or any(type(value) is not str or not _ID.fullmatch(value) for value in values)
            or len(set(values)) != len(values)):
        return None
    return set(values)


def compare_coverage(before, order, after, model_id):
    """Compare exact native sets with the management inventory bracketing the form."""
    owned, confirmed = _ids(before), _ids(after)
    if not owned or owned != confirmed or not isinstance(order, dict) or order.get("model_id") != model_id:
        return None
    state = order.get("state")
    if (not isinstance(state, dict) or type(state.get("selector_count")) is not int
            or state["selector_count"] != 1 or state.get("selector_disabled") is not False):
        return None
    options = state.get("options")
    if not isinstance(options, list) or any(not isinstance(row, dict) or type(row.get("disabled")) is not bool
                                           for row in options):
        return None
    offered = _ids([row.get("id") for row in options])
    selected = _ids(state.get("selected_values"))
    value = state.get("value")
    if (not offered or not selected or len(selected) != 1 or type(value) is not str or value not in selected
            or not selected <= {row["id"] for row in options if not row["disabled"]}):
        return None
    return {"managed_count": len(owned), "delivery_count": len(offered),
            "matching_count": len(owned & offered),
            "disabled_count": sum(row["disabled"] for row in options)}


def coverage_snapshot(path: Path, *, now: float) -> dict:
    """Expose only counts. Never certify a route airport's correspondence."""
    pending = {"status": "unverified", "airport_crosswalk_verified": False}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return pending
    if not isinstance(saved, dict) or saved.get("source") != SOURCE:
        return pending
    stamp = saved.get("observed_at")
    if type(stamp) not in (int, float) or not 0 < stamp <= now or not 0 <= now - stamp <= MAX_AGE:
        return pending
    keys = ("managed_count", "delivery_count", "matching_count", "disabled_count")
    if any(type(saved.get(key)) is not int or not 0 <= saved[key] <= 10000 for key in keys):
        return pending
    managed, delivery, matching, disabled = (saved[key] for key in keys)
    if not managed or not delivery or matching > min(managed, delivery) or disabled > delivery:
        return pending
    return {**pending, "status": "matched" if managed == delivery == matching else "different",
            "source": SOURCE, "observed_at": stamp, **{key: saved[key] for key in keys}}


def collect_owned_delivery_coverage(bot, *, path=None):
    """Read-only, bounded independent check through native managed and order screens."""
    from fleet import _MODELS_JS
    from game_observations import _stable_read

    if getattr(bot, "stopping", False):
        return False
    path = Path(path) if path is not None else paths.current().data / "owned_delivery_coverage.json"
    started = time.time()
    # Revoke the previous observation before a new attempt. An interrupted
    # attempt cannot leave obsolete coverage marked current.
    paths.write_atomic(path, "{}")

    def managed():
        try:
            bot.open_popup("hubs.php", "Hubs", "nav_hubs")
            return _stable_read(bot, MANAGED_HUB_IDS_JS)
        finally:
            bot.close_popup(quiet=True)

    before = managed()
    if not _ids(before) or getattr(bot, "stopping", False):
        return False
    try:
        bot.open_popup("routes_main.php", "Routes", "nav_routes")
        bot.ajax("ac_orders.php?first=true", "routeAction")
        models = _stable_read(bot, _MODELS_JS)
        if not isinstance(models, list) or any(not isinstance(row, dict) for row in models):
            return False
        model_ids = [row.get("id") for row in models]
        model_ids = _ids(model_ids)
        if not model_ids or getattr(bot, "stopping", False):
            return False
        model_id = min(model_ids, key=int)
        bot.ajax(f"ac_orders.php?mode=detail&id={model_id}&charter=0", "acModel")
        order = _stable_read(bot, ORDER_DELIVERY_IDS_JS)
    finally:
        bot.close_popup(quiet=True)
    if order is None or getattr(bot, "stopping", False):
        return False
    after = managed()
    finished = time.time()
    counts = compare_coverage(before, order, after, model_id)
    if not counts or not 0 <= finished - started <= MAX_WINDOW or getattr(bot, "stopping", False):
        return False
    paths.write_atomic(path, json.dumps({"source": SOURCE, "observed_at": int(finished), **counts}))
    return counts["managed_count"] == counts["delivery_count"] == counts["matching_count"]
