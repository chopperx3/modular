import 'package:flutter/material.dart';

import 'core/settings.dart';
import 'core/theme.dart';
import 'screens/home_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final settings = AppSettings();
  await settings.load();
  runApp(ModularOcrApp(settings: settings));
}

class ModularOcrApp extends StatelessWidget {
  final AppSettings settings;
  const ModularOcrApp({super.key, required this.settings});

  ThemeMode _modeFrom(String s) => switch (s) {
        'light' => ThemeMode.light,
        'dark'  => ThemeMode.dark,
        _       => ThemeMode.system,
      };

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: settings,
      builder: (_, __) => MaterialApp(
        title: 'MODULAR OCR',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        themeMode: _modeFrom(settings.themeMode),
        home: HomeScreen(settings: settings),
      ),
    );
  }
}
