# PROD v2 – Freigabe und umschaltbarer Rollout

> **Noch nicht freigegeben.** Die Änderungen liegen im DEV-Branch und werden zunächst in Draft-PR **#73** gesammelt. Die produktive Installation auf GH-PiHub darf erst nach persönlicher Prüfung/Freigabe, Merge von #73 nach `main` und erfolgreichem Build umgestellt werden.

## Vor dem Merge

1. DEV über `http://127.0.0.1:8766` vollständig abnehmen: Login/CSRF/Rollen, Playlist-Anlegen und -Löschen, bestehende Zuordnungen, Quellenstatus, SMB-Test und automatischer 4-GiB-Teileimport, Zeitpläne und manuelle Inhalte.
2. Prüfen: `DEV_AUTO_PUBLISH=0` und `DEV_PRUNE_MISSING=0`; die DEV-Installation hat **eigene** `config/`-, `data/`-, `.env`- und Image-Daten. Die produktiven Pis sind keine DEV-Testziele.
3. Snapshot/Backup von produktiver `.env`, `config/`, `data/`, Quell-Mount-Konfiguration und aktuellen Image-Tags anlegen. Originale Zugangsdaten bleiben ausschließlich auf dem Server.
4. Entscheidung dokumentieren, erst dann #73 nach `main` mergen. CI muss das Image `ghcr.io/ffworker/anthias-hub:sha-<FULL-40-HEX-COMMIT>` erfolgreich veröffentlichen.

## Nach Freigabe – nur im produktiven Checkout

Im bestehenden **Produktionsordner** arbeiten, **nicht** unter `anthias-hub-dev`. Die folgenden Schritte beziehen sich auf den bereits eingesetzten Pull-CD-Modus mit `compose.cd.yaml` **und** der bestehenden lokalen Override-Datei.

1. Vor Änderung prüfen: `HUB_DEVELOPMENT_MODE=0`, `DEV_SMB_UI=0` und `FOLDER_AUTO_PUBLISH=0` (oder separat fachlich genehmigter Publishing-Betrieb). Der DEV-SMB-Browserconnector wird **nicht** mit den produktiven Host-Mounts vermischt.
2. Ein vollständiges, wiederherstellbares Backup der produktiven `.env` und der Persistenzverzeichnisse erstellen. Die produktive `.env` enthält Secrets und gehört **nie** ins öffentliche Git-Repo.
3. **Nur nach bestätigter Build-SHA**: in der bestehenden `.env` `ANTHIAS_HUB_IMAGE=ghcr.io/ffworker/anthias-hub:sha-<FULL_SHA>` und `HUB_WORKFLOW_V2=1` setzen. Bestehende SMB-, Cookie-, Proxy-, Account- und Compose-Einstellungen unverändert lassen.
4. Compose-Konfiguration und Image **vor** Container-Neustart kontrollieren:

```bash
cd /root/apps/anthias-hub  # ggf. bestehenden echten Produktionspfad verwenden
OVERRIDE=$(sed -n 's/^HUB_COMPOSE_OVERRIDE=//p' .env)
test -n "$OVERRIDE" && test -f "$OVERRIDE" || { echo "STOP: Override fehlt"; exit 1; }
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub config --quiet
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub pull anthias-hub
```

5. Wenn der Pin korrekt auf das freigegebene SHA zeigt, **nur** den Web-Hub neu erstellen (Importer, Datenbank/Dateien, Caddy, RSS2Slideshow und Pis nicht neu starten):

```bash
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub \
  up -d --no-build --no-deps --force-recreate anthias-hub
curl -fsS http://127.0.0.1:8765/healthz
```

6. Im Browser richtige UI-Kennung und Build-SHA, bestehenden Login und Status aller Bildschirme sowie Test-Playlist, Zuordnungen, Medien, Quelle, Zeitplan und Import prüfen. **Keine Test-Pi-Löschaktion** bei diesem Smoke-Test.

### Rollback

Wenn Funktionsprüfungen scheitern: vorher gesicherte `.env` (damit **altes Image-SHA und alter `HUB_WORKFLOW_V2`-Wert**) wiederherstellen und denselben `docker compose … up -d --no-build --no-deps --force-recreate anthias-hub`-Befehl ausführen. Persistenz **nicht** löschen, keine `down -v`-, `--remove-orphans`- oder Neubuild-Kommandos verwenden. Falls durch manuelle Bearbeitung Daten geändert wurden, ist ein separater Datenabgleich nötig – nur das Image zurückzusetzen macht solche Änderungen nicht rückgängig.

**Schalter:** `HUB_WORKFLOW_V2` aktiviert die neue Navigation/Steuerzentrale ausschließlich im gewählten Image. `main`/GHCR und der Produktivhost werden bis zur fachlichen Freigabe **nicht** vom DEV-Merge verändert.
