# Automatisches Deployment auf der Hub-VM

> **Nur Test-/Staging-VM!** Dieses Dokument beschreibt den **bestehenden**, absichtlich auf `:main` folgenden Updater. Die aktuelle VM ist ein Wegwerf-Testsystem. Für die später frisch installierte Produktiv-VM den Timer **nicht installieren/aktivieren**. `scripts/auto_deploy.py` erzwingt `:main` unabhängig von `ANTHIAS_HUB_IMAGE` in `.env`; ein bloßer Image-Pin genügt deshalb **nicht**. Produktiv stattdessen die [reproduzierbare Installation mit manuell freigegebenem SHA-Image](reproducible-production.md) verwenden. Automatische freigegebene Releases sind noch nicht implementiert.


GitHub Actions testet und veröffentlicht nach erfolgreichem Push auf `main` das öffentliche `ghcr.io/ffworker/anthias-hub:main`. Die VM fragt die Registry alle 15 Minuten **ausgehend** ab. GitHub erhält keinen SSH-Zugang ins Servernetz. Der erste Wechsel vom lokal gebauten `anthias-hub:pilot` auf das veröffentlichte Image erfolgt bewusst manuell.

## Einmalig auf der VM

Alle Befehle **im bestehenden Anthias-Hub-Checkout** als der Account ausführen, der bisher Docker Compose bedient. Nicht `scripts/setup-pilot.sh` erneut starten und keine `.env`, `config/` oder `data/` ersetzen. Vorher Hub-Daten (und vor Schreibtests separat die Pi-Playlists) sichern. Beispiel für die Hub-Daten, Ablage außerhalb des Checkout wählen und vor fremdem Zugriff schützen:

```bash
cd /PFAD/ZUM/anthias-hub
git pull --ff-only
umask 077
backup="$HOME/anthias-hub-before-cd-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$backup" .env config data
docker compose -f compose.cd.yaml -p anthias-hub pull
docker compose -f compose.cd.yaml -p anthias-hub up -d
docker compose -f compose.cd.yaml -p anthias-hub ps
curl -fsS http://127.0.0.1:8765/healthz
```

Danach im Browser Login, Geräteliste und Playlist **lesend** prüfen. `healthz` beweist nur den Webprozess, nicht die Pi-API oder den TV. Falls der erste Wechsel fehlschlägt, zum bisherigen lokalen Pilot-Image zurück:

```bash
docker compose -p anthias-hub up -d --no-build
```

Erst wenn der manuelle Wechsel funktioniert, Timer installieren. Der ausführende Account muss schon Docker-Zugriff und Schreibrecht auf Checkout und `data/` besitzen; Docker-Zugriff ist praktisch Root-Zugriff. Keine neuen Gruppenmitgliedschaften nur für diesen Zweck vergeben. Bei Root-Installation `root` verwenden, der Container läuft trotzdem mit `HUB_UID/HUB_GID` unprivilegiert.

```bash
sudo bash scripts/install-auto-deploy.sh "$(id -un)"
systemctl status anthias-hub-cd.timer
```

Der Installer legt genau zwei systemweite Units an und weigert sich, vorhandene zu überschreiben. Er verändert weder Zugangsdaten noch Pi-Playlists. Der Timer ruft `scripts/auto_deploy.py` auf: Er prüft die vorhandene CD-Compose-Installation, holt `:main`, vergleicht die Docker-Image-ID, startet nur bei Änderung neu und wartet auf `/healthz`. Bei Fehler stellt er die vorherige Image-ID wieder her, prüft deren Health und merkt sich die abgelehnte Image-ID in `data/.cd-rejected`, damit ein Fehler nicht alle 15 Minuten erneut deployed wird. **Bei fehlgeschlagenem Rollback sofort eingreifen.** Eine neue Image-ID wird wieder versucht. Das Script aktualisiert **nicht** seinen eigenen Checkout; neue CD-Script-Versionen benötigen weiterhin `git pull --ff-only` auf der VM.

## Betrieb

```bash
systemctl list-timers anthias-hub-cd.timer
journalctl -u anthias-hub-cd.service -n 60 --no-pager
sudo systemctl start anthias-hub-cd.service   # Check sofort auslösen
sudo systemctl disable --now anthias-hub-cd.timer  # Auto-Deploy stoppen
```

Die Zeit zwischen erfolgreichem GitHub-Build und VM-Update beträgt gewöhnlich bis zu 17 Minuten. Docker-Zugriff, Containerstart und Pi-Zugriff müssen separat überwacht werden; ein grünes `healthz` ist keine Inhaltsfreigabe. Wer Änderungen nur nach Freigabe ausrollen möchte, sollte den Timer deaktivieren und die CD-Compose-Datei manuell starten. Bei Ausfall der Registry bleibt das bereits laufende Image unverändert. Backup und Restore der Hub-/Pi-Daten bleiben unabhängig vom Image-Rollback.

**Produktiv-Migration:** Bei einer bestehenden Installation den Timer zuerst mit `sudo systemctl disable --now anthias-hub-cd.timer` anhalten, dann die Pin-/Backup-Anleitung in [reproducible-production.md](reproducible-production.md) befolgen. Keine automatische `:main`-Aktualisierung mit einem Release-Pin vermischen.

**Wichtig:** Diese Dateien im Git-Repo richten keinen Timer auf deiner VM ein. Ohne VM-Zugang konnten wir die tatsächliche Migration, Rechte, Docker-Compose-Version und Live-Health nicht prüfen.