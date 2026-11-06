# Marketing-Kurzanleitung — Digital Signage

**Zweck:** Inhalte auf bereits von der IT eingerichteten Bildschirmen pflegen. Keine Installation, kein SSH und kein Raspberry-Pi-Zugriff erforderlich.

## Standardablauf: Netzwerkordner-Playlist

**Dateien werden weiterhin im gewohnten Marketing-Netzwerkordner gespeichert.**
Du brauchst weder einen Raspberry Pi noch eine ZIP-Datei oder einen
manuellen Upload im Hub.

1. Bilder/Videos im gewohnten Ordner hinzufügen oder ersetzen.
2. Anthias Hub öffnen → **Bibliothek** → die von IT angelegte Ordner-Playlist
   (zum Beispiel „Bistro“) öffnen.
3. Beim gewünschten **Bild** im Feld **Anzeigedauer** Sekunden eintragen und
   auf **Speichern** klicken (5–3600 Sekunden).
4. Video-Laufzeiten sind automatisch. Ein RSS-/Webseiten-Slide kann ebenfalls
   eine eigene Anzeigedauer bekommen.
5. Oben auf **Letzter Import** achten. Wenn kein Abgleich gemeldet wird, IT
   informieren statt Dateien mehrfach hochzuladen.

IT verbindet Netzwerkquelle und Zielbildschirm. Änderungen erscheinen auf
dem Pi **erst wenn die automatische Geräteveröffentlichung von IT aktiviert**
und erfolgreich durchgeführt wurde. Die vorhandene Anthias-Playlist bleibt auch bei einem vorübergehend nicht verfügbaren Hub auf dem Pi bestehen. Änderungen am Bildschirm erst nach
erfolgreicher Prüfung der Freigabe übernehmen.

## Drei klare Aktionen – manuell, ZIP, ganze Vorlage

1. **Manuell hinzufügen:** Bildschirme → gewünschten Pi → Playlist → Inhalt hinzufügen. Mit **Datei** ein einzelnes Bild/Video hochladen; **Webseite** für eine URL. IT darf unter **Netzwerkordner** bis zu 20 freigegebene Bilder/Videos *einmalig* direkt auf den Pi kopieren. Das ist **keine** automatische Verknüpfung.
2. **ZIP importieren oder exportieren:** Unter **ZIP / Mehrere** eine normale Bild-/Video-ZIP oder mehrere Dateien einmalig auf den Pi importieren. Für ein **vollständiges Hub-Vorlagen-Backup** dagegen in der Bibliothek die Vorlage öffnen → **Backup-ZIP exportieren**; Import in der Bibliothek unter **Vorlagenbackup wiederherstellen**. Die beiden ZIP-Formate nicht verwechseln.
3. **Playlist anwenden:** Unter **Vorlage anwenden** einzelne gespeicherte Inhalte oder eine ganze Vorlage auswählen. **Bestehende Playlist ergänzen** hängt nur an; **leere Playlist initialisieren** wird serverseitig abgelehnt, falls schon Inhalte vorhanden sind. Nichts wird automatisch gelöscht.

Anzeigedauer und optionalen Zeitplan prüfen; Video-Laufzeiten ermittelt der Pi. Nach Änderungen die Wiedergabe am echten Bildschirm kontrollieren. Bei unterbrochenen Uploads nicht blind erneut übertragen.

## Häufige Aufgaben

| Aufgabe | Wo? | Wichtig |
| --- | --- | --- |
| Bilder oder Videos hochladen | Bildschirm → Playlist → Inhalt hinzufügen | Für mehrere Dateien gibt es Mehrfachauswahl und ZIP-Import; bei Fehlern den Pi prüfen, bevor erneut hochgeladen wird |
| Webseite einbinden | Bildschirm → Playlist → Inhalt hinzufügen → Webseite | Die Seite muss **vom jeweiligen Pi** erreichbar sein |
| Wiederkehrende Inhalte vorbereiten | **Bibliothek** → Vorlage anlegen / bearbeiten | **Speichern ist nicht Veröffentlichen**: Inhalte anschließend zum Zielbildschirm übertragen |
| Zeiten festlegen | Bildschirm → **Zeitplanung** oder direkt am Playlist-Inhalt | Gemeinsame Vorlagen sind wiederverwendbar; die tatsächliche Zuordnung gilt pro Gerät/Inhalt |
| Reihenfolge / Pause ändern | Bildschirm → Playlist | Änderungen wirken auf die Playlist dieses Pis |

## RSS-Nachrichten auf einem Bildschirm

**RSS2Slideshow** erstellt eine sich selbst aktualisierende Nachrichten-Webseite; **Anthias Hub** plant deren Anzeige wie jede andere Webseite. Die beiden Anwendungen sind unabhängig.

1. In RSS2Slideshow die Nachrichtenquellen und das Design im dafür freigegebenen Editor pflegen.
2. Bei **ordnergebundenen Playlists** trägt IT die freigegebene Kiosk-Adresse einmalig in der zugeordneten Bibliotheksvorlage unter **RSS2Slideshow / Webseite zur Playlist hinzufügen** ein. Für manuell gepflegte Playlists weiterhin **Inhalt hinzufügen → Webseite** verwenden. Nie die `/admin`-Adresse nutzen.
3. Die **Anzeigedauer der Webseite im Hub** einstellen: So lange bleibt die Nachrichten-Seite in der Playlist. Der **Artikelwechsel innerhalb der Seite** wird separat in RSS2Slideshow konfiguriert.
4. Am Bildschirm prüfen, dass Artikel geladen werden und die Webseite zum geplanten Zeitpunkt erscheint.

## Wenn etwas nicht klappt

- **Bildschirm offline / Inhalt fehlt:** Im Hub den Gerätestatus prüfen und die IT informieren; nicht mehrfach blind veröffentlichen.
- **Zeitplan greift nicht:** Prüfen, welcher Plan dem **einzelnen Inhalt auf diesem Bildschirm** zugeordnet ist. Zeitpläne gelten in der lokalen Pi-Zeitzone.
- **Webseite oder RSS bleibt leer:** Die Seite muss vom **Pi** erreichbar sein; ein funktionierender Hub-Login beweist das nicht.
- **Vorlage übertragen, aber nicht sichtbar:** Playlist, Pause-Status und Zeitfenster auf dem Ziel-Pi prüfen.

**Wichtig:** Der Hub ist die komfortable Verwaltung; die Wiedergabe läuft eigenständig auf den Pis. Direkter Zugriff auf die Anthias-Verwaltungsoberfläche ist ein **IT-Fallback**, nicht der normale Marketing-Zugang: Sie kann Hub-Rollenbeschränkungen umgehen.

Weiterführend: [Zeitplanung](scheduling.md) · [Dateien/ZIP importieren](marketing-bulk-import.md) · [IT-Administration](IT_ADMIN_GUIDE.md).
