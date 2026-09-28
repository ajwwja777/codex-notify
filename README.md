# codex-notify

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Windows 上的 Codex CLI 或 VS Code Codex 插件每轮回复结束后，通过 **pushplus App** 通知手机。支持右下角托盘一键开启／暂停，适合离开电脑等待任务完成时使用。

已在荣耀 Android 手机不开 VPN 的情况下验收。电脑上的 Codex 仍使用原有网络设置；本工具不替代 Codex 自身需要的网络连接。此项目为社区工具，与 OpenAI、pushplus 无隶属关系。

## 功能

- 接收 Codex 的 `agent-turn-complete` 回调；只有一句 OK、没有调用工具的正常结束轮次也能通知。
- 关闭窗口收起到托盘；绿色表示开启，灰色表示暂停。
- 暂停不发送新消息，取消尚未发送的队列，恢复后不补发；切换开关不消耗推送额度。已开始的请求无法撤回。
- 保留并继续调用安装前的 Codex `notify` 命令，包括暂停推送时。
- 只向 pushplus 发送项目目录名、完成时间、通用提示和短通知编号，不发送提示词或回答正文。
- 令牌以 Windows DPAPI 加密保存在当前用户的电脑，发送队列持久化并去重。

## 环境要求

- Windows 本地运行的 Codex CLI 或 VS Code Codex 插件，已登录并能够正常对话，已有用户级 `config.toml`。
- 完整版 Python 3.10 或更新版本，包含 pip、Tkinter 和同目录的 `pythonw.exe`。已实测 Python 3.10.0；其他版本需自行验证依赖兼容性。
- 安装时能直连 PyPI，发送时能直连 `https://www.pushplus.plus`。
- 手机安装并登录 [pushplus App](https://www.pushplus.plus/doc/channel/app.html)，开启通知权限，按服务当前要求完成账号认证。使用自己的 pushplus 用户令牌。

当前未适配 macOS、Linux、WSL、Remote SSH 中的远端 Codex 或云端任务。不是独立 EXE，安装后不要删除或移动所用的 Python。

## 安装

下载 [最新版本](https://github.com/ajwwja777/codex-notify/releases/latest) 的 Source code ZIP 并解压，或克隆仓库：

```powershell
git clone https://github.com/ajwwja777/codex-notify.git
cd codex-notify
```

在源码根目录的 PowerShell 中执行（`py` 不可用时换成自己的 `python.exe` 完整路径）：

```powershell
py -3 scripts/install_windows.py --source src/notify.py --target D:\Downloads\CodexNotify
```

`--target` 可替换为自己有写入权限的目录，没有 D 盘也可以安装。当前安装器生成的 `Status.cmd` 使用 ASCII，请使用不含中文等非 ASCII 字符的 Python 路径和安装路径。一般不需要管理员权限。

安装器会：

1. 复制运行文件到目标目录的 `app/`，将固定版本的界面依赖安装到 `app/vendor/`，不安装到全局 Python。
2. 在 `data/` 备份现有 Codex 配置，保存原 `notify`，并替换用户级 `notify`；保持其他 TOML 设置不变。
3. 创建 `CodexNotify.lnk` 和 `Status.cmd`，将 `data/` 权限限制为当前用户和 SYSTEM。

配置路径遵循 `CODEX_HOME`，未设置时为 `%USERPROFILE%\.codex\config.toml`。安装前退出其他正在修改该配置的程序。当前安装器遇到多行 `notify` 数组会拒绝自动修改，先将该数组整理为等价的单行形式后再安装。

## 配置手机通知

1. 打开安装目录中的 **CodexNotify.lnk**。
2. 将自己的 pushplus 用户令牌粘贴到设置窗口，点击“保存令牌”。不要把令牌发到 Issues、聊天或提交进 Git。
3. 确认状态为开启，点击“发送测试通知”，检查手机是否实际收到。测试会计入请求额度，保存令牌不会。
4. **退出并重新启动安装前已打开的 Codex CLI；VS Code 插件请重启 VS Code。** 已经运行的进程可能仍使用旧的 `notify` 配置。
5. 在 CLI 和插件中分别发送“只回复 OK，不调用工具”，检查手机通知。

CLI 可以用 `codex resume <会话ID>` 恢复原会话。项目实测中，安装前启动的旧 CLI 没有通知，退出并恢复原会话后成功。

通知示例：

```text
Codex | my-project
本轮回复已结束，请返回电脑查看。
项目：my-project
时间：2026-09-28T20:00:00+08:00
通知编号：0123456789
```

## 日常开关

| 操作 | 效果 |
| --- | --- |
| 点击窗口关闭按钮 | 收起到托盘，继续按当前状态工作 |
| 托盘右键 → 暂停推送 | 暂停发送，取消待发送消息 |
| 托盘右键 → 开启推送 | 恢复后续轮次通知 |
| 托盘右键 → 打开设置 | 显示设置窗口 |
| 托盘右键 → 暂停推送并退出 | 保存暂停状态并退出界面 |

托盘图标可能位于 Windows 右下角的隐藏图标区域。重新打开快捷方式会唤回已有窗口。退出后重新打开仍保留暂停状态，需要手动开启。

不安装 Windows 服务或开机启动项。发送器由完成事件触发，队列清空后退出；托盘界面不必常驻才能发送。电脑关机或睡眠时无法发送。

## 配额、隐私和限制

- 本工具固定每次请求间隔至少 13 秒，北京时间每天最多 190 次请求，包含测试与重试；不是服务方对账号额度的承诺。账号通过其他程序发送的请求不计入本地预算。实际额度以 [pushplus 当前规则](https://www.pushplus.plus/doc/guide/use.html) 为准。
- 消息等待超过一小时会过期，队列元数据最多保留 30 天。明确的临时错误最多尝试三次；网络结果不确定时不自动重发，避免重复。
- `accepted` 仅表示 pushplus 接收了请求，不表示手机已经送达。手机系统权限、网络和服务方限流可能影响送达。
- 仅通知正常完成的轮次，不通知中间进度、等待审批、崩溃或中断，也不判断任务结果是否正确。
- 本工具不持久化提示词和回答正文。原有回调仍接收 Codex 原始参数，其数据处理由原回调负责。
- 项目目录名会发送给 pushplus；它也可能含有敏感信息，请根据自己的项目命名判断是否适用。
- `data/` 含加密令牌、配置备份、队列和日志，不要公开。配置备份可能含其他应用原本写入的秘密；DPAPI 也不防御已控制当前 Windows 账户的程序。
- 只有 pushplus HTTP 客户端绕过系统／环境 HTTP 代理，不改变系统 VPN 设置，不能绕过 VPN 的系统路由。

## 排查与维护

**测试通知能收到，某个旧会话收不到：** 先退出该 CLI，再用 `codex resume` 恢复。插件重启 VS Code。若仍失败，检查该会话是否使用另一份 `CODEX_HOME`、命令行覆盖或不同机器上的后端。

**所有通知都收不到：** 确认托盘开启、令牌已配置，使用“查看发送状态”或 `Status.cmd` 查看状态。检查手机登录账户和通知权限。`limited` 表示本地额度用尽，`expired` 表示过期，`uncertain` 表示网络结果不确定；不要仅凭 `accepted` 判定送达。

**安装失败：** 先确认 Codex 用户配置存在，Python 能运行 `-m pip --version` 和 `-m tkinter`，并能直连 PyPI。安装器不会下载 Python。安装中断后检查终端错误，修复原因再重跑；如已替换回调，配置备份在 `data/codex-config-before-*.toml`。

**更新：** 先从托盘选择“暂停推送并退出”，取得新版源码，使用相同 Python 和相同目标目录重跑安装命令。保留原有令牌及开关状态；重新打开后按需开启。不要直接搬动已安装目录，否则 Codex 中的绝对路径会失效。

**卸载：** 先暂停并退出，将 Codex 用户配置中的顶层 `notify` 恢复为 `data/config.json` 里的 `previous_notify`；原来没有回调时删除该项。重启 Codex／VS Code 后再删除安装目录。不要直接用旧的整份配置覆盖当前配置，以免丢失安装后修改的其他设置。

提交 [Issue](https://github.com/ajwwja777/codex-notify/issues) 时提供 Windows、Python、Codex／插件版本、复现步骤和去除敏感信息的状态结果，不要上传令牌、完整配置备份或对话正文。

## 源码和验证

```text
src/notify.py                 完成回调、队列和发送器
src/tray_ui.py                Windows 托盘与设置窗口
scripts/install_windows.py   安装工具
scripts/probe.py             回调验证工具
scripts/smoke_tray_windows.py 隔离的 Windows 托盘验证
tests/                       离线测试
requirements-windows.txt     固定版本的界面依赖
```

源码目录运行离线测试，不发送真实推送：

```powershell
py -3 -m unittest discover -s tests -v
```

2026-09-28 验证记录：Windows Python 3.10.0 的 17 项测试通过，隔离托盘交互验证通过；A6000 Python 3.8 的 13 项通过、4 项平台／依赖相关检查跳过。Codex CLI 0.158.0、VS Code 扩展 26.917.62051（后端 0.155.0-alpha.16.3）、pushplus App 1.4.7 与荣耀 Magic8 Pro 完成实收验收。用户随后确认旧 CLI 重启并恢复后也收到通知。其他版本和机型尚未逐一验证。

2026-09-28：按用户要求整理公开使用文档、采用 MIT 许可证，v0.1.0 提供源码、安装脚本和固定依赖清单。本次不改变已部署发送器。Codex 升级后若出现异常，应重新验证完成回调与原回调路径。

## 许可证

[MIT](LICENSE)，Copyright (c) 2026 ajwwja777。第三方依赖适用各自的许可证。
