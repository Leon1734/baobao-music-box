package com.leon1734.baobaomusic

import android.annotation.SuppressLint
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.View
import android.view.WindowManager
import android.webkit.*
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.*
import java.net.HttpURLConnection
import java.net.URL

/**
 * 宝宝音乐盒 · Android
 *
 * 思路：不重写播放器逻辑，而是在 APK 里跑桌面版那份 server.py（纯标准库），
 *      WebView 指向 http://127.0.0.1:8082/player.html —— 和 Windows 版共用同一套代码。
 *
 * 启动顺序：
 *   1. 起 Python（Chaquopy）
 *   2. 后台线程跑 server.serve()（它自己会在 8082 监听）
 *   3. 轮询 /api/health 直到就绪
 *   4. WebView 加载播放器页面
 */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var serverStarted = false

    companion object {
        private const val TAG = "BaobaoMusic"
        private const val PORT = 8082
        private val PLAYER_URL = "http://127.0.0.1:$PORT/player.html"
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 播放时别让屏幕黑掉
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        web = WebView(this)
        setContentView(web)
        with(web.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true                       // 播放器用 localStorage 存歌单/设置
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false        // 允许自动续播下一首
            allowFileAccess = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            cacheMode = WebSettings.LOAD_DEFAULT
            userAgentString = "$userAgentString BaobaoMusicBox/${BuildConfig.VERSION_NAME}"
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView?, request: WebResourceRequest?
            ): Boolean = false                              // 站内跳转都在 WebView 里走
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        }

        // 先显示一个加载页，等 Python 服务就绪再跳转
        web.loadDataWithBaseURL(null, LOADING_HTML, "text/html", "utf-8", null)

        startPythonServer()
    }

    private fun startPythonServer() {
        if (serverStarted) return
        serverStarted = true
        scope.launch(Dispatchers.IO) {
            try {
                // APK 里的 assets 是只读的，先拷到应用私有目录，
                // 这样 server.py 把资源目录和数据目录都当成普通可写目录用
                val dataDir = prepareAssets()

                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(applicationContext))
                }
                val py = Python.getInstance()
                // 关键：必须在 import server 之前设好 os.environ，
                // server.py 是在 import 时读 MB_DATA_DIR 解析目录的
                py.getModule("os").callAttr("environ")
                    .callAttr("__setitem__", "MB_DATA_DIR", dataDir.absolutePath)

                val server = py.getModule("server")          // src/main/python/server.py
                server.callAttr("set_port", PORT)

                // serve() 是阻塞的，扔到独立线程
                Thread {
                    try {
                        server.callAttr("serve")
                    } catch (t: Throwable) {
                        Log.e(TAG, "Python 服务退出", t)
                    }
                }.start()

                // 轮询 /api/health 确认真的起来了（不看端口占用，端口被占≠服务就绪）
                val ok = waitReady(60_000)
                withContext(Dispatchers.Main) {
                    if (ok) {
                        web.loadUrl(PLAYER_URL)
                    } else {
                        web.loadDataWithBaseURL(
                            null,
                            errorHtml("服务在 60 秒内没有就绪。\n\n可能是端口 $PORT 被占用。"),
                            "text/html", "utf-8", null
                        )
                    }
                }
            } catch (t: Throwable) {
                Log.e(TAG, "Python 启动失败", t)
                withContext(Dispatchers.Main) {
                    web.loadDataWithBaseURL(
                        null, errorHtml("Python 启动失败：\n${t.message}"),
                        "text/html", "utf-8", null
                    )
                }
            }
        }
    }

    /**
     * 把 APK assets 里的资源拷到应用私有目录（filesDir）。
     *
     * 为什么需要：APK 内的 assets 是只读的，而 server.py 需要写缓存
     * （歌词缓存 / 儿童乐园缓存 / error.log），所以统一拷一份到可写目录。
     * 用 assets 的版本号做标记，升级 App 后自动重新解包。
     */
    private fun prepareAssets(): java.io.File {
        val dst = java.io.File(filesDir, "app")
        val stamp = java.io.File(dst, ".assets_version")
        val want = BuildConfig.VERSION_CODE.toString()
        if (dst.isDirectory && stamp.isFile && stamp.readText().trim() == want) {
            return dst   // 已解包且版本一致，直接用
        }
        dst.deleteRecursively()
        dst.mkdirs()
        val am = assets
        // 单个文件
        for (f in listOf(
            "player.html", "manifest.json", "sw.js", "favicon.png",
            "icon-192.png", "icon-512.png", "kids_cache.json"
        )) {
            try {
                am.open(f).use { input ->
                    java.io.File(dst, f).outputStream().use { input.copyTo(it) }
                }
            } catch (e: Exception) {
                Log.w(TAG, "asset 缺失(可忽略): $f")
            }
        }
        // 整个目录
        for (dir in listOf("photos_web", "音源")) {
            try {
                copyAssetDir(am, dir, java.io.File(dst, dir))
            } catch (e: Exception) {
                Log.w(TAG, "asset 目录缺失(可忽略): $dir")
            }
        }
        try { stamp.writeText(want) } catch (_: Exception) {}
        Log.i(TAG, "assets 已解包到 ${dst.absolutePath}")
        return dst
    }

    private fun copyAssetDir(am: android.content.res.AssetManager, src: String, dst: java.io.File) {
        val children = am.list(src) ?: return
        if (children.isEmpty()) {                      // 是文件不是目录
            dst.parentFile?.mkdirs()
            am.open(src).use { input -> dst.outputStream().use { input.copyTo(it) } }
            return
        }
        dst.mkdirs()
        for (c in children) copyAssetDir(am, "$src/$c", java.io.File(dst, c))
    }

    /** 轮询 health，直到拿到 app=baobao-music 才算就绪 */
    private fun waitReady(timeoutMs: Long): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            try {
                val c = URL("http://127.0.0.1:$PORT/api/health").openConnection() as HttpURLConnection
                c.connectTimeout = 1500
                c.readTimeout = 1500
                val body = c.inputStream.bufferedReader().use { it.readText() }
                if (body.contains("baobao-music")) return true
            } catch (_: Throwable) {
                // 还没起来，继续等
            }
            Thread.sleep(300)
        }
        return false
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    override fun onPause() {
        super.onPause()
        // 退到后台时暂停播放，避免"关不掉的声音"
        web.evaluateJavascript(
            "try{const a=document.querySelector('audio'); if(a) a.pause();}catch(e){}", null
        )
    }

    private val LOADING_HTML = """
        <!doctype html><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <style>
          html,body{height:100%;margin:0;background:#0f0f16;color:#e8e8f0;
                    font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
          .w{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}
          .s{width:38px;height:38px;border:3px solid #ffffff22;border-top-color:#7c5cff;
             border-radius:50%;animation:r .9s linear infinite}
          @keyframes r{to{transform:rotate(360deg)}}
          .t{font-size:15px;opacity:.8}
        </style>
        <div class="w"><div class="s"></div><div class="t">宝宝音乐盒启动中…</div></div>
    """.trimIndent()

    private fun errorHtml(msg: String) = """
        <!doctype html><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <style>
          html,body{height:100%;margin:0;background:#0f0f16;color:#e8e8f0;
                    font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
          .w{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;
             gap:14px;padding:28px;text-align:center;box-sizing:border-box}
          h2{font-size:17px;margin:0;color:#ff8a8a}
          pre{white-space:pre-wrap;font-size:13px;opacity:.85;line-height:1.6;margin:0}
        </style>
        <div class="w"><h2>启动失败</h2><pre>${msg.replace("<", "&lt;")}</pre></div>
    """.trimIndent()
}
