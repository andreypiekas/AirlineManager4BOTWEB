"""Capture the native event lists as context for route-demand observations."""
from __future__ import annotations

import time

from selenium.common.exceptions import TimeoutException


EVENT_SOURCES = {"specialEvents.php": "game_special_events", "events.php": "game_route_events"}

_DEMAND_EVENTS_JS = r"""
const [source] = arguments;
const panel = document.querySelector('#popup #eventAction');
if (!panel || !panel.getClientRects().length ||
    panel.querySelector('img[src*="loader"], [aria-busy="true"]')) return null;

const text = node => node?.innerText.trim() ?? '';
const special = source === 'game_special_events';
const count = special
    ? text(panel.querySelector(':scope > .row:first-child')).match(/^Special events available:\s*([0-9]+)$/i)
    : text(panel.querySelector('#eventCount')?.parentElement).match(/^Events available\s+([0-9]+)$/i);
const cards = panel.querySelectorAll(special ? ':scope > .row.border' : '#event-list > .list-list');
if (!count || Number(count[1]) !== cards.length) return null;

const events = [];
for (const card of cards) {
    const countdown = text(card.querySelector('.hasCountdown')).match(/^(?:(\d{1,3})d )?(\d{2}):([0-5]\d):([0-5]\d)$/);
    if (!countdown || Number(countdown[2]) > 23) return null;
    const remaining = Number(countdown[1] || 0) * 86400 + Number(countdown[2]) * 3600 +
                      Number(countdown[3]) * 60 + Number(countdown[4]);
    if (special) {
        const title = text(card.querySelector('.feature-name'));
        const description = text(card.querySelector('td.feature-description'));
        if (!title || !description) return null;
        events.push({title, description, seconds_remaining: remaining});
        continue;
    }

    const ids = card.getAttribute('onclick')?.match(
        /Ajax\('route_research_route\.php\?type=events&dep=([1-9][0-9]{0,11})&arr=([1-9][0-9]{0,11})','eventDetails'\)/);
    const airports = [...card.querySelectorAll('span.xl-text')].map(text);
    const classes = ['economy', 'business', 'first'].filter(name => card.classList.contains(`list-${name}`));
    const boost = text(card).match(/\b(Up|Down) by\s+(\d+|\d{1,3}(?:,\d{3})+)(?=\s|$)/i);
    if (!ids || ids[1] === ids[2] || airports.length !== 2 ||
        !airports.every(code => /^[A-Z]{3,4}$/.test(code)) || classes.length !== 1 || !boost) return null;
    const amount = Number(boost[2].replaceAll(',', ''));
    if (!Number.isSafeInteger(amount)) return null;
    events.push({origin_id: ids[1], destination_id: ids[2], origin_code: airports[0], destination_code: airports[1],
                 cabin: classes[0], demand_change: boost[1].toLowerCase() === 'up' ? amount : -amount,
                 seconds_remaining: remaining});
}
return {reported_count: Number(count[1]), events};
"""


def collect_demand_events(bot):
    """Read both panels independently. Missing or inconsistent panels are omitted."""
    panels = []
    try:
        bot.open_popup("events_main.php", "Events", "nav_events")
        for url, source in EVENT_SOURCES.items():
            if bot.stopping:
                break
            try:
                bot.ajax(url, "eventAction", timeout=8)
                panel = bot.js(_DEMAND_EVENTS_JS, source)
            except TimeoutException:
                continue
            if panel is not None:
                panels.append({"source": source, "observed_at": time.time(), **panel})
    finally:
        bot.close_popup(quiet=True)
    return panels
