# DEV: vier Betriebsarten, eine Inhaltsquelle pro Bildschirm

> Dieser Entwicklungsstand ist **nur** für den isolierten Compose-Stack
> `anthias-hub-dev` (Port 8766). Produktive Images, SMB-Mounts,
> Anwendungen und Pi-Playlists unverändert lassen.

## Steuerungslogik

Ein Bildschirm erhält genau **einen** Inhaltsmodus. Diese Reihenfolge ist
fest; sie lässt sich nicht durch eine zweite Bearbeitungsoberfläche umgehen:

1. **Netzwerkordner:** Eine fest zugeordnete Playlist hat `folder_source`.
   Bilder/Videos aus dem Ordner, Reihenfolge/Bilddauer zentral in der Playlist.
   Der Bildschirm zeigt **nur** Quelle, echten Sync-Zustand und den Link zur
   zentralen Playlist. Keine direkte Medienbearbeitung am Bildschirm.
2. **Playlist:** Eine normale, fest zugeordnete Hub-Playlist ohne
   Netzwerkquelle. Alle Bilder/Videos/Webseiten zentral pflegen. Auf dem Pi
   keine zweite Bearbeitungsoberfläche. Bei aktivem Publisher werden die
   verifizierten Hub-Inhalte synchronisiert.
3. **Manuell:** Kein zentraler Owner, aber mindestens ein Pi-Asset. Nur hier
   öffnet sich der manuelle Editor, mit Datei, ZIP und Webseite.
4. **Leer:** Kein Owner und die Anthias-API bestätigt null Medien.
   Eine klare Auswahl für den Einstieg: manuell beginnen oder zentrale
   Playlist erstellen/zuordnen.

**Offline** ist kein Beweis für „leer“. **Konflikt** zwischen zwei
Zuordnungen ist keine Einladung zum Bearbeiten; beide Zustände zeigen
stattdessen einen Prüfhinweis.

### Wichtige Grenzen

- Eine Zuordnung alleine **veröffentlicht nichts** auf einem Pi.
  `DEV_AUTO_PUBLISH=0` bleibt Standard.
- Selbst nach Einschalten übernimmt der Publisher ausschließlich eigene,
  verifizierte, journalisierte Medien; fremde Altinhalte werden **nicht**
  heimlich gelöscht. Ein wirklich exklusiver Bildschirm muss zunächst
  bewusst auf einem leeren Test-Pi geprüft werden.
- Die automatische Deaktivierung entfallener Dateien bei **Netzwerkordnern**
  ist unabhängig davon ein kontrollierter Opt-in (`DEV_PRUNE_MISSING=0`).
  Nicht erreichbare/leere Quellen werden nicht als Löschanweisung behandelt.
- Bei **manuellen zentralen Playlists** entfernt ein bewusst gelöschter
  Playlist-Eintrag beim aktiven Publisher nur seinen Hub-eigenen Pi-Eintrag
  durch Deaktivieren (keine physische DELETE-Anforderung).
- Alte einmalige „Vorlage anhängen“-Routen existieren zur Kompatibilität,
  werden in DEV-v2 **nicht** als konkurrierende Hauptaktionen angeboten.
  Für zugeordnete Bildschirme blockiert das Backend direkte Pi-Schreibaktionen.

## Start auf dem **bestehenden** Host – nur DEV aktualisieren

Wichtig: Das ist ein **nicht gemergter Entwicklungsbranch**. Nur im bereits
vorhandenen separaten Checkout arbeiten:

```bash
cd /root/apps/anthias-hub-dev
git fetch origin dev/screen-source-of-truth-v2-20261113
git switch -c dev/screen-source-of-truth-v2-20261113 \
  --track origin/dev/screen-source-of-truth-v2-20261113

# Baut und aktualisiert ausschließlich anthias-hub-dev auf Port 8766.
bash scripts/dev-cohost.sh start
bash scripts/dev-cohost.sh status
```

Den Browser über den vorhandenen SSH-Tunnel auf
`http://127.0.0.1:8766` öffnen. Der Footer zeigt die neue UI-Kennung und
`Build lokal/dev`.

## Netzwerkverbindung – warum „gespeichert“ nicht „gemountet“ heißt

Das Web-UI hat absichtlich keine Root-Rechte und verarbeitet **keine**
SMB-Passwörter. Es führt lediglich ein Statusprotokoll:

**Pfad gespeichert → Host-Mount bestätigt → Ordner sichtbar → Playlist
importiert → auf Pi veröffentlicht**.

Unter „Ordner & Quellen“ aktualisiert sich der Status automatisch etwa
**alle 10 Sekunden**. `Aktuellen Status prüfen` liest den Zustand erneut.
Das ist keine erneute Root-Mount-Anforderung und **keine animierte
Pseudo-Fortschrittsanzeige**.

Wenn kein DEV-Host-Mountdienst eingerichtet ist, lautet die Meldung
ausdrücklich **„kein Host-Mountdienst meldet einen Versuch“** – egal wie
lange du wartest. Erst ein eingerichteter Root-Timer prüft neue Pfade
automatisch. Bei eingerichteten Timer-Skripten folgt normalerweise binnen
ca. einer Minute ein Host-Prüflauf; danach prüft der unabhängige Importer
standardmäßig alle 60 Sekunden. Je nach Ablauf kann es also mehr als
einen Takt dauern.

## Optional: echte SMB-Quelle für DEV einrichten

**Nicht nötig** zum Testen des lokalen Ordners `dev-sources/demo`.

Diesen Abschnitt nur verwenden, wenn du absichtlich einen **separaten,
read-only DEV-CIFS-Mount** testen möchtest. Keine Mounts der produktiven
Instanz wiederverwenden. Die neue Datei
`compose.dev.smb.yaml` bindet ausschließlich
`/srv/anthias-dev-sources:/sources:ro` in DEV ein.

1. Im DEV-Hub den gewünschten SMB-Stammordner speichern
   (`Ordner & Quellen`). Es wird nur die DEV-Registry geändert.
2. Auf dem **Host** als Root `/etc/anthias-hub-dev/secrets/` (Modus 0700)
   erstellen. Eine neue Credentials-Datei (Modus 0600, Owner Root) mit
   `username=...`, `password=...` und ggf. `domain=...` anlegen.
   Zugangsdaten niemals in Chat, Git oder Hub-UI schreiben.
3. Unter `/etc/anthias-hub-dev/smb-allowlist.json` (Root, 0600)
   eine **separate** Freigabeliste erstellen; `server` und `share`
   müssen exakt zur DEV-Registry passen. Beispiel mit fiktiven Werten:

```json
{
  "allowed_shares": [
    {
      "server": "10.0.0.10",
      "share": "media$",
      "credentials": "/etc/anthias-hub-dev/secrets/marketing.smb"
    }
  ]
}
```

4. Den gesonderten DEV-Root-Timer installieren und den ersten
   Prüfbericht abwarten:

```bash
cd /root/apps/anthias-hub-dev
bash scripts/install-dev-smb-mounts.sh
systemctl --no-pager status anthias-hub-dev-smb-mounts.service
findmnt -M /srv/anthias-dev-sources/default -o TARGET,SOURCE,FSTYPE,OPTIONS
```

5. **Erst nachdem `findmnt` tatsächlich CIFS zeigt**, in der separaten
   `/root/apps/anthias-hub-dev/.env` eintragen:

```dotenv
DEV_SMB_MODE=1
```

   Danach `bash scripts/dev-cohost.sh start`. Es baut ausschließlich
   DEV neu und bindet die DEV-Mounts ein. Das Recreate ist wichtig:
   Docker sieht einen nachträglich hinzugekommenen CIFS-Submount sonst
   möglicherweise nicht (Bind-Propagation).

Die GUI zeigt nun die Host-Bestätigung, erkannte Unterordner, den
Import-Heartbeat und – wenn später aktiv – die Pi-Veröffentlichung.
Bei Fehlern die Dienst-Logs auf dem Host auswerten:

```bash
journalctl -u anthias-hub-dev-smb-mounts.service -n 80 --no-pager
bash scripts/dev-cohost.sh logs
```

**Kein automatisches Umhängen bestehender Quellen.** Wenn am DEV-Mountpunkt
ein anderer Pfad liegt, meldet der Koordinator `conflict` und verändert
den Mount nicht. Wenn du den UNC-Pfad änderst, muss der bestehende DEV-Mount
kontrolliert behandelt werden. Nie den produktiven Mount anfassen.

## Prüflauf

- [ ] DEV startet separat; Produktion weiterhin unverändert erreichbar.
- [ ] Unverbundener Pi zeigt nicht fälschlich „Leer“.
- [ ] Leerer Test-Pi zeigt „Leer“ und nur passende Einstiegsaktionen.
- [ ] Ein direktes Testmedium führt zu „Manuell“; der manuelle Editor funktioniert.
- [ ] Eine normale Hub-Playlist lässt sich fest zuweisen: „Playlist“,
      kein Pi-Editor, auch nicht über `?editor=1` und nicht per POST.
- [ ] Ordner-Playlist erzeugt „Netzwerkordner“ mit Pfad/Import/Pi-Status.
- [ ] Pi-Medien werden erst nach **separat eingeschaltetem Publisher** aktualisiert.
- [ ] „Ordner & Quellen“ zeigt ohne Mountdienst ausdrücklich „nicht geprüft“
      und nach Einrichtung echte Fortschrittsschritte samt Fehlerfällen.
- [ ] Nur der **dafür vorgesehene Test-Pi** wird irgendwann für Schreibtests
      in `ANTHIAS_ALLOWED_CIDRS` der DEV-.env freigegeben (/32).
