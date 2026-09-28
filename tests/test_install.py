import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'install_windows.py' if (HERE/'install_windows.py').exists() else HERE.parent/'scripts/install_windows.py'
try:
    spec=importlib.util.spec_from_file_location('installer',SOURCE)
    installer=importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
except ImportError:
    installer=None


@unittest.skipIf(installer is None,'Installation uses Windows Python with pip or Python 3.11+')
class ConfigTests(unittest.TestCase):
    def test_preserves_all_unrelated_configuration(self):
        original='notify = ["old.exe", "turn-ended"]\nmodel = "existing-model"\n\n[features]\nother_feature = true\n'
        updated=installer.replace_notify(original,['D:/Python/pythonw.exe','D:/Downloads/CodexNotify/app/notify.py'])
        self.assertTrue(updated.endswith('model = "existing-model"\n\n[features]\nother_feature = true\n'))
    def test_new_notify_goes_before_tables(self):
        updated=installer.replace_notify('[features]\nother_feature=true\n',['app.exe'])
        self.assertEqual(installer.tomllib.loads(updated)['notify'],['app.exe'])
    def test_multiline_fails_without_modification(self):
        with self.assertRaises(Exception): installer.replace_notify('notify = [\n"old.exe"\n]\n',['new.exe'])


if __name__=='__main__': unittest.main()
