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
(
  set -e
  cd /root/apps/anthias-hub-dev
  git fetch origin dev/screen-source-of-truth-v2-20261113
  if git show-ref --verify --quiet refs/heads/dev/screen-source-of-truth-v2-20261113; then
    git switch dev/screen-source-of-truth-v2-20261113
  else
    git switch --track origin/dev/screen-source-of-truth-v2-20261113
  fi
  git pull --ff-only

  # Baut und aktualisiert ausschließlich anthias-hub-dev auf Port 8766.
  bash scripts/dev-cohost.sh start
  bash scripts/dev-cohost.sh status
)
```

Falls der DEV-Account beim ersten Passwortdialog nicht fertig angelegt wurde
(`start` meldet `DEV setup incomplete`), zuvor im DEV-Checkout noch einmal
`bash scripts/dev-cohost.sh init` aufrufen. Das setzt die vorhandenen
DEV-Secrets nicht zurück und greift nicht auf die Produktion zu.

Den Browser über den vorhandenen SSH-Tunnel auf
`http://127.0.0.1:8766` öffnen. Der Footer zeigt die neue UI-Kennung und
`Build lokal/dev`.

## SMB-Verbindung vollständig über den DEV-Browser

**Neu:** Der DEV-Hub verbindet SMB-Freigaben direkt über einen unprivilegierten
SMB3-Client. Weder ein Host-Mount noch ein systemd-Timer oder eine
Credentials-Datei am Host muss eingerichtet werden.

1. Im DEV-Hub **Ordner & Quellen** öffnen.
2. SMB-Pfad, Benutzer, Kennwort und ggf. Domäne eingeben.
3. **Verbinden & prüfen**: echte Prüfung, sofort sichtbarer Fehler oder Erfolg.
4. Der DEV-Importer kopiert Medien in seinen separaten DEV-Spiegel. Die
   Statusanzeige zeigt Verbindung, erkannte Ordner, Dateikopien und Import.
5. **Jetzt synchronisieren** stößt einen neuen Importlauf an.
6. Unter **Playlists** einen erkannten Bildschirmordner auswählen.
   Veröffentlichung auf Test-Pis ist weiterhin separat und standardmäßig aus.

Für alle Details siehe [SMB nur per Browser](dev-smb-browser-only.md).

Das ältere Host-CIFS-Mount-Skript bleibt im Repository für bestehende
Installationen, ist für diesen DEV-Workflow aber **nicht erforderlich** und
darf nicht parallel zu `DEV_SMB_UI=1` eingeschaltet werden.

## Kompakte Oberfläche (UI ui-20261113-07)

Die DEV-Ansichten bleiben funktional unverändert, werden aber deutlich
dichter dargestellt:

- **Bildschirme:** Gerät, Online-Status und Steuerungsart stehen zusammen;
  sekundäre Bereichslinks sind unter „Weitere Bereiche“ erreichbar.
- **Playlists:** Die Liste ist sofort sichtbar. „Neue Playlist“ klappt bei
  Bedarf auf (bei leerer Bibliothek automatisch geöffnet).
- **Playlist-Detail:** Inhaltsstatus und Medien bleiben immer sichtbar;
  „Bildschirme zuweisen“ und „Medien hinzufügen“ sind aufklappbar.
  Ohne bisherige Zuordnung bzw. bei leerer Playlist sind die Formulare
  initial geöffnet. Die Wiedergabereihenfolge steht oben als nummerierte Liste. Medien lassen
  sich direkt per Auf/Ab sortieren; Dauer und sicheres Entfernen liegen in
  „⋯“.
- **Ordner & Quellen:** Der Live-SMB-Status und „Jetzt synchronisieren“
  bleiben sichtbar. Der Credential-Editor öffnet sich über
  „SMB-Verbindung“ und ist bei erstmaliger Einrichtung automatisch
  aufgeklappt; „Weitere Quellenaktionen“ enthält Entfernen mit
  denselben Schutzbestätigungen wie zuvor.
- **Sicherheit:** Keine CSRF-Prüfung, Gerätezuordnung, Dateibegrenzung,
  Rechteprüfung oder bestehende API-Route wurde für die Verdichtung
  entfernt. Die Backend-Logik bleibt die Quelle der Wahrheit.

Alle Aufklapppfeile sind einheitlich. Die Änderungen gelten ausschließlich
mit `HUB_WORKFLOW_V2=1`,
nicht im normalen Produktiv-Hub.

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
