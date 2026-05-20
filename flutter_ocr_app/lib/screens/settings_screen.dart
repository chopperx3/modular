import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/settings.dart';

class SettingsScreen extends StatefulWidget {
  final AppSettings settings;
  final ApiClient api;
  const SettingsScreen({super.key, required this.settings, required this.api});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _apiCtrl;
  bool _checking = false;
  String? _healthMsg;
  Color? _healthColor;

  @override
  void initState() {
    super.initState();
    _apiCtrl = TextEditingController(text: widget.settings.apiUrl);
  }

  @override
  void dispose() {
    _apiCtrl.dispose();
    super.dispose();
  }

  Future<void> _testConnection() async {
    setState(() {
      _checking = true;
      _healthMsg = null;
    });
    try {
      await widget.settings.setApiUrl(_apiCtrl.text);
      final h = await widget.api.health();
      if (!mounted) return;
      final engines = (h['engines'] as Map?) ?? {};
      final ok = engines.values.any((v) => v == true);
      setState(() {
        _healthMsg = ok
            ? 'API conectada · EasyOCR: ${engines['easyocr']} · Tesseract: ${engines['tesseract']} · Groq: ${engines['groq_vision']}'
            : 'API responde pero ningún motor disponible';
        _healthColor = ok ? Colors.green : Colors.orange;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _healthMsg = 'Falló: $e';
        _healthColor = Colors.red;
      });
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Ajustes')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Conexión al backend', style: Theme.of(context).textTheme.titleSmall),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _apiCtrl,
                      decoration: const InputDecoration(
                        labelText: 'URL del API',
                        hintText: 'http://10.0.2.2:8000',
                        prefixIcon: Icon(Icons.dns_outlined),
                        helperText: 'Emulador Android: 10.0.2.2 · Dispositivo físico: IP de tu PC',
                      ),
                    ),
                    const SizedBox(height: 10),
                    FilledButton.tonalIcon(
                      onPressed: _checking ? null : _testConnection,
                      icon: _checking
                          ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.cable),
                      label: Text(_checking ? 'Verificando…' : 'Probar conexión'),
                    ),
                    if (_healthMsg != null) ...[
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: (_healthColor ?? scheme.primary).withValues(alpha: .12),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: (_healthColor ?? scheme.primary).withValues(alpha: .35)),
                        ),
                        child: Text(_healthMsg!, style: TextStyle(color: _healthColor)),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Preferencias OCR', style: Theme.of(context).textTheme.titleSmall),
                    const SizedBox(height: 4),
                    AnimatedBuilder(
                      animation: widget.settings,
                      builder: (_, __) => Column(
                        children: [
                          SwitchListTile(
                            contentPadding: EdgeInsets.zero,
                            title: const Text('Modo manuscrita por defecto'),
                            subtitle: const Text('Activa el motor IA de visión'),
                            value: widget.settings.handwriting,
                            onChanged: (v) => widget.settings.setHandwriting(v),
                          ),
                          const Divider(height: 0),
                          Padding(
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            child: Row(
                              children: [
                                const Text('Idiomas:'),
                                const SizedBox(width: 12),
                                Wrap(
                                  spacing: 8,
                                  children: [
                                    for (final code in const ['es', 'en'])
                                      FilterChip(
                                        label: Text(code.toUpperCase()),
                                        selected: widget.settings.langs.contains(code),
                                        onSelected: (_) => widget.settings.toggleLang(code),
                                      ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Apariencia', style: Theme.of(context).textTheme.titleSmall),
                    const SizedBox(height: 8),
                    AnimatedBuilder(
                      animation: widget.settings,
                      builder: (_, __) => SegmentedButton<String>(
                        segments: const [
                          ButtonSegment(value: 'system', label: Text('Sistema'), icon: Icon(Icons.brightness_auto)),
                          ButtonSegment(value: 'light',  label: Text('Claro'),   icon: Icon(Icons.light_mode)),
                          ButtonSegment(value: 'dark',   label: Text('Oscuro'),  icon: Icon(Icons.dark_mode)),
                        ],
                        selected: {widget.settings.themeMode},
                        onSelectionChanged: (s) => widget.settings.setThemeMode(s.first),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Acerca de', style: Theme.of(context).textTheme.titleSmall),
                    const SizedBox(height: 6),
                    const Text('MODULAR OCR v2.0.0'),
                    const SizedBox(height: 4),
                    Text(
                      'Sistema OCR inteligente para digitalización de documentos manuscritos. '
                      'Combina EasyOCR + Llama 4 Scout Vision y se compara cuantitativamente contra Tesseract.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
