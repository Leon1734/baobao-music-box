"""发布 v1.2.0：建 GitHub Release 并上传本地构建的 Windows exe。

为什么 exe 要本地传而不是 CI 构建：
  photos_web/ 和 音源/ 没进仓库（照片是私人的、音源是第三方文件），
  CI checkout 拿不到它们，构建出来的 exe 会缺照片轮播和在线音源。
  所以 Windows 版必须本地打好再上传。

token 从 git credential 取，只在本进程内使用，绝不打印或落盘。
"""
import subprocess, json, ssl, os, sys, mimetypes, urllib.request, urllib.error

REPO = "Leon1734/baobao-music-box"
TAG = "v1.2.3"
NAME = "宝宝音乐盒 v1.2.3 · 修复：无边框窗口没有标题栏按钮、拖不动"
EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dist", "宝宝音乐盒.exe")
ASSET_NAME = "baobao-music-box-v1.2.3-win64.exe"   # 必须 ASCII，中文名会被 GitHub 吞掉

NOTES = """## 宝宝音乐盒 v1.2.3

### ⚡ 性能修复（本次重点）

**多源并行搜索有结构性缺陷，慢平台会拖死整个请求。**

5 处多源并行（搜索 / 跨源换源 / 榜单 / 推荐歌单 / 歌单搜索）全是同一套写法：
1. 线程池套在 `with` 里，异常退出时会**等所有线程跑完**才返回
2. `as_completed(timeout=18)` 超时直接抛错，中断结果收集
3. 之后的「串行兜底」把慢平台**一个个同步**再跑一遍

最坏 **18 + 4×15 = 78 秒** —— 界面表现为"搜索卡了一分多钟"。
实测榜单接口曾撞满上限 **8111ms**。

现在改成 `wait(短超时) 轮询 + 硬截止 + 宽限期早返回`：
慢源补空、不等残留线程、已有结果就先出界面。

| 接口 | 修复前 | 修复后 |
|------|--------|--------|
| 排行榜 | 8111 ms | **530 ms** |
| 歌单搜索 | 2061 ms | **993 ms** |

合成用例 5 项验证（`tools/verify_pmap.py`）：
```
(1) 2快+2慢(30s)/deadline=3s   -> 3.04s  ok
(2) 4个全慢(25s)/deadline=2s   -> 2.03s  ok
(3) 单源短路                    -> 0.000s ok
(4) 异常源隔离                  -> 0.00s  ok
(5) grace=2/deadline=8 慢源拖着  -> 2.04s  ok（不加宽限期会卡满 8 秒）
```
回归 `tools/verify.py` **27/27 通过，无 JS 错误**。

### 🔍 顺带修复
播放列表 / 我喜欢 / 统计 4 处空 `catch` 补上错误日志 ——
吞掉异常意味着播放列表悄悄变空，连排查线索都没有。

### 📦 下载
| 平台 | 文件 |
|------|------|
| Windows | `baobao-music-box-v1.2.3-win64.exe`（免安装单文件，双击即用，照片/音源/壁纸全内置）|
| Android | `baobao-music-box-v1.2.1-android.apk`（侧载安装，Android 7.0+）|

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
