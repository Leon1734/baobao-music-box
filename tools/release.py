"""发布 v1.2.0：建 GitHub Release 并上传本地构建的 Windows exe。

为什么 exe 要本地传而不是 CI 构建：
  photos_web/ 和 音源/ 没进仓库（照片是私人的、音源是第三方文件），
  CI checkout 拿不到它们，构建出来的 exe 会缺照片轮播和在线音源。
  所以 Windows 版必须本地打好再上传。

token 从 git credential 取，只在本进程内使用，绝不打印或落盘。
"""
import subprocess, json, ssl, os, sys, mimetypes, urllib.request, urllib.error

REPO = "Leon1734/baobao-music-box"
TAG = "v1.2.0"
NAME = "宝宝音乐盒 v1.2.0 · 多音源 + 全屏播放页 + 壁纸皮肤 + 无边框窗口"
EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dist", "宝宝音乐盒.exe")
ASSET_NAME = "baobao-music-box-v1.2.0-win64.exe"   # 必须 ASCII，中文名会被 GitHub 吞掉

NOTES = """## 宝宝音乐盒 v1.2.0

### 🎵 多音源（本次最大改动）
- 搜索 / 榜单 / 歌单 / 推荐全部接入 **酷我 · 网易云 · QQ音乐 · 酷狗** 四平台
- 排行榜从 18 个扩到 **137 个**，推荐歌单 **106 个**
- 榜单 / 推荐 / 歌单搜索改用**平台 Tab 切换**，选哪个平台就只看哪个平台（选择会记住）
- 某平台放不出来时**自动跨源换源**兜底

### 🖥️ 全屏播放页重做
- 左栏大封面 + 完整控制，右栏大歌词，底部**频谱实时跳动**
- 频谱 **6 种样式**：柱状 / 镜像 / 峰值 / 波形 / 点阵 / 圆环
- 新增**播放列表抽屉**（快捷键 `Q`，`Esc` 分级关闭）
- **双语歌词配对高亮**：原文和它的中文译文一起亮

### 🎨 外观
- **无边框窗口**：去掉系统标题栏，自绘同色标题栏（拖拽区 + 最小化/最大化/关闭）
- **壁纸皮肤**：水墨 / 满月 / 小奶 / 节气 / 登月 5 张，压暗与模糊可调
- 歌单详情改为独立视图，带「← 返回」按钮

### 🐛 修复
- 酷我直链对任意 ID 都返回可播 URL（垃圾 ID 会返回**别的歌**）→ 跨源检索提到盲目直连之前，不再"放错歌"
- QQ 搜索去掉 `new_json=1`（换字段名导致 0 结果）
- 酷狗榜单改用 `m.kugou.com/rank/info`（旧接口已半废）
- 编码回退按坏字比例判断，避免零星坏字节把整篇中文变乱码
- WebView2 黑屏：`--disable-features=CalculateNativeWinOcclusion`

### 📦 下载
| 平台 | 文件 |
|------|------|
| Windows | `baobao-music-box-v1.2.0-win64.exe`（免安装，双击即用）|
| Android | `baobao-music-box-v1.2.0-android.apk`（侧载安装，Android 7.0+）|

> 不含任何第三方凭据；320k 播放不校验密钥，功能无损失。
"""


def token():
    p = subprocess.run(
        "printf 'protocol=https\\nhost=github.com\\n\\n' | git credential fill",
        shell=True, capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return ""


def main():
    tk = token()
    if not tk:
        print("❌ 取不到 GitHub token"); return 1
    print(f"✅ token 已取得（{len(tk)} 字符，不显示）")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    H = {"Authorization": "Bearer " + tk, "Accept": "application/vnd.github+json",
         "User-Agent": "mb-release", "X-GitHub-Api-Version": "2022-11-28"}

    def call(url, method="GET", data=None, headers=None):
        h = dict(H)
        if headers:
            h.update(headers)
        req = urllib.request.Request("https://api.github.com" + url, data=data,
                                     headers=h, method=method)
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})

    # 1) 找/建 Release
    try:
        st, rel = call(f"/repos/{REPO}/releases/tags/{TAG}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            rel = None
        else:
            print("❌ 查询 Release 失败:", e); return 1
    if rel:
        rid = rel["id"]
        print(f"✅ Release {TAG} 已存在（id={rid}），当前附件 {len(rel.get('assets', []))} 个")
        # ⚠️ CI（softprops/action-gh-release）建的 Release 是没有说明文字的，
        # 这里补上，否则 Release 页面上什么都没有。
        if not (rel.get("body") or "").strip():
            call(f"/repos/{REPO}/releases/{rid}", "PATCH",
                 json.dumps({"body": NOTES}).encode(),
                 {"Content-Type": "application/json"})
            print("✅ 已补上发布说明（原 Release 的 body 为空）")
        else:
            print("⏭ 已有发布说明，保持不动")
    else:
        payload = json.dumps({"tag_name": TAG, "name": NAME,
                              "body": NOTES, "draft": False, "prerelease": False}).encode()
        st, rel = call(f"/repos/{REPO}/releases", "POST", payload,
                       {"Content-Type": "application/json"})
        rid = rel["id"]
        print(f"✅ 已创建 Release {TAG}（id={rid}）")

    # 2) 上传 exe（已存在同名附件就跳过）
    st, assets = call(f"/repos/{REPO}/releases/{rid}/assets")
    have = {a["name"] for a in assets}
    if ASSET_NAME in have:
        print(f"⏭ 附件 {ASSET_NAME} 已存在，跳过上传")
    else:
        if not os.path.exists(EXE):
            print("❌ 找不到 exe:", EXE); return 1
        size = os.path.getsize(EXE)
        print(f"⬆️  上传 {ASSET_NAME}（{size/1024/1024:.1f} MB）...")
        with open(EXE, "rb") as f:
            blob = f.read()
        ctype = mimetypes.guess_type(ASSET_NAME)[0] or "application/octet-stream"
        url = (f"https://uploads.github.com/repos/{REPO}/releases/{rid}/assets"
               f"?name={urllib.parse.quote(ASSET_NAME)}")
        req = urllib.request.Request(url, data=blob, method="POST", headers={
            "Authorization": "Bearer " + tk, "Content-Type": ctype,
            "Content-Length": str(size), "User-Agent": "mb-release",
            "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=900, context=ctx) as r:
            a = json.loads(r.read())
        print(f"✅ 上传完成: {a['name']}  {a['size']/1024/1024:.1f} MB")

    # 3) 回读确认（不信自报，一定重新查一遍）
    st, fin = call(f"/repos/{REPO}/releases/tags/{TAG}")
    print(f"\n=== Release {TAG} 实况 ===")
    print(f"  标题: {fin['name']}")
    print(f"  状态: draft={fin['draft']} prerelease={fin['prerelease']}")
    print(f"  链接: {fin['html_url']}")
    print(f"  附件 {len(fin.get('assets', []))} 个:")
    for a in fin.get("assets", []):
        print(f"    - {a['name']:42s} {a['size']/1024/1024:6.2f} MB  {a['download_count']} 次下载")
    return 0


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())
