// 宝宝音乐盒 · Android
// 架构：Chaquopy 在 APK 里跑 Python，直接复用桌面版的 server.py（纯标准库，零改动），
//      WebView 指向 http://127.0.0.1:8082/player.html —— 和 Windows 版同一套代码。
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
        // Chaquopy 插件仓库（APK 内跑 Python）
        maven { url = uri("https://chaquo.com/maven") }
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "宝宝音乐盒"
include(":app")
