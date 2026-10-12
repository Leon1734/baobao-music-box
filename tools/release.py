"""发布 v1.2.0：建 GitHub Release 并上传本地构建的 Windows exe。

为什么 exe 要本地传而不是 CI 构建：
  photos_web/ 和 音源/ 没进仓库（照片是私人的、音源是第三方文件），
  CI checkout 拿不到它们，构建出来的 exe 会缺照片轮播和在线音源。
  所以 Windows 版必须本地打好再上传。

token 从 git credential 取，只在本进程内使用，绝不打印或落盘。
"""
import subprocess, json, ssl, os, sys, mimetypes, urllib.request, urllib.error

REPO = "Leon1734/baobao-music-box"
TAG = "v1.3.0"
NAME = "宝宝音乐盒 v1.3.0 · 播放链路重做：本地洛雪音源引擎 + 免安装自带 Node"
EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dist", "宝宝音乐盒.exe")
ASSET_NAME = "baobao-music-box-v1.3.0-win64.exe"   # 必须 ASCII，中文名会被 GitHub 吞掉

NOTES = """## 宝宝音乐盒 v1.3.0

### 🎵 在线播放链路重做（本次重点）

之前播放不稳定的根因有三层，这版全部修掉：

1. **HYW 音源服务器不可用** —— 旧链路 `HYW → 跨源 → 直链` 全依赖它，一挂全挂
2. **酷我占位音频** —— 直链对 VIP 歌返回的是「此歌曲无法播放」提示音
   （合法 MP3、ID3 全对，仅 ~180KB/11 秒）→ 这就是「播放 11 秒就提示无法播放」
3. **跨源换源形同虚设** —— 只用 HYW 试链，HYW 挂了就切不动音源

**修法：接入本地洛雪音源引擎** —— 洛雪客户端能播的歌，这里也能播了。

- 在 Node 沙箱里直接执行 `音源/*.js`（星海 / 长青 / K×H 等多源并行竞速）
- 取链顺序：本地洛雪源 → HYW → 跨源（每候选先洛雪后 HYW）→ 直链 → 重试
- **可播性双重验证**：音频魔数 + 文件总长 ≥1MB（专门拦占位音）
- 前端最后一道防线：在线歌实际时长 <30s → 判占位 → 自动换链重试

### 📦 免安装 exe 自带 Node 运行时

exe 现在**内置 Node 运行时**（+22MB），拿到 exe 的人**不需要装任何东西**就能在线播放。
体积从 31.8MB → 54.1MB，换来「开箱即用」。

### 🔍 顺带修复与升级

- 网易云搜索接口变更（result 变成加密串）→ 改用 POST 形态，搜索恢复
- 咪咕成为第五平台（搜索 + 封面/歌词直链自带）
- 搜索联想（输入即提示，QQ+网易双源）
- 热搜词三平台聚合（酷我 + QQ + 网易）

### ✅ 验证（真实执行）

```
五平台端到端取链：kw ✅ wy ✅ tx ✅ kg ✅ mg ✅   （4.1 ~ 52.8MB 全为真音频）
音频代理拉流：HTTP 206 + CORS + fLaC 无损头
内置 Node 生效：daemon 进程 = _MEI.../node/node.exe
功能回归：tools/verify.py 26/27，无 JS 错误
```

### 📥 下载

| 平台 | 文件 |
|------|------|
| Windows | `baobao-music-box-v1.3.0-win64.exe`（免安装单文件，双击即用，照片/音源/壁纸/Node 全内置）|
| Android | `baobao-music-box-v1.3.0-android.apk`（侧载安装，Android 7.0+）|

> 不含任何第三方凭据；320k 播放不校验密钥，功能无损失。
"""




def token():
    # ⚠ 两个实测坑：
    #   1. Hermes 自带 git（%LOCALAPPDATA%/hermes/tools/git-*）的
    #      credential.helper=helper-selector 会**挂起**（无输出、不返回）；
    #      系统 Git（D:\Programs\Git，helper=manager）秒回。
    #   2. **绝不能用 shell=True + printf 管道**：Windows 下 shell=True 走 cmd.exe，
    #      而 printf/单引号是 bash 语法 → 输入格式错 → git credential fill 全部挂起
    #      （表现为每个候选干等 25s）。必须用 Python 直接把 stdin 喂给子进程。
    import os as _os
    # 系统 Git 放最前（0.6s 秒回）；"git" 放最后（Hermes 自带那个会挂 25s）
    cands = []
    for p in (r"D:\Programs\Git\cmd\git.exe",
              _os.path.expandvars(r"%ProgramFiles%\Git\cmd\git.exe"),
              _os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe")):
        if _os.path.exists(p) and p not in cands:
            cands.append(p)
    cands.append("git")
    stdin_data = "protocol=https\nhost=github.com\n\n"
    for exe in cands:
        try:
            p = subprocess.run([exe, "credential", "fill"], input=stdin_data,
                               capture_output=True, text=True, timeout=25)
            for line in p.stdout.splitlines():
                if line.startswith("password=") and len(line) > 12:
                    print(f"  [token] 凭据来自: {exe}")
                    return line.split("=", 1)[1].strip()
            print(f"  [token] {exe} 未返回凭据，换下一个…")
        except subprocess.TimeoutExpired:
            print(f"  [token] {exe} 25s 无响应（凭据助手挂起），换下一个…")
            continue
        except Exception as e:
            print(f"  [token] {exe} 失败: {type(e).__name__}")
            continue
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
