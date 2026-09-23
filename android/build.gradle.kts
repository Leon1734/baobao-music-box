plugins {
    id("com.android.application") version "8.5.2" apply false
    // Kotlin 插件：MainActivity.kt 需要（少了它 kotlinOptions 会解析不了）
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
    // Chaquopy：在 APK 里嵌入 Python 解释器
    id("com.chaquo.python") version "15.0.1" apply false
}
