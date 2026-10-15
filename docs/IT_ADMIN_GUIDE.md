# IT-Administratorhandbuch — Anthias Hub

**Stand:** 13.10.2026 · **Umfang:** eigenständiger Docker-Dienst. Nicht der Anthias-Player und nicht die separate RSS-/Content-Webseite.

**VM-Lebenszyklus:** Die gegenwärtige gemeinsame Test-VM ist ausdrücklich keine Produktivvorlage. Für eine Neuinstallation siehe [reproducible-production.md](reproducible-production.md).

**Teststatus:** Der Betreiber hat die Geräteübersicht, API-Erreichbarkeit und reale Playlist-Anzeige eines Anthias-Pis bestätigt. Schreibende API-Operationen, Datei-Uploads und der Betrieb mit Marketing im Firmennetz sind weiterhin **nicht produktiv nachgewiesen**.

## 1. Systemübersicht und Verantwortlichkeit

~~~text
Owner/IT/Marketing/Viewer via lokaler SSH-Tunnel (Pilot); später HTTPS/VPN
                            |
                        Anthias Hub
                    Docker host :8765 (localhost)
                     | Config: users.json
                     | Daten: devices.json, audit.jsonl
                     |
             Anthias API v2 (HTTP)
                  /       |        \
                 Pi A     Pi B     Pi C
                  |       |        |
                 TV A    TV B     TV C
~~~

**Owner:** kombiniert IT-Geräteverwaltung und Marketing-Playlistrechte. **IT:** Geräte inventarisieren, URL/IP/Standort pflegen, API-Status und Inhalte lesend prüfen, **HDMI-CEC an/aus**, **Pi-Neustart/Shutdown** nach Bestätigung auslösen und die native Anthias-Adminseite zur Fehlersuche öffnen. **Marketing:** bestehende Playlists auf ausgewählten Geräten über die Hub-UI bearbeiten und bei Anzeigeproblemen nach Bestätigung **nur den Pi neu starten** (in der Bildschirmkachel unter „Hilfe bei Anzeigeproblemen“). **Viewer:** nur lesen. Alle Marketing-Accounts können derzeit sämtliche registrierten Geräte bearbeiten (keine Standort-spezifischen ACLs).

Einzelanwender können `bash scripts/setup-pilot.sh --solo` für ein Owner-Konto verwenden; bestehende IT-/Marketing-Installationen bleiben unverändert. Weitere Zugriffsmöglichkeiten: [network-access.md](network-access.md).

Der Hub ist **kein eigener Player, kein Reverse-Proxy zur vollständigen Anthias-Administration und kein Ersatz für Pi-Backups**. Die Original-Playlist und Medien bleiben auf dem jeweiligen Pi. Die Hub-Bibliothek speichert nur ihre selbst hochgeladenen Medien als wiederverwendbare Vorlagen unter `data/library/`; sie spiegelt keine bereits auf den Pis vorhandenen Medien. Eine optionale externe News-/Web-Anwendung wird lediglich als Website-Asset in Anthias eingebunden; sie ist weder Bestandteil noch Abhängigkeit des Hubs.

## 2. Hostinstallation und Dateiablage

Beliebiger separater Checkout, etwa /opt/anthias-hub oder /home/ADMIN/apps/anthias-hub auf dem Test-Docker-Host. **Nicht** in einem anderen Anwendungs-Checkout installieren. Compose-Projekt: anthias-hub; Dienst: anthias-hub; Image: anthias-hub:pilot.

| Pfad im Hub-Checkout | Inhalt | Git | Backup |
| --- | --- | --- | --- |
| compose.yaml, Dockerfile, app/, scripts/ | Versionierter Code | Ja | Versions-SHA notieren |
| .env | Secret Key, Netzwerkgrenzen, Cookie-Modus, UID/GID | Nein | Ja, streng vertraulich |
| config/users.json | Accounts mit scrypt-Hashes | Nein | Ja, vertraulich |
| data/devices.json | Geräteinventar (private IPs!) | Nein | Ja |
| data/audit.jsonl | Audit-Events von Hub-Schreibaktionen | Nein | Ja, Datenschutzfristen |
| data/library/ | Vorlagen und Originalmedien der Hub-Bibliothek | Nein | **Ja, inklusive Restore-Test und Kapazitätsplanung** |
| Datenbank/Medien auf jedem Anthias-Pi | Inhalte und Zeitpläne der Displays | Eigenes System | **Separat auf jedem Pi** |

Docker Compose bindet Host **127.0.0.1:8765** an Container-Port 8765; das ist Absicht. Die Daten-Mounts liegen unter ./config (im Container nur lesbar) und ./data (beschreibbar). Ein Worker mit mehreren Threads, read-only Root-Filesystem, keine zusätzlichen Datenbanken. Host-Netzwerk muss die Management-IPs der Pis erreichen.

### Ersteinrichtung

Voraussetzungen: Docker Engine mit Compose-Plugin, Git, OpenSSL, curl, ss und Netzwerkroute zum Anthias-Pi. **Auf einer neuen VM zuerst einen normalen Admin-User, SSH-Key für den Admin-Client (PowerShell oder Linux/macOS) und `~/.ssh/config`-Alias einrichten; Root-SSH und Passwort-Login erst nach geprüftem Key-only-Login deaktivieren**. Das komplette Vorgehen mit Hardening, Firewall und dem bestehenden `/root/apps`-Migrationshinweis steht unter [SSH-Zugriff und VM-Hardening](ssh-access.md). Für Deployments `~/apps/` des passenden Admins verwenden.

~~~bash
git clone https://github.com/ffworker/anthias-hub.git
cd anthias-hub
docker compose version
bash scripts/setup-pilot.sh
~~~

Das Setup erzeugt den Sitzungsschlüssel und getrennte IT-/Marketing-Konten. Nach einem abgebrochenen Passwortdialog oder versehentlich gelöschtem `config/users.json` lässt sich `bash scripts/setup-pilot.sh` erneut ausführen: Vorhandene `.env`, `data/` und gültige Konten bleiben erhalten; nur fehlende Rollen werden abgefragt. Zum gezielten Ändern bestehender Konten `bash scripts/setup-pilot.sh --reset-users` ausführen und die jeweilige Rückfrage bestätigen (Standard: Konto behalten). Zum Zurücksetzen der Konten **nicht** `.env` löschen. Eine beschädigte `users.json` wird nicht überschrieben; zuerst aus einem Backup wiederherstellen. Auf einem Host mit `ANTHIAS_HUB_IMAGE` verwendet das Skript `compose.cd.yaml` mit dem gepinnten Image statt eines neuen Pilot-Builds. Den `:main`-Auto-Deploy-Timer nicht auf Produktion aktivieren.

**Root-Betrieb:** Das Skript darf beim ersten Mal mit lokalen Root-Rechten (Konsole/`sudo`) gestartet werden – **das erfordert keine SSH-Root-Anmeldung**. Dann besitzt Host-root die `.env`, während der Container **nicht** als root, sondern unter UID/GID **10001:10001** läuft; `config/` und `data/` erhalten passende Eigentümer. Bei anderen Hostbenutzern werden deren UID/GID genutzt. Für die anschließende Wartung eine konsistente administrative Identität verwenden. Docker-Berechtigungen sind Root-äquivalent und dürfen nur vertrauenswürdigen Administratoren gegeben werden.

~~~bash
docker compose -p anthias-hub ps
curl -fsS http://127.0.0.1:8765/healthz
docker compose -p anthias-hub logs --tail=80
~~~

Antwort 'ok' auf /healthz prüft **nur den Webprozess**, nicht Anthias, Medienwiedergabe, HDMI oder den TV.

### Zugriff von Windows PowerShell oder Linux/macOS

Einmalig am Admin-PC einen eigenen Ed25519-Key und die beiden SSH-Aliase aus den **ausklappbaren** [PowerShell-/Linux-Anleitungen zur SSH-Konfiguration](ssh-access.md) einrichten. Danach im Terminal:

~~~bash
ssh signage-host           # normale Shell ohne root@ oder User/IP eintippen
ssh -N signage-host-tunnel # separates Fenster für beide lokalen Web-Tunnel
~~~

Dann **http://127.0.0.1:8765** (Hub) und, falls auf derselben VM installiert, **http://127.0.0.1:8085** (RSS2Slideshow) öffnen. Bei belegten Windows-Ports alternative lokale `-L`-Ports verwenden, siehe Anleitung. Direkter Zugriff über `http://DOCKER-HOST:8765` funktioniert **absichtlich nicht**. Keine Firewall-Freigabe für 8765/8085 erforderlich; der Pi braucht für die RSS-Webseite einen **separat freigegebenen internen** Endpunkt.

**COOKIE_SECURE=0** gilt nur für den lokalen HTTP-Test über SSH. Für Marketing-Arbeitsplätze: internes HTTPS mit Reverse-Proxy oder VPN, COOKIE_SECURE=1, Zugriffsbeschränkung auf berechtigte Clients, Admin-Zugriff begrenzen. Keine öffentliche Freigabe dieses Piloten.

## 3. Geräte hinzufügen und pflegen (IT)

1. IP und aktuelle Anthias-Version vom Gerät ermitteln, idealerweise stabile DHCP-Reservierung.
2. Als IT in Hub anmelden, eindeutige Geräte-ID, Anzeigename, feste **private IP** und Standort eintragen. DNS-Namen, Zugangsdaten in URLs und öffentliche IPs werden absichtlich abgelehnt.
3. Netzwerk-Allowlist ANTHIAS_ALLOWED_CIDRS in .env auf das **tatsächliche Management-VLAN** einschränken; danach Hub neu erstellen.
4. Gerätekachel: API erreichbar und Anzahl der Playlist-Einträge überprüfen. 'Playlist ansehen' zeigt die Inhalte read-only für IT.
5. Link 'Original Anthias' führt zum **eigenen, vollständigen Pi-Dashboard**. Dortiges Sicherheitsniveau und Zugriffsrechte gelten separat. Nur IT freigeben.
6. Unter **Gerätesteuerung** kann IT am jeweiligen Gerät **Bildschirm an/aus** (experimentelles HDMI-CEC), **Pi neu starten** oder **Pi herunterfahren** anfordern. Erst Bestätigungsfeld markieren; Shutdown verlangt zusätzlich die exakte Eingabe des Bildschirmnamens. Nach Reboot/Shutdown den Gerätestatus beobachten, nicht blind erneut klicken. Shutdown kann eine manuelle Einschaltung vor Ort erfordern. Marketing sieht stattdessen nur den eingeklappten **Hilfe bei Anzeigeproblemen**-Neustart, keine HDMI-/Shutdown-Funktionen; Viewer hat keine Steuerbefehle. Die Steuerung sendet **POST** an erlaubte Anthias-v2-Pfade, nutzt Hub-Rollen, CSRF und Audit-Log, **keine Shell/SSH-Befehle**. Nur ein neuer Anthias-Stand mit entsprechendem HDMI-CEC-Treiber kann die Anzeige wirklich schalten; bei HTTP 503/502, fehlendem CEC-Adapter oder aktivem Display-Zeitplan das Original-Anthias-Gerät prüfen. Die native Anthias-Authentifizierung kann zusätzliche Berechtigungen verlangen. **Zuerst am Test-Pi und echtem Monitor ausprobieren.** Details: [Anthias API](https://anthias.screenly.io/api/) und [Display Schedule / CEC-Limits](https://anthias.screenly.io/docs/display-schedule/).
6. 'Entfernen' löscht lediglich die Hub-Registrierung; die Pi-Playlist bleibt unangetastet.

Die Statusanzeige basiert auf GET /api/v2/assets. Der Player kann erreichbar sein, obwohl das TV schwarz ist oder gerade ein anderer Inhalt läuft. Live-TV-Screenshot ist **nicht** enthalten.

**Marketing-Workflow:** nach explizitem Test und separatem Pi-Backup als Marketing anmelden → Gerät wählen → einzelne Playlist über Webformulare verwalten. URL, Bild oder Video hinzufügen, umbenennen, aktivieren/deaktivieren, sortieren und löschen. Änderungen erfolgen sofort auf dem jeweiligen Pi. Keine Gruppenaktionen, Terminplanung oder Entwürfe im Hub. Medienupload, Sortierung und Löschung sind erst nach echtem Pi-Test freizugeben.

**Wichtige Netzgrenze:** Ohne ACLs kann ein Client, der den Pi direkt per HTTP erreicht, die Hub-Rollen umgehen. Anthias-Pi-Managementports ausschließlich vom Hub-Host und autorisierten IT-Rechnern erreichbar machen. Die Hub-Rollen sind keine Ersatz-Firewall.

## 4. Regelbetrieb und Monitoring

### Täglich / auf Störungsmeldung

~~~bash
cd /PFAD/ZU/anthias-hub
docker compose -p anthias-hub ps
curl -fsS http://127.0.0.1:8765/healthz
docker compose -p anthias-hub logs --tail=80
~~~

Die Geräte-/Playlistansicht pro Pi prüfen; für echten Displayzustand **Pi und TV separat** kontrollieren. Wöchentlich Host-Speicher, Containerlogs, Backups und inventarisierte IPs prüfen. Monatlich Software-/Python-Base-Image-Updates und Zugriffsregeln kontrollieren. Kein unbeaufsichtigtes Upgrade zur Geschäftszeit.

Die Datei data/audit.jsonl protokolliert Zeit, Benutzer, Aktion, Geräte- und Asset-ID. Sie ist **keine revisionssichere Audit-Datenbank** und enthält keine vollständigen Vorher-/Nachher-Werte. Aufbewahrung, sichere Übertragung und eventuelle Rotation intern regeln. Niemals Geheimnisse oder private Geräteinformationen in öffentliche GitHub-Issues posten.

## 5. Backup vor jedem Upgrade

Das Archiv enthält **sensible Benutzerhashes, Session-Secrets und interne Geräteadressen**. Deshalb nur auf einem geschützten Admin-Host, mit umask 077 und gesicherter Off-Host-Kopie. Folgende Befehle setzen root als Administrator voraus:

~~~bash
cd /PFAD/ZU/anthias-hub
umask 077
install -d -m 700 /root/anthias-hub-backups
docker compose -p anthias-hub stop
tar -czf "/root/anthias-hub-backups/hub-$(date +%Y%m%d-%H%M%S).tar.gz" .env config data
docker compose -p anthias-hub start
git rev-parse HEAD
~~~

Ausfallfenster für konsistente Dateiablage vorher absprechen. Backup wiederholt **nicht** das Pi-Backup: Playlist, Media-Dateien, Scheduling und der Anthias-eigene Datenspeicher liegen auf **jedem Pi**. Diese dort separat sichern, bevor Marketing Schreiboperationen testet.

### Restore

1. Aktuellen Hostzustand/Commit/Backup-Stand dokumentieren; Hub stoppen.
2. Git-Code auf den nachweislich zum Backup passenden Stand bringen, möglichst in einem separaten Checkout statt blindem 'git reset --hard'.
3. Vertrauliches Archiv in den richtigen Checkout restaurieren. Eigentümer von ./config und ./data gegen HUB_UID/HUB_GID in .env prüfen.
4. 'docker compose -p anthias-hub up -d --build', /healthz, Login, Geräteinventar und Pi-Verbindung prüfen.
5. Bei gelöschter Playlist/Datei auf einem Pi: Wiederherstellung **am Pi**, nicht aus dem Hub-Archiv.

Eine regelmäßig getestete Rücksicherung und eine verschlüsselte Off-Host-Kopie sind Pflicht für einen verlässlichen Produktivbetrieb.

## 6. Accounts und Passwortrotation

Accounts sind statisch. Das CLI ersetzt beim erneuten Anlegen desselben Usernamens den alten Hash. Aus dem Repo-Verzeichnis, wenn Dateirechte passen:

~~~bash
cd /PFAD/ZU/anthias-hub
uid=$(sed -n 's/^HUB_UID=//p' .env)
gid=$(sed -n 's/^HUB_GID=//p' .env)
docker run --rm -it --user "$uid:$gid" --mount "type=bind,source=$(pwd)/config,target=/config" --entrypoint python anthias-hub:pilot -m scripts.create_user /config/users.json marketing marketing
~~~

Für IT die letzten beiden Argumente in 'it it' ändern; optional 'viewer viewer'. Passwort nur interaktiv eingeben, keine Klartextwerte in .env, Terminalhistory, README oder Tickets.

**Hinweis zur Sitzungssicherheit:** Ein reiner Passwortwechsel widerruft bereits signierte Sessions möglicherweise nicht. Für einen Sicherheitsvorfall zusätzlich den APP_SECRET_KEY in .env ändern, den Container neu erstellen (nicht bloß 'restart') und die Anmeldung aller Benutzer erzwingen.

## 7. Aktualisierung und Rückweg

> **Achtung: Die folgenden Befehle aktualisieren ausschließlich den lokal gebauten Test-Piloten mit `compose.yaml`.** Die aktuelle VM ist wegwerfbar. Für einen **neuen, reproduzierbaren Produktiv-Host**: [Release-/Neuinstallations-Runbook](reproducible-production.md) mit freigegebenem SHA-Image, `compose.cd.yaml`, manueller Bereitstellung, Backup, Verifikation und Rückweg. **Keine** `:main`-Auto-Deploy-Timer auf Produktivsystemen. Auch das Konto-/Passwort-CLI in Abschnitt 6 verwendet bisher das lokale `anthias-hub:pilot`-Image; bei einem neuen Host mit gepinntem GHCR-Image die entsprechende freigegebene Image-Referenz für den manuellen `docker run`-Aufruf verwenden.


Nur im **Anthias-Hub-Checkout**, niemals im Repo einer anderen Anwendung:

~~~bash
cd /PFAD/ZU/anthias-hub
git status --short --branch
git rev-parse HEAD
# ZUERST: Backup aus Abschnitt 5 erstellen
git pull --ff-only
docker compose -p anthias-hub up -d --build
docker compose -p anthias-hub ps
curl -fsS http://127.0.0.1:8765/healthz
~~~

`docker compose pull` ist hier **nicht** der Update-Befehl. `anthias-hub:pilot` ist ein lokal gebautes Image; Docker sucht beim Pull sonst fälschlich auf Docker Hub und meldet „pull access denied“. Das veröffentlichte GHCR-Image heißt `ghcr.io/ffworker/anthias-hub:latest` und ist nicht die Image-Referenz dieser Pilot-Compose-Datei. Keine Registry-Anmeldedaten nötig, um den lokalen Build zu aktualisieren.

Vorherige Git-SHA im Änderungsprotokoll notieren. Kein 'docker compose down -v', kein 'docker system prune', kein blindes 'git reset --hard'. Bei Regression vorherigen getesteten Commit in separatem Checkout vorbereiten und Hub-Datenrestore gezielt ausführen. **Ein Hub-Rollback macht zuvor durchgeführte Pi-Playliständerungen nicht rückgängig!**

Bei Git-Meldung 'dubious ownership': Original-Repo-Eigentümer und Admin-Kontext prüfen; nicht pauschal alle Pfade als safe markieren.

## 8. Troubleshooting-Tabelle

| Symptom | Erste Prüfung | Einordnung |
| --- | --- | --- |
| Windows kommt nicht auf HOST:8765 | localhost-/healthz auf Host, SSH-Tunnel | Lokalbindung ist Absicht; kein Firewall-Port öffnen |
| Login schlägt fehl | Users-Datei, Passwort, Browser-Cookie, HTTP/HTTPS | Testtunnel COOKIE_SECURE=0; öffentliches HTTPS benötigt 1 |
| Nach Root-Setup Permission denied | ls -ld config data; UID/GID in .env | Containerzugriff 10001:10001, nicht chmod 777 |
| Geräte offline | Route/Firewall Host→Pi, GET /api/v2/assets, Pi-Status | Kein Live-Screen-Status |
| Playlist lesbar, Schreibaktion scheitert | Hub-Logs, reale Pi-API-Version, HTTP-Code | Schreiben/Upload separat gegen Test-Pi validieren |
| Website hinzufügen meldet HTTP 500 | Pi-Logs und Playlist sofort neu laden; Anthias-Version notieren | Ältere Anthias-Versionen können das Asset trotz 500 erstellt haben ([Upstream #2190](https://github.com/Screenly/Anthias/issues/2190)). Der Hub legt neue Assets deaktiviert an und aktiviert sie danach per PATCH; bei Fehlern nicht blind erneut senden. Auf dem Test-Pi prüfen. |
| Inhalt fehlt auf TV | Pi-Zeitplan, Aktivierung, Dauer, URL, Viewer, HDMI | Hub kann TV-Bild nicht direkt feststellen |
| Neue Logins plötzlich ungültig | APP_SECRET_KEY geändert? | Session-Signaturen hängen am Key |
| Upload scheitert | Dateityp/Signatur, Größenlimit 50 MB, Anthias-Schema | Keine automatische Malware-Prüfung |
| Änderungen nach Restart verschwunden | Sicherstellen, dass ./data und ./config richtig gemountet sind | Daten in Bind-Mounts, nicht im Image |
| Vermuteter Missbrauch | Hub-Zugriff beschränken, Audit/Logs sichern | Credentials/Session-Key erneuern; Pi separat überprüfen |

Timeout bei einer Schreibaktion bedeutet nicht zwingend, dass sie nicht angekommen ist; Playlist erst neu laden, bevor ein zweiter Schreibversuch folgt.

## 9. Kriterien für Freigabe an Marketing

HTTPS + Secure-Cookies + Firewall-ACLs, getrennte sichere Accounts, geschütztes Backup **des Hubs und jedes Pis**, geprüfte Restore-Strategie, Tests auf *tatsächlich installierter Anthias-Version* für Hinzufügen/Upload/Ändern/Sortieren/Löschen, Verantwortliche für Betrieb/Änderungen, Audit-Datenschutz/Retention und ein nachvollziehbarer Rollback-Prozess. Ein erfolgreicher HTTP-GET-Test ist dafür nicht ausreichend.
