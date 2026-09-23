"""把 Release v1.2.0 上命名错误的 APK 附件改回正确版本号。

背景：android.yml 里版本号写死成 v1.1.0，导致 v1.2.0 的 APK 顶着 v1.1.0 的名字。
内容是对的（30.68MB，与 v1.1.0 的 30.65MB 不同，是 tag 触发的重新构建），
只是名字会误导下载者。工作流已修（版本号改从 tag 推导），这里补修已上传的那个。
"""
import subprocess, json, ssl, sys, urllib.request, urllib.error

REPO = "Leon1734/baobao-music-box"
TAG = "v1.2.0"
OLD = "baobao-music-box-v1.1.0-android.apk"
NEW = "baobao-music-box-v1.2.0-android.apk"


def token():
    for attempt in range(3):
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
        print("❌ 取不到 token"); return 1
    print(f"✅ token 已取得（{len(tk)} 字符）")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    H = {"Authorization": "Bearer " + tk, "Accept": "application/vnd.github+json",
         "User-Agent": "mb-release"}

    def call(u, m="GET", d=None, ct=None):
        h = dict(H)
        if ct:
            h["Content-Type"] = ct
        r = urllib.request.Request("https://api.github.com" + u, data=d, headers=h, method=m)
        with urllib.request.urlopen(r, timeout=60, context=ctx) as x:
            b = x.read()
            return json.loads(b) if b else {}

    rel = call(f"/repos/{REPO}/releases/tags/{TAG}")
    for a in rel["assets"]:
        if a["name"] == OLD:
            r = call(f"/repos/{REPO}/releases/assets/{a['id']}", "PATCH",
                     json.dumps({"name": NEW}).encode(), "application/json")
            print(f"✅ 重命名成功: {OLD}\n            -> {r['name']}")
        else:
            print(f"⏭  保持不动: {a['name']}")

    rel = call(f"/repos/{REPO}/releases/tags/{TAG}")
    print(f"\n=== Release {TAG} 最终状态 ===")
    print(f"  {rel['html_url']}")
    print(f"  draft={rel['draft']}  prerelease={rel['prerelease']}")
    for a in sorted(rel["assets"], key=lambda x: x["name"]):
        print(f"    - {a['name']:40s} {a['size']/1024/1024:6.2f} MB  {a['download_count']} 下载")
    return 0


if __name__ == "__main__":
    sys.exit(main())
