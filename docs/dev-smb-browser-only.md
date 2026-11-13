# SMB ausschließlich über die DEV-Oberfläche einrichten

**Keine Linux-Mounts, keine SMB-Credentials-Dateien und kein SSH für die
Einrichtung einer Freigabe.** Voraussetzung: der separat laufende DEV-Hub
wurde mit diesem Branch aktualisiert. Produktion bleibt unberührt.

## Browser-Ablauf

1. DEV über den bestehenden SSH-Tunnel öffnen:
   `http://127.0.0.1:8766`. Mit einem IT-/Owner-Konto einloggen.
2. **Ordner & Quellen** öffnen.
3. Unter **SMB-Pfad hinterlegen** die Adresse (z. B.
   `//10.11.12.13/files$/Marketing/Bildschirme`), Benutzername,
   Kennwort und ggf. Domäne eingeben.
4. **Verbinden & prüfen** drücken. Hier wird **sofort** eine echte
   SMB3-Verbindung aufgebaut und die Liste der direkten Unterordner
   gelesen. Bei falschem Kennwort oder unerreichbarer Freigabe gibt
   es eine Fehlermeldung, ohne dass der letzte funktionierende
   Speicherstand überschrieben wird.
5. Nach Erfolg zeigt **Was passiert gerade?** den wirklichen Zustand.
   Der separate DEV-Importer liest den Ordner ein, kopiert JPG/PNG/WebP/MP4
   in seinen DEV-Speicher und stellt die Unterordner als Playlist-Quellen
   bereit. Der Status aktualisiert sich alle drei Sekunden.
   **Große Freigaben werden automatisch in Abschnitten mit höchstens 4 GiB
   übertragen.** Das ist eine Grenze pro Abschnitt, nicht für die gesamte
   Bibliothek. Weitere Abschnitte folgen ohne erneuten Klick. Jeder
   erfolgreich vollständig kopierte Datensatz wird als Checkpoint
   gespeichert und bei einem Neustart nicht erneut übertragen.
   Im UI erscheinen `X von Y Medien` sowie die bestätigten GiB.
6. Später **Jetzt synchronisieren** drücken, um einen weiteren Import
   anzustoßen, oder automatisch alle 60 Sekunden synchronisieren lassen.
7. **Playlists** öffnen und eine Ordner-Playlist aus einem bestätigten
   Unterordner anlegen. Eine dauerhafte Bildschirmzuordnung und das
   automatische Veröffentlichen auf den Pi sind separate Schritte.
   **Automatische Pi-Veröffentlichung ist weiterhin AUS.**

## Was wirklich passiert

Die Anwendung benutzt `smbprotocol` als SMB3-Client. Sie führt **nur
lesende SMB-Anfragen** (Verzeichnisse listen, Dateien öffnen) aus;
es gibt keine Remote-Schreiboperationen, keinen `mount.cifs`-Aufruf
und keine Root-Rechte in den Web-/Importer-Containern.

Zugangsdaten werden im DEV-Datenverzeichnis als **Fernet-verschlüsseltes
Dokument (Dateimodus 0600)** gespeichert. Der Schlüssel wird aus dem
individuellen DEV-`APP_SECRET_KEY` abgeleitet. Das Passwort wird
weder in HTML zurückgerendert noch im Status, in Logs, Git oder in
URLs ausgegeben. **Bei Änderung des DEV-`APP_SECRET_KEY` muss man
die SMB-Anmeldung im Browser neu eingeben.** Bitte ein eigenes
Konto mit rein lesendem SMB-Zugriff nutzen.

SMB3-Verschlüsselung wird für den Zugriff vorausgesetzt
(`encrypt=True`). Ältere SMB-Server ohne SMB3 lassen sich in
diesem Modus bewusst nicht verbinden. Der Server muss vom DEV-Container
auf Port 445 erreichbar sein.

Im DEV-Cache wird die ursprüngliche Dateistruktur
`default/<Bildschirmordner>/<Medium>` angelegt. Bei Netzwerkfehlern
bleiben die zuletzt erfolgreich kopierten Medien erhalten; die
Synchronisierung und Pi-Veröffentlichung werden nicht fälschlich als
erfolgreich markiert. Wechsel auf eine andere SMB-Quelle wird zuerst
in einen gesonderten Zwischenspeicher kopiert, statt die Inhalte
zweier Quellen zu vermischen.

Ein unvollständiger Teilimport bleibt als „Medienübernahme läuft“
sichtbar. Bis alle Dateien geprüft sind, wird die neue SMB-Quelle
nicht als fertig synchronisiert oder veröffentlichungsbereit dargestellt.
Neue Quellen werden in einem separaten versteckten Zwischenspeicher
geladen und erst vollständig gegen den bestehenden DEV-Spiegel getauscht.
Bei zu wenig DEV-Speicherplatz (pro Datei mindestens 256 MiB Reserve)
erscheint ein konkreter Fehler, ohne die Hostplatte vollzuschreiben.

**Dateientfernung ist bewusst konservativ:** Wenn eine Datei auf SMB
verschwindet, wird sie im lokalen DEV-Cache vorläufig behalten.
Automatische Bereinigung/Deaktivierung ist ein später getrennt
freizugebender Schritt und kein Teil der Browser-Verbindung.

## Einmaliger DEV-Code-Update (nicht SMB-Konfiguration)

Wenn der Branch noch nicht lokal aktiv ist, im **separaten DEV-Checkout**
ausführen:

```bash
cd /root/apps/anthias-hub-dev
git fetch origin dev/screen-source-of-truth-v2-20261113
git switch dev/screen-source-of-truth-v2-20261113
git pull --ff-only
bash scripts/dev-cohost.sh start
bash scripts/dev-cohost.sh status
```

Dabei wird **nur** das Docker-Compose-Projekt
`anthias-hub-dev` auf Port 8766 aktualisiert. Die Produktion wird
nicht neugestartet. Nach dieser einmaligen Bereitstellung erfolgt das
Hinzufügen und Synchronisieren von SMB-Netzwerkordnern ausschließlich im UI.
