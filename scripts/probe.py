import json
import pathlib
import queue
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent
if len(sys.argv) > 1 and sys.argv[1] == 'callback':
    event = json.loads(sys.argv[-1])
    # Never persist prompt or reply text.
    with (ROOT / 'probe-events.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps({k: event.get(k) for k in ['type', 'thread-id', 'turn-id', 'cwd']})+'\n')
    sys.exit(0)

exe, mode = sys.argv[1:3]
override = 'notify=' + json.dumps([sys.executable, str(ROOT/'probe.py'), 'callback'])
cwd = ROOT/'empty'
cwd.mkdir(exist_ok=True)
if mode == 'cli':
    r = subprocess.run([exe, 'exec', '--skip-git-repo-check', '--ephemeral', '-C', str(cwd), '-s', 'read-only', '-c', override,
                        'Do not use any tools. Reply with only OK.'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=150)
    print(json.dumps({'mode': mode, 'returncode': r.returncode, 'stdout': r.stdout[-500:], 'stderr_tail': r.stderr[-1000:]}, ensure_ascii=True))
else:
    p = subprocess.Popen([exe, 'app-server', '-c', override], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, encoding='utf-8', errors='replace', cwd=str(cwd))
    q = queue.Queue()
    def reader():
        for line in p.stdout:
            try: q.put(json.loads(line))
            except ValueError: pass
    threading.Thread(target=reader, daemon=True).start()
    def send(method, params, ident=None):
        data = {'method': method, 'params': params}
        if ident is not None: data['id'] = ident
        p.stdin.write(json.dumps(data)+'\n'); p.stdin.flush()
    try:
        send('initialize', {'clientInfo': {'name': 'codex_notify_probe', 'version': '0.1.0'}}, 0)
        deadline = time.monotonic()+150
        while time.monotonic() < deadline:
            m = q.get(timeout=max(1, deadline-time.monotonic()))
            if 'error' in m:
                print(json.dumps(m)); break
            if m.get('id') == 0:
                send('initialized', {})
                send('thread/start', {'cwd': str(cwd), 'approvalPolicy': 'never', 'sandbox': 'read-only', 'ephemeral': True}, 1)
            elif m.get('id') == 1:
                tid = m['result']['thread']['id']
                send('turn/start', {'threadId': tid, 'input': [{'type': 'text', 'text': 'Do not use any tools. Reply with only OK.'}]}, 2)
            elif m.get('method') == 'turn/completed':
                print(json.dumps({'mode': mode, 'turn': m['params']['turn']})); time.sleep(2); break
    finally:
        p.terminate(); p.wait(timeout=10)
if (ROOT/'probe-events.jsonl').exists():
    print((ROOT/'probe-events.jsonl').read_text())
