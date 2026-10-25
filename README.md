# Pulse Monitor

一个受 [Uptime Kuma](https://github.com/louislam/uptime-kuma) 启发、独立实现的轻量网站可用性监控工具。支持 HTTP/HTTPS 定时检查、状态概览、响应时间、历史记录和 Webhook 告警。

## v0.2 功能

- 编辑监控名称、地址和检查间隔；暂停或恢复自动检查。暂停后仍可手动检查。修改地址时会重置当前状态，保留历史记录。
- 连续 3 次失败后发送一次故障 Webhook；已告警的故障首次恢复时发送一次恢复 Webhook。偶发失败不会触发告警。
- 使用最多 8 个并发工作线程检查服务；同一监控项不会同时执行多个检查。每次 HTTP 检查的超时为 5 秒。
- 详情页显示近 24 小时按检查次数计算的可用率、检查次数和观察到的异常时段。异常时段的起止是检查时间，不代表精确的故障发生与恢复时间。

旧版 `pulse.db` 会在启动时自动添加所需字段，保留监控项及检查记录。

## 快速开始

需要 Python 3.10 或更新版本，无需安装第三方依赖。

```bash
python pulse.py
```

打开 <http://127.0.0.1:3001>，点击「添加监控」，输入名称和网站地址。监控结果保存在当前目录的 `pulse.db`，重启后仍会保留。

## 配置

通过环境变量配置：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | 监听地址；仅在可信网络中设为 `0.0.0.0` |
| `PORT` | `3001` | Web 端口 |
| `DATABASE_PATH` | 项目目录中的 `pulse.db` | SQLite 数据库位置 |
| `WEBHOOK_URL` | 空 | 连续 3 次失败后，以及已告警故障恢复时发送 JSON POST |

Webhook 请求体包括 `monitor`、`url`、`up`、`status_code`、`response_ms`、`error` 和 `checked_at`。

本项目默认只允许本机访问。若开放到网络，应在反向代理前添加身份验证与 HTTPS。它实现的是 Uptime Kuma 的核心场景，不包含其完整功能，也没有复制其源码或品牌素材。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试会在本机启动临时 HTTP 服务，并在 `tests/` 下创建临时 SQLite 数据库。

## 许可证

MIT。见 [LICENSE](LICENSE)。
