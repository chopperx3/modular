import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'socket_client.dart';

class AppSettings extends ChangeNotifier {
  static const _kApiUrl       = 'api_url';
  static const _kLangs        = 'langs';
  static const _kHandwriting  = 'handwriting';
  static const _kThemeMode    = 'theme_mode';
  static const _kClientId     = 'client_id';
  static const _kDeviceName   = 'device_name';
  static const _kUseSocket    = 'use_socket';

  static const _defaultApiUrl = 'http://10.0.2.2:8000';

  late SharedPreferences _prefs;

  String   _apiUrl      = _defaultApiUrl;
  Set<String> _langs    = {'es', 'en'};
  bool     _handwriting = false;
  String   _themeMode   = 'system';
  String   _clientId    = '';
  String   _deviceName  = '';
  bool     _useSocket   = true;

  String   get apiUrl      => _apiUrl;
  Set<String> get langs    => _langs;
  bool     get handwriting => _handwriting;
  String   get themeMode   => _themeMode;
  String   get clientId    => _clientId;
  String   get deviceName  => _deviceName;
  bool     get useSocket   => _useSocket;

  Future<void> load() async {
    _prefs       = await SharedPreferences.getInstance();
    _apiUrl      = _prefs.getString(_kApiUrl) ?? _defaultApiUrl;
    _langs       = (_prefs.getStringList(_kLangs) ?? ['es', 'en']).toSet();
    _handwriting = _prefs.getBool(_kHandwriting) ?? false;
    _themeMode   = _prefs.getString(_kThemeMode) ?? 'system';
    _useSocket   = _prefs.getBool(_kUseSocket) ?? true;
    _clientId    = _prefs.getString(_kClientId) ?? '';
    if (_clientId.isEmpty) {
      _clientId = 'app-${randomId(6)}';
      await _prefs.setString(_kClientId, _clientId);
    }
    _deviceName  = _prefs.getString(_kDeviceName) ?? '${Platform.operatingSystem}-${_clientId.substring(4, 8)}';
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

  Future<void> setUseSocket(bool v) async {
    _useSocket = v;
    await _prefs.setBool(_kUseSocket, v);
    notifyListeners();
  }

  Future<void> setDeviceName(String v) async {
    final name = v.trim();
    if (name.isEmpty) return;
    _deviceName = name.length > 64 ? name.substring(0, 64) : name;
    await _prefs.setString(_kDeviceName, _deviceName);
    notifyListeners();
  }

  Future<void> setThemeMode(String mode) async {
    _themeMode = mode;
    await _prefs.setString(_kThemeMode, mode);
    notifyListeners();
  }
}
