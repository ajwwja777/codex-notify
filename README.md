# codex-notify

目标：命令行或 VS Code 插件中的 Codex 完成任务后，在手机上通知用户。

当前阶段：可行性讨论。先核实任务完成事件的识别方式，确认手机平台和通知渠道偏好，比较接入方案、限制与维护成本，与用户确认基本任务和项目框架后再实施。

笔记本对话入口：`D:\Code\jiaan_workspace\codex-notify\AGENTS.md`。框架通过笔记本统一入口读取，项目正式记录维护在本目录。

2026-09-28：按用户要求创建笔记本与 A6000 项目目录及引导文档；尚未初始化 Git、创建远端或开发通知功能。下一步由项目对话与用户讨论可行性。

## Implementation approved (2026-09-28)

The user approved pushplus App notifications for each completed turn in local Windows Codex CLI and VS Code. Android receives via domestic push; no phone VPN required.

Source, Git and records live on A6000; the lightweight sender runs on Windows. Keep existing Codex callbacks. Send only project name, completion time and a generic completion message. Use deduplication, a rate-limited queue, bounded retries and failure records.

Layout: src/ sender; scripts/ setup and verification; tests/ offline tests. Credentials and runtime state stay outside Git. Acceptance requires one CLI turn and one IDE turn reaching the locked phone with VPN disabled. Foundation only: implementation and acceptance pending.
