"""Install a runtime copy, preserve existing notify and all other Codex settings."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

try:
    import tomllib
except ImportError:
    from pip._vendor import tomli as tomllib


def replace_notify(text, command):
    before = tomllib.loads(text)
    lines = text.splitlines(keepends=True)
    positions = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith('['):
            break
        if re.match(r'^\s*notify\s*=', line):
            positions.append(i)
    value = 'notify = ' + json.dumps(command, ensure_ascii=False) + '\n'
    if before.get('notify') is not None:
        if len(positions) != 1:
            raise RuntimeError('Cannot safely locate existing top-level notify')
        i = positions[0]
        # Fail closed on multiline arrays; this installation has a single-line value.
        if tomllib.loads(lines[i]).get('notify') != before['notify']:
            raise RuntimeError('Multiline notify requires manual merge')
        lines[i] = value
        result = ''.join(lines)
    else:
        result = value + text
    after = tomllib.loads(result)
    expected = dict(before); expected['notify'] = command
    if after != expected:
        raise RuntimeError('Unrelated settings changed')
    return result


def install(source, target):
    if os.name != 'nt':
        raise RuntimeError('Windows only')
    codex = Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex')))/'config.toml'
    original = codex.read_bytes()
    text = original.decode('utf-8-sig')
    parsed = tomllib.loads(text)
    app = target/'app'; data = target/'data'
    sender = app/'notify.py'
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    if not pythonw.is_file():
        raise RuntimeError('pythonw.exe missing')
    command = [str(pythonw), str(sender)]
    replacement = replace_notify(text, command)
    previous = parsed.get('notify', [])
    cfg = {'enabled': True, 'previous_notify': previous}
    if (data/'config.json').exists():
        cfg = json.loads((data/'config.json').read_text(encoding='utf-8'))
        if previous != command:
            cfg['previous_notify'] = previous
    elif previous == command:
        raise RuntimeError('Missing previous callback metadata; refusing recursive installation')
    app.mkdir(parents=True, exist_ok=True); data.mkdir(exist_ok=True)
    identity = subprocess.check_output(['whoami', '/user', '/fo', 'csv']).decode('ascii', errors='ignore')
    sid = re.search(r'S-1-5-21-(?:\d+-){3}\d+', identity)
    if not sid:
        raise RuntimeError('Cannot determine Windows user SID')
    subprocess.run(['icacls', str(data), '/inheritance:r', '/grant:r', '*'+sid.group(0)+':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], check=True, capture_output=True)
    shutil.copy2(source, sender)
    (data/'config.json').write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    backup = data/('codex-config-before-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.toml')
    backup.write_bytes(original)
    # Detect another application changing config during install.
    if codex.read_bytes() != original:
        raise RuntimeError('Codex config changed concurrently; rerun installation')
    temp = codex.with_name('config.codex-notify.tmp')
    temp.write_bytes(replacement.encode('utf-8'))
    temp.replace(codex)
    (target/'Status.cmd').write_text('@echo off\r\n"'+sys.executable+'" "'+str(sender)+'" --status\r\npause\r\n', encoding='ascii')
    print(json.dumps({'installed': str(target), 'previous_callback_preserved': bool(cfg['previous_notify']), 'config_backup': str(backup)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', type=Path, default=Path('D:/Downloads/CodexNotify'))
    args = parser.parse_args()
    install(args.source.resolve(), args.target.resolve())
