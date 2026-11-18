# OCR API

服务地址：`https://ocr.did2818233534.camdvr.org/v1`

这是专门的 OCR 接口，不是聊天模型，不兼容 `/chat/completions`。调用方使用独立 API key。图片和识别结果不落盘、不记日志；仅记录密钥摘要、启用状态和最近 31 天的调用次数。密钥只有创建时显示原文。

## 调用

```bash
export OCR_API_KEY='填写你获得的 API key'
curl --fail-with-body https://ocr.did2818233534.camdvr.org/v1/ocr \
  -H "Authorization: Bearer $OCR_API_KEY" \
  -H 'Content-Type: image/png' --data-binary @screenshot.png
```

| 接口 | 用途 |
| --- | --- |
| `POST /v1/ocr` | 返回 `lines`（文字、置信度、坐标）及 `ms` |
| `POST /v1/receipts/parse` | 同上，加 `fields`（账单字段）；列表截图可能另有 `entries`、`skipped` |
| `GET /v1/usage` | 查看当前密钥的当天用量和限额，需要 Bearer key |
| `GET /v1/health` | 网关健康检查，不代表推理服务可用 |

POST 直接发送 PNG/JPEG/WebP 原始字节（不是 multipart），最大 16 MiB。Content-Type 为 `image/png`、`image/jpeg`、`image/webp` 或 `application/octet-stream`。需要 Content-Length，不支持 chunked 上传。

账单接口可加 `X-Date: YYYY-MM-DD` 表示截图日期，用于解析“今天/昨天”；`X-Cashflow: 1` 同时提取收入。结果需要用户核对，不能直接当作可靠财务记录。

Python 示例（只有标准库）：

```python
import json, os, urllib.request
from pathlib import Path
req = urllib.request.Request(
    'https://ocr.did2818233534.camdvr.org/v1/receipts/parse',
    data=Path('screenshot.png').read_bytes(),
    headers={'Authorization': 'Bearer ' + os.environ['OCR_API_KEY'],
             'Content-Type': 'image/png', 'X-Cashflow': '1'})
with urllib.request.urlopen(req, timeout=150) as response:
    print(json.load(response))
```

错误格式为 `{"error":{"code":"...","message":"..."}}`。401：密钥错误/已撤销；413：文件过大；415：类型错误；429：分钟或每日额度已用完；503：正在处理过多请求；502：识别服务暂不可用。429 响应带 Retry-After，日额度于 UTC 00:00 重置（北京时间 08:00）。通过格式验证、准备交给 OCR 的请求即计一次，识别失败也计数；查询用量不计数。客户端应避免高频重试。

## 服务器管理

当前安装在服务器 `/opt/pocket-ledger-ocr-api`，systemd 系统服务 `pocket-ledger-ocr-api.service` 随开机启动，监听 `127.0.0.1:18092`，Caddy 只将 `/v1/*` 转给它。GPU 优先，失败改用 CPU。旧 `/parse`、`/ocr` 与更新包下载路由保留，旧接口继续使用原有口令，不使用新 API key 的额度；不要把旧口令给外部调用者。

以服务器用户 did 执行：

```bash
cd /opt/pocket-ledger-ocr-api
# 每人创建一个密钥：输出只给对应调用者，切勿公开
python3 gateway.py create-key friend-name --rpm 20 --daily 500
# 列表不显示密钥原文：依次为 ID、名称、每分钟限额、每日限额、启用状态
python3 gateway.py list-keys
# 按列表中的 ID 撤销，立即生效，无需重启
python3 gateway.py revoke-key KEY_ID
```

`data/api.sqlite3` 保存密钥摘要与用量，迁移时停服务后复制整个 `data/`。`service.env` 保存上游私密口令，权限 0600；不要上传 Git。部署文件中的 User/Group 是当前主机的 did，其他主机需相应修改。

小账内置专用密钥默认限额为 **60 次/分钟、3000 次/天**，所有安装共享此额度。APK 密钥可被提取，不能当作保密凭据或付费账户身份；它仅有 OCR 调用及自身用量查询权限，无管理权限。泄露时撤销并为新版重新签发。管理功能只通过 SSH 命令行开放。

## Android 构建

将应用专用密钥保存为 `app/src/main/assets/ocr-api.json`，内容为 `{"key":"sk-ocr-..."}`。此文件已被 Git 忽略，由构建者单独保管，打包时会包含到 APK。不能使用服务器上游口令替代它。

默认及旧官方服务地址会自动使用新版 API 与内置密钥。自定义地址以 `/v1` 结尾时发送 Bearer key，其他地址沿用 X-Token；内置 key 只发给精确匹配的官方 HTTPS 地址且不跟随重定向。保留用户的截图识别开关，不自动开启截图上传。

验证：`python3 -m unittest tests.test_ocr_api -v`。
