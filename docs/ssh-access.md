# SSH-Zugang & VM-Hardening (Windows oder Linux)

**Ziel:** Ein SSH-Key für den Admin-Zugang, ein kurzer Host-Alias und **ein Tunnel für beide Anwendungen**: Anthias Hub (`127.0.0.1:8765`) und RSS2Slideshow (`127.0.0.1:8085`). Beide Dienste bleiben auf der VM an localhost gebunden.

**Wähle unten dein Client-System.** Die PowerShell- und Linux/macOS-Anleitungen sind auf GitHub aufklappbar; **VM-Einrichtung und SSH-Hardening erfolgen unabhängig davon immer auf dem Linux-Server**. Nur für frisch installierte VMs; Hinweise zur alten Root-Test-VM stehen am Ende.

> **Zwei getrennte Schlüssel:** Hier geht es um **Admin-PC → VM**, **nicht** um den RSS2Slideshow-Deploy-Key **VM → GitHub** (`~/.ssh/rss2slideshow_deploy_ed25519`). Private Schlüssel niemals hochladen oder im Git-Repository speichern.

## 1. VM vorbereiten (Linux-Server / Hypervisor-Konsole)

<details>
<summary><strong>Linux-Server: Admin-Konto und SSH vorbereiten</strong> (anzeigen)</summary>

Über die **Hypervisor-Konsole** arbeiten; `hubadmin` ist ein Beispielname:

~~~bash
sudo apt update
sudo apt install openssh-server sudo
sudo adduser hubadmin
sudo usermod -aG sudo hubadmin
~~~

Wurde die VM zunächst nur mit Root installiert, können diese Befehle an der Konsole auch als Root ohne `sudo` ausgeführt werden. `hubadmin` benötigt ein eigenes sicheres Passwort für `sudo` und für die **einmalige** Übertragung des öffentlichen SSH-Keys.

Projektverzeichnisse auf einer neuen VM später unter `/home/hubadmin/apps/` statt `/root/apps/` anlegen. Klären, unter welchem Account Git und Docker Compose laufen: `docker`-Gruppenzugehörigkeit und `sudo docker` sind praktisch **Root-Rechte** und gehören nur zu vertrauenswürdigen Administratoren.

</details>

**Vor dem allerersten SSH-Login** den echten SSH-Host-Fingerprint **an der VM-Konsole** auslesen und mit dem Fingerprint vergleichen, den dein Client bei der ersten Verbindung anzeigt:

~~~bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
~~~

Host-Fingerprint unbekannt oder nachträglich verändert? Nicht blind akzeptieren und niemals `StrictHostKeyChecking=no` setzen. Erst Host/IP und Identität verifizieren.

## 2. Client auswählen: SSH-Key erstellen, übertragen, testen

<details open>
<summary><strong>🪟 Windows – PowerShell</strong> (anklicken zum Ein-/Ausklappen)</summary>

Auf **deinem Windows-PC** in PowerShell:

~~~powershell
# Eigenen Admin-Key anlegen; eine Passphrase setzen.
New-Item -ItemType Directory -Force "$HOME\.ssh" | Out-Null
ssh-keygen -t ed25519 -a 100 -f "$HOME\.ssh\id_ed25519_gh_pihub" -C "gh-pihub-admin"

# Nur den PUBLIC Key übertragen (VM_IP ersetzen).
Get-Content "$HOME\.ssh\id_ed25519_gh_pihub.pub" |
  ssh hubadmin@VM_IP "umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"

# In einem NEUEN PowerShell-Fenster Key-only-Anmeldung prüfen.
ssh -i "$HOME\.ssh\id_ed25519_gh_pihub" -o IdentitiesOnly=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no hubadmin@VM_IP
~~~

Auf der VM **`whoami`** (muss `hubadmin` ergeben) und **`sudo -v`** prüfen; diese Sitzung geöffnet lassen.

**Die SSH-Config liegt unter:** `$HOME\.ssh\config` (ohne `.txt`).

</details>

<details>
<summary><strong>🐧 Linux / macOS – Bash oder Zsh</strong> (anklicken zum Ein-/Ausklappen)</summary>

Auf **deinem Linux-/Mac-Admin-Rechner** im Terminal:

~~~bash
# Eigenen Admin-Key anlegen; eine Passphrase setzen.
install -d -m 700 "$HOME/.ssh"
ssh-keygen -t ed25519 -a 100 -f "$HOME/.ssh/id_ed25519_gh_pihub" -C "gh-pihub-admin"

# Nur den PUBLIC Key übertragen (VM_IP ersetzen).
cat "$HOME/.ssh/id_ed25519_gh_pihub.pub" |
  ssh hubadmin@VM_IP "umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"

# In einem NEUEN Terminal Key-only-Anmeldung prüfen.
ssh -i "$HOME/.ssh/id_ed25519_gh_pihub" -o IdentitiesOnly=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no hubadmin@VM_IP
~~~

Auf der VM **`whoami`** (muss `hubadmin` ergeben) und **`sudo -v`** prüfen; diese Sitzung geöffnet lassen.

**Die SSH-Config liegt unter:** `~/.ssh/config`.

</details>

**Für beide:** `VM_IP` durch die private VM-IP ersetzen. Der private Key hat **keine** `.pub`-Endung und bleibt auf deinem Rechner; nur die `.pub`-Datei wird übertragen. Keinen vorhandenen Key überschreiben. Bei `Permission denied (publickey)` zuerst Benutzername, Rechte auf `~/.ssh/authorized_keys` und den übertragenen Key korrigieren. **Root-/Passwort-Login noch nicht abschalten.**

## 3. Gemeinsamen SSH-Alias einrichten (PowerShell und Linux identisch)

Die Datei **`~/.ssh/config` auf deinem Client** (Windows: `$HOME\.ssh\config`) anlegen oder ergänzen – andere Host-Blöcke erhalten:

~~~sshconfig
Host gh-pihub gh-pihub-tunnel
    HostName VM_IP
    User hubadmin
    IdentityFile ~/.ssh/id_ed25519_gh_pihub
    IdentitiesOnly yes
    ServerAliveInterval 30
    ExitOnForwardFailure yes

Host gh-pihub-tunnel
    LocalForward 127.0.0.1:8765 127.0.0.1:8765
    LocalForward 127.0.0.1:8085 127.0.0.1:8085
~~~

`VM_IP` ersetzen. Unter Linux/macOS `chmod 600 ~/.ssh/config` sicherstellen. Danach sind **auf beiden Client-Systemen** dieselben Befehle gültig:

~~~bash
ssh gh-pihub             # Shell: Key wird automatisch ausgewählt
ssh -N gh-pihub-tunnel   # Separates Terminal: beide Web-Tunnel öffnen
~~~

Im **eigenen Browser**: **http://127.0.0.1:8765** (Hub) und **http://127.0.0.1:8085** (RSS). Tunnel mit **Strg+C** beenden.

<details>
<summary><strong>Optional: Tunnel ohne Alias / lokale Ports bereits belegt</strong></summary>

Mit vorhandenem `gh-pihub`-Alias beide Dienste direkt weiterleiten:

~~~bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 -L 127.0.0.1:8085:127.0.0.1:8085 gh-pihub
~~~

Bei einem belegten lokalen Port **nur links** umstellen, z. B. `-L 127.0.0.1:18765:127.0.0.1:8765` und `-L 127.0.0.1:18085:127.0.0.1:8085` (Browser: `127.0.0.1:18765` / `127.0.0.1:18085`). `ExitOnForwardFailure yes` meldet fehlgeschlagene Tunnel bereits beim Verbindungsaufbau.

</details>

Der lokale Tunnel macht RSS **nicht** für Anthias-Pis erreichbar: Für RSS als TV-Webseite braucht es einen **separat eingeschränkt erreichbaren internen Endpoint**. Weder RSS-`/admin` noch die Hub-/Pi-Managementports öffentlich freigeben.

## 4. Linux-VM härten – erst nach **erfolgreichem Key-Login**

**VM-Konsole und mindestens eine funktionierende SSH-Sitzung geöffnet lassen.** Das gilt unabhängig davon, welches Client-Betriebssystem du in Schritt 2 gewählt hast.

<details>
<summary><strong>Linux-Server: SSH-Hardening-Befehle und sichere Prüfung</strong> (anzeigen)</summary>

Auf **Debian 13 / der Linux-VM** prüfen, ob `/etc/ssh/sshd_config` die Dateien aus `/etc/ssh/sshd_config.d/*.conf` einliest. Für manche OpenSSH-Einstellungen gilt der **erste gelesene Wert**: Deshalb hinterher die tatsächlich wirksame Konfiguration prüfen.

~~~bash
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
~~~

**Nicht neu laden**, solange `sshd -t` fehlschlägt oder die effektive Konfiguration nicht mindestens `permitrootlogin no`, `passwordauthentication no`, `kbdinteractiveauthentication no`, `pubkeyauthentication yes` zeigt. Bei Abweichungen `Include`, frühere `*.conf`-Dateien und ggf. `Match`-Regeln prüfen.

Erst dann:

~~~bash
sudo systemctl reload ssh
~~~

**Nochmals von einem neuen Client-Terminal testen:**

~~~bash
ssh gh-pihub
ssh -N gh-pihub-tunnel  # in einem separaten Terminal; mit Strg+C schließen
~~~

Erneut `sudo -v` und die beiden Browserseiten prüfen. Erst wenn alles funktioniert, die alten SSH-Sitzungen schließen. Bei Fehlern über die offene VM-Konsole reparieren.

</details>

Für einen echten Produktionshost zusätzlich: Sicherheitsupdates, Firewall/ACL nur für Admin-PCs oder VPN zu SSH, Backups/Restore und Host-Logs. **Ports 8765/8085 sowie Pi-Management-APIs nicht im LAN oder Internet öffnen.** Für regulären Marketing-Zugang einen internen HTTPS-Reverse-Proxy/VPN und sichere Cookies vorsehen statt individueller Admin-Tunnel.

## Alte Root-Test-VM: nicht blind auf dieses Modell umstellen!

Der Wegwerf-Host nutzt möglicherweise `/root/apps/anthias-hub` und `/root/apps/rss2slideshow`. Ein neues `hubadmin`-Konto darf standardmäßig nicht auf `/root/apps/` zugreifen; Checkouts, Docker- und Dateiberechtigungen sowie der **separate RSS-GitHub-Deploy-Key** müssen zuerst bewusst migriert werden. **Nicht** einfach `PermitRootLogin no` setzen, solange das der einzige funktionsfähige Verwaltungsweg ist. Für die spätere VM ist ein sauberer Neuaufbau mit `hubadmin` und `~/apps/` vorzuziehen.

Mehr dazu: [gemeinsame Test-VM](gh-pihub-test-vm.md) · [Produktionsinstallation](reproducible-production.md) · [Docker-Deployment](deploy-docker-host.md) · [IT-Admin-Guide](IT_ADMIN_GUIDE.md).
