"""Persistent request budget and cache policy for the ITRA importer."""
import datetime as dt
import email.utils
import json
from pathlib import Path

from itra import atomic_json

DETAIL_DAYS = 60
SPACING_SECONDS = 20 * 60
UTC = dt.timezone.utc


def moment(value):
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def write_changed(path, value):
    if load_json(path, None) != value:
        atomic_json(path, value)


def retry_after(value, now):
    if not value:
        return None
    try:
        return now + dt.timedelta(seconds=max(0, int(value)))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except (ValueError, TypeError, OverflowError):
            return None


class RequestBudget:
    def __init__(self, cache):
        self.path = cache / 'request-state.json'
        self.state = load_json(self.path, {'schemaVersion': 1})
        # Existing installations may already be blocked: do not probe again on upgrade.
        if not self.path.exists():
            status = load_json(cache / 'status.json', {})
            error = status.get('detailRefreshError') or ''
            if error:
                when = moment(status.get('attemptedAt'))
                if when:
                    self.fail(error, when, blocked=any(x in error for x in ('403', '429', 'captcha', 'WAF')))

    def deferred_until(self, now, include_spacing=True):
        keys = ['cooldownUntil'] + (['nextRequestAt'] if include_spacing else [])
        future = [moment(self.state.get(k)) for k in keys if self.state.get(k)]
        return max((value for value in future if value > now), default=None)

    def reserve(self, now):
        if self.deferred_until(now):
            return False
        self.state.update(lastAttemptAt=now.isoformat(), nextRequestAt=(now + dt.timedelta(seconds=SPACING_SECONDS)).isoformat())
        # Persist before the request so interrupted or overlapping jobs cannot repeat it.
        write_changed(self.path, self.state)
        return True

    def success(self, now):
        self.state.update(consecutiveFailures=0, lastSuccessAt=now.isoformat(), lastError=None, cooldownUntil=None)
        write_changed(self.path, self.state)

    def fail(self, message, now, blocked=False, retry=None, scope='detail'):
        count = int(self.state.get('consecutiveFailures', 0)) + 1
        hours = min((48 if blocked else 6) * 2 ** min(count - 1, 8), 14 * 24)
        until = now + dt.timedelta(hours=hours)
        supplied = retry_after(retry, now)
        if supplied and supplied > until:
            until = supplied
        self.state.update(lastAttemptAt=now.isoformat(), lastError=message, lastErrorScope=scope, consecutiveFailures=count, cooldownUntil=until.isoformat())
        write_changed(self.path, self.state)


def detail_queue(races, details, failures, today, now, fingerprint):
    eligible = []
    for race in races:
        if (race.get('dateEnd') or race.get('date') or '') < today:
            continue
        saved = details.get(race['sourceId'])
        same = saved and saved.get('fingerprint') == fingerprint(race)
        if same and (now - moment(saved['detailsFetchedAt'])).total_seconds() < DETAIL_DAYS * 86400:
            continue
        failed = failures.get(race['sourceId'])
        if failed and failed.get('fingerprint') == fingerprint(race) and (now - moment(failed['attemptedAt'])).total_seconds() < DETAIL_DAYS * 86400:
            continue
        # New/changed courses first. Within each group the earliest event wins,
        # including repeat refreshes; an old cache date never outranks race date.
        eligible.append((bool(same), race.get('date') or '9999', saved.get('detailsFetchedAt', '') if saved else '', race['id'], race))
    return [item[-1] for item in sorted(eligible, key=lambda item: item[:-1])]
