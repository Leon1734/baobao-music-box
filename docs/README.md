# 文档与开发产物

## 目录说明

| 目录 | 内容 | 是否入库 |
|------|------|----------|
| `screenshots/` | 自动化测试与预览脚本生成的界面截图 | ❌ 不入库（18MB 开发产物，本地看就行） |
| `screenshots/verify_shots/` | `tools/verify.py`、`tools/verify_ui.py`、`tools/verify_fs.py` 的输出 | ❌ |
| `screenshots/preview/` | `tools/preview.py` 生成的界面预览图 | ❌ |

截图随时可以用脚本重新生成：

```bash
python tools/preview.py      # 界面预览（首页/设置/壁纸/歌单详情/全屏页）
python tools/verify.py       # 27 项功能回归，跑完顺带出图
```

## 项目根目录布局

```
Music/
├── app.py  server.py  player.html  build_exe.py   ← 程序本体，必须在根
├── manifest.json  sw.js  favicon.png  icon-*.png  ← PWA，必须在根
├── config.json  config.example.json               ← 配置，必须在根
├── 启动音乐盒.bat  停止音乐盒.bat  预览最新版.bat   ← 双击用的
├── README.md  LICENSE  DEVELOPMENT_PLAN.md  IDEA.md
├── 音源/  wallpapers/  photos/  photos_web/       ← 资源，必须在根
├── tools/          测试与预览脚本
├── docs/           本文档 + 截图
├── reference/      参考的开源项目（洛雪音源、AudioDock、rustmusic-ref）
├── archive/        历史原型与备份
├── logs/           运行日志
├── android/        Android 工程（Chaquopy）
└── dist/  release_pkg/  build/                    ← 构建产物
```

> ⚠️ **为什么程序本体不能挪进子目录**：`server.py` / `app.py` / `build_exe.py`
> 都以「项目根 = `DATA_DIR`」为前提按**文件名**找 `config.json`、`player.html`、
> `kids_cache.json`、`音源/`、`photos_web/`、`wallpapers/`。
> 挪进子目录会导致：配置读不到、页面 404、打包漏文件。
> 整理脚本 `tools/organize.py` 里的 `KEEP_AT_ROOT` 就是为守住这条线而存在的。
