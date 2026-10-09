"""Read-only local build progress view. Contains no environment variables or credentials."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HTML = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>PharOS · Build progress</title><style>
*{box-sizing:border-box}body{margin:0;background:#090e10;color:#e9eeeb;font:15px system-ui,-apple-system,sans-serif}main{max-width:1120px;margin:64px auto;padding:0 28px}.brand{letter-spacing:.2em;color:#d4f88b;font-size:13px}h1{font-weight:500;font-size:52px;letter-spacing:-.05em;margin:20px 0 12px}.intro{color:#93a09b;font-size:17px;line-height:1.6;max-width:680px}.line{height:1px;background:#28342e;margin:34px 0}.grid{display:grid;grid-template-columns:1.25fr 1fr;gap:28px}.card{border:1px solid #29352f;background:#101719;border-radius:12px;padding:24px}h2{font-size:15px;font-weight:500;color:#a4b2ab;margin:0 0 20px}.row{display:flex;gap:14px;padding:15px 0;border-bottom:1px solid #26302b}.row:last-child{border:0}.dot{height:8px;width:8px;border-radius:50%;margin-top:7px;flex-shrink:0;background:#d4f88b}.busy{background:#e6bd70}.blocked{background:#b586e0}.detail{color:#8b9c92;font-size:13px;line-height:1.5;margin-top:4px}.tag{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#c5e99b;margin-left:auto;white-space:nowrap}.sha{font-family:monospace;color:#c6e48e;margin-right:10px}.commit{font-size:13px;line-height:1.6;margin-bottom:13px}a{display:inline-block;margin-top:26px;background:#d4f88b;color:#152010;padding:13px 18px;border-radius:6px;font-weight:600;text-decoration:none}.footer{margin-top:28px;color:#7f9186;font-size:12px}@media(max-width:700px){main{margin-top:28px}.grid{grid-template-columns:1fr}h1{font-size:40px}}
</style></head><body><main><div class="brand">◈ &nbsp; PHAROS / BUILD LOG</div><h1>Road intelligence, taking shape.</h1><p class="intro">A live view of the build. The console, workshop adapters, and traffic scenario engine are being developed in parallel.</p><div class="line"></div><div class="grid"><section class="card"><h2>IMPLEMENTATION</h2><div id="tasks"></div></section><section class="card"><h2>FOCUSED GIT COMMITS</h2><div id="commits"></div></section></div><a href="http://127.0.0.1:8765" id="preview" hidden>Open the PharOS console ↗</a><div class="footer" id="status">Refreshing…</div></main><script>
async function refresh(){try{let r=await fetch('/status');let s=await r.json();document.querySelector('#tasks').replaceChildren(...s.tasks.map(t=>{let e=document.createElement('div');e.className='row';let dot=document.createElement('span');dot.className='dot '+t.state;let body=document.createElement('div');let title=document.createElement('div');title.textContent=t.name;let detail=document.createElement('div');detail.className='detail';detail.textContent=t.detail;body.append(title,detail);let tag=document.createElement('span');tag.className='tag';tag.textContent=t.label;e.append(dot,body,tag);return e}));document.querySelector('#commits').replaceChildren(...s.commits.map(c=>{let e=document.createElement('div');e.className='commit';let hash=document.createElement('span');hash.className='sha';hash.textContent=c.sha;e.append(hash,document.createTextNode(c.subject));return e}));document.querySelector('#status').textContent='Local build · codex/pharos-initial-build · '+s.commits.length+' recent commits · refreshed '+new Date().toLocaleTimeString();document.querySelector('#preview').hidden=!s.preview_ready}catch(e){document.querySelector('#status').textContent='Progress server temporarily unavailable'}}refresh();setInterval(refresh,4000);
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            progress = ROOT / 'data' / 'build-progress.json'
            value = json.loads(progress.read_text()) if progress.exists() else {'tasks': []}
            output = subprocess.check_output(['git', 'log', '-20', '--format=%h%x09%s'], cwd=ROOT, text=True)
            value['commits'] = [dict(zip(('sha','subject'), line.split('\t',1))) for line in output.splitlines()]
            data = json.dumps(value).encode()
            mime = 'application/json'
        elif self.path == '/':
            data, mime = HTML.encode(), 'text/html; charset=utf-8'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1',8766),Handler).serve_forever()
