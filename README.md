# 小账 · 安卓本地记账

安卓手机离线记账，SQLite 保存手机账目；电脑通过局域网接收完整副本，使用可直接阅读和复制的 JSON 文件保存。无需云端。

## 目录

| 用途 | 本机位置 |
| --- | --- |
| Git 源码 | `/home/guga/myself/project/pocket-ledger` |
| 电脑服务程序 | `/opt/pocket-ledger/server.py` |
| 独立数据目录 | `/opt/pocket-ledger/data/` |
| 账目及同步版本 | `/opt/pocket-ledger/data/ledger.json` |
| 配对配置 | `/opt/pocket-ledger/data/config.json` |
| 一次性旧数据库备份 | `/opt/pocket-ledger/backups/ledger-before-json-*.sqlite3` |
| 手机安装包（不提交 Git） | `dist/小账-1.0.0.apk` |

电脑运行程序及数据不依赖源码目录。用户级 systemd 配置保存在 `~/.config/systemd/user/pocket-ledger.service`，启动的是 `/opt/pocket-ledger/server.py`。已为本机用户开启 linger，使服务可以开机启动而无需桌面登录。

## 使用

1. 手机安装 APK，支持 Android 8.0 及以上。本机实体手机已覆盖安装，不会卸载应用或清除账目。
2. 电脑服务依赖系统 Python 和 `python3-zeroconf`，本机已经具备。其他电脑先安装发行版的 `python3-zeroconf` 包，再运行 `bash desktop/install-service.sh`。
3. 安装脚本把程序部署到 `/opt/pocket-ledger`，保留已存在的数据及密钥，更新并启动开机服务。首次创建 `/opt` 下的目录可能需要 sudo；不把密码写入脚本或配置。
4. 运行 `python3 /opt/pocket-ledger/server.py --pair` 查看地址和配对密钥。
5. 手机与电脑连接同一局域网，在“同步”页填写 `guga.local` 或电脑局域网 IPv4 地址，以及 64 位配对密钥，点击“保存并开启后台检查”。本机手机已经配对，无需再次填写。

手机每次新增或编辑账目，**先写入本地数据库，再后台尝试同步**。电脑不在线、网络错误或同步失败不会弹窗，也不会影响保存；下次发现电脑、每分钟检查或手动同步会重试。删除同样同步到电脑。

“暂停后台检查”只暂停持续的 mDNS 发现与一分钟定时检查。只要已经配对，每次保存仍会尝试同步，也能手动点击“立即同步”。手动同步失败会在同步页显示原因，便于排查。

## 界面和统计

- **账本**：本月、本周总额，四类支出摘要，按月查看流水；点击记录修改或删除，右下角添加。
- **统计**：当月、本周、近 7 天、近 30 天；分类百分比环形图、每天支出柱状图、日均和自付金额。
- **同步**：连接状态、最近成功时间、待同步提示、手动同步、后台检查开关、配对和 JSON 导出。

支出属性为“日常生活、额外支出、报销垫付、借出赠与”。属性菜单紧贴输入框下方展开，包含图标、说明和选中标记；点击外部或返回键先收起菜单。支持方向键选择和 Escape 收起。

总支出包括全部属性，自付支出排除报销垫付。“报销垫付”和“借出赠与”是支出属性，不另外管理报销到账或借款回收状态。金额以整数分保存，避免浮点金额误差。

统计按手机本地日历日期计算，本周从周一开始，近 7 / 30 天包含今天。当月、本周统计截至今天；未来日期记录保存在对应月份流水中，未计入当前统计。日均包含范围内所有自然日，包括零支出日。

## 返回操作

- 键盘打开时先收起键盘。
- 属性菜单展开时先收起菜单。
- 编辑页面有未保存修改时，确认放弃才关闭；取消确认会保留输入。
- 统计和同步页面返回账本；未保存的连接设置也会提示确认。
- 账本首页选择“留在小账 / 返回桌面”，不会一次返回就退出。返回桌面后，已开启的同步服务继续运行。

系统栏与键盘使用原生安全区域布局，底部采用浅色手势区域，菜单不会被系统导航栏遮挡。

## mDNS 和同步机制

电脑使用 `python-zeroconf` 发布 `_pocket-ledger._tcp.local.` 服务，本机主机名为 `guga.local`，端口 TCP 47831。手机使用 Android NSD 发现服务，解析其地址，再验证 TXT 中绑定地址和端口的 HMAC 签名；匹配已保存的配对密钥后才更新电脑地址并同步。电脑 IP 变化时会重新发布，手机每分钟也重新检查。原先的自定义 UDP 47832 广播已移除。

首次配对仍需要密钥。mDNS 负责发现，不代替身份校验；密钥不会通过发现消息发送。HTTP 请求与响应也使用 HMAC-SHA256，要求两端时间差在 120 秒以内。

仅支持 RFC1918 私有 IPv4 局域网，不使用公网或 IPv6-only 网络。若有防火墙，需允许可信局域网的 TCP 47831 和 mDNS UDP 5353。访客 Wi-Fi、AP 隔离或 VPN 可能影响发现；保存的电脑地址仍可作为连接入口。`.local` 地址能否直接解析取决于手机系统，服务发现会使用解析出的局域网 IPv4 地址。

**局域网 HTTP 内容未加密**，请使用可信网络。配对配置和账本文件限制为当前用户读写。手机关闭了系统自动备份。

手机为唯一编辑端，电脑按设备 ID 保存完整镜像。每次变更递增 revision，旧版本拒绝，相同版本重复同步幂等。删除会传播，电脑不是历史版本归档。每份请求上限为 4 MiB；超过上限时手机账目仍保留，手动同步可查看失败状态。

Android 后台使用 `connectedDevice` 前台服务与常驻通知。省电、Doze、厂商限制或强行停止会影响定时精度。手机重启后需要打开应用恢复检查；电脑通过 systemd 独立开机运行。

参考：[Android NSD](https://developer.android.com/develop/connectivity/wifi/use-nsd)、[python-zeroconf](https://python-zeroconf.readthedocs.io/en/latest/api.html)。

## 复制和迁移电脑数据

日常数据目录只有两个文件：`ledger.json` 与 `config.json`。`ledger.json` 为 UTF-8、缩进排版的 JSON，包含格式版本、设备同步版本和账目；金额单位为分，账目时间沿用手机本地时间。`config.json` 保存配对密钥，应一起迁移。

1. 在旧电脑执行 `systemctl --user stop pocket-ledger`。
2. 复制整个 `/opt/pocket-ledger/data/` 到新电脑的同名目录；目标服务应处于停止状态，先备份目标已有数据，避免误覆盖。
3. 确认目标服务用户拥有目录读写权限，再启动服务。
4. 保留原 `config.json` 后，手机无需重新配对；mDNS 会发现新电脑地址。旧电脑应停用服务，避免两台电脑同时使用同一份配对身份。

也可以用 `python3 /opt/pocket-ledger/server.py --data /其他目录` 指定数据目录。手动查看 JSON 没有限制；迁移或修改文件时先停止服务。

JSON 保存采用同目录临时文件、fsync 和原子替换，并串行处理并发请求。写入失败不会覆盖上一份完整账本。旧版 SQLite 会在首次启动时转换为 JSON，核对后将旧数据库归档到 `/opt/pocket-ledger/backups/`；本机转换已完成，账目、版本和配对配置均核对一致。

这只是电脑副本的可迁移存储。手机可导出 JSON，但当前没有手机 JSON 导入/恢复界面；卸载手机应用前请先导出。

## 运维和更新

```bash
systemctl --user status pocket-ledger
journalctl --user -u pocket-ledger
python3 /opt/pocket-ledger/server.py --pair
python3 /opt/pocket-ledger/server.py --export /绝对路径/账本备份.json

# 更新部署，不覆盖 data 目录
bash desktop/install-service.sh

# 停止 / 恢复服务
systemctl --user stop pocket-ledger
systemctl --user start pocket-ledger
```

调试时保留手机 USB / ADB 连接以及两端正式服务，只清理临时测试进程和测试记录；不在电脑桌面弹出调试窗口。

## 开发和验证

仓库：`git@github.com:did2818233534/pocket-ledger.git`，分支 `main`。`.gitignore` 排除构建缓存、APK、截图、数据库、配对配置、签名文件和本地工具路径。

```bash
# 使用本机已有 SDK 直接构建，无需下载 Gradle 依赖
bash build-apk.sh

# 标准 Gradle 构建
GRADLE_USER_HOME=/opt/gradle-cache JAVA_HOME=/opt/android-studio/jbr \
  /opt/gradle/bin/gradle assembleDebug lintDebug --no-daemon

python3 -m unittest discover -s tests -v
node --test tests/model.test.js
```

工具默认位于 `/opt/android-sdk`、`/opt/gradle`、`/opt/gradle-cache`。其他机器需配置相应路径和签名密钥。APK 当前为调试签名侧载版；正式发行应保管独立发行签名。

已通过 APK 构建与签名验证、Android 15 真机记账/编辑/删除/返回/属性菜单/统计测试、mDNS 替换失效 IP、保存时静默同步、离线保存及恢复后自动重试。服务端测试覆盖版本幂等、错误签名、旧版本拒绝、新属性、mDNS 签名绑定、JSON 写入失败保护、目录复制和旧数据库迁移。测试记录按独立 ID 删除，不修改已有账目。

`tests/device_mdns_sync.py` 需要已配对且解锁的手机、WebView CDP 端口 9228 和本机安装的正式服务，测试会短暂停止/恢复该服务并清理自己的记录。`tests/device_category_picker.py` 和 `tests/device_back_navigation.py` 使用 `ANDROID_SERIAL` 指定手机。

Android Lint 因缺少 `intellij-core-31.9.2.jar` 和 `kotlin-compiler-31.9.2.jar` 未完成，未宣称静态检查全部通过。长期休眠、不同手机厂商和路由器策略仍需实机观察。

布局参考 [Money Lover](https://moneylover.me/) 的流水和分类报告结构，中文界面、图标及配色为本项目实现。
