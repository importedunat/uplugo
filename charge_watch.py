# SPDX-License-Identifier: GPL-3.0-only
"""Bounded local observations, never estimates of charging current or health."""
from i18n import _
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

MAX_SESSIONS = 24
MAX_SAMPLES = 1440
STATUSES = ('Charging', 'Discharging', 'Full')
REASONS = ('connection', 'gap', 'clock')
MAX_NOTE = 160


def clean_note(value):
    return value.strip() if isinstance(value, str) and len(value) <= MAX_NOTE and (not value or value.isprintable()) else ''


def timestamp(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 32503680000


def percentage(value):
    return type(value) is int and 0 <= value <= 100


def usb_port(value):
    return value if isinstance(value, str) and re.fullmatch(r'\d{1,3}-\d{1,3}(?:\.\d{1,3}){0,8}', value) else ''


def clean_summary(value):
    if (not isinstance(value, dict) or not timestamp(value.get('started'))
            or not timestamp(value.get('seen')) or value['seen'] < value['started']
            or not percentage(value.get('baseline')) or not percentage(value.get('capacity'))
            or value.get('status') not in STATUSES):
        return None
    return dict(started=value['started'], seen=value['seen'], baseline=value['baseline'],
                capacity=value['capacity'], status=value['status'], port=usb_port(value.get('port')),
                reason=value.get('reason') if value.get('reason') in REASONS else 'gap',
                session_id=value.get('session_id') if isinstance(value.get('session_id'), str) and re.fullmatch(r'[0-9a-f]{32}', value['session_id']) else '',
                note=clean_note(value.get('note')))


class ChargeWatch:
    def __init__(self, path):
        self.path = Path(path)
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        self.entries = {}
        for identity, entry in (data.items() if isinstance(data, dict) else []):
            if not isinstance(entry, dict):
                continue
            # Migrate older history without writing to disk until a new observation.
            entry = dict(entry)
            samples = entry.get('samples', [])
            samples = [s for s in samples if isinstance(s, dict) and timestamp(s.get('at'))
                       and percentage(s.get('capacity'))] if isinstance(samples, list) else []
            if not percentage(entry.get('baseline')):
                entry['baseline'] = samples[0]['capacity'] if samples else entry.get('capacity')
            connection = entry.get('connection', '')
            entry['connection'] = connection if isinstance(connection, str) else ''
            if not usb_port(entry.get('port')):
                parts = entry['connection'].split(':')
                entry['port'] = usb_port(parts[-2]) if len(parts) >= 3 else ''
            summary = clean_summary(entry)
            if summary is None or not timestamp(entry.get('changed')):
                continue
            entry.update(summary)
            entry['samples'] = []
            for sample in samples[-MAX_SAMPLES:]:
                if not entry['started'] <= sample['at'] <= entry['seen']:
                    continue
                if entry['samples'] and sample['at'] < entry['samples'][-1]['at']:
                    continue
                entry['samples'].append(dict(at=sample['at'], capacity=sample['capacity'],
                    status=sample.get('status') if sample.get('status') in STATUSES else entry['status'],
                    profile=self.profile(sample.get('profile'))))
            histories = entry.get('sessions', [])
            entry['sessions'] = [s for value in histories if (s := clean_summary(value)) is not None][-MAX_SESSIONS:] if isinstance(histories, list) else []
            # Stable IDs bind an editor to its period even after a reconnection or
            # clock change. Legacy history is migrated in memory until a save.
            ids = set()
            for period in [entry, *entry['sessions']]:
                if not period['session_id'] or period['session_id'] in ids:
                    period['session_id'] = uuid.uuid4().hex
                ids.add(period['session_id'])
            increase = entry.get('increase')
            if (not isinstance(increase, dict) or not timestamp(increase.get('at'))
                    or not entry['started'] <= increase['at'] <= entry['seen']
                    or not percentage(increase.get('before')) or not percentage(increase.get('after'))
                    or increase['before'] >= increase['after']):
                entry.pop('increase', None)
            charging_started = entry.get('charging_started')
            if not timestamp(charging_started) or not entry['started'] <= charging_started <= entry['seen']:
                # Only claim time in the last uninterrupted Charging run retained.
                charging_started = entry['seen']
                for sample in reversed(entry['samples']):
                    if sample['status'] != 'Charging':
                        break
                    charging_started = sample['at']
            entry['charging_started'] = charging_started
            self.entries[identity] = entry
        self.saved = 0

    @staticmethod
    def profile(value):
        return value if isinstance(value, str) and len(value) <= 80 else 'default'

    def observe(self, identity, connection, reading, now=None, *, port=None):
        now = time.time() if now is None else now
        capacity = reading.get('capacity') if isinstance(reading, dict) else None
        if (not identity or not percentage(capacity) or not timestamp(now)
                or reading.get('status') not in STATUSES):
            return
        entry = self.entries.get(identity, {})
        reason = ('connection' if entry.get('connection') != connection else
                  'clock' if now < entry.get('seen', 0) else
                  'gap' if now - entry.get('seen', 0) > 15 else None)
        if not entry or reason:
            histories = list(entry.get('sessions', []))
            if entry:
                previous = clean_summary(dict(entry, reason=reason))
                if previous:
                    histories.append(previous)
            entry = dict(connection=connection, started=now, baseline=capacity, changed=now,
                         capacity=capacity, sessions=histories[-MAX_SESSIONS:], port=usb_port(port),
                         session_id=uuid.uuid4().hex, note='')
            self.entries[identity] = entry
        elif usb_port(port):
            entry['port'] = usb_port(port)
        status = reading['status']
        previous_status = entry.get('status')
        if status == 'Charging' and entry.get('status') != 'Charging':
            entry['charging_started'] = now
            entry.pop('increase', None)
        if capacity != entry['capacity']:
            if capacity > entry['capacity'] and status == previous_status == 'Charging':
                entry['increase'] = dict(at=now, before=entry['capacity'], after=capacity)
            entry['changed'] = now
            entry['capacity'] = capacity
        entry['seen'], entry['status'] = now, status
        profile = self.profile(reading.get('charge_profile', 'default'))
        if entry.get('profile') != profile:
            entry.update(profile=profile, profile_since=now, profile_baseline=capacity)
        samples = entry.setdefault('samples', [])
        if (not samples or now - samples[-1]['at'] >= 60 or capacity != samples[-1]['capacity']
                or status != samples[-1]['status'] or profile != samples[-1].get('profile')):
            samples.append(dict(at=now, capacity=capacity, status=status, profile=profile))
            del samples[:-MAX_SAMPLES]
        if now - self.saved >= 10 or now < self.saved:
            self.flush()
            self.saved = now

    def flush(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix=self.path.name+'.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(self.entries, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def annotate(self, identity, session_id, note):
        """Edit exactly one retained period; never copy a cable claim forward."""
        if not isinstance(note, str) or len(note) > MAX_NOTE or (note and not note.isprintable()):
            raise ValueError('invalid-note')
        entry = self.entries.get(identity)
        if not entry or not session_id:
            raise LookupError('missing-observation')
        period = next((p for p in [entry, *entry['sessions']] if p['session_id'] == session_id), None)
        if period is None:
            raise LookupError('missing-observation')
        previous = period['note']
        period['note'] = note.strip()
        try:
            self.flush()
        except OSError:
            period['note'] = previous
            raise

    def sessions(self, identity, now=None):
        """Newest first; duration ends at the last report, never at the wall clock."""
        now = time.time() if now is None else now
        entry = self.entries.get(identity)
        if not entry:
            return []
        current = clean_summary(entry)
        current.update(current=True, fresh=0 <= now-entry['seen'] <= 6)
        return [current] + [dict(s, current=False, fresh=False) for s in reversed(entry['sessions'])]

    def describe(self, identity, now=None):
        now = time.time() if now is None else now
        entry = self.entries.get(identity)
        if not entry or not 0 <= now - entry['seen'] <= 6:
            return _('Sem leitura USB recente; aguardando o controle.')
        if entry['status'] == 'Full':
            return _('O controle informa bateria cheia.')
        if entry['status'] != 'Charging':
            return _('O controle não informa carga neste momento.')
        increase = entry.get('increase')
        if increase and entry['capacity'] >= increase['after']:
            at = time.strftime('%H:%M:%S', time.localtime(increase['at']))
            message = _('Aumento observado: {0}% → {1}% às {2}.').format(increase['before'], increase['after'], at)
            stalled = max(0, int((now - increase['at']) / 60))
            if stalled >= 30:
                message += _(' Sem novo aumento há {0} min.').format(stalled)
            return message
        minutes = max(0, int((now - entry.get('charging_started', entry['started'])) / 60))
        if minutes >= 30:
            return _('Sem aumento há {0} min. A carga efetiva ainda não foi confirmada.').format(minutes)
        return _('Aguardando aumento da bateria · observando há {0} min.').format(minutes)
