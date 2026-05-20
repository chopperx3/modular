import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppSettings extends ChangeNotifier {
  static const _kApiUrl       = 'api_url';
  static const _kLangs        = 'langs';
  static const _kHandwriting  = 'handwriting';
  static const _kThemeMode    = 'theme_mode';

  static const _defaultApiUrl = 'http://10.0.2.2:8000';

  late SharedPreferences _prefs;

  String   _apiUrl      = _defaultApiUrl;
  Set<String> _langs    = {'es', 'en'};
  bool     _handwriting = false;
  String   _themeMode   = 'system';

  String   get apiUrl      => _apiUrl;
  Set<String> get langs    => _langs;
  bool     get handwriting => _handwriting;
  String   get themeMode   => _themeMode;

  Future<void> load() async {
    _prefs       = await SharedPreferences.getInstance();
    _apiUrl      = _prefs.getString(_kApiUrl) ?? _defaultApiUrl;
    _langs       = (_prefs.getStringList(_kLangs) ?? ['es', 'en']).toSet();
    _handwriting = _prefs.getBool(_kHandwriting) ?? false;
    _themeMode   = _prefs.getString(_kThemeMode) ?? 'system';
    notifyListeners();
  }

  Future<void> setApiUrl(String v) async {
    _apiUrl = v.trim();
    await _prefs.setString(_kApiUrl, _apiUrl);
    notifyListeners();
  }

  Future<void> toggleLang(String code) async {
    _langs = {..._langs};
    if (_langs.contains(code)) {
      _langs.remove(code);
    } else {
      _langs.add(code);
    }
    if (_langs.isEmpty) _langs.add('es');
    await _prefs.setStringList(_kLangs, _langs.toList());
    notifyListeners();
  }

  Future<void> setHandwriting(bool v) async {
    _handwriting = v;
    await _prefs.setBool(_kHandwriting, v);
    notifyListeners();
  }

  Future<void> setThemeMode(String mode) async {
    _themeMode = mode;
    await _prefs.setString(_kThemeMode, mode);
    notifyListeners();
  }
}
