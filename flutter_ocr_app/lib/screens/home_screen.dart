import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/settings.dart';
import 'benchmark_screen.dart';
import 'capture_screen.dart';
import 'history_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  final AppSettings settings;
  const HomeScreen({super.key, required this.settings});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;
  late ApiClient _api;

  @override
  void initState() {
    super.initState();
    _api = ApiClient(widget.settings.apiUrl);
    widget.settings.addListener(_onSettings);
  }

  void _onSettings() {
    if (_api.baseUrl != widget.settings.apiUrl) {
      setState(() => _api.baseUrl = widget.settings.apiUrl);
    }
  }

  @override
  void dispose() {
    widget.settings.removeListener(_onSettings);
    _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      CaptureScreen(api: _api, settings: widget.settings),
      HistoryScreen(api: _api),
      BenchmarkScreen(api: _api),
      SettingsScreen(settings: widget.settings, api: _api),
    ];

    return Scaffold(
      body: IndexedStack(index: _index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.document_scanner_outlined),
            selectedIcon: Icon(Icons.document_scanner),
            label: 'Capturar',
          ),
          NavigationDestination(
            icon: Icon(Icons.history_outlined),
            selectedIcon: Icon(Icons.history),
            label: 'Historial',
          ),
          NavigationDestination(
            icon: Icon(Icons.analytics_outlined),
            selectedIcon: Icon(Icons.analytics),
            label: 'Comparar',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Ajustes',
          ),
        ],
      ),
    );
  }
}
