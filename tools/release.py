"""发布 v1.2.0：建 GitHub Release 并上传本地构建的 Windows exe。

为什么 exe 要本地传而不是 CI 构建：
  photos_web/ 和 音源/ 没进仓库（照片是私人的、音源是第三方文件），
  CI checkout 拿不到它们，构建出来的 exe 会缺照片轮播和在线音源。
  所以 Windows 版必须本地打好再上传。

token 从 git credential 取，只在本进程内使用，绝不打印或落盘。
"""
import subprocess, json, ssl, os, sys, mimetypes, urllib.request, urllib.error

REPO = "Leon1734/baobao-music-box"
TAG = "v1.3.1"
NAME = "宝宝音乐盒 v1.3.1 · 修复：孤儿窗口提示 / 多实例数据目录串扰"
EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dist", "宝宝音乐盒.exe")
ASSET_NAME = "baobao-music-box-v1.3.1-win64.exe"   # 必须 ASCII，中文名会被 GitHub 吞掉

NOTES = """## 宝宝音乐盒 v1.3.1

### 🔧 修复两个实际遇到的使用问题

**1. 「本地服务未响应」的孤儿窗口**
在 8082 端口有另一份拷贝运行时双击 exe，会复用那个实例的窗口；一旦它先退出，
窗口就变成「服务已断开的孤儿」，且提示文案让 exe 用户去跑 .bat（错误指引）。
- exe / 原生窗口：提示改为「请关闭本窗口，重新双击打开」
- 浏览器：保留「运行启动音乐盒.bat」的提示
- 新增每 5 秒自愈探测：服务恢复后**自动撤掉警告条**，不用手动刷新

**2. 多实例数据目录串扰**
同机存在多份拷贝（如 dist/ 与 release_pkg/）时，exe 会复用另一份的服务 →
用户看到的是**别人的库**（照片/音源/缓存都不同）。
现在按数据目录判断：相同才复用（双击两次的正常场景），不同则自己起服务（端口自动 +10）。

### 🎵 v1.3.0 起自带的能力（如果你从旧版升级）

- **在线播放链路重做**：内置洛雪音源引擎（星海/长青/K×H 五源竞速）
  —— 酷我/网易/QQ/酷狗/咪咕五平台实测 5/5 真歌可播
- **免安装 exe 内置 Node 运行时**，什么都不用装即可在线播放
- 网易云搜索接口修复、咪咕第五平台、搜索联想、热搜三平台聚合

### 📥 下载

| 平台 | 文件 |
|------|------|
| Windows | `baobao-music-box-v1.3.1-win64.exe`（免安装单文件，双击即用，照片/音源/壁纸/Node 全内置）|
| Android | `baobao-music-box-v1.3.1-android.apk`（侧载安装，Android 7.0+）|

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

    def call(url, method="GET", data=None, headers=None, retries=3):
        """带退避重试的 API 调用。
        ⚠ 实测：CI 与本地脚本并发操作同一个 Release 时，GitHub 会返回瞬时 500
          （曾导致补标题的 PATCH 直接抛异常、整个发版流程崩掉）。5xx 一律退避重试。"""
        import time as _t
        h = dict(H)
        if headers:
            h.update(headers)
        last = None
        for attempt in range(retries):
            req = urllib.request.Request("https://api.github.com" + url, data=data,
                                         headers=h, method=method)
            try:
                with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                    body = r.read()
                    return r.status, (json.loads(body) if body else {})
            except urllib.error.HTTPError as e:
                if e.code >= 500 and attempt < retries - 1:
                    wait = 2 * (attempt + 1)
                    print(f"  [retry] HTTP {e.code}（{method} {url[:50]}），{wait}s 后重试…")
                    _t.sleep(wait); last = e; continue
                raise
            except Exception as e:
                if attempt < retries - 1:
                    _t.sleep(2 * (attempt + 1)); last = e; continue
                raise
        raise last if last else RuntimeError(f"API 调用失败: {method} {url}")

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
        # 同理标题也只会是裸 tag（"v1.3.0"），一并补成完整标题。
        patch = {}
        if not (rel.get("body") or "").strip():
            patch["body"] = NOTES
        if (rel.get("name") or "").strip() in ("", TAG, TAG.lstrip("v")):
            patch["name"] = NAME
        if patch:
            # 补标题/说明是**非关键路径**：失败也不能中断主流程（上传 exe 才是关键），
            # 否则一次瞬时 500 就把整个发版打断（实测踩过）。
            try:
                call(f"/repos/{REPO}/releases/{rid}", "PATCH",
                     json.dumps(patch).encode(),
                     {"Content-Type": "application/json"})
                print(f"✅ 已补上 {'发布说明' if 'body' in patch else ''}"
                      f"{' + ' if len(patch) > 1 else ''}{'标题' if 'name' in patch else ''}")
            except Exception as e:
                print(f"⚠️ 补标题/说明失败（不影响上传；稍后重跑本脚本即可补上）: "
                      f"{type(e).__name__}")
        else:
            print("⏭ 已有发布说明与标题，保持不动")
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
