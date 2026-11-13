# DEV – Steuerzentrale-Prototyp (UI 2026-11-13-08)

**Nur isolierter DEV-Stack:** \`/root/apps/anthias-hub-dev\`, Compose-Projekt \`anthias-hub-dev\`, Port \`127.0.0.1:8766\`. Nicht direkt auf die Produktion ausrollen.

## Eine Stelle zum Steuern, eigene Seiten zum Arbeiten

Im Kopfmenü **Steuerzentrale** (Owner/IT/Marketing) gibt es fünf serverseitige Tabs:

| Bereich | Steuerzentrale – ändern | Fachansicht – ansehen/arbeiten |
| --- | --- | --- |
| Bildschirme | Registrieren, Namen/URL/Ort ändern, Steuerbefehle, Registrierung entfernen | Flottenstatus und Inhalt des gewählten Bildschirms |
| Playlists | Neu, Template-Backup importieren/exportieren, feste Zielzuordnungen, Netzwerkquelle wählen, **Playlist löschen** | Wiedergabereihenfolge, Dauer und Medien/URLs bearbeiten |
| Ordner & Quellen | SMB-Lesekonto testen/ändern, Quellen austragen, Import anstoßen (IT) | Verbindungs- und Kopierfortschritt, erkannte Ordner |
| Zeitpläne | Vorlagen anlegen, bearbeiten, entfernen; optional bestätigte Pi-Synchronisierung | Gemeinsame Zeitfenster und Geräte-Zeitpläne ansehen |
| Übersicht | Weiterleitung zu den vier Fachbereichen | Keine verborgene Automatik |

Ein Klick auf die Tabs ist ein reiner GET, kein Schreibvorgang. Alle Formulare verwenden die bestehenden Hub-POST-Endpunkte mit CSRF, Rolle und vorhandenen Sicherheitsbestätigungen. Eine Bildschirmzuordnung veröffentlicht **nicht** selbstständig Medien. DEV-Pi-Publishing bleibt \`DEV_AUTO_PUBLISH=0\`.

### Test-Playlist löschen

**Steuerzentrale → Playlists → gewünschte Playlist → Optionen/Vorlage löschen.** Name exakt eingeben und endgültiges Entfernen bestätigen. Wenn die Playlist noch einem Bildschirm zugeordnet ist, zuerst dort **Bildschirme zuweisen → alle Häkchen entfernen → Zuordnungen speichern**. Die bisherige Sperre bleibt korrekt erhalten. Der Hub löscht nur die lokale Playlist, nicht bereits auf Pis vorhandene Medien. Es erfolgt kein Anthias-Lösch-POST.

## DEV aktualisieren (nach Merge des UI-Unter-PRs)

\`\`\`bash
(
  set -e
  cd /root/apps/anthias-hub-dev
  git fetch origin dev/screen-source-of-truth-v2-20261113
  git switch dev/screen-source-of-truth-v2-20261113
  git merge --ff-only origin/dev/screen-source-of-truth-v2-20261113
  bash scripts/dev-cohost.sh start
  bash scripts/dev-cohost.sh status
)
\`\`\`

Die bestehende DEV-\`.env\` bleibt unverändert. Prüfe, dass \`HUB_WORKFLOW_V2=1\` und \`DEV_AUTO_PUBLISH=0\` nur im DEV-Checkout gesetzt sind. Falls der lokale DEV-Branch noch fehlt, stattdessen \`git switch --track origin/dev/screen-source-of-truth-v2-20261113\` verwenden. Zugriff nur über vorhandenen SSH-Tunnel: \`http://127.0.0.1:8766\`.

## Abnahme vor Produktionsentscheidung

- Login als IT/Marketing/Viewer: Steuerzentrale nur für Rollen mit Änderungsrechten; SMB nur IT/Owner; Viewer liest Status/Fachansichten.
- Neuen Test-Bildschirm und eine manuelle Playlist anlegen, Medien hinzufügen/sortieren, optional Ziel zuordnen; Pi bleibt bis zur Freigabe unverändert.
- Test-Playlist nach Entzuordnung löschen. Falscher Name, fehlende CSRF und noch aktive Zuordnung blockieren das Löschen.
- SMB über Browser verbinden, großen Ordner automatisch in 4-GiB-Abschnitten abgleichen, Syncstatus mit echten Zahlen prüfen; Quellenaustrag bei aktiver Playlist verhindern.
- Zeitplan erstellen, bearbeiten und entfernen; vergewissern, dass ein reines Speichern keinen ungefragten Pi-Write auslöst.
- Bestehende produktive SMB-Mounts, RSS2Slideshow, Nutzerkonten, Bildschirmliste und Media-Files dürfen durch DEV nicht verändert werden.

**Freigabegrenze:** Der gesammelte Draft-PR **#73** bleibt auf GitHub ungemergt nach \`main\`, bis die fachliche Abnahme und ein separater Produktions-Rollbackplan vorliegen. Der UI-Unter-PR darf nach grüner CI **nur in den DEV-Zweig** gemergt werden. Dann enthält #73 automatisch die gesamte Änderung.
