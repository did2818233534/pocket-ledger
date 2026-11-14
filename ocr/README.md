# 截图识别服务

手机截图后由这个服务识别文字并提取一笔账单（金额、日期、商户、商品说明、付款方式、收入/支出/理财转账），手机把结果作为“待确认”展示，用户核对后保存才进入账本。服务不保存图片和结果。

- 识别：[RapidOCR](https://github.com/RapidAI/RapidOCR)（PP-OCRv6 small，ONNX Runtime，CPU；可选 NVIDIA 显卡）
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
| `OCR_DEVICE` | `cpu`（默认）或 `cuda`，见“用 NVIDIA 显卡” |
| `OCR_DET_SIDE` | 文字检测输入的长边上限，默认 `736` |
| `OCR_REC_BATCH` | 每次送去识别的文字行数，默认沿用 RapidOCR 的 6 |

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
| `GET /health` | 健康检查；显卡实例另返回 `"device": "cuda"` |

设置了 `OCR_TOKEN` 时，POST 需带同值的 `X-Token` 请求头。服务没有其他鉴权，也不加密：局域网或私有网络（Tailscale、节点小宝等）内可直接用；要从公网访问时，让容器只监听本机（`OCR_BIND=127.0.0.1:18090`），放在 Caddy 等 HTTPS 反向代理后面，并务必设置口令。

## 用 NVIDIA 显卡（可选）

用 `onnxruntime-gpu` 构建，CUDA 和 cuDNN 以 pip 包装进镜像（镜像约 3 GB），宿主机只需要 NVIDIA 驱动（这个版本的 CUDA 13 需要较新的驱动，实测 595.84）：

```bash
docker build -t pocket-ledger-ocr:gpu --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple   --build-arg ORT="onnxruntime-gpu[cuda,cudnn]" .
```

装了 NVIDIA Container Toolkit 时，运行加 `--gpus all -e OCR_DEVICE=cuda` 即可。没装时可以把设备节点和驱动库直接挂进容器（库路径以 Ubuntu 为例）：

```bash
LIB=/usr/lib/x86_64-linux-gnu
docker run -d --name pocket-ledger-ocr-gpu --restart unless-stopped -p 127.0.0.1:18091:18086 --env-file .env   -e OCR_DEVICE=cuda -e LD_LIBRARY_PATH=/usr/local/nvidia/lib   --device /dev/nvidia0 --device /dev/nvidiactl --device /dev/nvidia-uvm --device /dev/nvidia-uvm-tools   -v $LIB/libcuda.so.1:/usr/local/nvidia/lib/libcuda.so.1:ro   -v $LIB/libnvidia-ptxjitcompiler.so.1:/usr/local/nvidia/lib/libnvidia-ptxjitcompiler.so.1:ro   -v $LIB/libnvidia-nvvm.so.4:/usr/local/nvidia/lib/libnvidia-nvvm.so.4:ro   --cpu-shares 256 -m 3g pocket-ledger-ocr:gpu
```

- 启动时先识别一张内置的小图预热（约 1 s），之后第一张真实截图不再变慢。常驻显存约 0.8 GB，空闲时不增加功耗。
- 卷积算法用 cuDNN 的 `HEURISTIC`。`DEFAULT` 看似省事，实际是固定用一个通用算法，实测比 `HEURISTIC` 慢 7 倍；`EXHAUSTIVE` 会对每种新尺寸重新搜索，而截图和文字行尺寸各不相同。
- 可以同时保留 CPU 实例作备用，由 Caddy 优先转给显卡实例、它不可用时转给 CPU 实例：

```
reverse_proxy 127.0.0.1:18091 127.0.0.1:18090 {
    lb_policy first
    lb_try_duration 5s
    health_uri /health
    health_interval 10s
}
```

## 实测

服务端耗时（不含上传）：

| 截图 | 文字行数 | Intel N100（绿联 DXP2800） | i9-13900HX，`OCR_THREADS=8` | RTX 5070 Ti Laptop |
| --- | --- | --- | --- | --- |
| 微信“支付成功”页 | 9 | 约 1.5 s | 约 0.2 s | 约 0.03 s |
| 支付宝账单详情 | 16–33 | 约 3.3 s | 约 0.3 s | 约 0.04 s |
| 支付宝账单长截图（1440×23021，分 10 块） | 267 | — | 约 4.6 s | 约 0.7–0.9 s |

检测输入限制为长边 736 px、关闭方向分类后，金额、时间、商户、卡号尾号等字段与原始分辨率结果一致。

## 测试

```bash
python3 -m unittest tests.test_ocr_receipt -v
```

测试数据是按真实截图版面构造的假账单，不含真实交易信息。
