"""Run a bounded pytest scope and retain execution provenance and JUnit counts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def git_state():
    prefix = ['git', '-c', f'safe.directory={ROOT.as_posix()}']
    def read(*args):
        return subprocess.check_output(prefix + list(args), cwd=ROOT,
                                       encoding='utf-8').rstrip('\r\n')
    status = read('status', '--porcelain=v1', '--untracked-files=all')
    return {'head': read('rev-parse', 'HEAD'),
            'branch': read('branch', '--show-current'),
            'dirty': bool(status), 'status_porcelain': status.splitlines()}


def source_manifest():
    paths = [p for folder in ('src/kiomet_ai/v2', 'tests', 'tools')
             for p in (ROOT / folder).rglob('*.py')
             if not any(part in ('__pycache__', '.venv') for part in p.parts)]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('pytest_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    scope = args.pytest_args
    if scope and scope[0] == '--':
        scope = scope[1:]
    if not scope:
        parser.error('explicit pytest scope required after --')
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    junit = output.with_suffix('.junit.xml')
    log = output.with_suffix('.log')
    if junit.exists():
        junit.unlink()
    before = git_state()
    manifest = source_manifest()
    command = [sys.executable, '-B', '-m', 'pytest', *scope, f'--junitxml={junit}']
    started = time.time()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    # Collect deselection through pytest's hook, rather than parsing human output.
    plugin = ROOT / 'runtime/research/v2/regression_receipt_plugin.py'
    plugin.parent.mkdir(parents=True, exist_ok=True)
    count_path = output.with_suffix('.selection.json')
    if count_path.exists():
        count_path.unlink()
    plugin.write_text(
        'import json, os\n'
        'deselected = 0\n'
        'def pytest_deselected(items):\n'
        '    global deselected\n'
        '    deselected += len(items)\n'
        'def pytest_sessionfinish(session, exitstatus):\n'
        '    with open(os.environ["V2_RECEIPT_SELECTION"], "w", encoding="utf8") as f:\n'
        '        json.dump({"deselected": deselected}, f)\n', encoding='utf-8')
    env['V2_RECEIPT_SELECTION'] = str(count_path)
    env['PYTHONPATH'] = os.pathsep.join([str(plugin.parent), str(ROOT / 'src'),
                                       env.get('PYTHONPATH', '')])
    command.extend(['-p', 'regression_receipt_plugin'])
    with log.open('w', encoding='utf-8') as stream:
        run = subprocess.run(command, cwd=ROOT, env=env, stdout=stream,
                             stderr=subprocess.STDOUT, check=False)
    counts = {'pass': None, 'fail': None, 'skip': None, 'errors': None,
              'deselected': None}
    if junit.exists():
        tree = ET.parse(junit)
        cases = tree.findall('.//testcase')
        counts['fail'] = sum(c.find('failure') is not None for c in cases)
        counts['errors'] = sum(c.find('error') is not None for c in cases)
        counts['skip'] = sum(c.find('skipped') is not None for c in cases)
        counts['pass'] = sum(all(c.find(tag) is None for tag in
                                 ('failure', 'error', 'skipped')) for c in cases)
    if count_path.exists():
        counts['deselected'] = json.loads(count_path.read_text(encoding='utf-8'))['deselected']
    after = git_state()
    after_manifest = source_manifest()
    changed = sorted(k for k in manifest.keys() | after_manifest.keys()
                     if manifest.get(k) != after_manifest.get(k))
    receipt = {'execution_head': before['head'], 'git_before': before,
               'git_after': after, 'test_scope': scope, 'command': command,
               'started_unix_seconds': started, 'duration_seconds': time.time()-started,
               'exit_code': run.returncode, 'counts': counts,
               'source_manifest_before': manifest, 'source_manifest_after': after_manifest,
               'source_files_changed_during_run': changed,
               'head_changed_during_run': before['head'] != after['head'],
               'log_path': str(log), 'junit_path': str(junit),
               'valid_stable_run': not changed and before['head'] == after['head']}
    output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: receipt[k] for k in ('execution_head', 'exit_code',
                                            'counts', 'valid_stable_run')}), flush=True)
    return run.returncode


if __name__ == '__main__':
    raise SystemExit(main())
