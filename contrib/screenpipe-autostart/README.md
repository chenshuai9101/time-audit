# Screenpipe 开机自启（macOS LaunchAgent）

时间审计需要 Screenpipe 在后台 24/7 录屏才有数据可分析。这个目录提供一份 LaunchAgent 模板，让 Screenpipe 在登录时自动启动。

## 直接安装

```bash
cd contrib/screenpipe-autostart
chmod +x install.sh
./install.sh
```

脚本会：

1. 把 plist 模板里的 `__USER_HOME__` 替换成你的 `$HOME`
2. 校验 plist 语法
3. 卸掉旧 LaunchAgent（如有）
4. 用 `launchctl bootstrap` 加载新版
5. 提示你去 GUI 授权 Screen Recording 权限

## 为什么需要单独授权权限

macOS TCC（隐私权限子系统）按"二进制真路径"授权，且 **不会从 Terminal 继承权限给 launchd 子进程**。所以即便你之前在 Terminal 里跑 `screenpipe record` 时已经允许过屏幕录制，由 launchd 拉起的 screenpipe 仍会被拒绝。

授权一次就行，路径是：

```
/opt/homebrew/lib/node_modules/@screenpipe/cli-darwin-arm64/bin/screenpipe
```

## 为什么不直接用 brew 装的服务

Homebrew 上的 `screenpipe` formula 已被官方标记 deprecated（`brew info` 显示 "does not build! It will be disabled on 2026-08-25"）。不要走 brew。

## 为什么 `npm i -g screenpipe` 也不行

主包 `screenpipe` 当前版本（0.3.350）的 `optionalDependencies` 写的是 `@screenpipe/cli-darwin-arm64@0.3.350`，但这个版本在 npm 上根本没发布——最新只到 0.3.282。结果 npm 不报错地跳过可选依赖，运行时再抱怨"no prebuilt binary"。

正确做法：直接装平台二进制：

```bash
npm i -g @screenpipe/cli-darwin-arm64@0.3.282
```

这会在 `/opt/homebrew/bin/screenpipe` 提供能跑的二进制。

## plist 关键设计说明

```xml
<key>KeepAlive</key>
<dict>
    <key>Crashed</key><true/>           <!-- 崩溃自动重启 -->
    <key>SuccessfulExit</key><false/>   <!-- 你主动 launchctl bootout 后不重启 -->
</dict>
<key>ThrottleInterval</key>
<integer>60</integer>                   <!-- 反崩溃风暴：最少 60 秒一次重启 -->
<key>ProcessType</key>
<string>Background</string>             <!-- 让 macOS 给低优先级 -->
<key>Nice</key>
<integer>5</integer>                    <!-- 不抢前台 CPU -->
```

如果你想加音频转写，把 `--disable-audio` 拿掉，但同时要给 Terminal 和 screenpipe 二进制都授权 Microphone 权限。

## 完全卸载

```bash
launchctl bootout gui/$(id -u)/com.screenpipe.recorder
rm ~/Library/LaunchAgents/com.screenpipe.recorder.plist
pkill -TERM screenpipe
# 数据保留在 ~/.screenpipe/，要清掉的话加：
# rm -rf ~/.screenpipe/
```
