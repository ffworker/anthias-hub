# Neuen Anthias-Player aufnehmen — IT-/Azubi-Checkliste

**Ziel:** Einen Raspberry Pi standardisiert aufbauen und sicher in Anthias Hub aufnehmen. Zuerst **einen Test-Pi** abnehmen, dann weitere Geräte nacheinander. Bestehende funktionierende Bildschirme bis zur erfolgreichen Umschaltung unverändert lassen.

## 1. Vorbereitung

- [ ] Geräte-ID, Standort, Raspberry-Pi-Modell, Bildschirm, Netzteil und Datenträger dokumentieren.
- [ ] Bei einem Austausch: vorhandene Playlist, Medien, Zeitpläne und die bisherige Wiedergabe sichern bzw. dokumentieren. Alten Datenträger bis zum erfolgreich geprüften Ersatz aufbewahren.
- [ ] Ein freigegebenes Verwaltungsnetz und eine **stabile IP** vorsehen, bevorzugt per DHCP-Reservierung. Keine doppelte Adresse vergeben; DNS/NTP und Erreichbarkeit prüfen.
- [ ] Verwaltete SSH-/Admin-Zugänge und ein Updateschema für den Pi festlegen; keine Standardpasswörter verwenden.

## 2. Anthias aufsetzen

**Empfohlener Standard:** Raspberry Pi OS Lite **64-Bit** auf dafür unterstützter Hardware installieren und Anthias über das [offizielle Installationsverfahren](https://anthias.screenly.io/docs/install/) einrichten. **Pi 4/5 bevorzugen**; Pi 3 B/B+ ist mit 64-Bit unterstützt, aber bei anspruchsvollen Videos eingeschränkter. Für ältere Pi-Modelle die [offiziell passende Image-/Architekturvariante](https://anthias.screenly.io/get-started/) prüfen, statt pauschal 64-Bit zu installieren. Für ein reines Anthias-Gerät ist das fertige Anthias-Image über Raspberry Pi Imager eine Alternative. **Die Methoden nicht mischen**: fertige Images und Installationen auf Raspberry Pi OS Lite haben unterschiedliche Updatewege.

Für die bewusst gewählte Lite-/Skript-Variante:

```bash
curl -fsSL https://install-anthias.srly.io -o install-anthias.sh
less install-anthias.sh  # vor Ausführung prüfen
bash install-anthias.sh
```

Bei den Installer-Abfragen **Netzwerkverwaltung, Anthias-Version/Tag und System-Upgrade bewusst auswählen und dokumentieren**. Für reproduzierbare Rollouts nach einem getesteten Tag statt unkontrolliertem `latest` fragen. Die Netzwerkverwaltung durch den Installer kann bestehende Konfiguration verändern: vorher lokale Konsole/Recovery sichern. Nach Abschluss neu starten und prüfen, ob Anthias tatsächlich startet.

Die native Anthias-Oberfläche ist anschließend normalerweise unter `http://<PI-IP>/` erreichbar. Nur im vertrauenswürdigen IT-Netz öffnen; die Pi-API darf nicht frei für Marketing-Clients oder das Internet erreichbar sein.

## 3. Im Hub registrieren (IT)

- [ ] Kontrollieren, dass der **Hub-Host** die Pi-IP/Anthias-API erreichen kann und die Adresse in `ANTHIAS_ALLOWED_CIDRS` freigegeben ist.
- [ ] Mit IT-/Owner-Konto im Hub unter **Bildschirme** den Pi registrieren; Name/Standort eindeutig wählen.
- [ ] Den Pi **nicht** über eine öffentliche Management-Adresse anbinden. Den Hub für Marketing nur über freigegebenen HTTPS-/VPN-Zugang bereitstellen.
- [ ] Eine Test-Webseite und ein Testbild über den Hub hinzufügen, Reihenfolge und Anzeigedauer prüfen. Am **physischen Bildschirm** bestätigen, nicht nur in der Vorschau.
- [ ] Wochen-/Uhrzeit-Zeitplan testen, Pi neu starten und die Wiedergabe erneut prüfen.
- [ ] Falls vom Modell und Monitor unterstützt, Bildschirmsteuerung (HDMI-CEC) und Pi-Reboot gezielt testen. Power-Off nur mit lokalem Wiederanlaufplan prüfen.
- [ ] Den Hub kurzzeitig unerreichbar machen und bestätigen, dass die bereits eingerichtete **native Pi-Playlist und Zeitplanung weiterlaufen**. Bei Webseiten muss der jeweilige Webserver separat erreichbar bleiben.

## 4. Freigabe und Übergabe

- [ ] Pi-Backup und Wiederherstellungsweg dokumentieren; Hub-Daten werden **separat** gesichert.
- [ ] Installierten Anthias-Stand/Tag, OS-Version, Hostname, IP-Reservierung, Standort und Prüfergebnis festhalten (keine Passwörter in Tickets).
- [ ] Erst nach erfolgreichem Bildschirmtest alten Player ersetzen; bei Problemen vorheriges System wieder anschließen.
- [ ] Danach erst das nächste Gerät umstellen. Für den Bistro-Bildschirm ebenfalls **zuletzt** ein eigenes Wartungsfenster planen.

**Betriebsprinzip:** Der Hub vereinfacht zentrale Pflege; **Anthias läuft auf jedem Pi eigenständig**. Die direkte Pi-Oberfläche ist ein IT-Fallback, keine zweite frei zugängliche Marketing-Verwaltung. Änderungen direkt am Pi können im Hub bei Zeitplänen als *„Abweichend in Anthias“* markiert werden.

Weitere Prüfpunkte: [Pilot-/Produktionsabnahme](pilot-acceptance.md) · [IT-Betrieb und Backups](IT_ADMIN_GUIDE.md) · [Sicherheit](../SECURITY.md).
