# Medien und ZIP-Import

Die aktuelle UI bietet **Einzelupload**, **Mehrfachauswahl** und **ZIP-Import**
für PNG/JPG/WebP/MP4. Inhalte können entweder in einer **Bibliotheksvorlage**
gespeichert oder einer bestehenden **Player-Playlist** hinzugefügt werden.
Das Speichern in der Bibliothek veröffentlicht niemals automatisch auf einem Pi.

## Welchen Import verwenden?

- **Einzelne oder mehrere Mediendateien / normale ZIP:** Bibliothek →
  Vorlage → „Mehrere Dateien oder ZIP hinzufügen“, alternativ auf dem
  Bildschirm im Playlist Studio → Inhalt hinzufügen → Bild/Video.
- **Vorlagenbackup wiederherstellen:** Bibliothek → „Erweitert“ →
  Vorlagenbackup wiederherstellen. Diese Hub-ZIP benötigt eine
  `manifest.json`; eine gewöhnliche Medien-ZIP gehört hier **nicht** hinein.
- **Bibliotheksinhalte auf einen Pi übertragen:** Aus der Bibliothek eine
  Einzeldatei oder komplette Vorlage an die bestehende Playlist anhängen.
  Bereits vorhandene Inhalte bleiben erhalten. Identische Webseiten werden
  übersprungen; Medien können doppelt übertragen werden.

Bei Mehrfachauswahl werden Dateien **nacheinander in separaten Requests**
übertragen. Fortschritt und Fehler sind pro Datei sichtbar. Ein Abbruch
kann auf dem Pi bereits angelegte Dateien **nicht** rückgängig machen;
nach Teilfehlern die Pi-Playlist prüfen, bevor erneut übertragen wird.

## Aktuelle Grenzen

| Regel | Wert |
| --- | --- |
| Erlaubte Medien | PNG, JPG/JPEG, WebP, MP4 |
| Dateien pro Sammelimport | 20 |
| Maximale einzelne Mediendatei | **4 GiB** |
| Gewöhnliches Medien-ZIP | **4 GiB Archiv und 4 GiB insgesamt entpackt** |
| ZIP-Einträge insgesamt | maximal 60 (einschließlich Ordner) |
| Kompressionsverhältnis je ZIP-Datei | maximal 150:1 |
| HTTP-Request-Limit | 4 GiB + 16 MiB Overhead |
| Hub-Speicherreserve | mindestens 1 GiB |
| Pi-Speicherprüfung | API `/api/v2/info.free_space`; zwei temporäre Kopien und Reserve (mindestens 2 GiB oder 20%) |

Es gibt außerdem Schutz gegen Pfad-Traversal, doppelte Archiv-Einträge,
Links, unbekannte Dateitypen und zu große entpackte Archive. Der kleinste
Grenzwert von Browser, Reverse Proxy, Hub und Pi bestimmt die tatsächlich
mögliche Übertragung. Für große Dateien sind ausreichender Festplattenplatz,
Dateisystem-Unterstützung (FAT32 kann keine volle 4-GiB-Datei aufnehmen),
Zeitlimits und der Codec relevant. Der vorhandene Caddy-Proxy hat bei
normalen Installationen keinen globalen 4-GiB-Upload-Puffer nötig.

**Speicherfreigabe:** Anthias meldet den verfügbaren Speicher über die
Info-API. Fehlt ein auswertbarer Wert, bleibt der automatische Upload
gesperrt; eine explizite Ausnahme ist nur bei **unbekanntem** Speicherstand
möglich, nicht bei nachweislich zu wenig Platz. Das früher verwendete
`ANTHIAS_VERIFIED_STORAGE_URLS`-Attest ist für die normale
Speicherberechnung nicht mehr notwendig. Unterschiedliche Pi-Mounts können
eine API-Anzeige ungenau machen: vor sehr großen Uploads realen Platz prüfen.

## Betriebs- und Testhinweise

- Erst kleine Medien, dann größere Dateien auf einem **Test-Pi** ausprobieren.
  Die implementierte 4-GiB-Grenze ist **keine** bestätigte Zusage, dass jeder
  Pi und jedes Speichermedium 4 GiB zuverlässig übertragen/abspielen kann.
- Bei Uploadfehlern Server-/Pi-Speicher, Proxy-Timeout, Format und
  Pi-Erreichbarkeit prüfen; bereits hochgeladene Assets nicht blind duplizieren.
- Der Hub-Export einer Bibliotheksvorlage ist **kein** vollständiges Backup
  von `.env`, Konten, Datenverzeichnissen oder Pi-Inhalten. Siehe
  [Release- und Realgerätetests](pilot-acceptance.md) und
  [Backups / Wiederherstellung](reproducible-production.md).
