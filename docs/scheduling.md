# Zeitplanung auf Anthias-Geräten (Marketing + IT)

**Stand:** 16. Oktober 2026. Anthias Hub nutzt die native **v2 Asset-Scheduling-API** von Anthias: \`play_days\` (ISO-Wochentag 1=Montag bis 7=Sonntag), \`play_time_from\` und \`play_time_to\`. Das **Zeitplan-Studio** ist auf der Bildschirmübersicht sowie in der jeweiligen Playlist unter **Zeitpläne** erreichbar.

## Beispielszenario

1. Öffne **Bildschirme → [Pi] → Zeitpläne**. Dort bleiben andere Pis unverändert.
2. Erstelle den benannten Zeitplan **Werktag_Default** für **Mo–Fr, 08:00–18:00 Uhr** (Beispielschaltfläche vorhanden).
3. Erstelle **Event** für **Samstag, 10:00–14:00 Uhr**.
4. Wähle unten den Plan und **markiere die Inhalte**, die zu diesen Zeiten sichtbar sein sollen. Drücke **Auf ausgewählte Inhalte anwenden**. Die Zuordnung erfolgt direkt auf dem Anthias-Pi.
5. Wähle **Ohne Zeitplan** und markiere Inhalte, um nur deren Wochen-/Uhrzeitfilter zurückzusetzen. Die bestehende Datumsspanne (\`start_date\`/\`end_date\`), \`is_enabled\`, Reihenfolge und Anzeigedauer bleiben erhalten.

**Wichtig:** Ein Anthias-Inhalt hat **genau einen** wiederkehrenden Wochentags-/Uhrzeitfilter. Mehrere benannte Zeitpläne auf demselben Pi gelten also für **verschiedene Inhalte**, nicht als mehrere unabhängige Zeitfenster für dieselbe Datei. Neue Inhalte erhalten nicht automatisch einen der Hub-Zeitpläne; weise sie nach dem Import gezielt zu.

Ein Zeitfenster mit \`22:00 → 06:00\` reicht bis in den nächsten Tag; die ausgewählten Wochentage meinen den **Starttag**. Die Endzeit ist exklusiv. Die **lokale Zeitzone auf dem Raspberry Pi** bestimmt die Ausführung; der Hub muss zur Wiedergabe nicht online sein. Anthias aktualisiert den Viewer beim Fensterwechsel.

## Wie Hub und Anthias zusammenarbeiten

- Die **Namen** der Zeitplanvorlagen stehen in der persistenten Hub-Datei \`/data/schedules.json\` (Container-Volume). Anthias selbst hat **keine benannten Zeitplan-Objekte**.
- Die tatsächlichen Wiedergabebeschränkungen bleiben **nativ am Pi** in den einzelnen Assets. Eine direkte Änderung im originalen Anthias-UI wird angezeigt, auch wenn der Zeitplanname im Hub nicht mehr passt. Solche Änderungen erscheinen als **„Individuell in Anthias“**.
- **Zeitplanvorlage bearbeiten:** Nur die gespeicherte Hub-Vorlage ändern; bereits mit dem alten Zeitfenster konfigurierte Inhalte bleiben sicherheitshalber unverändert. Damit die neuen Zeiten wirksam werden, wähle die Inhalte unten **erneut** aus und wende den geänderten Plan an.
- **Zeitplanvorlage entfernen:** Löscht **nur** die benannte Hub-Vorlage. Die zeitlichen Einstellungen am Pi werden nicht stillschweigend verändert. Um sie zu entfernen, wähle **Ohne Zeitplan** und die betreffenden Inhalte.
- Der Hub sendet ausschließlich \`PATCH /api/v2/assets/{asset_id}\` mit \`play_days\`, \`play_time_from\`, \`play_time_to\`. Vor einem Batch werden alle ausgewählten Einträge validiert. Nach jedem PATCH wird die Antwort auf die tatsächliche Übernahme des Plans geprüft.
- Wenn Anthias die Scheduling-Felder noch nicht liefert, wird dies abgelehnt, statt einen erfolgreichen Speichervorgang vorzutäuschen. **Es muss eine kompatible Anthias-Version installiert sein.**
- Eine Massenänderung kann bei API-Fehlern **teilweise** angewendet worden sein. Dann zeigt der Hub die bestätigte Anzahl an und fordert zur Kontrolle direkt am Player auf. **Kein automatischer Retry und keine automatische Änderung anderer Inhalte.**

## Rechte, Sicherheit und Betrieb

**Marketing, IT und Owner:** Zeitplanvorlagen anlegen, bearbeiten, löschen und auf Assets anwenden. **Viewer:** Zeitfenster und Zuordnungen nur ansehen. Alle Schreibaktionen sind CSRF-geschützt, registrierten Pis vorbehalten und protokolliert. Zeitplan-Namen, Wochentage und Uhrzeiten werden serverseitig validiert; es werden maximal 20 Vorlagen je Gerät und höchstens 100 Assets pro einmaliger Zuweisung akzeptiert.

Die Vorlagen-Datei liegt auf dem bestehenden /data-Volume und muss zusammen mit \`devices.json\` und Bibliothek gesichert werden. Die echten Laufzeiten liegen auf den Pis und überleben einen Neustart des Hubs.

**Abgrenzung:** Die Anthias-Geräteeinstellung für **Bildschirm an/aus** (\`display_power_schedule_enabled\`) ist **separat** von der Inhalts-Zeitplanung. Dieses Hub-Studio steuert, **welcher Inhalt wann sichtbar ist**, nicht die HDMI-Stromversorgung. Sollen Inhalte bei geschlossenem Geschäft überhaupt nicht angezeigt werden, kann die Playlist außerhalb der Zeitfenster leer wirken; das bedeutet nicht, dass der Fernseher abgeschaltet wird.

## Offizieller Bezug

- [Anthias Asset Scheduling](https://anthias.screenly.io/docs/asset-scheduling/)
- [Anthias v2 API Reference](https://anthias.screenly.io/api/)
