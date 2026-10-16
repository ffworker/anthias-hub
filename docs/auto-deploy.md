# Anthias Hub: automatische Updates auf der Test-VM

**Genau ein automatischer Kanal: `ghcr.io/ffworker/anthias-hub:latest`.** Nach einem erfolgreichen `main`-Build veröffentlicht GitHub Actions dieses Image. Der vorhandene systemd-Timer prüft es ungefähr alle 15 Minuten. Keine Alpha-/Beta-/Stable-Kanäle; pro Build bleibt zusätzlich ein Git-SHA-Image für die Nachvollziehbarkeit.

## Deine bestehende VM einmalig umstellen

Auf der VM, im bestehenden Hub-Checkout; **keine Accounts oder Laufzeitdaten zurücksetzen**:

```bash
cd ~/apps/anthias-hub
sudo systemctl stop anthias-hub-cd.timer
git pull --ff-only
umask 077
tar -czf "$HOME/anthias-hub-before-latest-$(date +%Y%m%d-%H%M%S).tar.gz" .env config data
```

Ändere in der privaten `.env` die **bestehende** Zeile zu `ANTHIAS_HUB_IMAGE=ghcr.io/ffworker/anthias-hub:latest` (nicht doppelt eintragen), damit auch **manuelle Compose-Aufrufe** `:latest` benutzen. Alle anderen Einstellungen bleiben unverändert. Für deine VM muss der bereits konfigurierte `HUB_COMPOSE_OVERRIDE` weiter auf die tatsächlich vorhandene LAN-Datei verweisen, zum Beispiel `/etc/anthias-hub/compose-lan.yaml`.

Der neue Updater akzeptiert die bereits laufende alte `ghcr.io/ffworker/anthias-hub:sha-<40_HEX>`-Version sowie das frühere `:main` als **einmalige Migrationsbasis**. `anthias-hub:pilot` erfordert weiterhin eine manuelle Migration und wird nicht automatisch überschrieben.

```bash
# Vor dem Start prüfen:
docker ps --filter name=anthias-hub
curl -fsS http://127.0.0.1:8765/healthz

# Timer wieder aktivieren und die Prüfung sofort auslösen:
sudo systemctl reset-failed anthias-hub-cd.service
sudo systemctl start anthias-hub-cd.timer
sudo systemctl start anthias-hub-cd.service

sudo journalctl -u anthias-hub-cd.service -n 25 --no-pager
docker ps --filter name=anthias-hub
curl -fsS http://127.0.0.1:8765/healthz
```

Erwartet: `Anthias Hub deployment: updated` oder `unchanged`. Bei einem Wechsel muss danach `ghcr.io/ffworker/anthias-hub:latest` unter `docker ps` erscheinen. Prüfe zusätzlich die erhaltenen Portbindungen, Login und Playlist. Das Script verändert weder `.env` noch `config/` oder `data/` (abgesehen von der eigenen Ablehnungs-Markierung im Fehlerfall).

## Funktionsweise und Grenzen

Der Timer zieht `:latest` aus GHCR (ohne eingehendes SSH von GitHub), vergleicht die Image-ID und erstellt den Container **nur bei geändertem Image** neu. Anschließend prüft er `/healthz`. Bei Fehlschlag versucht er das alte Image wiederherzustellen und markiert die fehlgeschlagene Image-ID, um erneute Fehlversuche zu vermeiden. **Falls das Rollback selbst fehlschlägt, sofort eingreifen.**

Die optionale Compose-Datei aus `HUB_COMPOSE_OVERRIDE` gilt für `ps`, `pull`, `up` und Rollback. `git pull --ff-only` ist **nicht** Bestandteil des Timers: Änderungen am Updater selbst oder den Host-Skripten erfordern weiterhin einen gelegentlichen manuellen Pull; neue App-Versionen im Image dagegen nicht.

```bash
systemctl status anthias-hub-cd.timer --no-pager
systemctl list-timers anthias-hub-cd.timer
sudo journalctl -u anthias-hub-cd.service -n 40 --no-pager
sudo systemctl start anthias-hub-cd.service  # Prüfung sofort
sudo systemctl stop anthias-hub-cd.timer     # Auto-Deploy pausieren
```

Verwende für **manuelle** Hub-Deployments nur `compose.cd.yaml` mit genau demselben externen Compose-Override. Ein Start mit `compose.yaml` würde wieder das lokale `:pilot`-Image verwenden. Die Registry kann ausfallen, ohne dass das laufende Image dadurch gelöscht wird. `/healthz` beweist nur die Web-Erreichbarkeit, nicht das tatsächliche TV-Bild. Dieser automatisch bewegte Kanal ist für die Test-/Staging-VM gedacht; für einen späteren Produktivhost den Timer deaktivieren und ein geprüftes SHA-/Digest-Image pinnen.

## Routine manual Hub commands

Always use the **pull-based** Compose file and the same private override
configured for automatic deploy. `restart` does not reload changed `.env`
values; use `up --force-recreate` for those changes:

```bash
cd ~/apps/anthias-hub
OVERRIDE=$(sed -n 's/^HUB_COMPOSE_OVERRIDE=//p' .env)
test -n "$OVERRIDE" && test -f "$OVERRIDE" || exit 1

# Ordinary restart:
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub restart anthias-hub

# After .env/override edits (Hub only):
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub up -d --no-build --no-deps --force-recreate anthias-hub
```

Use these examples for the current override-based test VM. A fresh
installation without `HUB_COMPOSE_OVERRIDE` must omit the second `-f`
instead of inventing a file. Do **not** use plain `docker compose up -d
--build` on an auto-deployed host.

## Optional HTTPS with host-local Caddy

For a VM without an enterprise certificate authority or public certificate,
see [Caddy + its own HTTPS CA](network-access.md#d-optional-caddy--your-own-internal-https-ca-no-external-ca-required).
Caddy runs independently as a host systemd service and handles TCP/443.
Distribute only its verified public `root.crt` to authorized clients. Keep
`COOKIE_SECURE=0` until a trusted HTTPS login works; then set it to `1`,
retire the LAN TCP/80 Docker publish via the **existing external override**
and, only when Caddy is the sole trusted backend entry point, use
`TRUSTED_PROXY_COUNT=1`. Pause the Hub CD timer only during the coordinated
Compose change and resume afterward. Never remove or rename
`HUB_COMPOSE_OVERRIDE` just to close port 80. The updater touches neither
Caddy's configuration nor its CA/private keys: these need separate encrypted
backups and restoration procedures.

### Aktueller Test-VM-Stand

HTTPS über hostseitigen Caddy funktioniert; der Hub nutzt
`COOKIE_SECURE=1`, `TRUSTED_PROXY_COUNT=1` und ausschließlich
`127.0.0.1:8765`. Die zusätzliche LAN-Port-80-Bindung ist entfernt.
Die Windows-CA-Vertrauensstellung wurde am Admin-PC getestet; weitere
Clients benötigen den verifizierten CA-Root. Der `:latest`-Updater und
RSS2Slideshow sind separate Dienste.

Für manuelle Neustarts und `.env`-Änderungen gelten **ausschließlich**
die Befehle unter „Routine manual Hub commands“ oben.

## Optional host-local Compose configuration

For a separately approved LAN bind or TLS deployment, set `HUB_COMPOSE_OVERRIDE=/ABSOLUTE/PATH/TO/override.yaml` in the **private** `.env` (see [network-access.md](network-access.md)). The updater includes it in `docker compose -f compose.cd.yaml -f ...` for status, pull, update **and rollback**, and stops if the file is missing. The setup script also honors this setting. Manual commands in this guide require the same additional `-f` argument if an override is active; do not run base-only `up` on an overridden service. This option does not make the `:latest` updater production safe.
