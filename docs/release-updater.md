# Android Release Updater

可复用的 Android 更新库，从 GitHub Release 的 `latest.json` 检查并下载 APK，使用 Android PackageInstaller 安装。独立于 DSH、DeepSeek、Node.js 和聊天界面；Android 9（API 28）及以上可用。

## 接入另一个应用

将 `release-updater` 目录复制到目标工程，根工程提供 `com.android.library` 插件，然后添加：

```groovy
// settings.gradle
include ':release-updater'

// app/build.gradle
dependencies { implementation project(':release-updater') }
```

在宿主 `AndroidManifest.xml` 的 `<application>` 中配置自己的仓库：

```xml
<meta-data android:name="dev.guga.updates.REPOSITORY"
    android:value="https://github.com/OWNER/REPOSITORY" />
<meta-data android:name="dev.guga.updates.NOTIFICATION_ICON"
    android:resource="@drawable/ic_notification" />
```

默认清单地址为 `仓库/releases/latest/download/latest.json`。可选配置 `dev.guga.updates.MANIFEST_URL` 指定另一个 HTTPS 清单地址；APK 仍须来自所配置仓库的 `/releases/download/`。可选 `dev.guga.updates.APP_NAME` 覆盖通知名称，默认使用宿主应用名称。通知图标应为 Android 通知用的单色资源，不配置则使用系统下载图标。安装 Activity、结果 Receiver 和所需权限由库的 Manifest 合并，不需要复制组件。

```java
import dev.guga.updates.ReleaseUpdater;
import dev.guga.updates.UpdateButton;

@Override protected void onResume() {
    super.onResume();
    ReleaseUpdater.checkAutomatically(this);
}

// 设置开关：默认开启，用户更改后立即持久化。
boolean enabled = ReleaseUpdater.isAutomaticEnabled(this);
ReleaseUpdater.setAutomaticEnabled(this, enabled);

// 可选现成按钮，父布局固定高度 52dp，宽度由宿主布局决定。
UpdateButton button = new UpdateButton(this);
container.addView(button, new LinearLayout.LayoutParams(
    ViewGroup.LayoutParams.MATCH_PARENT,
    Math.round(52 * getResources().getDisplayMetrics().density)));
```

按钮默认浅紫配色，可使用标准 View/TextView API 自定义颜色和背景；`setDetailsHandler(message -> ...)` 可接入宿主自己的详情弹窗。也可以完全不使用此控件，通过 `checkManually(context, finished)`、`isRunning()`、`statusMessage()`、`latestDownloadReady(context)` 和 `installDownloaded(activity)` 构建自己的界面。完成回调在主线程执行；重复检查复用正在进行的任务，回调等待该任务结束。下载期间可在界面可见时读取状态，离开页面应停止自己的 UI 轮询。

## 行为约定

- 自动检查默认开启；前台入口调用后，每个本地自然日最多尝试一次，失败也计入当天。无常驻服务、定时唤醒或后台轮询。自动失败不弹窗。
- 手动检查不受当天限制，失败显示可读状态。按钮大小不变，最多两行并缩小字号，仍超出则显示详情。
- 再进入更新页面显示“检查更新”；检查服务端版本后复用有效缓存，下载完成按钮变成“安装更新”。其他状态点击仍检查更新。
- APK 验证大小、SHA-256、包名、版本、最低系统版本和签名。仅支持完整单 APK，不支持 split APK 集合/APKS/XAPK；APK 上限 200 MiB。
- APK 必须与宿主包名、当前签名一致，`versionCode` 更大。安装需系统允许“安装未知应用”，可能还需用户确认；库无法保证静默安装。手动安装问题用前台弹窗反馈。
- 自动下载完成后，在具备安装权限时尝试系统安装，否则提供通知入口。Android 13+ 通知权限由宿主自行决定何时请求；未授权不影响手动入口。
- 安装成功或新版本下次启动时删除已安装 APK。旧缓存不影响重新检查更高版本。
- 状态和缓存属于当前宿主应用。持久化使用 `updates` SharedPreferences、`files/updates/`，通知 channel 为 `updates`、ID 为 `50202`，宿主应保留这些名称。每个应用仅配置一个更新源。

## 发布清单

把 `latest.json` 与 APK 一起上传到正式 GitHub Release；不要将未完成的 Release 标成 Latest。

```json
{
  "schema": 1,
  "versionCode": 23,
  "versionName": "1.2.0",
  "prerelease": false,
  "assets": {
    "arm64-v8a": {
      "url": "https://github.com/OWNER/REPOSITORY/releases/download/v1.2.0/app-arm64.apk",
      "sha256": "替换为该APK的64位SHA256十六进制摘要",
      "size": 12345678
    },
    "universal": {
      "url": "https://github.com/OWNER/REPOSITORY/releases/download/v1.2.0/app-universal.apk",
      "sha256": "替换为该APK的64位SHA256十六进制摘要",
      "size": 23456789
    }
  }
}
```

优先按照设备支持的 ABI 顺序匹配；没有专用 APK 时使用可选 `universal`。`size` 必须为实际字节数。`versionCode` 决定是否升级，版本名称仅用于显示。预发布清单不安装。当前仅支持公开、无认证的 HTTPS 仓库资源。

## 构建与分发

```sh
./gradlew :release-updater:assembleRelease \
  :release-updater:publishReleasePublicationToLocalDistributionRepository
```

AAR 位于 `release-updater/build/outputs/aar/release-updater-release.aar`；包含 POM、依赖信息和源码的本地 Maven 仓库位于 `release-updater/build/maven-repository/`，坐标为 `dev.guga:release-updater:0.1.0`。复制该 Maven 仓库到其他项目并配置 `maven { url uri('路径') }` 后即可使用坐标依赖。没有发布到 Maven Central。

仅复制 AAR 时还需显式添加 `com.squareup.okhttp3:okhttp:4.12.0`，使用 Maven 形式则会传递该依赖。测试位于宿主 `app/src/androidTest/java/dev/guga/updates` 和 `dev/guga/dsh/UpdateUiTests.java`，测试辅助入口不打包进发布库。
