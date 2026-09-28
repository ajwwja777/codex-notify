# codex-notify

目标：命令行或 VS Code 插件中的 Codex 完成任务后，在手机上通知用户。

当前阶段：首版部署与自动通知验收完成。用户已确认 App 测试、CLI、插件后端及 VS Code 插件界面新对话的手机实收。

笔记本对话入口：`D:\Code\jiaan_workspace\codex-notify\AGENTS.md`。框架通过笔记本统一入口读取，项目正式记录维护在本目录。

2026-09-28：按用户要求创建笔记本与 A6000 项目目录及引导文档；尚未初始化 Git、创建远端或开发通知功能。下一步由项目对话与用户讨论可行性。

## Implementation approved (2026-09-28)

The user approved pushplus App notifications for each completed turn in local Windows Codex CLI and VS Code. Android receives via domestic push; no phone VPN required.

Source, Git and records live on A6000; the lightweight sender runs on Windows. Keep existing Codex callbacks. Send only project name, completion time and a generic completion message. Use deduplication, a rate-limited queue, bounded retries and failure records.

Layout: src/ sender; scripts/ setup and verification; tests/ offline tests. Credentials and runtime state stay outside Git. Acceptance requires one CLI turn and one IDE turn reaching the locked phone with VPN disabled. This paragraph records the initial scope; deployment and acceptance results are recorded below.

## 首版实现与部署（2026-09-28）

来源：本项目对话。用户明确：荣耀 Magic8 Pro、pushplus App 1.4.7、接受实名认证、手机不开 VPN；本地 CLI 和 VS Code 插件每轮最终回复结束均通知。用户认可把笔记本发送器视为客户端 App，并指定放在 D 盘 Downloads。主代码、Git 和正式记录仍归 A6000；笔记本不建立研发仓库。

- 仓库：https://github.com/ajwwja777/codex-notify （public，main）。基础提交 bd7dc3e 已推送并核对远端。
- 主代码：本目录 src/notify.py；scripts/install_windows.py 为安装工具；scripts/probe.py 为无正文持久化的完成回调验证工具；tests/ 为离线测试。
- Windows 应用：`D:\Downloads\CodexNotify`。`app/notify.py` 是部署副本；`data/` 保存 DPAPI 加密令牌、受限 ACL 的配置备份、发送队列和日志。`CodexNotify.lnk` 打开设置/测试/状态窗口，`Status.cmd` 显示状态。没有安装 Windows 服务或开机任务。
- Python 运行依赖：`D:\Downloads\Python\pythonw.exe`（3.10.0）；后台发送器仅用标准库，托盘界面依赖固定版本 pystray/Pillow/six，部署在 app/vendor。安装工具在 Python 3.10 上使用 pip 内置的 TOML 解析器。
- Codex 的用户级 `notify` 指向应用脚本，原电脑操作工具的 `turn-ended` 回调存入本地配置并继续调用。安装前完整备份留在应用 data/；已比对除 notify 外的所有 TOML 设置完全一致。

### 行为与边界

接收官方 agent-turn-complete 事件，只为拥有 thread-id 和 turn-id 的轮次入队。按这两个 ID 去重，队列只保存哈希 ID、项目目录名、时间和发送状态；不存提示词、完整回复和完整项目路径。原回调收到原始参数。

每次回调快速启动独立隐藏发送进程；文件锁使同一时刻只有一个队列消费者。队列清空即退出。应用关闭窗口不影响通知；笔记本关机/睡眠期间无法发送，进程被终止后由下一次完成事件或应用测试按钮唤起队列。过期一小时的消息不再发送；元数据最长保留 30 天。

通过 HTTPS POST 到 pushplus 的 App 渠道，仅此 HTTP 客户端禁用系统/环境代理，不更改系统 VPN 或 Codex 网络配置。进程级代理或 VPN 的系统隧道路由仍由用户现有网络软件控制。

请求间隔至少 13 秒；本应用北京时间每天最多 190 次请求，重试计数，给服务方 200 次额度留余量。该预算不涵盖账号在其他程序中的请求。明确临时服务错误最多尝试 3 次；网络结果不确定时不自动重发，避免重复。受服务端或手机系统限制，无法保证每条通知都即时送达。

通知仅包含“本轮回复已结束”、项目名、时间和短通知编号。accepted 表示 pushplus 已接收请求，不等于手机送达；uncertain 表示结果不确定；limited、expired、failed 均可在应用状态中查看。第一版只通知轮次正常回复结束，不将中间进度、审批等待、崩溃或中断当作成功完成。

### 已完成验证与验收

- Windows 15 项测试通过，覆盖去重、敏感正文不持久化、限速、每日预算、有限重试、不确定结果不重发、超时丢弃、原回调参数保留、进程锁、DPAPI 加密和配置合并。
- A6000 的 Python 3.8：11 项通过，4 项 Windows/安装环境专用检查跳过。
- 实际 Codex CLI 0.158.0 完成一次仅回复 OK 的轮次，产生 notify 回调。
- 插件 26.917.62051 自带后端 0.155.0-alpha.16.3 通过 App Server 完成一次仅回复 OK 的轮次，产生同类 notify 回调。这是后端验证，不等同于插件界面最终验收。
- 笔记本直连 pushplus HTTPS 首页返回 200；尚不能替代推送送达测试。
- 2026-09-28 后续：用户已在本地窗口配置令牌，并明确确认手机收到 App 测试通知。安装后的 CLI 与插件 App Server 后端分别通过正式用户级 notify 完成一次 OK 轮次，对应 codex-notify-cli-check、codex-notify-ide-backend-check 两条请求均获 pushplus accepted；本次未覆写回调配置。
- 用户随后明确确认 codex-notify-cli-check 和 codex-notify-ide-backend-check 两条自动通知均已实收。
- 最终验收反馈：在要求手机关闭 VPN、锁屏并使用 VS Code 插件新对话发送“只回复 OK，不调用工具”的验收步骤后，用户明确确认该轮也能自动通知。插件界面实收已确认；首版验收闭环。手机状态以用户操作为准，未通过工具独立观测。

参考：OpenAI Notifications https://learn.chatgpt.com/docs/config-file/config-advanced#notifications ；pushplus App https://www.pushplus.plus/doc/channel/app.html ；额度 https://pushplus.plus/doc/guide/use.html 。

2026-09-28 验收结论：发送器作为 D:\Downloads\CodexNotify 客户端 App 运行，CLI 与插件每轮最终回复结束自动提醒。用户无需常驻打开设置窗口。后续按实际使用反馈维护；升级 Codex 后若通知异常，核查用户级 notify 是否仍指向发送器及原回调路径是否有效。

## 托盘开关更新（2026-09-28）

来源：用户要求应用关闭窗口后留在 Windows 右下角，右键选择开启/关闭推送。已完成并部署。

- 新界面 src/tray_ui.py：窗口关闭时收起到托盘；绿色铃铛表示开启，灰色表示暂停。右键菜单为“打开设置”“开启推送”“暂停推送”“暂停推送并退出”。单击托盘图标或重复打开应用快捷方式会显示已有设置窗口，不重复创建托盘实例。
- 开关复用本地 enabled 配置，保留原 Codex 回调和令牌。暂停后新轮次不入队、不调用推送 API；暂停时尚未发送的队列置为 cancelled，恢复后不会补发。已经开始的网络请求无法撤回。
- “暂停推送并退出”保存暂停状态并移除托盘；重新打开应用仍保留上次状态，需要时从菜单开启。普通关闭窗口仅收起，不暂停。没有添加开机启动项或 Windows 服务。
- 设置窗口显示当前状态、今日本应用请求数、令牌是否配置，提供明确的开启/暂停按钮；保存令牌与发送测试分开，避免保存时额外消耗额度。
- 应用目录仍为 D:\Downloads\CodexNotify；新文件 app/tray_ui.py、app/codex-notify.ico，GUI 依赖只在 app/vendor，未安装到全局 Python。旧发送器备份留在 data/backups/before-tray/。
- requirements-windows.txt 固定 pystray 0.19.5、Pillow 12.3.0、six 1.17.0。托盘使用标准库 Tkinter 主循环和 pystray 的 Windows 后端，跨线程菜单动作交给 GUI 队列处理。参考：https://pystray.readthedocs.io/en/latest/usage.html 。
- 验证：Windows 17 项离线测试全部通过；A6000 13 项通过、4 项平台检查跳过。scripts/smoke_tray_windows.py 在隔离状态目录中实际创建 Windows 托盘，验证关闭收起、菜单暂停/恢复、唤回窗口、单实例和退出暂停；请求计数为 0，不消耗真实推送额度。正式部署副本也通过该验证。
- 部署保留用户原有 enabled=true 状态，已启动新版窗口及托盘。Windows 可能将图标放在右下角“显示隐藏的图标”区域，可由用户拖到任务栏通知区域。
