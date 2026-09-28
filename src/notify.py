"""Codex notify bridge. Python 3.8+, standard library only."""
import contextlib
import ctypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(os.environ.get('CODEX_NOTIFY_HOME', str(Path(__file__).resolve().parent.parent / 'data')))
ENDPOINT = 'https://www.pushplus.plus/send'
INTERVAL = 13  # Below five requests per rolling minute; retries also count.
DAILY_LIMIT = 190  # Leave some room for manual account tests (provider limit: 200).
TTL = 3600
MAX_ATTEMPTS = 3


def config():
    try:
        return json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def database():
    ROOT.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(ROOT / 'queue.sqlite3'), timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE IF NOT EXISTS events (
          id TEXT PRIMARY KEY, project TEXT NOT NULL, created REAL NOT NULL,
          state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          next_try REAL NOT NULL DEFAULT 0, result TEXT);
        CREATE TABLE IF NOT EXISTS requests (at REAL NOT NULL, day TEXT NOT NULL);
    ''')
    return db


def audit(kind):
    # Log only controlled messages: never raw exception text, payloads or credentials.
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        path = ROOT / 'sender.log'
        if path.exists() and path.stat().st_size > 512000:
            path.replace(ROOT / 'sender.previous.log')
        with path.open('a', encoding='utf-8') as f:
            f.write(dt.datetime.now().isoformat(timespec='seconds') + ' ' + kind + '\n')
    except OSError:
        pass


def protect(data, decrypt=False):
    """Windows DPAPI, bound to the signed-in Windows account."""
    if os.name != 'nt':
        raise RuntimeError('DPAPI requires Windows')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.windll.crypt32
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


def save_token(token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', token):
        raise ValueError('Expected a pushplus token, not a URL.')
    ROOT.mkdir(parents=True, exist_ok=True)
    target = ROOT / 'token.dpapi'
    temporary = ROOT / ('token-' + uuid.uuid4().hex + '.tmp')
    temporary.write_bytes(protect(token.encode('utf-8')))
    temporary.replace(target)


def load_token():
    return protect((ROOT / 'token.dpapi').read_bytes(), decrypt=True).decode('utf-8')


def spawn(args):
    kwargs = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL,
              'stderr': subprocess.DEVNULL, 'close_fds': True}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs['start_new_session'] = True
    return subprocess.Popen(args, **kwargs)


def start_worker():
    spawn([sys.executable, str(Path(__file__).resolve()), '--worker'])


def previous_callback(raw, cfg):
    previous = cfg.get('previous_notify', [])
    if previous:
        try:
            spawn(previous + [raw])
        except (OSError, ValueError):
            audit('previous_callback_launch_failed')


def project_name(cwd):
    name = str(cwd or '').replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]
    return ''.join(c for c in name if c.isprintable())[:60] or 'Codex'


def enqueue(event, db, now=None):
    if event.get('type') != 'agent-turn-complete':
        return False
    thread, turn = event.get('thread-id'), event.get('turn-id')
    if not isinstance(thread, str) or not isinstance(turn, str) or not thread or not turn:
        audit('ignored_event_without_identity')
        return False
    ident = hashlib.sha256(json.dumps([thread, turn]).encode()).hexdigest()
    with db:
        cur = db.execute('INSERT OR IGNORE INTO events(id,project,created) VALUES (?,?,?)',
                         (ident, project_name(event.get('cwd')), time.time() if now is None else now))
    return cur.rowcount == 1


def bridge(raw):
    cfg = config()
    previous_callback(raw, cfg)
    try:
        event = json.loads(raw)
        if not isinstance(event, dict):
            return
        if not cfg.get('enabled', True) or not (ROOT / 'token.dpapi').exists():
            audit('notification_not_configured_or_disabled')
            return
        with contextlib.closing(database()) as db:
            if enqueue(event, db):
                audit('event_queued')
        # Even duplicate events can wake a queue left behind by a stopped worker.
        start_worker()
    except Exception:
        audit('bridge_failed')


@contextlib.contextmanager
def worker_lock():
    ROOT.mkdir(parents=True, exist_ok=True)
    f = (ROOT / 'worker.lock').open('a+b')
    locked = False
    try:
        if os.name == 'nt':
            import msvcrt
            if f.tell() == 0:
                f.write(b'0'); f.flush()
            f.seek(0)
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1); locked = True
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); locked = True
            except OSError:
                pass
        yield locked
    finally:
        if locked:
            if os.name == 'nt':
                f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def china_day(now):
    return dt.datetime.fromtimestamp(now, dt.timezone(dt.timedelta(hours=8))).date().isoformat()


def payload(row, token):
    stamp = dt.datetime.fromtimestamp(row['created'], dt.timezone.utc).astimezone().isoformat(timespec='seconds')
    return {'token': token, 'channel': 'app', 'template': 'txt',
            'title': 'Codex | ' + row['project'],
            'content': '本轮回复已结束，请返回电脑查看。\n项目：' + row['project'] +
                       '\n时间：' + stamp + '\n通知编号：' + row['id'][:10]}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def deliver(body):
    # Only this service bypasses environment/system HTTP proxies. No system changes.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with opener.open(request, timeout=10) as response:
            result = json.loads(response.read(65536))
        code = result.get('code')
        if code == 200:
            return 'accepted', 'provider_accepted'  # Acceptance is not handset delivery.
        if code in (500, 503):
            return 'retry', 'provider_temporary_error'
        if code in (900, 905):
            return 'halt', 'provider_auth_or_quota_' + str(code)
        return 'failed', 'provider_code_' + str(code)[:12]
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return 'halt', 'http_rate_limited'
        return ('retry' if exc.code >= 500 else 'failed'), 'http_' + str(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        # A lost response can mean the request was accepted. Do not blindly duplicate it.
        return 'uncertain', 'network_result_unknown'
    except (ValueError, AttributeError):
        return 'uncertain', 'invalid_provider_response'


def step(db, token, now=None, send=deliver):
    now = time.time() if now is None else now
    with db:
        db.execute("UPDATE events SET state='expired', result='older_than_one_hour' WHERE state='pending' AND created<?", (now-TTL,))
    row = db.execute("SELECT * FROM events WHERE state='pending' ORDER BY created LIMIT 1").fetchone()
    if row is None:
        return None
    count = db.execute('SELECT count(*) FROM requests WHERE day=?', (china_day(now),)).fetchone()[0]
    if count >= DAILY_LIMIT:
        with db:
            db.execute("UPDATE events SET state='limited',result='local_daily_limit' WHERE state='pending'")
        audit('local_daily_limit'); return None
    last = db.execute('SELECT max(at) FROM requests').fetchone()[0]
    wait = max(row['next_try']-now, (last+INTERVAL-now) if last is not None else 0)
    if wait > 0:
        return min(wait, 30)
    # Commit before HTTP: a process crash must not cause an automatic duplicate.
    with db:
        db.execute("UPDATE events SET state='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
        db.execute('INSERT INTO requests VALUES (?,?)', (now, china_day(now)))
    state, result = send(payload(row, token))
    if state == 'retry':
        state = 'pending' if row['attempts']+1 < MAX_ATTEMPTS else 'failed'
    with db:
        db.execute('UPDATE events SET state=?,result=?,next_try=? WHERE id=?',
                   (state, result, now+max(INTERVAL, 30*(row['attempts']+1)), row['id']))
        if state == 'halt':
            db.execute("UPDATE events SET state='failed',result='provider_paused_batch' WHERE state='pending'")
    audit(result)
    return 0


def worker():
    # Brief acquisition retry closes the enqueue/worker-exit race.
    for _ in range(4):
        with worker_lock() as acquired:
            if not acquired:
                time.sleep(0.5); continue
            if not config().get('enabled', True):
                return
            try:
                token = load_token()
            except Exception:
                audit('credential_unavailable'); return
            with contextlib.closing(database()) as db:
                with db:
                    db.execute("UPDATE events SET state='uncertain',result='worker_interrupted' WHERE state='sending'")
                    db.execute('DELETE FROM requests WHERE at<?', (time.time()-86400*8,))
                    db.execute('DELETE FROM events WHERE created<?', (time.time()-86400*30,))
                while config().get('enabled', True):
                    delay = step(db, token)
                    if delay is None:
                        return
                    time.sleep(delay)
            return


def status():
    print(json.dumps(status_data(), ensure_ascii=False))


def status_data():
    with contextlib.closing(database()) as db:
        return {'configured': (ROOT/'token.dpapi').exists(),
                          'enabled': config().get('enabled', True),
                          'requests_today': db.execute('SELECT count(*) FROM requests WHERE day=?', (china_day(time.time()),)).fetchone()[0],
                          'states': {r[0]: r[1] for r in db.execute('SELECT state,count(*) FROM events GROUP BY state')},
                          'recent': [dict(r) for r in db.execute('SELECT project,state,result FROM events ORDER BY created DESC LIMIT 5')]}


def set_enabled(enabled):
    cfg = config()
    cfg['enabled'] = bool(enabled)
    ROOT.mkdir(parents=True, exist_ok=True)
    temporary = ROOT / ('config-' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    temporary.replace(ROOT / 'config.json')
    if enabled:
        start_worker()
    else:
        with contextlib.closing(database()) as db:
            with db:
                db.execute("UPDATE events SET state='cancelled', result='paused_by_user' WHERE state='pending'")
    audit('notifications_enabled' if enabled else 'notifications_paused')


def test_notification():
    if not config().get('enabled', True):
        return False
    with contextlib.closing(database()) as db:
        enqueue({'type': 'agent-turn-complete', 'thread-id': 'self-test', 'turn-id': uuid.uuid4().hex, 'cwd': 'codex-notify-test'}, db)
    start_worker()


def setup_window():
    import tray_ui
    tray_ui.run()


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else '--status'
    try:
        if mode == '--worker': worker()
        elif mode == '--status': status()
        elif mode == '--setup': setup_window()
        elif mode == '--test': test_notification()
        else: bridge(mode)
    except Exception:
        audit('command_failed')
        if mode.startswith('--'):
            sys.exit(1)
