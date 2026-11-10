# Digital Signage: Netzwerk-, VLAN- und IPAM-Standard

> **Öffentliche Referenz, keine Standortinventur.** Alle Netzadressen, VLAN-Nummern und Gerätenamen in dieser Datei sind **Beispiele**, keine Angaben zu einer realen Installation. Reale VLANs, Gateways, Switchports, SSIDs, DHCP-Leases, MACs, Firewall-Regeln, Hostnamen und Geräte-IP-Adressen gehören in die zugriffsgeschützte interne IT-Dokumentation, nicht in GitHub oder öffentliche Tickets. Siehe [Repo-Hygiene](public-repo-hygiene.md).

## 1. Bausteine und Verantwortung

| Rolle | System | Verantwortung |
| --- | --- | --- |
| Verwaltungsoberfläche | Anthias Hub auf Linux/Docker | Geräte registrieren, Status, Playlists, gemeinsame Zeitpläne, sichere Übertragungen |
| HTTPS-Einstieg | Hostseitiger Reverse Proxy (z. B. Caddy) | Nur autorisierte Nutzer, HTTPS auf 443, Weitergabe an Hub auf Loopback 8765 |
| Player | Je Raspberry Pi mit Anthias | Eigene lokale Playlist, Medien, Zeitplanung, native REST-API v2 |
| Quelldaten | Freigegebener SMB-Server | Bilder/Videos; Hub-Host mountet den zentralen Stamm **read-only** |
| Importer | Separater optionaler Worker | Änderungen in Bibliotheksvorlagen übernehmen; Veröffentlichungen separat freigeben |
| Web-Inhalte | Separater RSS-/Kiosk-Webserver | Liefert dynamische Webseite, die **der Pi** selbst laden können muss |
| IP-/VLAN-Verwaltung | DHCP/DNS, Firewall, WLAN-Controller, Switches | VLAN-Zuordnung, Reservierungen, Routen, ACLs, Dokumentation |

```text
Freigegebener Admin-/Marketing-Browser
           | HTTPS 443 (authentifiziert)
           v
   HTTPS-Reverse-Proxy auf Hub-Host
           | localhost:8765
           v
      Anthias-Hub-Container
           | TCP 80 /api/v2/* (ausgehend zum Pi)
           +--------------------------> Anthias-Pi A (WLAN oder LAN)
           +--------------------------> Anthias-Pi B
           | SMB TCP 445 (nur Host/Importer)
           +--------------------------> freigegebener Medienserver

   Anthias-Pi ---- HTTP(S) ----> gesonderter RSS-/Kiosk-Webserver
```

Der Hub ist **nicht** der Player. Eine Hub-Unterbrechung muss die vorhandenen Pi-Playlists und lokalen Zeitpläne unangetastet lassen. Dynamische Webseiten benötigen trotzdem den erreichbaren externen Webserver.

## 2. VLAN- und Subnetzentscheidung

**Standardziel:** Digital-Signage-Player pro Standort in einem klar bezeichneten, verwalteten IoT-/Signage-Segment. Ob dafür ein eigenes VLAN erforderlich ist oder ein vorhandenes, sauber geroutetes WLAN-VLAN verwendet wird, entscheidet die zuständige Netzwerkadministration. **Dies ist keine automatische VLAN-Konfiguration.**

In der **internen** Netzwerkdoku ist für *jeden* Standort festzuhalten:

1. Standort / Bereich / sichtbarer Bildschirmname; physischer Anschluss oder SSID; **tatsächliche VLAN-ID** aus Switch-/WLAN-Controller; zuständiges Team.
2. IPv4-Netz mit Präfix, Gateway/SVI, DHCP-Server/Scope, DNS/NTP; aktuelles ACL-/Routing-Verhalten.
3. Die Quelladresse des Hubs und die erlaubte Verbindung **Hub → Pi TCP/80**, Rückverkehr und optionale IT-SSH-Verwaltung.
4. Die tatsächliche Player-IP sowie ihre MAC, DHCP-Lease-/Reservierungs-ID, Hostname, Hub-Geräte-ID und Installation/Anthias-Version.

**Gleiches SSID ist kein Nachweis für dasselbe VLAN.** WLAN-Controller können je Standort, AP, Client oder Authentisierung verschiedene VLANs zuweisen. Umgekehrt ist ein anderes /24 nicht automatisch ein anderes VLAN. VLAN-IDs dürfen niemals aus dem dritten IPv4-Oktett abgeleitet werden.

Ein *rein hypothetisches* Segment könnte heißen `SITE-A-SIGNAGE`, VLAN-ID `<durch IT zu bestätigen>` und Subnetz `192.168.50.0/24`. **Nicht** diese Beispielwerte im Unternehmensnetz übernehmen.

**Migration:** Bestehende, funktionierende Spieler nicht blind in ein neues VLAN verschieben. Zuerst geroutete Hub-Erreichbarkeit, bestehende RSS-/Web-Quellen, DNS/NTP, Konnektivität und Rollback prüfen. Freigabe pro Bildschirm.

## 3. Adressbereich planen und im DHCP/IPAM reservieren

Empfehlung für kleine bis mittlere Installationen: **ein 32er-Hostblock pro tatsächlich genutztem /24**, z. B. `192.168.50.32–192.168.50.63` (nur Anschauung). Der Block wird **nicht** allein durch einen Eintrag im Hub reserviert.

Reihenfolge:

1. **Bestandsaufnahme:** DHCP-Scopes, aktive Leases, feste IPs, Reservierungen, Netzwerkdrucker, Access Points und andere Geräte auf Kollisionen prüfen.
2. **Bereich auswählen:** Keine bereits belegten Adressen; genügend Platz für Ersatzgeräte. Reservierungsblock, Gateway, DNS und echte VLAN-ID im internen IPAM eintragen.
3. **DHCP konfigurieren:** Bestehenden dynamischen Pool gegebenenfalls um den Signage-Block bereinigen bzw. ihn explizit ausschließen; MAC→IP-Reservierungen im autoritativen DHCP-Server erstellen. Keinesfalls unbeabsichtigt einen vorhandenen Pool löschen.
4. **Netzwerkeinstellung des Pi:** Bevorzugt DHCP + Reservierung. Bei zwingend statischer Konfiguration IP/Präfix/Gateway/DNS/NTP festhalten und Adresse sicher außerhalb dynamischer Vergaben halten. Keine widersprechende Reservierung und statische Konfiguration als „automatisch synchron“ betrachten.
5. **Verifikation:** Erreichbarkeit, korrekte Quell-/Rückroute, API-JSON, echte Bildausgabe, erneute Prüfung nach Neustart; im IPAM als *umgesetzt* markieren.

**Statusbezeichnungen:** `vorgeschlagen` · `auf DHCP-/Firewall-Seite umgesetzt` · `am Pi geprüft` · `produktiv freigegeben`. Ohne verifizierte DHCP-/Controller-Konfiguration bleibt ein Bereich **nur ein Vorschlag**.

## 4. Gewünschte Kommunikationspfade

| Quelle → Ziel | Protokoll | Bedingung |
| --- | --- | --- |
| Genehmigter Client → Hub-HTTPS-Proxy | TCP/443 | Authentifiziert; keine direkte Backend-Port-Freigabe |
| Hub-Host/Container → Anthias-Pi | TCP/80 | Anthias API v2 unter `/api/v2/assets`; ggf. ausdrücklich konfigurierte Ports |
| Autorisierte IT-Geräte → Pi | TCP/22 (optional) | SSH nur für IT und nur bei Bedarf |
| Pi → freigegebener RSS-/Webserver | TCP/80 bzw. 443 | Nur benötigte Webseiten-Quellen; Pi muss URL selbst erreichen |
| Hub-Host → SMB-Medienquelle | TCP/445 | Read-only-Mount; Credentials ausschließlich hostprivat |
| Pi → interne DNS/NTP-Dienste | DNS/53 und NTP/123 | Nur die tatsächlich betriebenen Dienste |
| Gewöhnlicher Marketing-Client → Pi-Management | **nicht zulassen** | Sonst werden Hub-Rollenbeschränkungen umgangen |
| Internet → Hub-Backend/Player-API | **nicht zulassen** | Nur freigegebener HTTPS-/VPN-Einstieg |

Firewall-Regeln sind standort- und policyabhängig. Ob ein Client eine Pi-Webseite öffnen kann, ist **kein** Nachweis, dass der Hub-Container sie erreichen kann. Die Portfreigaben nicht pauschal für ganze RFC1918-Netze öffnen. Bei aktivierten VLAN-ACLs auch Stateful-Rückverkehr prüfen.

## 5. Read-only Abnahme vor Hub-Registrierung

Am **neuen Pi**:

```bash
ip -4 addr show dev wlan0                  # oder die tatsächlich verwendete LAN-Schnittstelle
ip -4 route
ip -4 route get <HUB_LAN_IP>
nmcli -f GENERAL.CONNECTION device show wlan0  # falls NetworkManager benutzt wird
curl -i --max-time 8 http://127.0.0.1/api/v2/assets
```

Die Maske muss zum echten WLAN-/VLAN-Subnetz passen. Beispiel: Ein Pi mit `192.168.50.42/16` behandelt ein entferntes `192.168.60.x` fälschlich als lokal; mit beabsichtigtem `192.168.50.0/24` führt der Rückweg über das Gateway. **Nie ohne geprüften Scope und lokale Wiederherstellung blind auf /24 umstellen.**

Auf dem **Hub-Host**:

```bash
ip -4 route get <PI_IP>
curl -i --max-time 8 http://<PI_IP>/api/v2/assets
```

Im **Hub-Container** (der Hub nutzt `requests` ohne Umgebungs-Proxies und folgt keinen Weiterleitungen):

```bash
cd ~/apps/anthias-hub
OVERRIDE=$(sed -n 's/^HUB_COMPOSE_OVERRIDE=//p' .env)
test -n "$OVERRIDE" && test -f "$OVERRIDE" || exit 1
export PI_API='http://<PI_IP>'
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub \
  exec -T -e PI_API="$PI_API" anthias-hub python - <<'PY'
import os
import requests
session = requests.Session()
session.trust_env = False
try:
    response = session.get(
        os.environ["PI_API"] + "/api/v2/assets",
        timeout=6, allow_redirects=False,
    )
    print("HTTP:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))
    payload = response.json()
    print("JSON-Liste:", isinstance(payload, list),
          "Anzahl:", len(payload) if isinstance(payload, list) else "-")
except (requests.RequestException, ValueError) as exc:
    print("Prüfung fehlgeschlagen:", type(exc).__name__, str(exc)[:120])
PY
```

Erwartung: **HTTP 200, JSON-Liste**; `[]` gilt als erfolgreich und bedeutet **leere Playlist**. Ein Browser auf `http://<PI_IP>/` prüft nur die native HTML-Oberfläche, nicht die API. 301/302 (Redirect), 401/403, 404, HTML statt JSON und Timeouts getrennt diagnostizieren. Das Registrierungsformular speichert den Eintrag **auch ohne vorherige Erreichbarkeitsprüfung**; der nachgelagerte Gerätestatus kann daher „Nicht erreichbar“ anzeigen.

Falls Host funktioniert, Container nicht: Docker-Netz/Firewall prüfen. Falls Hub-Host scheitert: L3-Routen, WLAN-Isolation, Controller/ACL und **Rückroute auf dem Pi** prüfen. Bei überraschendem `Destination Host Unreachable` Subnetzmaske/ARP zuerst prüfen; keine ACLs auf Verdacht öffnen.

**Zusätzliche Kontrolle:** `docker network ls` und die *tatsächlichen* Docker-Bridge-Subnetze mit den Standort-Routen vergleichen. Docker-Bridges dürfen das Ziel-VLAN nicht ungewollt überdecken.

## 6. Aufnahme & Betrieb

- Im internen IPAM Geräte-ID, Modell, Standort/TV, Ethernet- und/oder WLAN-MAC, VLAN-ID, IP/Präfix, Gateway, DNS, DHCP-Reservierung, Quelle, verantwortliche Person und Abnahmedatum erfassen.
- Test mit **Hub → Pi `/api/v2/assets`** abschließen, dann IT → Hub → **Bildschirme → Bildschirm verbinden**; als Geräteadresse ausschließlich die private **Basis-URL** `http://<PI_IP>` verwenden, nicht `/api/v2/assets`.
- Erst nach positiver API-Abnahme ein Testmedium zuweisen und **am realen Bildschirm** prüfen. Für dynamische RSS-Webseiten muss zusätzlich **Pi → RSS-Webserver** funktionieren.
- Bei einem Umzug, AP-/VLAN-Wechsel oder Pi-Ersatz: IPAM, DHCP/DNS, Hub-Geräteadresse und Firewall-Regeln gemeinsam aktualisieren. Die Daten des früheren Pis nicht löschen, bevor die Wiedergabe verifiziert wurde.
- Backup und Wiederherstellung für Hub und Pi getrennt durchführen; die Vorlagen-ZIP ist kein Backup des gesamten Pi.

Weiterlesen: [Pi-Onboarding](player-onboarding.md), [IT-Guide](IT_ADMIN_GUIDE.md), [TLS und Netzwerkzugriff](network-access.md), [Ordner-Playlists](single-root-smb-setup.md), [Abnahmeliste](pilot-acceptance.md).
