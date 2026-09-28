"""Windows tray controller; sender remains a separate stdlib-only process."""
import ctypes
import hashlib
import os
from pathlib import Path
import queue
import sys
import tkinter as tk
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
import pystray
from PIL import Image, ImageDraw, ImageTk
import notify as service


class SingleInstance:
    def __init__(self):
        self.handle = None
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        self.kernel.CreateMutexW.restype = ctypes.c_void_p
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel.CloseHandle.restype = ctypes.c_int

    def acquire(self):
        suffix = hashlib.sha256(str(service.ROOT.resolve()).lower().encode()).hexdigest()[:24]
        self.handle = self.kernel.CreateMutexW(None, False, 'Local\\CodexNotify-' + suffix)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            self.close()
            service.ROOT.mkdir(parents=True, exist_ok=True)
            (service.ROOT / 'show.request').touch()
            return False
        return True

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def icon_image(enabled):
    image = Image.new('RGBA', (64, 64))
    draw = ImageDraw.Draw(image)
    color = '#16865b' if enabled else '#737b88'
    draw.rounded_rectangle((3, 3, 61, 61), radius=15, fill=color)
    draw.rounded_rectangle((20, 16, 44, 43), radius=12, fill='white')
    draw.rectangle((20, 30, 44, 44), fill='white')
    draw.rounded_rectangle((15, 41, 49, 47), radius=3, fill='white')
    draw.ellipse((28, 48, 36, 55), fill='white')
    if not enabled:
        draw.line((13, 13, 51, 51), fill=color, width=7)
        draw.line((13, 13, 51, 51), fill='white', width=3)
    return image


class TrayApp:
    def __init__(self):
        service.ROOT.mkdir(parents=True, exist_ok=True)
        self.actions = queue.Queue()
        self.alive = True
        self.last_enabled = None
        self.seen_request = self.request_stamp()
        self.window = tk.Tk()
        self.window.title('CodexNotify — 手机通知')
        self.window.geometry('600x415')
        self.window.minsize(550, 390)
        self.window.protocol('WM_DELETE_WINDOW', self.hide)
        frame = ttk.Frame(self.window, padding=22)
        frame.pack(fill=tk.BOTH, expand=True)
        self.state = tk.StringVar()
        ttk.Label(frame, textvariable=self.state, font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w')
        self.usage = tk.StringVar()
        ttk.Label(frame, textvariable=self.usage).pack(anchor='w', pady=(6, 16))
        controls = ttk.Frame(frame)
        controls.pack(anchor='w')
        self.enable_button = ttk.Button(controls, text='开启推送', command=lambda: self.set_enabled(True))
        self.enable_button.pack(side=tk.LEFT, padx=(0, 10))
        self.pause_button = ttk.Button(controls, text='暂停推送', command=lambda: self.set_enabled(False))
        self.pause_button.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(controls, text='查看发送状态', command=self.show_status).pack(side=tk.LEFT)
        ttk.Separator(frame).pack(fill=tk.X, pady=18)
        self.credential = tk.StringVar()
        ttk.Label(frame, textvariable=self.credential).pack(anchor='w')
        ttk.Label(frame, text='需要更换令牌时粘贴下方；令牌仅在本机加密保存。').pack(anchor='w', pady=5)
        self.entry = ttk.Entry(frame, show='*')
        self.entry.pack(fill=tk.X, pady=4)
        token_buttons = ttk.Frame(frame)
        token_buttons.pack(anchor='w', pady=8)
        ttk.Button(token_buttons, text='保存令牌', command=self.save).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(token_buttons, text='发送测试通知', command=self.test).pack(side=tk.LEFT)
        ttk.Label(frame, text='关闭窗口会收起到右下角托盘，右键图标可开启或暂停。\n绿色 = 开启；灰色 = 暂停。开关操作不消耗推送额度。').pack(anchor='w', pady=(14, 5))
        ttk.Button(frame, text='收起到托盘', command=self.hide).pack(anchor='e')
        self.images = {True: icon_image(True), False: icon_image(False)}
        self.tk_icons = {state: ImageTk.PhotoImage(image) for state, image in self.images.items()}
        item = pystray.MenuItem
        self.icon = pystray.Icon('CodexNotify', self.images[True], 'CodexNotify',
            menu=pystray.Menu(
                item('打开设置', lambda icon, menu: self.actions.put('show'), default=True),
                pystray.Menu.SEPARATOR,
                item('开启推送', lambda icon, menu: self.actions.put('enable'),
                     enabled=lambda menu: not service.config().get('enabled', True)),
                item('暂停推送', lambda icon, menu: self.actions.put('pause'),
                     enabled=lambda menu: service.config().get('enabled', True)),
                pystray.Menu.SEPARATOR,
                item('暂停推送并退出', lambda icon, menu: self.actions.put('exit'))))
        self.refresh()
        self.icon.run_detached()
        self.timer = self.window.after(150, self.pump)

    def request_stamp(self):
        try:
            return (service.ROOT / 'show.request').stat().st_mtime_ns
        except FileNotFoundError:
            return 0

    def refresh(self):
        enabled = service.config().get('enabled', True)
        self.state.set('手机推送已开启' if enabled else '手机推送已暂停')
        self.credential.set('pushplus 令牌：已配置' if (service.ROOT / 'token.dpapi').exists() else 'pushplus 令牌：未配置')
        self.enable_button.state(['disabled'] if enabled else ['!disabled'])
        self.pause_button.state(['!disabled'] if enabled else ['disabled'])
        if enabled != self.last_enabled:
            self.icon.icon = self.images[enabled]
            self.icon.title = 'CodexNotify — ' + ('推送开启' if enabled else '推送暂停')
            self.window.iconphoto(True, self.tk_icons[enabled])
            if self.icon.visible:
                self.icon.update_menu()
            self.last_enabled = enabled
        data = service.status_data()
        self.usage.set('今日本应用请求：' + str(data['requests_today']) + ' / ' + str(service.DAILY_LIMIT))

    def set_enabled(self, enabled):
        try:
            service.set_enabled(enabled)
            self.refresh()
        except Exception:
            service.audit('ui_switch_failed')
            self.show()
            messagebox.showerror('切换失败', '状态未能完整更新，请查看发送状态。', parent=self.window)

    def hide(self):
        if self.icon.visible:
            self.window.withdraw()
        else:
            messagebox.showerror('托盘尚未就绪', '请稍后再关闭窗口。', parent=self.window)

    def show(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def save(self):
        try:
            service.save_token(self.entry.get().strip())
            self.entry.delete(0, tk.END)
            self.refresh()
            messagebox.showinfo('已保存', '令牌已加密保存。', parent=self.window)
        except ValueError:
            messagebox.showerror('格式不正确', '请输入 pushplus 令牌本身，不是网页地址。', parent=self.window)
        except Exception:
            messagebox.showerror('保存失败', '本地保存失败，请查看应用日志。', parent=self.window)

    def test(self):
        if not service.config().get('enabled', True):
            messagebox.showinfo('推送已暂停', '请先开启推送，再发送测试通知。', parent=self.window)
            return
        if not (service.ROOT / 'token.dpapi').exists():
            messagebox.showinfo('尚未配置', '请先保存令牌。', parent=self.window)
            return
        service.test_notification()
        messagebox.showinfo('已排队', '测试通知已排队，将计入今日请求次数。', parent=self.window)

    def show_status(self):
        data = service.status_data()
        names = {'accepted': '服务端已接收', 'pending': '等待发送', 'cancelled': '暂停时取消',
                 'uncertain': '结果不确定', 'failed': '发送失败', 'limited': '达到额度',
                 'expired': '已过期', 'sending': '发送中', 'halt': '服务端限制'}
        text = '\n'.join(row['project'] + '：' + names.get(row['state'], row['state']) for row in data['recent']) or '暂无发送记录'
        messagebox.showinfo('最近发送状态', text + '\n\n是否送达以手机实际收到为准。', parent=self.window)

    def pump(self):
        if not self.alive:
            return
        try:
            while True:
                action = self.actions.get_nowait()
                if action == 'show': self.show()
                elif action == 'enable': self.set_enabled(True)
                elif action == 'pause': self.set_enabled(False)
                elif action == 'exit':
                    self.quit(); return
        except queue.Empty:
            pass
        stamp = self.request_stamp()
        if stamp != self.seen_request:
            self.seen_request = stamp
            self.show()
        self.refresh()
        self.timer = self.window.after(750, self.pump)

    def quit(self):
        # Sender is event driven, so an explicit exit must persist the pause.
        service.set_enabled(False)
        self.close()

    def close(self):
        self.alive = False
        if self.timer:
            self.window.after_cancel(self.timer)
            self.timer = None
        self.icon.stop()
        self.window.destroy()

    def run(self):
        try:
            self.window.mainloop()
        finally:
            self.icon.stop()


def run():
    instance = SingleInstance()
    if not instance.acquire():
        return
    try:
        TrayApp().run()
    finally:
        instance.close()


if __name__ == '__main__':
    run()
