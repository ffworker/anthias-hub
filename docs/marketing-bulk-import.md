# Marketing: Medien als ZIP oder Mehrfachauswahl hochladen

**Gilt für Anthias Hub (Test/Pilot)**. Es gibt **zwei verschiedene ZIP-Funktionen**:

- **Medien-Sammelimport** (neu): eine normale ZIP mit Bildern/Videos oder bis zu 20 einzeln ausgewählte Dateien. Eine `manifest.json` ist **nicht nötig**. Als Importziel kannst du die **Bibliotheksvorlage** oder die **Playlist eines ausgewählten Bildschirms** nutzen.
- **Playlist-ZIP importieren** (bereits vorhanden): erwartet ein mit Anthias Hub exportiertes Archiv **mit `manifest.json`**, um eine komplette Bibliotheksvorlage wiederherzustellen. Ein gewöhnliches Medien-ZIP ist hier weiterhin absichtlich ungültig.

## Welchen Import soll ich benutzen?

- **Bilder/Videos oder normale Medien-ZIP:** `Bibliothek` → `Bilder, Videos oder normale ZIP importieren` → **Zielvorlage** auswählen. Auf einem Player alternativ `Bildschirm → Inhalt hinzufügen → Bild / Video → Mehrere Bilder/Videos oder normale Medien-ZIP`. Dies ist der normale Weg für selbst gezippte PNG/JPG/WebP/MP4-Dateien; **keine** `manifest.json` erforderlich.
- **Anthias-Hub-Vorlagenbackup wiederherstellen:** `Bibliothek` → unten `Anthias-Hub-Vorlagenbackup wiederherstellen` aufklappen. Nur zuvor aus dem Hub exportierte vollständige Vorlagenpakete mit `manifest.json`; **nicht** für gewöhnliche Medien-ZIPs.
- **Vorlage auf Player anwenden:** `Bildschirm → Inhalt hinzufügen → Bibliothek` → einen einzelnen Inhalt auswählen **oder** unter `Gesamte Vorlage hinzufügen` alle Inhalte anhängen. Das funktioniert auch bei nicht-leeren Playlists, löscht nichts und überspringt identische Webseiten. Die komplette Vorlage kann ebenso über deren Bibliotheksdetailseite angehängt werden. Vorlagenmedien werden nicht automatisch auf Duplikate geprüft.

Playlist-Einträge haben für Marketing jetzt **Titel direkt im Eintrag** und bei Webseiten/Bildern einen **Dauer-Slider mit Sekundenanzeige**. Die Änderungen werden erst mit `Speichern` an den Player geschickt. Bei Videos ist die Dauer automatisch. Der separate Aktiv/Pausiert-Schalter bleibt bestehen.

## Bedienung

**In die Bibliothek:** `Bibliothek → Vorlage öffnen → Medien-Sammelimport`. Bilder/Videos landen in der ausgewählten Vorlage, **nicht** auf dem Pi. Danach einzelne Bibliothekseinträge über `Zu Bildschirm` gezielt veröffentlichen.

**Direkt zum Player:** `Bildschirme → gewünschten Bildschirm öffnen → Inhalt hinzufügen → Bild / Video → Mehrere Medien auf einmal`. Die Inhalte werden einzeln an die **bestehende** Playlist angehängt; es wird nichts gelöscht, zurückgesetzt oder umsortiert. Die Reihenfolge orientiert sich an der Dateireihenfolge im ZIP bzw. im Auswahlfeld.

Für beide Ziele funktioniert alternativ die Browser-Mehrfachauswahl von PNG/JPG/WebP/MP4 ohne ZIP. Die Videodauer wird automatisch gesetzt; `Bilddauer` gilt für sämtliche Bilder des Imports. Der Titel stammt aus dem Dateinamen (ohne Dateiendung).

### Grenzen und Schutzmechanismen

| Grenze | Wert |
| --- | --- |
| Dateien pro Vorgang | maximal 20 |
| Ein ZIP **oder** mehrere Mediendateien | ZIP nie zusammen mit anderen Dateien |
| HTTP-Upload / ZIP-Dateigröße | maximal 50 MiB insgesamt (51 MiB Multipart-Request-Limit) |
| Entpackte ZIP-Dateien insgesamt | maximal 150 MiB |
| Einzelne entpackte oder ausgewählte Datei | maximal 50 MiB |
| Maximal ZIP-Verzeichniseinträge (inkl. Ordner) | 60 |
| ZIP-Kompressionsverhältnis pro Datei | maximal 150:1 |
| ZIP-Verfahren | STORED oder DEFLATED |

Sicherheitskritische ZIP-Eigenschaften (Traversal/absolute/uneindeutige Pfade, doppelte Namen, Links, Spezialdateien, verschlüsselte Einträge, nicht unterstützte Kompressionsverfahren, gefährliche Größen oder Kompressionsverhältnisse) führen zum **Abbruch des gesamten ZIP vor dem ersten Import**. Unterordner sind erlaubt, die Dateien werden aber nie in diese Pfade extrahiert. Jede Datei wird begrenzt gelesen und anhand ihrer Signatur geprüft. Beschädigte und nicht unterstützte Einzelmedien werden im Ergebnisbericht als **fehlgeschlagen** angezeigt, ohne die übrigen Dateien zu blockieren.

### Fortschritt und Teilergebnisse

Die Fortschrittsanzeige unterscheidet das Senden vom Browser zum Hub von der anschließenden Verarbeitung. Nach dem Import zeigt der Hub für **jede** Datei *importiert* oder *fehlgeschlagen* sowie eine Zusammenfassung und einen Link zur aktualisierten Playlist/Bibliothek.

**Wichtig:** Ein Player-Sammelimport ist **nicht atomar**. Wenn etwa 2 von 5 Dateien erfolgreich waren und das Netz beim dritten Upload abbricht, bleiben die ersten beiden veröffentlicht. Auch ein als fehlgeschlagen gemeldeter Upload kann sich bereits teilweise auf dem Player befinden. **Niemals blind wiederholen**: erst die tatsächliche Playlist prüfen, dann nur die fehlenden Medien nachladen.

Ohne JavaScript funktioniert ein regulärer Formular-POST mit einer verkürzten Ergebnisnachricht; der detaillierte Bericht und Upload-Prozentwerte benötigen JavaScript.

### IT / Deployment

Das Feature verändert weder gespeicherte Bibliotheksmedien noch die ursprüngliche Playlist-ZIP-Import/Exportfunktion. Die neue Batch-Route nutzt dieselben Marketing-Rollen und CSRF-Prüfungen wie die bisherigen Uploads. Der Gunicorn-Timeout ist für einen begrenzten Batch-Vorgang von 135 auf 360 Sekunden erhöht; ein langsamer Pi kann trotzdem einzelne Zeitüberschreitungen auslösen. Für den Pilot zuerst auf einem **Testbildschirm** prüfen.

**Update der lokalen Pilot-VM nur nach Freigabe:** `git pull --ff-only && docker compose -p anthias-hub up -d --build`. Für eine produktive VM einen geprüften Commit bzw. ein Image-Digest pinnen, nicht unkontrolliert `:main` aktualisieren.
