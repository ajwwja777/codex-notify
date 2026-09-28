import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE = HERE/'notify.py' if (HERE/'notify.py').exists() else HERE.parent/'src/notify.py'
spec = importlib.util.spec_from_file_location('notify', SOURCE)
n = importlib.util.module_from_spec(spec); spec.loader.exec_module(n)


class SenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(n, 'ROOT', Path(self.tmp.name)); self.patch.start()
        self.db = n.database()
        self.event = {'type': 'agent-turn-complete', 'thread-id': 'thread', 'turn-id': 'turn',
                      'cwd': r'D:\private\project', 'last-assistant-message': 'SECRET REPLY', 'input-messages': ['SECRET PROMPT']}
    def tearDown(self):
        self.db.close(); self.patch.stop(); self.tmp.cleanup()
    def add(self, turn='turn', at=1000):
        return n.enqueue(dict(self.event, **{'turn-id': turn}), self.db, at)
    def rows(self):
        return self.db.execute('SELECT * FROM events ORDER BY created').fetchall()
    def test_dedup_and_privacy(self):
        self.assertTrue(self.add()); self.assertFalse(self.add())
        row = self.rows()[0]
        text = json.dumps(n.payload(row, 'token'))
        self.assertNotIn('SECRET', text); self.assertNotIn('private', text)
        self.assertEqual(row['project'], 'project')
        self.assertFalse(n.enqueue({'type': 'approval-requested'}, self.db))
    def test_missing_identity_ignored(self):
        self.assertFalse(n.enqueue({'type':'agent-turn-complete'}, self.db))
    def test_rate_limit_and_acceptance(self):
        self.add('one'); self.add('two',1001)
        sender = mock.Mock(return_value=('accepted','provider_accepted'))
        n.step(self.db,'token',1001,sender)
        self.assertEqual(n.step(self.db,'token',1002,sender),12)
        n.step(self.db,'token',1014,sender)
        self.assertEqual(sender.call_count,2)
        self.assertTrue(all(r['state']=='accepted' for r in self.rows()))
    def test_bounded_retries(self):
        self.add()
        sender=mock.Mock(return_value=('retry','temporary'))
        for at in [1000,1030,1090]: n.step(self.db,'token',at,sender)
        self.assertEqual(self.rows()[0]['state'],'failed')
        self.assertEqual(sender.call_count,3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM requests').fetchone()[0],3)
    def test_uncertain_delivery_not_retried(self):
        self.add()
        sender=mock.Mock(return_value=('uncertain','network_result_unknown'))
        n.step(self.db,'token',1000,sender); n.step(self.db,'token',1100,sender)
        self.assertEqual(sender.call_count,1)
    def test_daily_limit_includes_failures(self):
        self.add()
        with self.db:
            self.db.executemany('INSERT INTO requests VALUES (?,?)', [(900,n.china_day(1000))]*190)
        sender=mock.Mock()
        self.assertIsNone(n.step(self.db,'token',1000,sender))
        sender.assert_not_called(); self.assertEqual(self.rows()[0]['state'],'limited')
    def test_expiry(self):
        self.add(at=1000); sender=mock.Mock()
        n.step(self.db,'token',5000,sender)
        sender.assert_not_called(); self.assertEqual(self.rows()[0]['state'],'expired')
    def test_previous_callback_keeps_original_argument(self):
        raw=json.dumps(self.event)
        with mock.patch.object(n,'spawn') as spawn:
            n.previous_callback(raw,{'previous_notify':['existing.exe','turn-ended']})
            spawn.assert_called_once_with(['existing.exe','turn-ended',raw])
    def test_global_proxy_not_used(self):
        with mock.patch.dict(os.environ,{'HTTPS_PROXY':'http://invalid:1'}):
            opener=n.urllib.request.build_opener(n.urllib.request.ProxyHandler({}),n.NoRedirect())
            self.assertFalse(any(isinstance(h,n.urllib.request.ProxyHandler) and h.proxies for h in opener.handlers))
    def test_notification_does_not_wait_for_http(self):
        n.ROOT.joinpath('token.dpapi').write_bytes(b'fake')
        with mock.patch.object(n,'previous_callback'), mock.patch.object(n,'start_worker') as worker, mock.patch.object(n,'deliver') as deliver:
            n.bridge(json.dumps(self.event)); worker.assert_called_once(); deliver.assert_not_called()
    def test_worker_lock_exclusion(self):
        with n.worker_lock() as first:
            self.assertTrue(first)
            with n.worker_lock() as second: self.assertFalse(second)
    @unittest.skipUnless(os.name=='nt','Windows DPAPI')
    def test_token_encrypted_at_rest(self):
        token='example-test-token-1234567890'
        n.save_token(token)
        self.assertEqual(n.load_token(),token)
        self.assertNotIn(token.encode(),(n.ROOT/'token.dpapi').read_bytes())


if __name__=='__main__': unittest.main()
