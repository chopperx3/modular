import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/api_client.dart';
import '../models/ocr_result.dart';
import '../widgets/status_chip.dart';
import 'result_detail_screen.dart';

class HistoryScreen extends StatefulWidget {
  final ApiClient api;
  const HistoryScreen({super.key, required this.api});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  late Future<List<OcrResult>> _future;
  final _dateFmt = DateFormat('dd MMM yyyy, HH:mm');
  String _filter = '';

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  void _refresh() {
    setState(() {
      _future = widget.api.listResults(limit: 100);
    });
  }

  Future<void> _delete(int id) async {
    try {
      await widget.api.deleteResult(id);
      _refresh();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error al borrar: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Historial'),
        actions: [
          IconButton(
            onPressed: _refresh,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refrescar',
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: TextField(
              decoration: const InputDecoration(
                hintText: 'Buscar por nombre o texto…',
                prefixIcon: Icon(Icons.search),
              ),
              onChanged: (v) => setState(() => _filter = v.toLowerCase()),
            ),
          ),
          Expanded(
            child: FutureBuilder<List<OcrResult>>(
              future: _future,
              builder: (ctx, snap) {
                if (snap.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snap.hasError) {
                  return _ErrorView(error: snap.error, onRetry: _refresh);
                }
                final all = snap.data ?? const <OcrResult>[];
                final list = _filter.isEmpty
                    ? all
                    : all.where((r) =>
                        r.filename.toLowerCase().contains(_filter) ||
                        r.text.toLowerCase().contains(_filter)).toList();

                if (list.isEmpty) {
                  return _EmptyView(filtered: _filter.isNotEmpty);
                }
                return RefreshIndicator(
                  onRefresh: () async => _refresh(),
                  child: ListView.separated(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                    itemCount: list.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (_, i) {
                      final r = list[i];
                      return _ResultTile(
                        result: r,
                        dateLabel: _dateFmt.format(r.createdAt.toLocal()),
                        onTap: () {
                          Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) => ResultDetailScreen(api: widget.api, result: r),
                          ));
                        },
                        onDelete: () => _delete(r.id),
                      );
                    },
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _ResultTile extends StatelessWidget {
  final OcrResult result;
  final String dateLabel;
  final VoidCallback onTap;
  final VoidCallback onDelete;
  const _ResultTile({
    required this.result,
    required this.dateLabel,
    required this.onTap,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final preview = result.text.trim().replaceAll('\n', ' ');
    final scheme  = Theme.of(context).colorScheme;
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.description_outlined, size: 18, color: scheme.primary),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      result.filename,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (result.hasError)
                    StatusChip.error('Error')
                  else if (result.isProcessed)
                    StatusChip.ok('OK')
                  else
                    StatusChip.warn(result.estatus),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                preview.isEmpty ? '(sin texto)' : preview,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: scheme.onSurfaceVariant),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.schedule, size: 14, color: scheme.onSurfaceVariant),
                  const SizedBox(width: 4),
                  Text(dateLabel, style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
                  const Spacer(),
                  IconButton(
                    visualDensity: VisualDensity.compact,
                    onPressed: () async {
                      final ok = await showDialog<bool>(
                        context: context,
                        builder: (_) => AlertDialog(
                          title: const Text('¿Borrar resultado?'),
                          content: Text('Se eliminará "${result.filename}" del historial.'),
                          actions: [
                            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
                            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Borrar')),
                          ],
                        ),
                      );
                      if (ok == true) onDelete();
                    },
                    icon: Icon(Icons.delete_outline, color: scheme.error),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyView extends StatelessWidget {
  final bool filtered;
  const _EmptyView({required this.filtered});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(filtered ? Icons.search_off : Icons.inbox_outlined, size: 64, color: Theme.of(context).hintColor),
            const SizedBox(height: 12),
            Text(
              filtered ? 'Sin resultados para el filtro' : 'Aún no hay documentos procesados',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final Object? error;
  final VoidCallback onRetry;
  const _ErrorView({required this.error, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off, size: 56, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 12),
            const Text('No se pudo cargar el historial', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Text('$error', textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 16),
            FilledButton.tonalIcon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Reintentar')),
          ],
        ),
      ),
    );
  }
}
