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
    python_smb = os.environ.get('DEV_SMB_UI', '0') == '1'
    report_time = None
    report_stale = False
    raw_states = {}
    try:
        document = json.loads(Path(mount_status_path).read_text(encoding='utf-8'))
        raw_states = document.get('sources', {}) if isinstance(document.get('sources'), dict) else {}
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
        live = raw_states.get(alias, {})
        if not isinstance(live, dict) or live.get('fingerprint') != __import__('hashlib').sha256(
                row['unc'].encode('utf-8')).hexdigest() or report_stale:
            live = {}
        if python_smb and state in ('tested', 'syncing', 'connected'):
            mount_state = 'done'
            mount_detail = (
                'SMB-Anmeldung und Ordnerliste erfolgreich geprüft.'
                if state == 'tested' else
                'SMB verbunden – Medien werden eingelesen.'
                if state == 'syncing' else
                'SMB verbunden – DEV-Medienspiegel aktuell.'
            )
        elif state in ('mounted', 'already-mounted'):
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
            mount_detail = (str(live.get('detail', ''))[:160] or
                            'SMB-Fehler. Zugangsdaten und Freigabe prüfen.'
                            if python_smb else
                            'Verbindungs-/Mountfehler auf dem Host. Dienst-Logs prüfen.')
        elif report_stale:
            mount_state = 'waiting'
            mount_detail = 'Letzte Hostprüfung ist veraltet. Timer oder Mountdienst prüfen.'
        elif not report_time:
            mount_state = 'waiting'
            mount_detail = ('Noch kein SMB-Verbindungsversuch. Bitte Pfad und Anmeldedaten '
                            'eingeben und „Verbinden & prüfen“ klicken.' if python_smb else
                            'Kein Host-Mountdienst meldet einen Versuch. '
                            'Es läuft keine bestätigte SMB-Prüfung.')
        else:
            mount_state = 'waiting'
            mount_detail = 'Host hat noch keine erfolgreiche Prüfung für den gespeicherten Pfad gemeldet.'
        stage.append({'title': ('SMB-Verbindung geprüft' if python_smb
                                else 'SMB am Host bestätigt'), 'state': mount_state,
                      'detail': mount_detail})

        discovered = 0
        names = []
        if mount_state == 'done' and (not python_smb or state == 'connected'):
            try:
                from .folder_sync import default_library_folders, available_sources
                # Only count folders AFTER confirmed source validation.
                names = default_library_folders(root) if alias == 'default' else []
                discovered = (len(names) if alias == 'default'
                              else int(alias in available_sources(root)))
            except (OSError, ValueError):
                discovered = 0
        if python_smb and state == 'syncing':
            folder_state = 'waiting'
            copied_count = max(0, int(live.get('done', 0)))
            total_count = max(0, int(live.get('files', 0)))
            completed_gib = max(0, int(live.get('completed_bytes', 0))) / (1024 ** 3)
            total_gib = max(0, int(live.get('total_bytes', 0))) / (1024 ** 3)
            if total_count:
                folder_detail = (
                    f'Automatischer Teilimport: {copied_count} von {total_count} Medien '
                    f'({completed_gib:.2f} von {total_gib:.2f} GiB). '
                    'Die nächsten Abschnitte starten selbstständig.'
                )
            else:
                folder_detail = 'Medienliste wird ermittelt; Kopieren startet automatisch.'
        elif python_smb and state == 'tested':
            folder_state = 'waiting'
            folder_detail = ('Verbindung erfolgreich – ' +
                             str(int(live.get('folders', 0))) +
                             ' Unterordner gefunden. Importer startet die Übernahme.')
        elif mount_state != 'done':
            folder_state = 'waiting'
            folder_detail = ('Erst nach erfolgreicher SMB-Verbindung möglich.'
                             if python_smb else
                             'Erst nach erfolgreichem Host-Mount möglich.')
        elif discovered:
            folder_state = 'done'
            folder_detail = (f'{discovered} Unterordner erkannt.' if alias == 'default'
                             else 'Quelle im Hub sichtbar.')
        else:
            folder_state = 'waiting'
            folder_detail = ('Mount bestätigt, aber keine direkten Bildschirmordner gefunden.'
                             if alias == 'default' else
                             'Mount bestätigt, Quelle im Hub noch nicht sichtbar.')
        stage.append({'title': ('Medien automatisch übernehmen'
                                if python_smb and state == 'syncing'
                                else 'Ordner im Hub sichtbar'), 'state': folder_state,
                      'detail': folder_detail})

        status = [read_status(t['id']) for t in templates]
        imported_ok = bool(status) and all(s['state'] == 'ok' for s in status)
        imported_error = any(s['state'] in ('error', 'stale') for s in status)
        # Ignore stale template heartbeat while the protected SMB stage is
        # incomplete: the worker has intentionally not published it yet.
        if python_smb and state in ('syncing', 'tested'):
            imported_ok = False
            imported_error = False
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

        targets = sum(len(t.get('auto_devices', [])) for t in templates)
        auto_publish = bool(status) and all(s['auto_publish'] for s in status)
        published_errors = any(s.get('device_errors', 0) for s in status)
        if python_smb and state in ('syncing', 'tested'):
            published_errors = False
        publish_ready = (imported_ok and targets > 0 and auto_publish
                         and not published_errors)
        stage.append({
            'title': 'Automatisch auf Pi veröffentlichen',
            'state': ('done' if publish_ready
                      else 'error' if published_errors else 'waiting'),
            'detail': ('Publisher mit ' + str(targets) +
                       ' zugeordneten Bildschirm(en) zuletzt erfolgreich gemeldet.'
                       if publish_ready else
                       'Fehler beim Veröffentlichen auf mindestens einem Pi.'
                       if published_errors else
                       'Noch kein Zielbildschirm fest zugeordnet.'
                       if targets == 0 else
                       'Pi-Publisher ist deaktiviert oder noch nicht bestätigt.'),
        })
        result.append({
            'alias': alias, 'state': state, 'stages': stage,
            'last_host_check': report_time, 'report_stale': report_stale,
            'discovered': discovered,
            'folders': [{
                'name': name,
                'template_id': next((t['id'] for t in templates
                                     if t.get('folder_source') == 'default/' + name), None),
            } for name in names],
            'template_count': len(templates),
            'worker_interval_seconds': next(
                (s['interval_seconds'] for s in status if s.get('interval_seconds')), None),
            'provider': 'python-smb' if python_smb else 'host-mount',
            'copy_progress': {
                'done': int(live.get('done', 0)),
                'files': int(live.get('files', 0)),
                'bytes': int(live.get('bytes', 0)),
                'total_bytes': int(live.get('total_bytes', 0)),
                'completed_bytes': int(live.get('completed_bytes', 0)),
                'pending': int(live.get('pending', 0)),
                'state': state,
            } if python_smb else None,
        })
    return result
