
import os, sys, tempfile, json, time
from pathlib import Path
from unittest import mock
app_dir=Path(sys.argv[1] if len(sys.argv)>1 else 'D:/Downloads/CodexNotify/app').resolve()
sys.path.insert(0,str(app_dir/'vendor'))
sys.path.insert(0,str(app_dir))
with tempfile.TemporaryDirectory(prefix='tray-test-',dir=str(app_dir.parent/'data')) as scratch:
 os.environ['CODEX_NOTIFY_HOME']=scratch
 import notify as n
 import tray_ui as ui
 (n.ROOT/'config.json').write_text(json.dumps({'enabled':True,'previous_notify':['unchanged.exe']}))
 first=ui.SingleInstance(); assert first.acquire()
 second=ui.SingleInstance(); assert not second.acquire()
 app=None
 try:
  with mock.patch.object(n,'start_worker') as worker:
   app=ui.TrayApp()
   def spin(seconds=1):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
     app.window.update();time.sleep(.02)
   spin()
   assert app.icon.visible
   assert app.icon._menu_handle
   menu={i.text:i for i in app.icon.menu.items}
   app.hide();spin(.2);assert app.window.state()=='withdrawn'
   menu['暂停推送'](app.icon);spin()
   assert n.config()['enabled'] is False
   assert '暂停' in app.icon.title
   worker.assert_not_called()
   menu['开启推送'](app.icon);spin()
   assert n.config()['enabled'] is True
   assert '开启' in app.icon.title
   worker.assert_called_once()
   app.icon();spin();assert app.window.state()=='normal'
   app.hide();(n.ROOT/'show.request').touch();spin();assert app.window.state()=='normal'
   assert n.status_data()['requests_today']==0
   assert n.config()['previous_notify']==['unchanged.exe']
   menu['暂停推送并退出'](app.icon)
   end=time.monotonic()+2
   while app.alive and time.monotonic()<end:
    app.window.update();time.sleep(.02)
   assert not app.alive
   assert n.config()['enabled'] is False
   print('PASS: native tray, close-to-tray, pause/resume, default open, single instance, exit-pauses, zero API requests')
 finally:
  if app and app.alive:app.close()
  first.close();second.close()
