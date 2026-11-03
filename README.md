# iAP2 Location Bridge for Windows

[GitHub 项目主页](https://github.com/xpqball/iap2-location-bridge-windows) · [问题反馈](https://github.com/xpqball/iap2-location-bridge-windows/issues)

基于 [aur3l14no/accessory-location](https://github.com/aur3l14no/accessory-location) 的 Windows USB 移植版本，通过 iAP2 向连接的 iPhone 提供 GGA/RMC 定位数据。保留上游 Python 协议实现及 macOS 支持。

仓库、Python 分发包及命令行入口统一为 `iap2-location-bridge-windows`；Python 模块为 `iap2_location_bridge_windows`。

**实验性项目 · GPL-3.0-only**。需要设备接受的配件证书及匹配私钥，仓库不附带认证材料。此工具不读取手机最终采用的位置，不承诺解锁任何地区限定功能。

## 支持范围

| 项目 | 状态 |
| --- | --- |
| Windows USB | 重命名前已完成认证、定位发送、地图位置变化与停止后恢复验证；当前版本的新配件标识尚待实机复测 |
| macOS USB / 蓝牙 | 保留上游实现；本次 Windows 移植未重新实机验证 |
| Windows 蓝牙 | 未实现，CLI 会明确拒绝 |
| 自动化测试 | 本地 Windows 管理员环境 50 项通过、0 项跳过；普通权限可能跳过符号链接测试，远端结果以 Actions 为准 |

实机结果仅对应已测试设备组合，不代表所有 iOS 或硬件版本兼容。地图变化及恢复由操作者观察确认。命名统一后的安装包已通过完整离线测试；复测实机前请勿将早期记录视为新配件标识已被设备接受。

## Windows 快速开始

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/)、正常运行的 Apple Mobile Device Service，以及已解锁并信任电脑的 iPhone。可通过 Apple 官方 Windows 软件安装所需设备服务；不要将正常工作的 Apple USB 驱动替换为 WinUSB。

### 先在 iPhone 上完成准备

1. **连接并解锁。** 使用支持数据传输的 USB 数据线连接 Windows 电脑，解锁 iPhone。若出现配件连接提示，按屏幕提示允许本次连接；测试期间保持线缆连接稳定。
2. **信任并完成配对。** iPhone 出现“要信任此电脑吗？”时，选择“信任”并按提示输入设备密码。首次使用时可先打开 Windows 的“Apple 设备”或 iTunes，确认能识别手机并完成配对；本项目不会自动发起配对。已信任的电脑通常不会每次重新弹出提示。
3. **打开定位服务。** 进入“设置 → 隐私与安全性 → 定位服务”，保持开启。菜单名称可能随 iOS 版本略有变化。
4. **允许地图使用位置。** 在定位服务列表中找到“地图”，将访问权限设为“使用 App 期间”（或“使用 App 或小组件期间”），并开启“精确位置”。首次打开地图时也需同意定位权限。
5. **确认当前真实位置。** 打开苹果地图，点击“我的位置”按钮，确认蓝点能显示当前真实位置。若尚未取得位置，先在信号较好的地方等待定位，再开始测试。
6. **发送时让地图请求位置。** 电脑启动下方的发送命令后，保持手机解锁、地图在前台，再点击“我的位置”。这会让地图请求位置；程序需收到 `location_requested` 才会发送。以当前定位蓝点及实际所在区域判断效果。

本流程不要求 iPhone 越狱、开启开发者模式或安装 DiPlay APK。可选 APK 导入器只在电脑端提取认证材料。测试中的 Windows 符号链接权限要求与 iPhone 开发者模式无关。

准备阶段保持定位服务开启；只有在已收到发送确认、但地图仍未变化时，再按下文的方法短暂关闭后重新开启定位服务。测试结束后还需完成“停止与恢复”检查。

### 安装依赖并探测 USB

下载本仓库后，在仓库目录打开 PowerShell：

```powershell
uv sync --locked --python 3.11
uv run python tools/probe_windows_service.py
```

探测仅打开并关闭 `com.apple.carkit.service`，不加载认证材料、不发送坐标。成功时显示 `USB lockdown connected` 和 `CarKit service opened successfully`。

### 配置认证并测试

从早期测试版更新时，请重新执行依赖安装，并使用下方的新目录与环境变量。旧版命令入口和环境变量不再使用。

将自己的认证文件保存在仓库外的私有目录。证书必须为 DER PKCS#7，私钥为未加密 DER PKCS#8 P-256，且两者匹配：

```powershell
$identityDir = Join-Path $env:LOCALAPPDATA 'iap2-location-bridge-windows\identity'
$env:IAP2_LOCATION_BRIDGE_WINDOWS_CERT_FILE = Join-Path $identityDir 'certificate.p7b'
$env:IAP2_LOCATION_BRIDGE_WINDOWS_KEY_FILE = Join-Path $identityDir 'identity.pk8'
uv run iap2-location-bridge-windows probe --transport usb --auth-helper tools/local_mfi_v3_helper.py --duration 20
```

这里只设置路径，不生成或复制文件。自签名测试证书不能建立设备信任；需观察 `authentication_succeeded`。可选导入流程与材料来源边界见[认证文档](docs/authentication.md)。

### 发送定位

以下坐标仅为示例，请替换为实际测试目标。发送前打开手机地图并请求当前位置。

```powershell
uv run iap2-location-bridge-windows send --transport usb --auth-helper tools/local_mfi_v3_helper.py --latitude 48.1173 --longitude 11.5167 --duration 180
```

程序仅在配件识别、认证和定位订阅均完成后发送。`--duration` 限制握手后的主循环时长，并非整个进程的硬超时。

| 事件 | 含义 |
| --- | --- |
| `link_ready` | iAP2 链路握手成功 |
| `identification_accepted` | 配件身份描述被接受 |
| `authentication_succeeded` | 当前认证响应被设备接受 |
| `location_requested` | 手机请求定位数据 |
| `location_link_acknowledged` | 数据获链路确认，不等于系统采用坐标 |

必须在手机地图上确认实际位置变化。如果已收到链路确认但地图没有变化，可在测试期间关闭定位服务约 10 秒后重新开启，再请求当前位置；这并不保证所有设备都采用坐标。

### 停止与恢复

等待限时结束或按 Ctrl+C，然后断开 USB。重新请求真实位置；若地图仍显示上次结果，可重新开关定位服务、退出并重开地图，并在信号良好处等待重新定位。**进程退出不等于真实位置已恢复，需在手机上确认。** 拔线时可能出现 `ConnectionTerminatedError` 和非零退出码。

## 故障排查

| 现象 | 检查方式 |
| --- | --- |
| 找不到手机 | 检查数据线、解锁、信任状态及 Apple Mobile Device Service |
| 能连接 USB，但 CarKit 打不开 | 检查具体异常；设备系统限制与 USB 驱动问题需分别判断 |
| helper 启动失败 | 确认文件路径正确；`.py` helper 使用当前 Python 解释器启动，支持空格路径 |
| 认证失败 | 核对证书格式、密钥匹配和设备是否接受该身份 |
| 认证成功但没有订阅 | 打开手机地图并点击当前位置 |
| pytest 在控制台初始化时报错 | 使用下方 `-p no:xonsh` 命令，禁用依赖附带的无关插件 |

## 开发

```powershell
uv run ruff check src tests tools
uv run pytest -p no:xonsh -q
```

测试使用模拟协议对端及临时生成的认证材料，无需连接手机。Windows 权限测试核验实际 NTFS ACL；不具备符号链接创建权限时，仅跳过对应测试。

macOS 安装及使用同样的 Python CLI，以 `export` 设置认证文件路径。原生蓝牙桥接器需在 macOS 使用 Apple Command Line Tools 执行 `make native`。`tools/local-only.sb` 仅适用于 macOS，Windows 未实现等价的网络沙箱。

## 项目结构

```text
src/iap2_location_bridge_windows/   CLI、认证、传输、iAP2 链路和定位数据
tools/                   本地认证 helper、身份导入器和 USB 服务探测
tests/                   离线协议、签名、导入和平台适配测试
docs/                    协议、认证与研究来源
native/                  上游 macOS 蓝牙桥接器
.github/workflows/       Windows / macOS CI
```

详见[贡献指南](CONTRIBUTING.md)、[协议文档](docs/protocol.md)、[认证文档](docs/authentication.md)和[来源](docs/sources.md)。

## 来源与许可证

本项目是对上游的修改版本，不是独立重写。基线提交为 `8a13296a3d81dae18ad4481e7a9eca913c2c644f`；Windows 修改日期为 2026-11-03。主要修改：Python helper 跨平台启动、Windows 蓝牙提示、异常清理、Windows 身份目录及 ACL 核验、PowerShell 输出、USB 探测、本地 APK 导入以及 Windows 测试与 CI。

保留上游 [GNU GPL v3](LICENSE)，许可证标识为 `GPL-3.0-only`。第三方认证材料不属于本项目，也不因项目许可证获得重新授权。提交 issue 或 PR 时，请勿附带私钥、证书、配对记录或设备标识符。
