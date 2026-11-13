"""Honest read-only source setup progress. No privileged mount from Flask.

Statuses describe what has ACTUALLY happened, not predicted percentages.
The browser may poll the endpoint: filesystem reads never trigger a mount.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import time

from .folder_status import read_status
from .media_sources import load_sources, mount_statuses


def describe_sources(registry_path, mount_status_path, library_items, root=None):
    records = load_sources(registry_path)
    verified = mount_statuses(mount_status_path, registry_path)
    root = Path(root or os.environ.get('MEDIA_SOURCE_ROOT', '/sources'))
    report_time = None
    report_stale = False
    try:
        document = json.loads(Path(mount_status_path).read_text(encoding='utf-8'))
        stamp = document.get('checked_at')
        if isinstance(stamp, (float, int)) and stamp <= time.time():
            report_time = datetime.fromtimestamp(stamp, timezone.utc).strftime('%d.%m.%Y %H:%M:%S UTC')
            report_stale = time.time() - stamp >= 300
    except (ValueError, TypeError, OSError, OverflowError):
        pass
    result = []
    for row in records:
        alias = row['alias']
        state = verified.get(alias, 'pending')
        templates = [
            template for template in library_items
            if template.get('folder_source') == alias
            or (alias == 'default'
                and str(template.get('folder_source', '')).startswith('default/'))
        ]
        stage = []
        stage.append({'title': 'Pfad gespeichert', 'state': 'done',
                      'detail': 'Gespeichert, aber noch nicht automatisch eingehängt.'})
        if state in ('mounted', 'already-mounted'):
            mount_state = 'done'
            mount_detail = 'Der Host hat genau diese SMB-Quelle bestätigt.'
        elif state == 'blocked':
            mount_state = 'error'
            mount_detail = 'Quelle nicht auf der freigegebenen Host-Allowlist.'
        elif state == 'conflict':
            mount_state = 'error'
            mount_detail = 'Am Mountpunkt liegt bereits eine andere Quelle.'
        elif state == 'error':
            mount_state = 'error'
            mount_detail = 'Verbindungs-/Mountfehler auf dem Host. Dienst-Logs prüfen.'
        elif report_stale:
            mount_state = 'waiting'
            mount_detail = 'Letzte Hostprüfung ist veraltet. Timer oder Mountdienst prüfen.'
        elif not report_time:
            mount_state = 'waiting'
            mount_detail = 'Kein Host-Mountdienst meldet einen Versuch. Es läuft keine bestätigte SMB-Prüfung.'
        else:
            mount_state = 'waiting'
            mount_detail = 'Host hat noch keine erfolgreiche Prüfung für den gespeicherten Pfad gemeldet.'
        stage.append({'title': 'SMB am Host bestätigt', 'state': mount_state,
                      'detail': mount_detail})

        discovered = 0
        if mount_state == 'done':
            try:
                from .folder_sync import default_library_folders, available_sources
                # Only count folders AFTER confirmed source validation.
                discovered = (len(default_library_folders(root)) if alias == 'default'
                              else int(alias in available_sources(root)))
            except (OSError, ValueError):
                discovered = 0
        if mount_state != 'done':
            folder_state = 'waiting'
            folder_detail = 'Erst nach erfolgreichem Host-Mount möglich.'
        elif discovered:
            folder_state = 'done'
            folder_detail = (f'{discovered} Unterordner erkannt.' if alias == 'default'
                             else 'Quelle im Hub sichtbar.')
        else:
            folder_state = 'waiting'
            folder_detail = ('Mount bestätigt, aber keine direkten Bildschirmordner gefunden.'
                             if alias == 'default' else
                             'Mount bestätigt, Quelle im Hub noch nicht sichtbar.')
        stage.append({'title': 'Ordner im Hub sichtbar', 'state': folder_state,
                      'detail': folder_detail})

        status = [read_status(t['id']) for t in templates]
        imported_ok = bool(status) and all(s['state'] == 'ok' for s in status)
        imported_error = any(s['state'] in ('error', 'stale') for s in status)
        stage.append({
            'title': 'Playlist-Import',
            'state': 'done' if imported_ok else 'error' if imported_error else 'waiting',
            'detail': (
                f'{len(templates)} Playlist(s) mit aktuellem Importstatus.'
                if imported_ok else
                'Importfehler oder veralteter Heartbeat. Importer-Logs prüfen.'
                if imported_error else
                'Noch keine erfolgreiche Ordner-Playlist-Prüfung. Zuerst eine Playlist zuordnen.'
            ),
        })

        auto_publish = bool(status) and all(s['auto_publish'] for s in status)
        stage.append({
            'title': 'Automatisch auf Pi veröffentlichen',
            'state': ('done' if imported_ok and auto_publish
                      else 'waiting'),
            'detail': ('Publisher für zugeordnete Playlists aktiv.'
                       if imported_ok and auto_publish else
                       'Der Pi-Publisher ist nicht aktiv oder wurde noch nicht bestätigt.'),
        })
        result.append({
            'alias': alias, 'state': state, 'stages': stage,
            'last_host_check': report_time, 'report_stale': report_stale,
            'discovered': discovered, 'template_count': len(templates),
            'worker_interval_seconds': next(
                (s['interval_seconds'] for s in status if s.get('interval_seconds')), None),
        })
    return result
