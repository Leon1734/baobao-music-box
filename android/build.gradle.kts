plugins {
    // 版本组合说明（这三者必须配套，Chaquopy 有严格的 AGP 范围校验）：
    //   AGP 8.7.3  -> 需要 Gradle 8.9+、JDK 17
    //   Chaquopy 16.0.0 -> 需要 AGP 8.6.0+（15.x 只支持到 AGP 8.2，配 8.5 会直接报错）
    id("com.android.application") version "8.7.3" apply false
    // Kotlin 插件：MainActivity.kt 需要（少了它 kotlinOptions 会解析不了）
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
    // Chaquopy：在 APK 里嵌入 Python 解释器
    id("com.chaquo.python") version "16.0.0" apply false
}
