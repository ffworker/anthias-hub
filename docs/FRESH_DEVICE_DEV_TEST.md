# Anthias Hub – frischer Testaufbau (separat vom Live-Hub)

> **Entwicklungsstand, nicht produktiv deployen.** Der bestehende GH-PiHub,
> seine `.env`, sein Compose-Override, der Folder-Importer, die Pis und
> RSS2Slideshow werden **nicht** geändert. Hier wird auf einem **neuen
> Test-Host** mit einer **neuen Anthias-Pi-Installation** gearbeitet.

## Was wir bewusst vereinfacht haben

Das alte Verhalten behandelte die feste Netzwerkordner-Zuordnung wie eine
unüberwindbare Schreibsperre: „Der Bildschirm wird bereits verwaltet“.
Das hat Tests an einem neuen Pi unnötig erschwert.

Mit **nur in der separaten Testinstallation aktivem**
`HUB_DEVELOPMENT_MODE=1` gilt:

- Die Netzordner-Zuordnung und ihre tatsächlichen Sync-/Publish-Status bleiben
  sichtbar. Die Pi-Inhaltsliste ist im Testmodus direkt geöffnet.
- **Inhalte hinzufügen, bearbeiten, sortieren, (de)aktivieren, entfernen und
  Pi-Zeitpläne ausprobieren** ist trotz Zuordnung erlaubt.
- Beim Zuweisen eines Bildschirms, der noch in einer anderen
  Netzwerkordner-Playlist steckt, übernimmt die Testinstanz die Zuordnung.
  Es existiert danach weiterhin **genau eine** zugeordnete Ordner-Playlist.
  Das Umhängen der Zuordnung schreibt **nichts** auf den Pi.
- Im normalen Modus bleiben die bisherigen Sperren und die nur lesbare
  Managed-Ansicht erhalten.

**Nicht entfernt:** Anmeldung und Rollen, CSRF-Schutz, sichere lokale
Dateipfade, Dateityp-/Größenprüfung, bestätigte Löschaktionen und
Freigabegrenzen zum Anthias-Player. Die Experimentierfreigabe wird in
`compose.dev.yaml` ausdrücklich eingeschaltet, nicht global in `main`.

## Vorbereitung – auf dem NEUEN Test-Host

Voraussetzungen: Debian/Ubuntu mit Docker Engine, Compose Plugin, Git,
`curl` und `openssl`. Außerdem ein **separater/frischer Anthias-Pi**,
auf den du testweise schreiben darfst. Niemals die produktiven IPs als
Testziel registrieren.

```bash
git clone https://github.com/ffworker/anthias-hub.git anthias-hub-test
cd anthias-hub-test
git switch dev/fresh-device-workflow-20261112

# Nur auf dem neuen Host: eigene .env, eigene Benutzer, eigene Daten.
bash scripts/setup-pilot.sh --solo

# Lokale Testquelle – KEIN SMB-Mount und keine Firmenbilder nötig.
mkdir -p dev-sources/demo
# Lege später 1–2 eigene Test-PNG/JPG-Dateien in dev-sources/demo ab.

# Schaltet den experimentellen Editor und den separaten Importer EIN.
bash scripts/dev-sandbox.sh start
bash scripts/dev-sandbox.sh status
```

Der Test-Hub hört auf **127.0.0.1:8765**. Für den Browser auf deinem PC
nutze einen SSH-Tunnel vom PC zum neuen Host:

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 USER@TESTSERVER
```

Dann `http://127.0.0.1:8765` öffnen und mit dem selbst erstellten
Testkonto anmelden. Im Bildschirmbereich steht **„TESTSYSTEM · Bearbeiten
erlaubt“**; nur dann ist der Testmodus wirklich aktiv.

> Der Einstieg mit `setup-pilot.sh` startet zunächst kurz das normale
> Pilot-Compose. `dev-sandbox.sh start` erstellt es danach mit der
> Test-Override-Datei neu. **Nur auf dem frischen Host durchführen.**
> Der Sandbox-Helfer weigert sich außerdem, erkannte GHCR-/CD-Installationen
> zu verändern.

## Testablauf für morgen

1. **Frischen Pi registrieren:** Unter „Bildschirme“ einen neuen, privaten
   Anthias-Player registrieren und die Erreichbarkeit prüfen. Nur das neue
   Testgerät verwenden.
2. **Ordner-Playlist anlegen:** Unter „Playlists“ eine Playlist
   „Demo-Ordner“ mit Quelle `demo` anlegen. Falls `demo` noch nicht in
   der Auswahl steht, `bash scripts/dev-sandbox.sh status` und die
   `./dev-sources/demo`-Bind-Mounts prüfen.
3. **Ziel setzen:** In „Quelle & IT“ den neuen Pi auswählen und speichern.
   Wenn er bereits einer anderen Test-Playlist zugeordnet ist, übernimmt
   die Testinstanz ihn automatisch. Danach zeigt die Bildschirmseite
   weiterhin **„Netzwerkordner-Anzeige“**, aber mit Testmodus und
   geöffnetem Pi-Editor.
4. **Manuellen Editor ausprobieren:** Ein Testbild hinzufügen, Titel/Dauer
   ändern, anordnen, pausieren und Zeitplan setzen. Es darf **kein**
   „bereits verwaltet“ / HTTP 409 mehr durch die Playlist-Zuordnung geben.
5. **Ordnerimport prüfen:** Eine neue eigene PNG/JPG-Datei unter
   `dev-sources/demo` ablegen. Der getrennte Importer läuft in diesem
   Testsetup standardmäßig **alle 60 Sekunden**, damit Änderungen schnell
   sichtbar werden. In der Playlist sollte das Bild erscheinen, **noch
   nicht automatisch auf dem Pi**.
6. **Gezielte Pi-Synchronisierung testen (erst nach Prüfen des Testziels):**
   In der **Test-.env**, niemals in Produktion, `DEV_AUTO_PUBLISH=1`
   ergänzen; anschließend nur den Importer mit den beiden Compose-Dateien
   neu erstellen:
   ```bash
   docker compose -p anthias-hub -f compose.yaml -f compose.dev.yaml \
     up -d --no-deps --force-recreate anthias-folder-import
   ```
   Beim nächsten Lauf werden ausschließlich die zugeordneten Hub-Inhalte
   zum **frischen Test-Pi** veröffentlicht. Eine in der Hub-Vorlage
   vorhandene, aber auf dem Test-Pi fehlende Hub-Datei wird automatisch
   nachgeliefert. **Manuell hinzugefügte Testmedien** können daneben
   existieren: Die Sync ist keine pauschale „Pi leeren und neu befüllen“-
   Aktion.
7. **Später den 30-Minuten-Takt testen:** `FOLDER_SYNC_INTERVAL=1800` in
   der Test-.env setzen und den Importer wie oben neu erstellen. Der
   tatsächliche Takt wird anschließend im UI aus dem Worker-Heartbeat
   angezeigt. In diesem Testaufbau steht er zuerst absichtlich auf 1 Min.

**Löschverhalten:** `DEV_PRUNE_MISSING=0` ist der Default. Entfallene
SMB-/Testdateien werden **nicht automatisch auf dem Pi gelöscht**. Die
optionale Bereinigung nach zwei bestätigten nichtleeren Scans testen wir
erst gesondert, wenn die übrige Synchronisierung sauber funktioniert.

## Diagnose und nächster Entwicklungsschritt

```bash
cd anthias-hub-test
bash scripts/dev-sandbox.sh status
bash scripts/dev-sandbox.sh logs
docker compose -p anthias-hub -f compose.yaml -f compose.dev.yaml ps
```

Der UI-Footer zeigt die **UI-Kennung**; bei lokalen Builds erscheint
`Build lokal/dev` statt einer gebackenen Git-SHA. Das ist erwartet.
Ein CI-gebautes SHA-Image zeigt dagegen den exakten Commit.

Für Bugreports morgen am hilfreichsten: die Test-UI-Version, Bildschirm-
ID, Playlist-/Ordnername, erwartetes vs. tatsächliches Verhalten,
den Status des Importers und seine letzten Logs **ohne Secrets**.

Stoppen ohne die Testdaten zu löschen:

```bash
bash scripts/dev-sandbox.sh stop
```

**Keine** Dateien aus `/root/apps/anthias-hub` auf GH-PiHub kopieren,
**keine** echten Firmenfreigaben in `dev-sources` einbinden, **keinen**
`docker compose --remove-orphans`-Befehl auf dem produktiven Host ausführen.
