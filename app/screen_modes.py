"""Single, deterministic content owner for each screen.

This module makes no network requests: unknown API state is NEVER called empty.
One saved assignment always outranks stray Pi assets. A mixed/duplicate mapping
is an explicit conflict, not permission for another editor.
"""


def resolve_mode(device_id, templates, *, assets=None, error=None):
    assigned = [item for item in templates
                if device_id in item.get('auto_devices', [])]
    if len(assigned) > 1:
        return {'key': 'conflict', 'label': 'Zuordnung prüfen',
                'template': None, 'error': 'Mehrere Playlists zugeordnet'}
    if assigned:
        template = assigned[0]
        network = bool(template.get('folder_source'))
        return {
            'key': 'network' if network else 'playlist',
            'label': 'Netzwerkordner' if network else 'Playlist',
            'template': template,
            'error': error,
        }
    if error:
        return {'key': 'offline', 'label': 'Verbindung prüfen',
                'template': None, 'error': error}
    return {'key': 'manual' if assets else 'empty',
            'label': 'Manuell' if assets else 'Leer',
            'template': None, 'error': None}
