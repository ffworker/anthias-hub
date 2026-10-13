"""Run: python -m scripts.create_user /config/users.json marketing marketing"""
import getpass
import json
import os
import re
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash


def main():
    if len(sys.argv) != 4:
        raise SystemExit('Usage: python -m scripts.create_user PATH USERNAME ROLE(it|marketing|viewer)')
    filename, username, role = sys.argv[1:]
    if role not in ('it', 'marketing', 'viewer') or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{1,31}', username):
        raise SystemExit('Invalid username/role')
    password = getpass.getpass('New password (12+ characters): ')
    again = getpass.getpass('Repeat password: ')
    if len(password) < 12 or password != again:
        raise SystemExit('Passwords differ or are too short')
    p = Path(filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    users = json.loads(p.read_text())['users'] if p.exists() else []
    if any(u['username'] == username for u in users):
        users = [u for u in users if u['username'] != username]
    users.append({'username': username, 'role': role, 'password_hash': generate_password_hash(password, method='scrypt')})
    tmp = p.with_name('.users.tmp')
    tmp.write_text(json.dumps({'users': users}, indent=2) + '\n')
    os.chmod(tmp, 0o600)
    tmp.replace(p)
    print(f'Configured {username!r} as {role}; restart web service if needed.')

if __name__ == '__main__':
    main()
