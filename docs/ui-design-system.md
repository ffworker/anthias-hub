# Anthias Hub – UI-Designsystem

Stand: November 2026 · UI-Kennung: `ui-20261106-04`

## Produkt und Arbeitsabläufe

Die Oberfläche folgt einer ruhigen **Paper + Ink**-Gestaltung mit Korall-Akzenten. Das Ziel ist eine lesbare, konsistente Bedienung statt immer neuer Stilvarianten.

- **Ordner & Quellen:** IT verbindet freigegebene, schreibgeschützte Netzwerkquellen und prüft den Mount-Status.
- **Playlists:** Manuelle Hub-Vorlagen und ordnergebundene Vorlagen haben sichtbar unterschiedliche Herkunft; Bildzeiten und Reihenfolge werden hier bearbeitet.
- **Bildschirme:** Die tatsächliche Pi-Playlist, Gerätestatus, Zeitplanung und manuelle Uploads sind je Gerät erreichbar.
- **Drei klar getrennte Funktionen:** Dateien oder Netzwerkordner *einmalig* hochladen, Medien-ZIP vs. Hub-Backup-ZIP importieren/exportieren, gespeicherte Vorlagen kontrolliert anwenden/ergänzen.

**Speichern ist nicht automatisch Veröffentlichen.** Eine gespeicherte Netzwerkquelle aktiviert niemals selbständig den Hintergrund-Publisher; `FOLDER_AUTO_PUBLISH` bleibt serverseitig standardmäßig deaktiviert.

## Nur ein finales Theme-Stylesheet

`app/templates/base.html` lädt zuerst `style.css`, `modern.css`, `workspace.css` und anschließend die page-spezifischen Layoutstyles. **Danach wird genau ein finales Theme geladen:** `app/static/ui-system.css`.

Die früheren Dateien `ui-refinements.css`, `product-ui.css` und `workflow-ui.css` sind in `ui-system.css` zusammengeführt und entfernt. **Keine zusätzlichen globalen Override-Dateien anhängen.** Neue gemeinsame Designregeln in `ui-system.css` bearbeiten; seitenspezifische Funktionalität im vorhandenen Seitencss belassen.

`app/static/product-theme.js` verwaltet die gespeicherte Hell-/Dunkel-Präferenz im Browser, ohne externe Dienste.

### Verbindliche Designregeln

- Text, Flächen, Rahmen und Fokus über `--ui-*`-Variablen definieren; keine festen dunklen Hintergründe mit hellen Texten im hellen Theme.
- Primäraktionen: Koralle mit dunkler Schrift. Sekundäraktionen: neutrale Oberfläche und lesbare Schrift. Destruktive Aktionen: rot und bestätigungspflichtig.
- Status niemals ausschließlich farblich ausdrücken. `API erreichbar` beweist keine tatsächliche Wiedergabe am Fernseher.
- Buttons, Links, `<summary>`, Formulare und Dateikarten mit Tastatur, Maus und Touch bedienbar halten.
- Dateinamen mit `overflow-wrap:anywhere` erlauben; keine abgeschnittenen 3-Zeichen-Spalten oder horizontalen Überläufe.
- Bestehende Flask-Rollenprüfungen und CSRF beibehalten. Versteckte Reiter sind keine Zugriffskontrolle.
- Medienvorschau und Lightbox nicht ohne eigenen Test verändern. Medien-ZIP niemals mit Hub-Backup-ZIP verwechseln.
- Keine automatische Löschung, Ersetzung oder Umsortierung fremder Player-Inhalte.

## Abnahme vor Merge

1. `python -m pytest -q` sowie `node --test tests/css-maintenance.test.cjs`.
2. Hell- **und** Dunkel-Theme auf Login, Bildschirmübersicht, Ordner & Quellen, Bibliothek, Vorlagendetails, Pi-Playlist, „Inhalt hinzufügen“, Zeitplanung, Status-/Fehlermeldungen und Popovers prüfen.
3. Desktop, Tablet (ca. 768 px), Smartphone (ca. 390 px): keine abgeschnittenen Formulare, überlappenden Buttons oder unlesbaren Inhalte.
4. IT-, Marketing- und Viewer-Rollen prüfen. Änderungen am UI nicht mit einem ungeprüften produktiven Pi-Upload verbinden.
5. Auf echtem Test-Pi prüfen, bevor neue Publish-Funktionalität ausgerollt wird. Ein grüner Test allein ersetzt keine visuelle Abnahme.

## Welche UI-Version ist wirklich installiert?

Die Seite meldet die aktuelle Designversion direkt im HTML:

```html
<meta name="anthias-hub-ui" content="ui-20261106-04">
```

Auf der Hub-VM nach **Merge, erfolgreichem GHCR-Publish und Updater-Ausführung** prüfen:

```bash
curl -fsSL http://127.0.0.1:8765/login | grep 'name="anthias-hub-ui"'
sudo journalctl -u anthias-hub-cd.service -n 30 --no-pager
docker ps --filter name=anthias-hub
```

Fehlt der Marker, ist noch nicht die neue UI-Version installiert. Der `/healthz`-Endpunkt sagt nur etwas über die Server-Erreichbarkeit aus, nicht über die geladene Revision oder das tatsächliche TV-Bild.
