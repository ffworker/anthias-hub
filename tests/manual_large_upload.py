"""Optional 1-GiB localhost qualification; never contacts a real Anthias player.

Run from repository root: PYTHONPATH=. python tests/manual_large_upload.py
Requires about 5 GiB of disk working space. Creates and removes its own directory.
Not part of the fast unit suite. Uses Werkzeug HTTP, not Gunicorn or a proxy.
"""
import io, json, os, re, resource, tempfile, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
from werkzeug.serving import make_server
from werkzeug.security import generate_password_hash
from app.web import create_app
from app.library import Library
from app.anthias import Anthias

GIB=1024**3
started=time.monotonic()
with tempfile.TemporaryDirectory(dir=str(Path.cwd()), prefix='large-upload-') as tmp:
    root=Path(tmp)
    os.environ['TMPDIR']=str(root)
    users=root/'users.json'
    users.write_text(json.dumps({'users':[{'username':'marketing','role':'marketing','password_hash':generate_password_hash('local-test-password')}]}))
    app=create_app({'SECRET_KEY':'t'*48,'USERS_FILE':str(users),'DEVICES_FILE':str(root/'devices.json'),'AUDIT_FILE':str(root/'audit.jsonl'),'LIBRARY_DIR':str(root/'library'),'SESSION_COOKIE_SECURE':False})
    store=Library(root/'library'); item=store.create('Local load test')
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    client=requests.Session();client.trust_env=False
    page=client.get(base+'/login').text
    csrf=re.search(r'name="csrf" value="([^"]+)"',page).group(1)
    client.post(base+'/login',data={'csrf':csrf,'username':'marketing','password':'local-test-password'}).raise_for_status()
    page=client.get(base+'/library/'+item['id']).text
    csrf=re.search(r'name="csrf" value="([^"]+)"',page).group(1)
    source=root/'source.mp4'
    with source.open('wb') as f:
        f.write(b'\x00\x00\x00\x18ftyp' + b'\x00'*8);f.truncate(GIB)
    rss_before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    with source.open('rb') as f:
        encoder=MultipartEncoder(fields={'csrf':csrf,'duration':'15','media':('test.mp4',f,'video/mp4')})
        response=client.post(base+'/library/'+item['id']+'/media',data=encoder,headers={'Content-Type':encoder.content_type,'Accept':'application/json'},timeout=120)
    assert response.status_code==200,(response.status_code,response.text[:500])
    stored=store.get(item['id']);assert len(stored['items'])==1
    path=store.verified_media_path(item['id'],stored['items'][0]);assert path.stat().st_size==GIB
    with store.export_file(item['id']) as archive:
        restored=store.import_zip(archive)
    assert store.verified_media_path(restored['id'],restored['items'][0]).stat().st_size==GIB
    class MockPi(BaseHTTPRequestHandler):
        received=0
        def do_GET(self):
            data=json.dumps({'free_space':10*GIB}).encode();self.send_response(200);self.end_headers();self.wfile.write(data)
        def do_POST(self):
            remaining=int(self.headers['Content-Length'])
            while remaining:
                chunk=self.rfile.read(min(65536,remaining));assert chunk;remaining-=len(chunk);type(self).received+=len(chunk)
            self.send_response(200);self.end_headers();self.wfile.write(b'{"uri":"/mock/test.tmp"}')
        def log_message(self,*args):pass
    pi=ThreadingHTTPServer(('127.0.0.1',0),MockPi)
    threading.Thread(target=pi.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{pi.server_port}';os.environ['ANTHIAS_VERIFIED_STORAGE_URLS']=url
    with path.open('rb') as f:
        result=Anthias({'url':url}).upload(f,'test.mp4','video/mp4')
    assert result['uri']=='/mock/test.tmp'
    assert GIB<MockPi.received<GIB+1024
    print(json.dumps({'file_bytes':GIB,'hub_http_status':response.status_code,'backup_restore_verified':True,'mock_pi_multipart_bytes':MockPi.received,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'peak_rss_before_mib':rss_before/1024,'seconds':round(time.monotonic()-started,2)},indent=2))
    server.shutdown();server.server_close();pi.shutdown();pi.server_close()
