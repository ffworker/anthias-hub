# SSH-Zugriff, Windows-Alias & abgesicherte VM

Für **Anthias Hub (Port 8765)** und **RSS2Slideshow (Port 8085)** auf einer gemeinsamen Linux-VM. Beide Weboberflächen sind am VM-Host standardmäßig nur an `127.0.0.1` gebunden. Ein SSH-Tunnel gibt sie ausschließlich auf dem **eigenen Windows-PC** frei. **Nicht** die Docker-Bind-Adressen ändern oder beide Ports im LAN/Internet öffnen.

> **Wichtig:** Der SSH-Key **Windows-PC → VM** ist **nicht** der GitHub-Deploy-Key **VM → privates RSS2Slideshow-Repository** (`~/.ssh/rss2slideshow_deploy_ed25519`). Getrennte Schlüssel, verschiedene Aufgaben. Private Keys niemals ins Repository oder in Tickets kopieren. Dies ist ein Vorschlag für eine **neu installierte** VM; auf der alten Wegwerf-VM nichts blind umstellen.

## 1. Neuen Linux-Host vorbereiten (VM-Konsole)

Vor der SSH-Umstellung über die **Hypervisor-Konsole** einen normalen Administrator einrichten; `hubadmin` ist nur ein Beispielname:

```bash
sudo apt update
sudo apt install openssh-server sudo
sudo adduser hubadmin
sudo usermod -aG sudo hubadmin
```

Wenn die VM mit dem Root-Konto installiert wurde, sind diese Befehle direkt an der Konsole auch ohne `sudo` möglich. Das Konto erhält eine eigene, sichere Passwortanmeldung für `sudo` und die **anfängliche** SSH-Key-Verteilung. Für das spätere Deployment Git-Checkouts unter **`/home/hubadmin/apps/`** anlegen und Git/Compose möglichst konsistent unter diesem Konto betreiben.

**Docker-Sicherheit:** Mitgliedschaft in der Gruppe `docker` erlaubt faktisch Root-Zugriff auf den Host. Nur ausdrücklich autorisierten Administratoren Docker-Rechte geben; `sudo docker ...` ist ebenfalls eine privilegierte Aktion. Nicht pauschal alle Benutzer in `docker` aufnehmen, nur um einen Installationsbefehl lauffähig zu machen. Vor dem Hub-Setup bewusst klären, **mit welchem Account** Docker Compose betrieben wird (und die Zugriffsrechte testen).

## 2. SSH-Schlüssel auf dem Windows-PC erzeugen (PowerShell)

```powershell
New-Item -ItemType Directory -Force "$HOME\.ssh" | Out-Null
ssh-keygen -t ed25519 -a 100 -f "$HOME\.ssh\id_ed25519_gh_pihub" -C "gh-pihub-admin"
```

Eine **Passphrase** vergeben und sicher verwahren. Die Datei ohne `.pub` ist der **private** Schlüssel und bleibt ausschließlich auf dem Admin-PC. Nicht einen bestehenden Key überschreiben; bei vorhandenem Dateinamen einen neuen Namen wählen. Optional lässt sich die Passphrase über den Windows-OpenSSH-Agent zwischenspeichern, das ist für den Login aber nicht erforderlich.

Vor dem ersten Login den **ED25519-Host-Fingerprint** an der VM-Konsole ermitteln und mit der Anzeige auf dem PC vergleichen:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

**Unbekannte oder plötzlich geänderte SSH-Hostkeys niemals blind akzeptieren** (zuerst IP/DNS, VM und Fingerprint überprüfen).

## 3. Öffentlichen Schlüssel einmalig auf die VM kopieren

Solange Passwort-SSH für **`hubadmin`** noch erlaubt ist, auf dem Windows-PC:

```powershell
Get-Content "$HOME\.ssh\id_ed25519_gh_pihub.pub" |
  ssh hubadmin@VM_IP "umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"
```

`VM_IP` durch die private VM-Adresse ersetzen. Nur der **öffentliche** `.pub`-Schlüssel wird übertragen. Den Passwortzugang erst im **nächsten Schritt** abschalten.

Zuerst in **einem neuen PowerShell-Fenster** den Key-only-Login und `sudo` verifizieren:

```powershell
ssh -i "$HOME\.ssh\id_ed25519_gh_pihub" -o IdentitiesOnly=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no hubadmin@VM_IP
```

Auf der VM dann `whoami` und `sudo -v` prüfen. **Diese Sitzung geöffnet lassen**, bis die folgenden Prüfungen bestanden sind. Bei `Permission denied (publickey)` Benutzername, Schlüsseldatei und `~/.ssh/authorized_keys`-Rechte prüfen und nichts an der SSH-Konfiguration verschärfen, solange der Key-Login noch nicht funktioniert.

## 4. Windows-SSH-Alias: `~/.ssh/config`

Datei **`$HOME\.ssh\config`** auf dem Windows-PC anlegen/bearbeiten (ohne `.txt`); persönliche Einstellungen für andere Hosts nicht überschreiben:

```sshconfig
# Normale, interaktive SSH-Anmeldung.
Host gh-pihub gh-pihub-tunnel
    HostName VM_IP
    User hubadmin
    IdentityFile ~/.ssh/id_ed25519_gh_pihub
    IdentitiesOnly yes
    ServerAliveInterval 30
    ExitOnForwardFailure yes

# Bequemer Zugriff auf BEIDE lokalen Weboberflächen.
Host gh-pihub-tunnel
    LocalForward 127.0.0.1:8765 127.0.0.1:8765
    LocalForward 127.0.0.1:8085 127.0.0.1:8085
```

Wieder `VM_IP` ersetzen. **Auf dem Windows-PC** verwenden:

```powershell
ssh gh-pihub          # Interaktive Shell mit dem richtigen Key
ssh -N gh-pihub-tunnel # Nur Tunnel für Hub UND RSS, Terminal bleibt offen
```

Dann im eigenen Browser **http://127.0.0.1:8765** (Hub) und **http://127.0.0.1:8085** (RSS) öffnen. Mit **Strg+C** den Tunnel beenden.

**Alternative ohne Tunnel-Alias:** Wenn der `gh-pihub`-Host-Alias bereits besteht:

```powershell
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 -L 127.0.0.1:8085:127.0.0.1:8085 gh-pihub
```

Falls lokale Ports bereits belegt sind, **nur lokal** andere verwenden, z. B. `-L 127.0.0.1:18765:127.0.0.1:8765` und `-L 127.0.0.1:18085:127.0.0.1:8085`. Dann `http://127.0.0.1:18765` bzw. `http://127.0.0.1:18085` öffnen. `ExitOnForwardFailure yes` meldet einen nicht aufgebauten Porttunnel sofort.

**Achtung:** Die Weiterleitung nach `127.0.0.1` auf **deinem PC** macht den RSS-Kiosk **nicht** für einen Anthias-Pi erreichbar. Für die TV-Webseite ist separat ein eingeschränkt erreichbarer interner HTTPS-/Proxy-Endpunkt nötig; RSS-`/admin` darf dadurch nicht ungeschützt öffentlich werden.

## 5. SSH auf der VM härten – erst nach erfolgreichem Key-Login

**VM-Konsole und die bereits funktionierende SSH-Sitzung offen lassen.** Bei Debian/OpenSSH zunächst prüfen, ob `/etc/ssh/sshd_config` die Dateien in `/etc/ssh/sshd_config.d/*.conf` einliest. OpenSSH verwendet für manche mehrfach gesetzten Optionen den **ersten** gelesenen Wert; deshalb die endgültigen wirksamen Einstellungen immer kontrollieren.

Ein Beispiel für eine **früh eingelesene** lokale Datei, erstellt direkt auf der VM als Administrator:

```bash
sudo install -d -m 0755 /etc/ssh/sshd_config.d
sudo tee /etc/ssh/sshd_config.d/00-local-hardening.conf >/dev/null <<'EOF'
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
X11Forwarding no
EOF
sudo /usr/sbin/sshd -t
sudo /usr/sbin/sshd -T | grep -E '^(permitrootlogin|pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication|permitemptypasswords|x11forwarding) '
```

**Nur fortfahren**, wenn `sshd -t` fehlerfrei ist **und** die wirksamen Werte insbesondere `permitrootlogin no`, `passwordauthentication no`, `kbdinteractiveauthentication no`, `pubkeyauthentication yes` sind. Abweichende Werte/Distributionseinstellungen **zuerst** beheben (Reihenfolge der `Include`-Direktive und anderer SSH-Konfigurationsdateien prüfen). Dann:

```bash
sudo systemctl reload ssh
```

In **einem weiteren** Windows-PowerShell-Fenster mit `ssh gh-pihub` erneut anmelden, `sudo -v` prüfen und auch `ssh -N gh-pihub-tunnel` testen. Erst danach die ursprünglichen Sitzungen schließen. Bei einem Fehler über die noch offene VM-Konsole korrigieren; nicht ungetestet den letzten Admin-Zugang kappen.

Weitere Mindestmaßnahmen: Security-Updates aktivieren (z. B. `unattended-upgrades`), Host-Firewall/Management-VLAN so beschränken, dass SSH nur von Admin-PC/VPN erreichbar ist; **8765/8085 und Pi-Management-APIs nicht breit freigeben**. Host-Logs, Backups, VM-Konsole und Wiederherstellung regelmäßig prüfen. Für echte Marketing-Arbeitsplätze statt vieler SSH-Tunnel einen **internen HTTPS-Reverse-Proxy/VPN-Zugang** mit sicheren Cookies konfigurieren.

## Bestehende Root-Test-VM: kein blindes Umschalten!

Der aktuelle Wegwerf-Host kann `/root/apps/anthias-hub` und `/root/apps/rss2slideshow` verwenden. Ein normaler `hubadmin`-Benutzer kann diese Verzeichnisse unter `/root` in der Regel **nicht** betreten; Repository-, Laufzeitdatei- und Docker-Rechte sind ebenfalls nicht automatisch migriert. Deshalb **nicht allein** `PermitRootLogin no` setzen und dann die alten `root`-Betriebsbefehle übernehmen.

**Empfehlung:** Die spätere VM frisch mit `hubadmin` und `~/apps/` installieren. Soll die alte VM doch umgestellt werden: zuvor Daten/Secrets sichern, eine bewusste Migration der Checkouts und persistenter Volumes samt Besitz-/Container-UIDs planen, Docker-Zugriff testen, Key-only-Login als Normalbenutzer und `sudo` bestätigen **und erst anschließend** Root-SSH deaktivieren. Der bestehende RSS-**GitHub**-Deploy-Key muss beim Besitzerwechsel ebenfalls sicher behandelt werden; niemals einfach mit dem Windows-Zugriffsschlüssel verwechseln.

Siehe ergänzend: [Test-VM mit beiden Anwendungen](gh-pihub-test-vm.md), [Produktiv-VM](reproducible-production.md), [Docker-Pilot](deploy-docker-host.md) und [IT-Guide](IT_ADMIN_GUIDE.md).
