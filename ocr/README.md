# 截图识别服务

手机截图后由这个服务识别文字并提取一笔账单（金额、日期、商户、商品说明、付款方式、收入/支出/理财转账），手机把结果作为“待确认”展示，用户核对后保存才进入账本。服务不保存图片和结果。

- 识别：[RapidOCR](https://github.com/RapidAI/RapidOCR)（PP-OCRv6 small，ONNX Runtime，CPU）
- 提取：`receipt.py`，按版面规则提取，不依赖具体 App：最大号的纯金额文字是主金额；左列标签（收款方、商品说明、支付时间、账单分类…）取同一行的值；没有收款方标签时取主金额上方一行。支付宝账单页的“账单分类”决定收入/理财转账，并映射成一级备注。
- 长截图：高度超过宽度 2.4 倍时按约一屏高的块分段识别，相邻块重叠，切在边上的文字不丢不重。
- 账单列表：`parse_list()` 以每行右侧的金额为锚，向下找时间行确认是一条账单，再取同一行的标题和下方的账单分类、状态。

## 部署

```bash
cd ocr
OCR_TOKEN=可选口令 docker compose up -d --build
curl http://127.0.0.1:18086/health
```

`compose.yaml` 默认使用清华 PyPI 镜像构建，构建时下载模型，运行时无需联网。不要给容器设置 CPU 配额：配额会让 onnxruntime 线程频繁被节流，实测慢约 2.5 倍。

| 环境变量 | 说明 |
| --- | --- |
| `OCR_TOKEN` | 口令，见下文 |
| `OCR_BIND` | 宿主机监听地址，默认 `18086`；放在同机反向代理（Caddy 等）后面时用 `127.0.0.1:18090` 之类只监听本机 |
| `OCR_THREADS` | 推理线程数上限；和其他服务共用电脑时设置，默认用满物理核 |

没有 `docker compose` 插件时，等价命令：

```bash
docker build -t pocket-ledger-ocr --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple .
docker run -d --name pocket-ledger-ocr --restart unless-stopped -p 127.0.0.1:18090:18086 \
  --env-file .env --cpu-shares 256 -m 1500m pocket-ledger-ocr
```

| 接口 | 说明 |
| --- | --- |
| `POST /parse` | 请求体为 PNG/JPEG，返回 `{"fields": {...}, "lines": [...], "ms": 123}`；识别出账单列表时另有 `"entries": [...]`（每行一笔支出）和 `"skipped"`（跳过的收入、理财、关闭订单数）。可带 `X-Date: YYYY-MM-DD`（截图日期）换算“今天/昨天” |
| `POST /ocr` | 只返回文字行和坐标 |
| `GET /health` | 健康检查 |

设置了 `OCR_TOKEN` 时，POST 需带同值的 `X-Token` 请求头。服务没有其他鉴权，也不加密：局域网或私有网络（Tailscale、节点小宝等）内可直接用；要从公网访问时，让容器只监听本机（`OCR_BIND=127.0.0.1:18090`），放在 Caddy 等 HTTPS 反向代理后面，并务必设置口令。

## 实测

| 截图 | 文字行数 | Intel N100（绿联 DXP2800） | i9-13900HX，`OCR_THREADS=8` |
| --- | --- | --- | --- |
| 微信“支付成功”页 | 9 | 约 1.5 s | 约 0.2–0.3 s |
| 支付宝账单详情 | 33 | 约 3.3 s | 约 0.3 s |

检测输入限制为长边 736 px、关闭方向分类后，金额、时间、商户、卡号尾号等字段与原始分辨率结果一致。

## 测试

```bash
python3 -m unittest tests.test_ocr_receipt -v
```

测试数据是按真实截图版面构造的假账单，不含真实交易信息。
