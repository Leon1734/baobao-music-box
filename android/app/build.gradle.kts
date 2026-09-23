plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.leon1734.baobaomusic"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.leon1734.baobaomusic"
        minSdk = 24          // Android 7.0+，覆盖绝大多数在用手机
        targetSdk = 34
        versionCode = 1
        versionName = "1.1.0"

        // Chaquopy 只为这几种 ABI 构建（覆盖几乎所有现代手机，避免 APK 无谓膨胀）
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false      // 不混淆：server.py 是资源，混淆没意义还容易踩坑
            // 用 debug 签名，方便直接安装（自用分发场景，不上架应用商店）
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    // AGP 8 起 BuildConfig 默认不生成，但 MainActivity 要用 BuildConfig.VERSION_NAME/DEBUG
    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

chaquopy {
    defaultConfig {
        version = "3.11"                 // 和桌面版一致的 Python 3.11
        // server.py 只用标准库（http.server / socketserver / urllib / ssl / threading），
        // 所以这里不需要 pip install 任何东西 —— 包体积和构建时间都省下来了
    }
    // python 源码目录用默认的 src/main/python，不用额外声明
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.webkit:webkit:1.11.0")   // WebViewAssetLoader
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
