# Pulse Monitor

一个受 [Uptime Kuma](https://github.com/louislam/uptime-kuma) 启发、独立实现的轻量网站可用性监控工具。支持 HTTP/HTTPS 定时检查、状态概览、响应时间、历史记录和状态变化 Webhook。

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
| `WEBHOOK_URL` | 空 | 状态从正常变异常或从异常恢复时发送 JSON POST |

Webhook 只在已有首次检查结果后、状态实际变化时发送。请求体包括 `monitor`、`url`、`up`、`status_code`、`response_ms`、`error` 和 `checked_at`。

本项目默认只允许本机访问。若开放到网络，应在反向代理前添加身份验证与 HTTPS。它实现的是 Uptime Kuma 的核心场景，不包含其完整功能，也没有复制其源码或品牌素材。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试会在本机启动临时 HTTP 服务，并在 `tests/` 下创建临时 SQLite 数据库。

## 许可证

MIT。见 [LICENSE](LICENSE)。
