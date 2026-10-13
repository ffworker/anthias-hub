"""Small persistent allowlist of Anthias devices, editable by IT only."""
import ipaddress
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit

_lock = threading.Lock()
ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$')


def validate_device(name, slug, address, location=''):
    name, slug, address, location = (str(x).strip() for x in (name, slug, address, location))
    if not (1 <= len(name) <= 80 and ID.fullmatch(slug) and len(location) <= 80):
        raise ValueError('Ungültiger Name, Geräte-ID oder Standort')
    p = urlsplit(address)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/'):
        raise ValueError('Geräteadresse muss http(s)://IP[:port] sein')
    try:
        ip = ipaddress.ip_address(p.hostname)
    except ValueError:
        raise ValueError('Bitte zunächst eine feste IP-Adresse statt DNS-Namen verwenden') from None
    if not ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved or ip.is_loopback:
        raise ValueError('Nur private, erreichbare Geräte-IP-Adressen erlaubt')
    networks = [ipaddress.ip_network(x.strip()) for x in os.environ.get('ANTHIAS_ALLOWED_CIDRS', '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16').split(',') if x.strip()]
    if not any(ip in network for network in networks):
        raise ValueError('IP ist außerhalb der zugelassenen Verwaltungsnetze')
    if p.port and not 1 <= p.port <= 65535:
        raise ValueError('Ungültiger Port')
    return {'id': slug, 'name': name, 'url': address.rstrip('/'), 'location': location}


def load(path):
    p = Path(path)
    if not p.exists():
        return []
    with p.open(encoding='utf-8') as f:
        data = json.load(f)
    return data['devices']


def save(path, items):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        tmp = p.with_name('.devices.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump({'devices': items}, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)


def get(path, ident):
    return next((d for d in load(path) if d['id'] == ident), None)
