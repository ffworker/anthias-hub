# Scheduling 2.0 – Playlist und Zeitplanung

**Stand:** 16. Oktober 2026 · Gemeinsame Hub-Zeitplansammlung, individuelle Pi-Zuordnung · Deutsch.

## Navigation und Arbeit

Unter **Bildschirme → Playlist** teilen sich **Playlist** und **Zeitplanung** denselben Header und sind gleichwertige Ansichten desselben Pis. Die Playlist ist der Standard-Tab. Jeder Playlist-Inhalt zeigt seinen Zeitplan direkt an; im aufgeklappten Editor kann Marketing die Zeitplanung ändern, einschließlich „Ohne Zeitplan“, benannter Vorlage oder individueller Wochentage/Uhrzeiten.

Auf der **Zeitplanung**-Ansicht können Marketing und IT **gemeinsame Zeitplanvorlagen für alle Geräte** erstellen, z. B. Werktag_Default (Mo–Fr, 08–18 Uhr) oder Event (Sa, 10–14 Uhr). Ein auf Pi 3 erstellter Plan ist sofort auf Pi 5 und jedem zukünftig registrierten Gerät verfügbar. **Es gibt keine gerätespezifischen Kopien der Vorlage.** Die Zuordnung gilt hingegen immer nur für die ausgewählten Inhalte auf dem gerade geöffneten Pi. Die Wiedergabezeiten werden nativ auf Anthias gespeichert; **jeder Inhalt besitzt genau ein wiederkehrendes Zeitfenster**.

## Geräte-Standard und neue Inhalte

Jeder Pi hat optional **seinen eigenen Geräte-Standard aus der gemeinsamen Sammlung**, der bei neuen Inhalten vorgeschlagen wird. Ohne Standard werden neue Inhalte zeitlich nicht eingeschränkt. Für jeden direkten Website-, Einzelmedien-, Mehrfach- und ZIP-Upload sowie für das Übertragen einer Bibliotheksvorlage oder eines einzelnen Bibliotheksinhalts kann Marketing den Geräte-Standard übernehmen, einen anderen benannten Zeitplan wählen oder ausdrücklich **Ohne Zeitplan** wählen. Bei direkten Pi-Uploads gibt es zusätzlich eine Auswahl für individuelle Wochenzeiten.

Bei Sammeluploads gilt eine Auswahl für die gesamte Aktion; einzelne Inhalte können später abweichen. Bereits vorhandene Pi-Inhalte werden durch einen neuen Standard **nicht** verändert. Beim Übertragen einer Vorlage werden übersprungene schon vorhandene Webseiten nicht umgeplant.

**Bibliotheksvorlagen bleiben zeitplanunabhängig.** Ihre Dateien und Metadaten enthalten keine Pi-spezifischen Scheduling-Einstellungen. Die Zeitplanung wird erst am Ziel-Pi gewählt; die Auswahlliste passt sich an den Zielbildschirm an.

## Native Anthias-Semantik

Anthias ist die alleinige Wiedergabe-Engine: API v2 Asset-Felder play_days (1=Mo bis 7=So), play_time_from und play_time_to, interpretiert in der **lokalen Zeitzone des Pi**. Der Hub führt keine Hintergrund-Schedule aus.

Neue Inhalte mit einem Zeitplan werden **deaktiviert angelegt**, erst nach bestätigtem Schreiben der Wochenregel aktiviert. Bei einem API-Fehler bleibt ein teilweise angelegter Eintrag deaktiviert und muss überprüft werden. Die Reihenfolge und der Pause-Status bestehender Medien werden nicht verändert.

Die **gemeinsamen benannten Regeln**, **pro Pi gewählten Geräte-Standards** und **pro Pi gespeicherten Inhalt-zu-Regel-Zuordnungen** werden unter **/data/schedules.json** gespeichert. Beim ersten Schreibvorgang migriert Hub ältere, je Gerät angelegte Zeitpläne ohne ursprüngliche Datensätze zu löschen. Identische Namen mit identischen Zeiten werden zusammengeführt; bei gleichem Namen und unterschiedlichen Zeiten wird die abweichende Vorlage mit Gerätekennung unterscheidbar benannt. Geräte-Standards und Inhalt-Zuordnungen zeigen anschließend weiterhin auf die richtigen Regeln. Vor einem Rollout die bestehende `schedules.json` wie die anderen Hub-Daten sichern. Die tatsächlichen Zeiten bleiben in Anthias. Bei externen Änderungen zeigt der Hub **Abweichend in Anthias** statt den eigenen Stand ungefragt wiederherzustellen.

## Änderung, Löschung und Teilfehler

Das Bearbeiten einer gemeinsamen Vorlage ändert deren Namen und Zeiten in allen Hub-Auswahllisten, verändert jedoch zunächst **keinen Pi**. Eine explizite Checkbox aktualisiert bei Bedarf die bisher noch unverändert zugeordneten Assets **nur auf dem aktuell geöffneten Pi**. Andere Geräte können die geänderte Vorlage später kontrolliert übernehmen: `Aktualisierung ausstehend` heißt, dass Anthias noch die zuletzt bestätigten alten Zeiten ausführt. `Abweichend in Anthias` heißt, dass dort jemand die Regeln unabhängig vom Hub geändert hat – diese Einträge werden niemals automatisch überschrieben.

Das **hubweite Löschen** einer Vorlage erfordert eine zweite Bestätigung. Es entfernt diese Regel aus der Sammlung, löscht sie als Geräte-Standard auf **allen Pis** und bereinigt alle Zuordnungen im Hub. Die **tatsächlichen Pi-Zeitfenster bleiben erhalten**, bis Marketing sie ausdrücklich auf „Ohne Zeitplan“ setzt. Dabei bleiben Datumslimits und Pause-Status unverändert.

Bei teilweise erfolgten API-Aktionen zeigt Hub die bestätigte Anzahl an und fordert zur Prüfung der Pi-Playlist auf. **Kein automatischer Retry und kein automatischer Rollback.**

## Zeitlücken, Berechtigungen, Betrieb

Zeitplanung zeigt nur **Hinweise auf mögliche Lücken**, wenn nicht an allen Tagen ein dauerhaft verfügbares Medium aktiv ist. Es werden **keine Fallback-Playlists** erzeugt, keine Inhalte automatisch aktiviert und keine HDMI-/Bildschirmstromzeiten geändert. Zeitgesteuertes An-/Ausschalten des Fernsehers ist eine separate Anthias-Funktion und gehört nicht zu diesem Feature.

**Marketing, IT und Owner:** Zeitpläne verwalten, Geräte-Standard festlegen, Inhalte schedulen. Nur Marketing/Owner dürfen neue Inhalte hochladen und die Bibliothek bearbeiten. **Viewer:** nur lesen. Sämtliche Schreibaktionen erfordern Anmeldung und CSRF-Schutz und gelten ausschließlich für registrierte Geräte.

**Realgeräte-Abnahme:** Auf Pi 3 und Pi 5 im originalen Anthias-UI prüfen, ob Wochentage und Uhrzeiten korrekt ankommen und ob Playback beim Fensterwechsel erwartungsgemäß reagiert. Automatisierte API-Tests ersetzen diesen Praxistest nicht.
