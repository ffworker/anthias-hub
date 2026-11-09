## Composer / „Inhalt hinzufügen“ – UI-Pass 3 (09.11.2026)

- **Oft genutzt:** Datei, ZIP/Mehrere und gespeicherte Vorlage erscheinen als klarer Hauptblock. **Weitere Quellen:** Webseite und ausschließlich für IT/Owner Netzwerkordner. Die bestehenden `data-add-mode`-Schalter und dieselben serverseitigen Routen, Rollen und CSRF-Formulare bleiben erhalten.
- **ZIP:** Die bereits geöffnete, doppelte Accordion-Ebene entfällt zugunsten eines direkt sichtbaren Inhaltsbereichs, sobald „ZIP / Mehrere“ ausgewählt ist; bei fehlendem JavaScript bleibt das Formular sichtbar.
- **Texte:** Der Einstieg erklärt den Wirkungskreis, einzelne Quelltypen enthalten knappe, eindeutige Warnungen bzw. Hinweise. Keine Funktion, kein globales Publishing und kein Playergerät werden verändert.
- **Responsive / Themes:** Häufige Quellen auf einer Zeile, auf sehr schmalen Geräten sinnvoll zweizeilig; optionale Quellen erhalten einen eigenen Abschnitt. Styles im bestehenden zentralen `ui-system.css`, kein zusätzliches Framework.
- **UI-Revision:** `ui-20261109-03`. Browser-/Visual-Review nach grüner CI bleibt Pflicht vor Merge. Die bestehende Installation behält ihre private Image-Pin-Konfiguration; produktive Bildschirme werden nicht für UI-Tests beschrieben.

## Geräte-Unterseiten: Workflow-Klarheit (09.11.2026, zweiter Pass)

- **Playlist und Zeitplanung:** H1 bezeichnet die aktuelle Aufgabe; Gerätename und Standort stehen als Kontext darüber. Die Breadcrumbs bilden den tatsächlichen Pfad ab. Ein Bibliothekslink ist kein irreführender Breadcrumb mehr, die Hauptnavigation zu Playlists bleibt erhalten.
- **Zeitplanung bei leerer Plan-Sammlung:** Die leere, unerreichbare Sammlungsschleife vor dem ersten Formular wurde entfernt. Das Formular bleibt direkt geöffnet, ohne Änderungen an Rollen, CSRF oder Speicherablauf.
- **Playlist:** Die Sortierhilfe ist kompakter. Lange Medienadressen werden in der Kartenübersicht gekürzt; vollständiger Text bleibt als Tooltip vorhanden. Der bestehende Inline-Editor, die Zeitplanung und sichere Löschbestätigungen bleiben unverändert.
- **Design:** Gemeinsame final geladene CSS-Datei, neue UI-Kennung `ui-20261109-03`. Keine neuen Assets/Frameworks; keine API-, Geräte-, SMB-, Worker- oder Publisher-Änderung.

**Review:** CI und visuelle Freigabe vor Merge. Das registrierte Anzeigegerät wird produktiv verwendet und darf nicht als Testgerät benutzt werden. Kein automatischer Live-Deploy.

# Anthias Hub – UI-Designsystem

Stand: November 2026 · UI-Kennung: `ui-20261109-03`

## Klarheitspass 09.11.2026 (Code-Review; visuelle Abnahme ausstehend)

- **Bildschirme:** Die operativen Geräte erscheinen direkt nach einer schlanken Übersicht. Die bisherigen großen Anleitungskarten sind entfernt; Links zu Playlists und IT-Quellen folgen als leise Sekundäraufgaben.
- **Playlist-Bibliothek:** Vorhandene Vorlagen bleiben zuerst sichtbar. „Neue Playlist erstellen“ ist eine klare Aktion; auf leerem System öffnet sich der Dialog direkt. Backup-Import steht nachrangig.
- **Playlist-Detail:** Erst Titel, dann Importstatus. Sprungnavigation zu Inhalten, Hinzufügen, Anwenden und IT-Quellen; seltene IT-Einstellungen stehen unter den Inhaltstools.
- **Ordner & Quellen:** Standardbibliothek und bestätigter Hoststatus kommen vor Bestandszahlen. Die ersten erkannten Unterordner sind sofort sichtbar, Legacy-Mounts und Austragen bleiben getrennt und sicher.
- **Bedienung:** Gleichmäßige Abstände, zurückhaltende Sekundärlinks, weiterhin eine finale CSS-Datei. Deep-Links öffnen gezielt den erforderlichen nativen Aufklapper, auch aus einer anderen Seite.

**Status:** Geplantes UX-Update als eigener PR, keine Aussage über eine bereits geänderte Live-UI. Vor Ausrollen: Hell/Dunkel, 390/768/Desktop, Viewer/Marketing/IT, Formulare, Dropdowns, echte Browser-Screenshots und die vorhandenen Upload-/CSRF-Tests abnehmen. Kein unkontrollierter Player-Write.

## Produkt und Arbeitsabläufe

Die Oberfläche folgt einer ruhigen **Paper + Ink**-Gestaltung mit Korall-Akzenten. Das Ziel ist eine lesbare, konsistente Bedienung statt immer neuer Stilvarianten.

- **Bildschirme (Standard nach Anmeldung):** Der Login führt nach `/` zur Bildschirmübersicht. Hier wählt man einen Pi, bearbeitet dessen aktuelle Playlist, prüft Zeitplanung oder Status und öffnet die einheitlichen Aktionen „Steuern“ und „Verwalten“.
- **Playlists:** Die gespeicherten Vorlagen sind eigenständig. Innerhalb einer Vorlage ist die Arbeitsreihenfolge **01 Inhalte & Sortierung → 02 Uploads / Quellen → 03 Auf Bildschirm anwenden**. Datei, ZIP, Webseite, Netzwerkquelle und Erstinstallation nutzen konsistente, deutlich beschriftete Aufklappbereiche.
- **Ordner & Quellen (nur IT):** Die Standard-SMB-Freigabe und ihr **aktuell vom Host bestätigter Mountstatus** stehen oben. Weitere bereits vorhandene Einzelquellen und alte, nicht registrierte Host-Ordner bleiben als sichtbares Inventar darunter, auch wenn die Zusatzquellen-Konfiguration geschlossen ist. Hinzufügen, Pfadänderungen und Abmeldung sind bewusst nachrangig. Es ist kein allgemeiner Einstieg und keine Voraussetzung für manuell gepflegte Playlists.
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
<meta name="anthias-hub-ui" content="ui-20261109-03">
```

Auf der Hub-VM nach **Merge, erfolgreichem GHCR-Publish und Updater-Ausführung** prüfen:

```bash
curl -fsSL http://127.0.0.1:8765/login | grep 'name="anthias-hub-ui"'
sudo journalctl -u anthias-hub-cd.service -n 30 --no-pager
docker ps --filter name=anthias-hub
```

Fehlt der Marker, ist noch nicht die neue UI-Version installiert. Der `/healthz`-Endpunkt sagt nur etwas über die Server-Erreichbarkeit aus, nicht über die geladene Revision oder das tatsächliche TV-Bild.

### Status- und Menü-Hierarchie (SMB)

| Ebene | Darstellung | Regel |
| --- | --- | --- |
| Navigation | **Bildschirme** → **Playlists** → dezenter IT-Eintrag **Ordner & Quellen** | Alltagsarbeit vor Administration. IT-Sichtbarkeit bleibt rollenbasiert. |
| Primär auf der Quellen-Seite | Standard-Mount, farbiger und **beschrifteter** Status, SMB-Pfad, Host-Mountpunkt, erkannte Unterordner | „Eingehängt · Host bestätigt“ ausschließlich bei gültiger Hostmeldung unter 5 Minuten, Fingerprint zum gespeicherten SMB-Pfad passend. |
| Problemfall | „Mount unbestätigt“, „Mount fehlgeschlagen“, „Freigabe blockiert“ oder „Anderer Pfad gemountet“ | Fehlender/veralteter Report heißt **unbestätigt**, nicht definitiv „ausgehängt“. Keine falsche Live-Anzeige. |
| Inventar | Registrierte zusätzliche Quellen und alte Host-Verzeichnisse sofort sichtbar | Alte Verzeichnisse nur dann als „CIFS-Mount erkannt“ bezeichnen, wenn die Container-Mountinfo dies belegt. Sichtbarer Ordner allein beweist keinen Mount. |
| Sekundär | Unterordner-Details, Playlist-Verknüpfung | Begrenzt anzeigen; keine Karte pro Unterordner zur Mount-Verwaltung. |
| Tertiär | Pfadänderung, neue Einzelquelle, Registrierung austragen, ausgetragene Quellen | Explizite `details`-Aufklapper mit großem Pfeil; Abmelden bleibt von tatsächlichem `umount` und Pi-Dateien getrennt. |

**Abnahmefälle:** Leere Installation; gespeicherter, unbestätigter Mount; frischer erfolgreicher Mount; nicht freigegeben/fehlerhaft/konfliktierend; veralteter oder zum neuen UNC nicht passender Status; registrierte zusätzliche Quellen; Legacy-CIFS-Mount vs. nur sichtbarer Legacy-Ordner; abhängige Playlists; ausgetragene Quelle; IT/Marketing; hell/dunkel; 390/768/1280 px.
