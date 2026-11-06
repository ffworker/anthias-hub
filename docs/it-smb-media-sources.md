# IT: SMB-Medienquellen direkt im Anthias-Hub verwalten

## Empfohlener Standard: ein SMB-Stammordner, viele Playlists

Für Standorte mit einem gemeinsamen Marketing-Verzeichnis **nicht jedes
Bildschirmverzeichnis als eigene SMB-Quelle anlegen**. Stattdessen unter
**Medienquellen → Standardbibliothek** nur den gemeinsamen übergeordneten
UNC-Pfad eintragen (Beispiel: `//10.20.1.4/media$/Marketing/Bildschirme`).

Der Host-Mountdienst hängt diesen **einen** Pfad read-only als
`/srv/anthias-sources/default` ein. Das Hub-UI erkennt unmittelbar darunter
gelegene Verzeichnisse wie `Bistro`, `Empfang Nord` oder
`Lager Bildschirm` und bietet pro Ordner **„Als Playlist verwenden“**.
Das erzeugt eine Playlist-Vorlage, die den unveränderlichen Ordnerverweis
`default/<exakter Ordnername>` erhält. Die Playlist kann später
einem oder mehreren Anthias-Pis zugeordnet werden.

Marketing arbeitet unverändert in den vorhandenen Netzwerkordnern. Im Hub
bearbeitet Marketing Bild-Anzeigedauern und vorhandene RSS-Web-Slides.
Unter **Bildschirme** sind die Wiedergabelisten und Zeitpläne sichtbar.

Die automatische Ordnererkennung berücksichtigt nur **direkte Unterordner**
des freigegebenen Root-Mounts. Symlinks, versteckte Ordner sowie
Pfad-Traversal werden abgewiesen. **Es gibt kein automatisches Löschen**:
Entfernte Quelldateien verbleiben bis zum gesondert freigegebenen
Lösch-Abgleich in der Playlist. Das schützt vor SMB-Ausfällen.

Ein bestehender alter Einzel-Mount wie `bistro` darf als Rückfalloption
bestehen bleiben; er wird durch die neue Standardbibliothek nicht ersetzt.
Für den neuen Stammordner ist dieselbe Server/Share-Allowlist und
Credentials-Datei verwendbar, sofern deren Berechtigungen passen.

## Bedienkonzept

Im Hub erscheint für **IT und Owner** ein neuer Menüpunkt **Medienquellen**.
Hier werden beliebig viele Aliase (z. B. `bistro`, `empfang`,
`kantine`) verwaltet. Jeder Eintrag besteht aus einem **Alias** und einem
**SMB-UNC-Pfad** (z. B. `//10.20.1.4/media$/Screens/Bistro`).

- **Anlegen:** Alias + SMB-Pfad eingeben, speichern. Der Host-Mountdienst
  bindet die Freigabe nach seiner nächsten Prüfung unter
  `/srv/anthias-sources/<alias>` ein.
- **Bearbeiten:** SMB-Pfad im vorhandenen Eintrag ändern. Wenn der alte
  Mount noch aktiv ist, wird **nicht automatisch umgehängt**: IT muss den
  kontrollierten Wechsel am Host vornehmen; der Import bleibt bis dahin
  sicherheitshalber gesperrt.
- **Austragen (einzeln):** Quelle unter `Ordner & Quellen → Weitere SMB-Quellen`
  öffnen, `Quelle aus dem Hub entfernen` aufklappen, bestätigen. Für den
  Standardstammordner befindet sich dieselbe Aktion im Hauptbereich. Der Hub
  **blockiert die Entfernung**, solange eine aktive Playlist an den Alias
  gebunden ist (auch `default/<Unterordner>`). Zuerst die betroffenen Vorlagen
  prüfen und Zuordnungen gezielt lösen bzw. migrieren. Importierte Medien,
  individuelle Zeiten und Geräte-Playlists werden nicht gelöscht.
- **Nach dem Austragen:** Alias ist für neue Zuordnungen gesperrt, selbst wenn
  ein altes CIFS-Mount noch vorhanden ist; die Anzeige `Ausgetragene Quellen`
  erinnert an die nötige Host-Prüfung. Es wird **weder ein SMB-Mount ausgehängt
  noch ein Mountpoint-Ordner oder eine Datei gelöscht**. Der Root-Mount-Timer
  mountet ausgetragene Aliase nicht erneut, sofern sie nicht anderweitig
  konfiguriert sind. Gezielt wieder freigeben: Alias und geprüften UNC-Pfad
  neu registrieren.
- **Playlist:** Bibliothek → Vorlage → Netzwerkordner als Medienquelle.
  Hier nur den Alias wählen und Zielbildschirme konfigurieren.
- **Anzeige:** Neues/ersetztes Medium aus dem Share erscheint automatisch
  im Hub; die Marketing-Anzeigedauer bleibt erhalten.
- **Rollen:** Marketing kann weder SMB-Ziele ändern noch Admin-Quellen
  betrachten. Credentials werden nie im Web-Browser oder Repository gespeichert.

Die ersten Mounts auf einer vorhandenen Hostinstallation können in der
Liste **Bereits am Host eingebundene Ordner** erscheinen. Falls die
Mountinformationen im Container nur den Freigabestamm zeigen, den vollständigen
UNC-Pfad auf dem Host über `findmnt -M` prüfen und unter dem vorhandenen
Alias im UI eintragen.

## Einmalige Host-Einrichtung (Root)

Der Hub selbst hat absichtlich **keine Mount-Rechte**. Ein dedizierter
Host-timer führt die kontrollierten CIFS-Mounts aus. Er mountet nur
Server/Freigaben, die Root vorher in einer nicht vom Webcontainer
beschreibbaren Allowlist genehmigt hat.

1. Den Root-geschützten SMB-Credentials-Eintrag bereitstellen, z. B.
   `/etc/anthias-hub/secrets/marketing.smb` mit Modus `0600`
   und Eigentümer root:root. Passwort nie ins UI, Git oder Terminalprotokoll.
2. Die zugelassenen Server/Freigaben **ohne** Unterordnerpfad erfassen:

```json
{
  "allowed_shares": [
    {
      "server": "10.20.1.4",
      "share": "media$",
      "credentials": "/etc/anthias-hub/secrets/marketing.smb"
    }
  ]
}
```

Diese JSON-Datei gehört nach
`/etc/anthias-hub/smb-allowlist.json` mit Eigentümer root und Modus
`0600`. Die Pfad- und Credentials-Zuordnung ist nur über den Host
bearbeitbar; das UI darf bei derselben zugelassenen Server/Freigabe
beliebige Unterordner anlegen.

3. Bestehendes Quellverzeichnis `/srv/anthias-sources` behalten,
   und den einmaligen Mountdienst installieren:

```bash
cd /root/apps/anthias-hub
bash scripts/install-media-mounts.sh
systemctl start anthias-hub-smb-mounts.service
journalctl -u anthias-hub-smb-mounts.service -n 30 --no-pager
```

Das Skript verweigert bestehende Units, verändert keine Docker-Dienste
und schreibt keine Credentials. Der Timer prüft ungefähr jede Minute.
Status erscheint ohne Geheimnisse unter
`/srv/anthias-sources/.mount-status.json` (im Container schreibgeschützt
als `/sources/.mount-status.json`).

## Docker-Mounts: ursprüngliche Deploy-Konfiguration beibehalten

Auf der vorhandenen VM weiter **compose.cd.yaml** plus den ursprünglichen
`HUB_COMPOSE_OVERRIDE` verwenden. Ergänze im externen Override
**nur** den zusätzlichen Quell-Mount am vorhandenen Hub-Service:

```yaml
services:
  anthias-hub:
    volumes:
      - type: bind
        source: /srv/anthias-sources
        target: /sources
        read_only: true
        bind:
          propagation: rslave
```

Das ist **nicht** der vollständige LAN-Override, wenn weitere
lokale Optionen bestehen. Vor dem Editieren sichern.

Der separate Worker nutzt die Datei `compose.folder-import.yaml`, die
neue Unter-Mounts ebenfalls per `rslave` erhalten kann. Anzugeben ist:

```bash
export MEDIA_SOURCE_HOST_PATH=/srv/anthias-sources
export HUB_UID=10001 HUB_GID=10001
export FOLDER_AUTO_PUBLISH=0
docker compose -f compose.cd.yaml -f "$HUB_COMPOSE_OVERRIDE"   -f compose.folder-import.yaml -p anthias-hub config -q
```

Wenn die Container schon vor der Override-Änderung gestartet waren,
müssen die betroffenen Container **kontrolliert neu erstellt** werden,
denn ein `docker compose restart` übernimmt neue Mounts nicht.
Das bestehende Deployment mit systemd-Timer/Healthcheck/Rollback
ist zu berücksichtigen; keine Basiskonfiguration oder Datenordner ersetzen.

**Wichtig:** CIFS-Unter-Mounts, die erst nach Containerstart angelegt werden,
müssen über den Host-Mount-Propagation-Status tatsächlich im Docker-Container
sichtbar werden. Bei fehlender Propagation die Container kontrolliert
neu erstellen. Nie pauschal die Root-Mountpropagation umstellen.

## Sicherheit, Status und Fehlerfälle

- Nur **private IPv4-Serveradressen**, kein URL- oder UNC-Redirect und keine
  arbiträren Hostpfade.
- Die Allowlist erlaubt **genau Server + Share**, nicht beliebige Server.
  Credentials bleiben außerhalb der Container unter `/etc/anthias-hub/secrets`.
- SMB wird `ro,nosuid,nodev,noexec` gemountet; keine Änderungen am Share.
- Alias-Verzeichnisse müssen Root gehören, Symlinks werden abgewiesen.
- Für jede Quelle meldet der Host `mounted`, `already-mounted`,
  `blocked`, `conflict` oder `error`.
- Der Worker prüft mit `FOLDER_REQUIRE_VERIFIED=1`, ob der bestätigte
  Hoststatus zu **genau dem im UI gespeicherten UNC-Pfad** gehört.
  Fehlende/stale Statusdaten verhindern automatische Veröffentlichung.
- Niemals einen vorhandenen Mount automatisch unmounten oder ersetzen.
  Den betreffenden Import-Worker bei einer geplanten Änderung pausieren,
  `umount /srv/anthias-sources/<alias>` kontrolliert ausführen,
  Mountdienst prüfen und Worker wieder starten. Besonders bei produktiven
  Pis zuvor Medien-/Playlist-Backup und Wiedergabe abnehmen.
- Fehlende SMB-Dateien führen weiterhin **nicht** zu automatischen
  Pi-Löschungen. Das ist eine gesonderte Produktionsabnahme.

## Einzel-Mount nach UI-Austragung sicher am Host entfernen

Vorher Sicherung, betroffene Vorlagen, Hostdienst und tatsächlichen
Mountpunkt prüfen. Den Folder-Import-Worker für den betroffenen Alias vor
dem Eingriff kontrolliert pausieren; nicht blind einen produktiven Share
aushängen. Als Root auf dem **Host** (nicht im Webcontainer):

```bash
alias_name=old-screen   # Beispiel; durch tatsächlich ausgetragenen Alias ersetzen
findmnt -M "/srv/anthias-sources/$alias_name" -o TARGET,SOURCE,FSTYPE,OPTIONS
# Nur wenn der richtige, nicht mehr genutzte CIFS-Mount eindeutig bestätigt ist:
sudo umount "/srv/anthias-sources/$alias_name"
findmnt -M "/srv/anthias-sources/$alias_name" || true
```

Vorhandene eigenständige `/etc/fstab`-Einträge bzw. systemd-Mountunits für
diesen Altpfad ebenfalls prüfen, sonst wird er unter Umständen wieder
eingehängt. **Keine** rekursiven `rm`-Befehle und kein automatisches
`umount` aus dem Hub. Den Standardstammordner nicht aushängen, solange
irgendein `default/...`-Template aktiv ist. Danach den Worker kontrolliert
wieder starten und Status/Playlists prüfen.

## Abnahme

1. Den vorhandenen `bistro`-Alias im UI mit dem tatsächlichen UNC-Pfad
   registrieren. Der Host prüft, ob der schon bestehende Mount übereinstimmt.
2. Eine zweite Quelle unter derselben zugelassenen SMB-Freigabe im UI
   hinzufügen und warten, bis „Mount vom Host bestätigt“ erscheint.
3. Unter Bibliothek die neue Quelle einer *Test*-Vorlage zuweisen.
4. Datei hinzufügen, Importstatus prüfen, individuelle Dauer ändern.
5. Erst nach Test-Pi-Abnahme `FOLDER_AUTO_PUBLISH=1` separat aktivieren.

Weitere Referenz: [Company Folder Workflow](company-folder-workflow.md)
und [Folder-backed Playlists](folder-backed-playlists.md).
