# 宝宝音乐盒 · Baobao Music Box

一个**本地运行**的家庭音乐播放器：本地音乐 + 在线音源搜索 + 宝宝照片轮播 + 儿歌专区。
不需要注册、不需要账号、不上传任何数据。

![Python](https://img.shields.io/badge/Python-3.8%2B-blue) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

---

## 三个平台

| 平台 | 产物 | 说明 |
|------|------|------|
| **Windows** | [`宝宝音乐盒.exe`](../../releases) | 双击即用，免安装免 Python |
| **Android** | `*.apk`（Releases 或 Actions 产物） | 侧载安装，Android 7.0+ |
| **源码** | `python app.py` | 需要 Python 3.8+ |

### Windows：直接用 exe（推荐）

1. 从 [Releases](../../releases) 下载 `baobao-music-box-v1.2.1-win64.exe`
2. 双击运行 —— 直接弹出**原生播放器窗口**（Edge WebView2 内核，不是浏览器标签页；无边框自绘标题栏，与整体同色）
3. 关掉窗口即退出

> 不需要装 Python，不需要装任何东西。exe 约 31MB（内含照片/音源，开箱即用）。
> 首次启动等 10-20 秒（PyInstaller 解包 + 杀软扫描），之后就快了。

### Android：装 APK

从 Releases 下载 `baobao-music-box-v1.2.1-android.apk`，在手机上点开安装
（需要允许「安装未知来源应用」）。

> 安卓版把同一份 `server.py` 用 [Chaquopy](https://chaquo.com/chaquopy/) 跑在 APK 里，
> WebView 指向 `127.0.0.1:8082` —— **和 Windows 版共用同一套播放器代码**，行为一致。
> 构建走 GitHub Actions（本地不需要 Android SDK）。

### 源码运行

```bash
python app.py            # 自动选端口 + 弹原生窗口
python server.py         # 只起服务，手动访问 http://localhost:8082/player.html
```

Windows 用户可以直接双击 `启动音乐盒.bat` / `停止音乐盒.bat`。

**安卓工程**在 `android/`。改动 `player.html` 或 `server.py` 后跑一次同步脚本：

```bash
python tools/sync_android_assets.py
```

---

## 数据放在哪

**exe 旁边**（源码运行就是项目目录）—— 用户自己放文件，程序自动识别：

```
宝宝音乐盒.exe
photos/          ← 把宝宝照片丢这里，首页自动轮播（支持 jpg/png/webp/gif）
音源/            ← 放你自己的洛雪/LX 音源 .js 文件
config.json      ← 配置音源密钥（见下）
error.log        ← 出问题时自动生成，反馈时把它发出来
```

程序**优先用同级目录**的内容，找不到才用打包内置的那份。所以：

- 换成你自己的照片/音源，会覆盖内置的那份
- exe 里已经带了照片/音源，直接转发给别人即可开箱使用

---

## 在线播放

在线搜索、榜单、推荐、在线播放**全部开箱即用**，不需要配置任何东西。

音源接口对 320k 播放不校验密钥，所以公开分发的包里**不含任何第三方凭据**
（实测：不带密钥和带密钥，同一批歌都返回 200）。

如果你有自己的密钥，想用上（例如更高音质），放在 `config.json`：

```bash
cp config.example.json config.json
```

```json
{
  "hyw_key": "你的密钥"
}
```

也可以用环境变量：`MB_HYW_KEY=xxx`。自己私用想打进 exe：
`python build_exe.py --with-key`。

> 取链接有降级链：音源 API（8 秒超时）→ 酷我直链兜底（<1s）→ 音源重试。
> 上游不稳定时会自动换源。

---

## 功能

| 分类 | 内容 |
|------|------|
| **多音源** | 酷我 / 网易云 / QQ / 酷狗 **四平台**搜索与播放；哪个平台播不了自动跨源换源兜底 |
| **音乐库** | 首页推荐 · 在线搜索（分页加载）· 排行榜（137 个榜单）· 推荐歌单（106 个）· 歌单详情 · 儿童专区（7 个分类 + 精选歌单） |
| **平台切换** | 榜单 / 推荐歌单 / 歌单搜索都按平台分 Tab，选哪个平台就只看哪个平台，选择会记住 |
| **本地** | 选择文件 / 选择文件夹（记住授权，下次自动恢复）· 拖拽导入 · 自动读时长 |
| **个人** | 我喜欢 · 我的歌单（新建/重命名/删除）· 最近播放 · 播放统计（收听时长 + 最常听 TOP20 + 一键生成「宝宝最爱」） |
| **播放** | 10 段均衡器 · 倍速 · 频谱可视化（6 种样式：柱状/镜像/峰值/波形/点阵/圆环）· 15 种主题色 · 壁纸皮肤（5 张）· 睡眠定时（15/30/45/60/90 分 + 播完本曲 + 淡出） |
| **全屏播放页** | 大封面 + 大歌词左右分栏 · 完整控制 · 底部频谱跳动 · 播放列表抽屉（快捷键 `Q`）|
| **歌词** | 多源自动回退 · 逐行高亮 · 全屏歌词 · 双语歌词配对高亮（原文+译文一起亮）· 点击跳转 · 字号/偏移可调 · 手动滚动后自动恢复跟随 |
| **离线** | 歌曲缓存到本地（IndexedDB）· 缓存管理 · 无网可播 |
| **其他** | PWA 可安装 · 歌单导入导出 · 全量备份 / 恢复 · 快捷键（按 `?` 看全部） |

---

## 为什么是本地服务而不是纯网页

浏览器的音频跨域限制（CORS）会让在线音源无法播放，也无法用 Web Audio 做均衡器。
所以用一个小 Python 服务做三件事：

1. 代理音频请求，补上 CORS 头和 Range 支持（拖动进度条、均衡器必需）
2. 聚合多个音源接口，前端只调一个地址
3. 提供本地缓存和静态资源

服务只监听 `127.0.0.1`，不对外网开放。所有数据都在你本机。

---

## 开发

```bash
# 打包 exe
python build_exe.py        # 产物在 dist/

# 自动化测试（需要 playwright + 本地 Chrome）
python tools/verify.py      # 27 项功能回归
python tools/verify_ui.py   # 无边框标题栏 / 歌单详情视图
python tools/verify_fs.py   # 全屏播放列表 + 6 种频谱样式
python tools/stress.py      # 8 项压力测试（内存泄漏 / 竞态 / 边界输入）
python tools/preview.py     # 生成界面预览截图
```

### 目录结构

```
app.py                 exe 入口（选端口、开原生窗口、错误兜底）
server.py              本地服务（多音源聚合 + 音频代理 + 歌词多源竞速）
player.html            单文件前端（约 4400 行，10 个页面标签）
manifest.json / sw.js  PWA
build_exe.py           PyInstaller 打包脚本
tools/                 测试与预览脚本（verify*.py / preview.py / stress.py）
docs/screenshots/      界面截图
reference/             参考的开源项目（洛雪音源等）
archive/               历史原型与备份
音源/ wallpapers/      内置音源 .js / 壁纸图片
```

---

## 已知限制

- **歌词是逐行（LRC），不是逐字**：公开接口没有逐字歌词（yrc）数据，这是数据源限制
- **在线音源依赖第三方**：链接失效或被限流时，程序会自动重试并跳过，但没法保证每首都可播
- **exe 未做代码签名**：Windows SmartScreen 可能提示"未知发布者"，选"仍要运行"即可
- **暂只支持 Windows**：代码本身跨平台（Python + 浏览器），但打包脚本目前只做 Windows

---

## 许可

MIT —— 见 [LICENSE](LICENSE)

音源文件、音频内容版权归各自权利人，本项目不附带任何音源或音频内容。
