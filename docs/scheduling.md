# Scheduling 2.0 – Playlist und Zeitplanung

**Stand:** 16. Oktober 2026 · Pro Anthias-Gerät · Deutsch.

## Navigation und Arbeit

Unter **Bildschirme → Playlist** teilen sich **Playlist** und **Zeitplanung** denselben Header und sind gleichwertige Ansichten desselben Pis. Die Playlist ist der Standard-Tab. Jeder Playlist-Inhalt zeigt seinen Zeitplan direkt an; im aufgeklappten Editor kann Marketing die Zeitplanung ändern, einschließlich „Ohne Zeitplan“, benannter Vorlage oder individueller Wochentage/Uhrzeiten.

Auf der **Zeitplanung**-Ansicht können Marketing und IT benannte Wochenfenster erstellen, z. B. Werktag_Default (Mo–Fr, 08–18 Uhr) oder Event (Sa, 10–14 Uhr), und mehreren Inhalten zuweisen. Die Wochentage und Uhrzeiten werden direkt in Anthias gespeichert; **jeder Inhalt besitzt genau ein natives wiederkehrendes Zeitfenster**.

## Geräte-Standard und neue Inhalte

Jeder Pi hat optional **einen Geräte-Standard**, der bei neuen Inhalten vorgeschlagen wird. Ohne Standard werden neue Inhalte zeitlich nicht eingeschränkt. Für jeden direkten Website-, Einzelmedien-, Mehrfach- und ZIP-Upload sowie für das Übertragen einer Bibliotheksvorlage oder eines einzelnen Bibliotheksinhalts kann Marketing den Geräte-Standard übernehmen, einen anderen benannten Zeitplan wählen oder ausdrücklich **Ohne Zeitplan** wählen. Bei direkten Pi-Uploads gibt es zusätzlich eine Auswahl für individuelle Wochenzeiten.

Bei Sammeluploads gilt eine Auswahl für die gesamte Aktion; einzelne Inhalte können später abweichen. Bereits vorhandene Pi-Inhalte werden durch einen neuen Standard **nicht** verändert. Beim Übertragen einer Vorlage werden übersprungene schon vorhandene Webseiten nicht umgeplant.

**Bibliotheksvorlagen bleiben zeitplanunabhängig.** Ihre Dateien und Metadaten enthalten keine Pi-spezifischen Scheduling-Einstellungen. Die Zeitplanung wird erst am Ziel-Pi gewählt; die Auswahlliste passt sich an den Zielbildschirm an.

## Native Anthias-Semantik

Anthias ist die alleinige Wiedergabe-Engine: API v2 Asset-Felder play_days (1=Mo bis 7=So), play_time_from und play_time_to, interpretiert in der **lokalen Zeitzone des Pi**. Der Hub führt keine Hintergrund-Schedule aus.

Neue Inhalte mit einem Zeitplan werden **deaktiviert angelegt**, erst nach bestätigtem Schreiben der Wochenregel aktiviert. Bei einem API-Fehler bleibt ein teilweise angelegter Eintrag deaktiviert und muss überprüft werden. Die Reihenfolge und der Pause-Status bestehender Medien werden nicht verändert.

Benannte Regeln, Geräte-Standards und explizite Inhalt-zu-Regel-Zuordnungen werden im persistenten Hub-Volume unter **/data/schedules.json** gespeichert, kompatibel zu früheren Versionen. Die tatsächlichen Zeiten bleiben in Anthias. Bei externen Änderungen zeigt der Hub **Abweichend in Anthias** statt den eigenen Stand ungefragt wiederherzustellen.

## Änderung, Löschung und Teilfehler

Das Bearbeiten einer benannten Vorlage verändert die bisherigen Pi-Inhalte zunächst **nicht**. Eine explizite Checkbox bietet an, bestätigte, noch unverändert zugeordnete Assets beim Speichern ebenfalls zu aktualisieren. Direkt in Anthias veränderte Elemente werden dabei ausgespart. Das Entfernen eines Presets verändert den Pi überhaupt nicht; die geplanten Zeiten bleiben erhalten, bis Marketing sie bewusst per „Ohne Zeitplan“ zurücksetzt. Dabei bleiben Datumslimits und Pause-Status unverändert.

Bei teilweise erfolgten API-Aktionen zeigt Hub die bestätigte Anzahl an und fordert zur Prüfung der Pi-Playlist auf. **Kein automatischer Retry und kein automatischer Rollback.**

## Zeitlücken, Berechtigungen, Betrieb

Zeitplanung zeigt nur **Hinweise auf mögliche Lücken**, wenn nicht an allen Tagen ein dauerhaft verfügbares Medium aktiv ist. Es werden **keine Fallback-Playlists** erzeugt, keine Inhalte automatisch aktiviert und keine HDMI-/Bildschirmstromzeiten geändert. Zeitgesteuertes An-/Ausschalten des Fernsehers ist eine separate Anthias-Funktion und gehört nicht zu diesem Feature.

**Marketing, IT und Owner:** Zeitpläne verwalten, Geräte-Standard festlegen, Inhalte schedulen. Nur Marketing/Owner dürfen neue Inhalte hochladen und die Bibliothek bearbeiten. **Viewer:** nur lesen. Sämtliche Schreibaktionen erfordern Anmeldung und CSRF-Schutz und gelten ausschließlich für registrierte Geräte.

**Realgeräte-Abnahme:** Auf Pi 3 und Pi 5 im originalen Anthias-UI prüfen, ob Wochentage und Uhrzeiten korrekt ankommen und ob Playback beim Fensterwechsel erwartungsgemäß reagiert. Automatisierte API-Tests ersetzen diesen Praxistest nicht.
