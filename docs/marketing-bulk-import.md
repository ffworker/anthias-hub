> Aktuelle Speicherregel: Die Anthias-API `/api/v2/info.free_space` ist die maßgebliche Quelle für jeden Pi. Der Hub prüft die **konkret ausgewählte Datei** gegen ein Budget aus API-Freiraum mit zwei möglichen Dateikopien und bestehender Sicherheitsreserve. Keine manuelle IT-Dateisystemfreigabe notwendig. 4 GiB pro Mediendatei bleiben die technische Dateigrößengrenze; Medien-ZIPs sind unabhängig begrenzt.

# Marketing: Medien als ZIP oder Mehrfachauswahl hochladen

**Gilt für Anthias Hub (Test/Pilot)**. **Praxisrückmeldung vom 15.10.2026:** Der Betreiber bestätigt die Nutzung der Import-/Export- und Vorlagenbackup-Funktionen. Ein dokumentierter vollständiger Restore auf einer frischen Instanz, ein Prüfsummenvergleich und ein Backup der Raspberry-Pi-Daten sind damit **nicht** bestätigt (siehe [Pilot-Abnahme](pilot-acceptance.md)). Es gibt **zwei verschiedene ZIP-Funktionen**:

- **Medien-Sammelimport** (neu): eine normale ZIP mit Bildern/Videos oder bis zu 20 einzeln ausgewählte Dateien. Eine `manifest.json` ist **nicht nötig**. Als Importziel kannst du die **Bibliotheksvorlage** oder die **Playlist eines ausgewählten Bildschirms** nutzen.
- **Playlist-ZIP importieren** (bereits vorhanden): erwartet ein mit Anthias Hub exportiertes Archiv **mit `manifest.json`**, um eine komplette Bibliotheksvorlage wiederherzustellen. Ein gewöhnliches Medien-ZIP ist hier weiterhin absichtlich ungültig.

## Welchen Import soll ich benutzen?

- **Bilder/Videos oder normale Medien-ZIP:** `Bibliothek` → **Vorlage öffnen** → `Mehrere Dateien oder ZIP hinzufügen`. Auf einem Player alternativ `Bildschirm → Inhalt hinzufügen → Bild / Video → Mehrere Dateien oder ZIP hinzufügen`. Dies ist der normale Weg für selbst gezippte PNG/JPG/WebP/MP4-Dateien; **keine** `manifest.json` erforderlich.
- **Anthias-Hub-Vorlagenbackup wiederherstellen:** `Bibliothek` → `Vorlagenbackup wiederherstellen` unter **Erweitert** aufklappen. Nur zuvor aus dem Hub exportierte vollständige Vorlagenpakete mit `manifest.json`; **nicht** für gewöhnliche Medien-ZIPs.
- **Vorlage auf Player anwenden:** `Bildschirm → Inhalt hinzufügen → Bibliothek` → einen einzelnen Inhalt auswählen **oder** unter `Gesamte Vorlage hinzufügen` alle Inhalte anhängen. Das funktioniert auch bei nicht-leeren Playlists, löscht nichts und überspringt identische Webseiten. Die komplette Vorlage kann ebenso über deren Bibliotheksdetailseite angehängt werden. Vorlagenmedien werden nicht automatisch auf Duplikate geprüft.

Playlist-Einträge haben für Marketing jetzt **Titel direkt im Eintrag** und bei Webseiten/Bildern einen **Dauer-Slider mit Sekundenanzeige**. Die Änderungen werden erst mit `Speichern` an den Player geschickt. Bei Videos ist die Dauer automatisch. Der separate Aktiv/Pausiert-Schalter bleibt bestehen.

## Bedienung

**In die Bibliothek:** `Bibliothek → Vorlage öffnen → Medien-Sammelimport`. Bilder/Videos landen in der ausgewählten Vorlage, **nicht** auf dem Pi. Danach einzelne Bibliothekseinträge über `Zu Bildschirm` gezielt veröffentlichen.

**Direkt zum Player:** `Bildschirme → gewünschten Bildschirm öffnen → Inhalt hinzufügen → Bild / Video → Mehrere Medien auf einmal`. Die Inhalte werden einzeln an die **bestehende** Playlist angehängt; es wird nichts gelöscht, zurückgesetzt oder umsortiert. Die Reihenfolge orientiert sich an der Dateireihenfolge im ZIP bzw. im Auswahlfeld.

Für beide Ziele funktioniert alternativ die Browser-Mehrfachauswahl von PNG/JPG/WebP/MP4 ohne ZIP. Der Browser sendet jede Datei **in einem eigenen Request** (auch fünf 500-MB-Videos), prüft vor jedem Pi-Upload den freien Speicher neu und stoppt bei Fehler oder Abbruch. Server-seitig bleiben max. 4 GiB pro Datei sowie beim Formular ohne JavaScript 4 GiB insgesamt; ZIP-Dateien dürfen bis 4 GiB groß sein und höchstens 4 GiB Medien enthalten (entpackt). Die Videodauer wird automatisch gesetzt; `Bilddauer` gilt für sämtliche Bilder des Imports. Der Titel stammt aus dem Dateinamen (ohne Dateiendung).

### Grenzen und Schutzmechanismen

| Grenze | Wert |
| --- | --- |
| Dateien pro Vorgang | maximal 20 |
| Ein ZIP **oder** mehrere Mediendateien | ZIP nie zusammen mit anderen Dateien |
| Einzelvideo | maximal 4 GiB (4096 MiB) |
| HTTP-Anfrage an Hub | maximal 4 GiB plus 16 MiB Formular-/ZIP64-Overhead (für Vorlagenbackups) |
| Browser-Mehrfachauswahl (ohne ZIP) | bis zu 20 Dateien, je max. 4 GiB, nacheinander übertragen |
| Normale Medien-ZIP | maximal 4 GiB Archiv; nach Entpackung insgesamt max. 4 GiB |
| Entpackte ZIP-Dateien insgesamt | maximal 4 GiB |
| Einzelne entpackte ZIP-Datei | maximal 4 GiB |
| Maximal ZIP-Verzeichniseinträge (inkl. Ordner) | 60 |
| ZIP-Kompressionsverhältnis pro Datei | maximal 150:1 |
| ZIP-Verfahren | STORED oder DEFLATED |

Sicherheitskritische ZIP-Eigenschaften (Traversal/absolute/uneindeutige Pfade, doppelte Namen, Links, Spezialdateien, verschlüsselte Einträge, nicht unterstützte Kompressionsverfahren, gefährliche Größen oder Kompressionsverhältnisse) führen zum **Abbruch des gesamten ZIP vor dem ersten Import**. Unterordner sind erlaubt, die Dateien werden aber nie in diese Pfade extrahiert. Jede Datei wird begrenzt gelesen und anhand ihrer Signatur geprüft. Beschädigte und nicht unterstützte Einzelmedien werden im Ergebnisbericht als **fehlgeschlagen** angezeigt, ohne die übrigen Dateien zu blockieren.

### Fortschritt und Teilergebnisse

Die Fortschrittsanzeige unterscheidet das Senden vom Browser zum Hub von der anschließenden Verarbeitung. Nach dem Import zeigt der Hub für **jede** Datei *importiert* oder *fehlgeschlagen* sowie eine Zusammenfassung und einen Link zur aktualisierten Playlist/Bibliothek.

**Wichtig:** Ein Player-Sammelimport ist **nicht atomar**. Wenn etwa 2 von 5 Dateien erfolgreich waren und das Netz beim dritten Upload abbricht, bleiben die ersten beiden veröffentlicht. Auch ein als fehlgeschlagen gemeldeter Upload kann sich bereits teilweise auf dem Player befinden. **Niemals blind wiederholen**: erst die tatsächliche Playlist prüfen, dann nur die fehlenden Medien nachladen.

Ohne JavaScript funktioniert ein regulärer Formular-POST mit einer verkürzten Ergebnisnachricht; der detaillierte Bericht und Upload-Prozentwerte benötigen JavaScript.

### IT / Deployment

Das Feature verändert weder gespeicherte Bibliotheksmedien noch die ursprüngliche Playlist-ZIP-Import/Exportfunktion. Die neue Batch-Route nutzt dieselben Marketing-Rollen und CSRF-Prüfungen wie die bisherigen Uploads. Gunicorn lässt bei großen Uploads bis zu 7200 Sekunden zu; zusätzlich hat der Browser einen Timeout von 120 Minuten. Eine langsame Pi-Übertragung kann dennoch abbrechen. Für den Pilot zuerst auf einem **Testbildschirm** prüfen.

Die Test-VM verwendet den automatischen `:latest`-Updater mit Healthcheck und Rollback, siehe [Auto-Deploy](auto-deploy.md). Neue Host-Skripte benötigen dennoch einen manuellen `git pull --ff-only`.


### Speicherreserve und große Videos

Anthias Hub zeigt in der Bildschirmübersicht und Playlist den **vom Player gemeldeten freien Speicher** aus `GET /api/v2/info` sowie eine konservative Upload-Kapazität. Vor **jedem** Medienupload zum Pi wird die Angabe erneut eingelesen. Es bleiben mindestens **2 GiB sowie 20 % des gemeldeten freien Speichers** (maßgeblich ist die größere Reserve) unangetastet, plus Rundungspuffer. Reicht der Platz nicht oder ist `free_space` unbekannt, wird der Upload **vor der Übertragung verweigert**. Parallel laufende Hub-Uploads werden im aktuellen Single-Worker-Prozess serialisiert; Uploads über die native Anthias-Oberfläche oder andere Clients können den Speicher trotzdem gleichzeitig verändern.

Bei großen Uploads wird der Multipart-Body zum Pi **gestreamt**, nicht komplett im Python-RAM aufgebaut. Hub-Eingangsuploads und große Backup-ZIPs werden auf dem Hub-Dateisystem temporär abgelegt; dort ist daher ebenfalls ausreichend freier Platz nötig. Die Anthias-API liefert eine gerundete `free_space`-Textangabe aus ihrem System-Dateisystem, **keine genaue, garantierte Kapazität des Medien-Mounts**. Prüfe Speicherlayout und tatsächliche SD-Karte bei der Abnahme. Bei Timeout/Abbruch vor Wiederholung die Pi-Playlist und den freien Speicher kontrollieren.


### Wenn ein größerer Upload fehlschlägt oder gesperrt erscheint

Die bisherige JS-Sammelgrenze von 1 GiB bezog sich auf **alle ausgewählten Dateien zusammen**. Das neue UI sendet große Dateien einzeln und gibt die Schaltfläche auch nach Abbruch oder Fehler wieder frei. Ein laufender Upload ist explizit abbrechbar, **ein Abbruch kann bereits am Pi angekommene Dateien nicht zurücknehmen**.

Ist die verbleibende Pi-Kapazität zu klein oder meldet Anthias keine zuverlässige `free_space`-Angabe, bleibt die Sicherheitsprüfung erhalten: Pi-Playlist, Pi-Dateisystem und gegebenenfalls unvollständige Medien/SD-Karte prüfen, dann im Upload-Bereich per **↻** neu messen. Ein UI-Reset umgeht keine Speicherprüfung. Bei fehlender API-Messung gilt ausschließlich die unten beschriebene bewusste Ausnahme; bei zu knapper Kapazität gibt es keine Ausnahme. Bitte keine unsichere Umgehung der 2-GiB-/20-%-Reserve oder blindes erneutes Hochladen. Bibliotheksimporte verwenden hingegen Hub-Speicher, nicht den des Pis.


### Speicherprüfung fehlgeschlagen: bewusster manueller Upload

Vor jedem Pi-Medienupload wird die Anthias-Info-API auf freie Kapazität geprüft. Der Timeout ist jetzt länger, weil dieser API-Endpunkt auf einigen Geräten blockierend Systeminformationen sammelt. Auch lokalisierte/ältere Speicherangaben werden unterstützt. Im Upload-Bereich und im authentifizierten Speicher-Status-Endpunkt werden Ursachen wie HTTP 404, Zeitüberschreitung oder ein fehlender free_space-Wert angezeigt.

Nur wenn die **Speichermessung nicht verfügbar ist**, erscheint die Checkbox **„Speicherprüfung ignorieren“**. Sie setzt voraus, dass Marketing zuvor die Pi-Playlist und die tatsächliche freie Kapazität geprüft hat. Der Override gilt nur für den jeweiligen Upload, wird in der Audit-Datei als angeforderte Ausnahme vermerkt und nicht gespeichert. **Bei gemessenem Platzmangel wird weiterhin blockiert**, auch mit manuell gesetztem Formularparameter. Die 4-GiB-Einzelgrenze, Rechte, CSRF, Media-Signaturchecks und die übrigen Player-Sicherheitsmaßnahmen bleiben bestehen.

Die exakte Ursache am betroffenen Pi muss anhand seiner tatsächlichen Info-API-Antwort bestätigt werden. Bereits übertragene Dateien können auch ohne Playlist-Eintrag Speicher belegen. Kein blindes Retry.


### 4-GiB-Pilottest (16.10.2026)

Eine **einzelne** Mediendatei darf jetzt höchstens **4 GiB (4.294.967.296 Bytes)** umfassen. Der Browser sendet bis zu 20 Dateien weiterhin **nacheinander**, je als eigenen Multipart-Request; gewöhnliche Medien-ZIPs dürfen bis 4 GiB groß sein (max. 4 GiB entpackt). Die Flask-Anfragegrenze ist **4 GiB + 16 MiB** für Multipart-/ZIP64-Overhead. Vorlagenbackups haben eine Gesamtgrenze von rund 4 GiB (plus begrenztem Overhead); größere Vorlagen müssen aufgeteilt werden. Browser- und Server-Timeouts sind für langsame Pi-3-Transfers auf bis zu 120 Minuten angehoben; kein Upload-Resume und kein automatischer Retry.

**Storage-Schutz unverändert:** Die Hub-VM benötigt genug Platz in `/data` für Eingangs-Spooling und gegebenenfalls zusätzliche Bibliotheks-/Backupkopien, zuzüglich **1 GiB Hub-Reserve**. Der Pi kann beim Upload zwei Dateikopien gleichzeitig halten. Für ein 4-GiB-Video sind daher mindestens **ungefähr 10 GiB real freier Platz** auf den relevanten Pi-Dateisystemen nötig (mehr wegen Rundung); getrennte Mounts einzeln überprüfen. Eine nachgewiesene Platzunterschreitung kann nicht ignoriert werden. Bei unbekannter Mount-Zuordnung ist die explizite manuelle Bestätigung weiterhin erforderlich.

**Vor Übergabe an Marketing:** Auf dem frischen Pi 3 erst eine kleine MP4-Datei, danach etwa 600 MB, dann stufenweise größer testen. Die 4-GiB-Grenze ist softwareseitig implementiert, aber **noch nicht mit echtem Pi-3-Datenträger und installierter Anthias-Version erprobt**. FAT32 hat eine maximale Einzeldateigröße von 4 GiB minus 1 Byte und kann daher keine volle 4-GiB-Datei aufnehmen. Prüfe außerdem echte Dateisysteme, Netzwerk/Proxy, Pi-CPU und den Codec bei der TV-Wiedergabe.


### API als Speicherquelle (16.10.2026)

Für den regulären Raspberry-Pi-Betrieb verwendet der Hub den **von Anthias gelieferten freien Speicher direkt**. Eine leere oder fehlende `ANTHIAS_VERIFIED_STORAGE_URLS`-Konfiguration blockiert den Upload ab dieser Version nicht mehr; diese Einstellung ist obsolet. Die automatische Speicherprüfung vergleicht die **konkret ausgewählte Datei** mit dem aktuellen API-basierten Uploadbudget. Die 4 GiB bilden ausschließlich die Obergrenze **pro Datei**, nicht eine erforderliche Mindestmenge an freiem Speicher auf dem Pi. Kleinere Medien können auch bei weniger als 4 GiB gemeldetem freien Speicher hochgeladen werden, sofern die bisherige Reserve (mind. 2 GiB oder 20%) und Platz für zwei temporäre Dateikopien verbleiben.

Eine gemessene Knappheit kann nicht ignoriert werden. Nur wenn `free_space` fehlt oder die Info-API nicht erreichbar ist, wird die ausdrücklich bestätigte manuelle Ausnahme angeboten. **Grenze der API:** Anthias misst den Root-Speicher. Bei einem tatsächlich anders angebundenen externen Medienmount kann das von der Medienkapazität abweichen; diese Bereitstellung muss der Betreiber separat absichern.


### Große Medien-ZIPs (16.10.2026)

Der alte Deckel von **50 MiB pro Medien-ZIP** wurde für große Marketingvideos auf **4 GiB pro ZIP-Archiv** erhöht. **Zusätzlich maximal 4 GiB entpackte Inhalte insgesamt** und **4 GiB pro Eintrag**; maximal 20 Medien. Ein ZIP wird als eine Anfrage zum Hub gesendet; enthaltene Dateien werden dort einzeln geprüft und danach nacheinander zur Playlist/Bibliothek hinzugefügt. Vor dem ersten Import prüfen wir Metadaten, Pfade, erlaubte ZIP-Kompression und Größen aller Einträge; beim Entpacken streamen wir in begrenzten Blöcken mit Hub-Festplattenreserve. Der Schutz gegen ZIP-Bombs bleibt erhalten (u. a. maximales Kompressionsverhältnis 150:1, keine Traversal-Pfade, keine Links, keine doppelten Einträge). Backup-ZIPs mit `manifest.json` sind eine **separate** Funktion.

**Hinweis:** Ein 3-GiB-ZIP benötigt vorübergehend Platz für das Hub-Eingangsarchiv und die entpackten Medien, bei Bibliotheksimport zusätzlich für die gespeicherten Kopien. Auch auf dem Pi gilt weiterhin die aktuelle Anthias-API-Speicherprüfung **pro tatsächlich importierter Datei**. Erreicht ein Archiv diese Grenzen oder schlägt ein Upload nach einem Teilerfolg fehl, werden keine Dateien automatisch erneut gesendet oder zurückgerollt. Auf Pi 3 zuerst klein beginnen und dann größere Archive stufenweise testen.
