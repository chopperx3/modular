plugins {
    id("com.android.application")
    id("kotlin-android")
    // El plugin de Flutter debe ir después de Android y Kotlin
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.example.flutter_ocr_app"

    // Flutter inyecta estos valores desde la raíz del proyecto
    compileSdk = flutter.compileSdkVersion

    // Si NO usas C/C++, comenta esta línea para evitar problemas de NDK
    // ndkVersion = "27.0.12077973"

    // 👉 Compilar con Java 17
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    defaultConfig {
        applicationId = "com.example.flutter_ocr_app"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // Firma de ejemplo (debug) para poder correr --release
            signingConfig = signingConfigs.getByName("debug")
            // Si quieres ofuscar, descomenta:
            // isMinifyEnabled = true
            // proguardFiles(
            //     getDefaultProguardFile("proguard-android-optimize.txt"),
            //     "proguard-rules.pro"
            // )
        }
    }
}

flutter {
    source = "../.."
}
