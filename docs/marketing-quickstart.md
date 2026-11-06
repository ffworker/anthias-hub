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
und erfolgreich durchgeführt wurde. Das bestehende Binary-Emotions-System
wird bis zur Umstellung weiterhin normal benutzt.

## Alternative: manuell gepflegte Playlists

Für nicht mit Netzwerkordnern verbundene Playlists gilt weiterhin:

## In zwei Minuten starten

1. Den von der IT freigegebenen **Anthias Hub** im Browser öffnen und mit dem Marketing-Konto anmelden.
2. **Bildschirme** öffnen und den gewünschten Bildschirm auswählen.
3. In **Playlist** auf **Inhalt hinzufügen** klicken: **Bild/Video**, **Webseite** oder vorhandene **Bibliotheksvorlage** wählen.
4. Bei Bildern/Webseiten eine **Anzeigedauer** und optional einen **Zeitplan** wählen. Video-Laufzeiten werden vom Player bestimmt.
5. Playlist bei Bedarf per Drag-and-drop sortieren; einzelne Inhalte bearbeiten, pausieren oder entfernen. Das Ergebnis **am tatsächlichen Bildschirm** kontrollieren.

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
2. Bei **ordnergebundenen Playlists** trägt IT die freigegebene Kiosk-Adresse einmalig in der zugeordneten Bibliotheksvorlage unter **RSS2Slideshow / Web-Feed hinzufügen (IT)** ein. Für manuell gepflegte Playlists weiterhin **Inhalt hinzufügen → Webseite** verwenden. Nie die `/admin`-Adresse nutzen.
3. Die **Anzeigedauer der Webseite im Hub** einstellen: So lange bleibt die Nachrichten-Seite in der Playlist. Der **Artikelwechsel innerhalb der Seite** wird separat in RSS2Slideshow konfiguriert.
4. Am Bildschirm prüfen, dass Artikel geladen werden und die Webseite zum geplanten Zeitpunkt erscheint.

## Wenn etwas nicht klappt

- **Bildschirm offline / Inhalt fehlt:** Im Hub den Gerätestatus prüfen und die IT informieren; nicht mehrfach blind veröffentlichen.
- **Zeitplan greift nicht:** Prüfen, welcher Plan dem **einzelnen Inhalt auf diesem Bildschirm** zugeordnet ist. Zeitpläne gelten in der lokalen Pi-Zeitzone.
- **Webseite oder RSS bleibt leer:** Die Seite muss vom **Pi** erreichbar sein; ein funktionierender Hub-Login beweist das nicht.
- **Vorlage übertragen, aber nicht sichtbar:** Playlist, Pause-Status und Zeitfenster auf dem Ziel-Pi prüfen.

**Wichtig:** Der Hub ist die komfortable Verwaltung; die Wiedergabe läuft eigenständig auf den Pis. Direkter Zugriff auf die Anthias-Verwaltungsoberfläche ist ein **IT-Fallback**, nicht der normale Marketing-Zugang: Sie kann Hub-Rollenbeschränkungen umgehen.

Weiterführend: [Zeitplanung](scheduling.md) · [Dateien/ZIP importieren](marketing-bulk-import.md) · [IT-Administration](IT_ADMIN_GUIDE.md).
