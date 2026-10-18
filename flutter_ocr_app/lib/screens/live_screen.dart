import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/api_client.dart';
import '../core/settings.dart';
import '../core/socket_client.dart';
import '../widgets/status_chip.dart';
import 'result_detail_screen.dart';

class LiveScreen extends StatelessWidget {
  final ApiClient api;
  final OcrSocketClient socket;
  final AppSettings settings;
  const LiveScreen({super.key, required this.api, required this.socket, required this.settings});

  static final _timeFmt = DateFormat('HH:mm:ss');

  StatusChip _chip(SocketStatus s) => switch (s) {
        SocketStatus.connected    => StatusChip.ok('Conectado'),
        SocketStatus.connecting   => StatusChip.neutral('Conectando'),
        SocketStatus.reconnecting => StatusChip.warn('Reconectando'),
        SocketStatus.disconnected => StatusChip.error('Desconectado'),
      };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('En vivo')),
      body: AnimatedBuilder(
        animation: socket,
        builder: (context, _) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(child: Text('Canal WebSocket', style: theme.textTheme.titleSmall)),
                        _chip(socket.status),
                      ],
                    ),
                    const SizedBox(height: 10),
                    _kv(context, 'Servidor', socket.wsUri.toString()),
                    _kv(context, 'Este dispositivo', '${socket.device} · ${socket.clientId}'),
                    _kv(context, 'Sesión', socket.sessionId ?? '—'),
                    _kv(context, 'Latencia (ping)', socket.rttMs == null ? '—' : '${socket.rttMs} ms'),
                    _kv(context, 'Reconexiones', '${socket.reconnects}'),
                    _kv(context, 'Solicitudes pendientes', '${socket.pendingCount}'),
                    if (socket.nextRetryIn != null)
                      _kv(context, 'Próximo intento', 'en ${socket.nextRetryIn!.inSeconds} s'),
                    if (socket.lastError != null && socket.status != SocketStatus.connected)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(socket.lastError!, style: TextStyle(color: theme.colorScheme.error, fontSize: 12)),
                      ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        if (socket.status == SocketStatus.disconnected)
                          FilledButton.tonalIcon(
                            onPressed: () {
                              settings.setUseSocket(true);
                              socket.connect();
                            },
                            icon: const Icon(Icons.link),
                            label: const Text('Conectar'),
                          )
                        else
                          FilledButton.tonalIcon(
                            onPressed: socket.disconnect,
                            icon: const Icon(Icons.link_off),
                            label: const Text('Desconectar'),
                          ),
                        OutlinedButton.icon(
                          onPressed: socket.isConnected ? socket.simulateNetworkDrop : null,
                          icon: const Icon(Icons.wifi_off),
                          label: const Text('Simular caída'),
                        ),
                      ],
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
                    Text('Dispositivos en línea (${socket.clientsOnline})', style: theme.textTheme.titleSmall),
                    const SizedBox(height: 6),
                    if (socket.clients.isEmpty)
                      Text('Sin datos', style: theme.textTheme.bodySmall)
                    else
                      for (final c in socket.clients)
                        ListTile(
                          dense: true,
                          contentPadding: EdgeInsets.zero,
                          leading: Icon(c.clientId == socket.clientId ? Icons.smartphone : Icons.devices_other),
                          title: Text(c.device),
                          subtitle: Text(c.clientId),
                          trailing: c.clientId == socket.clientId ? const Text('tú') : null,
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
                    Text('Resultados de otros dispositivos', style: theme.textTheme.titleSmall),
                    const SizedBox(height: 6),
                    if (socket.events.isEmpty)
                      Text('Aún no llegan resultados', style: theme.textTheme.bodySmall)
                    else
                      for (final e in socket.events.take(20))
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const Icon(Icons.description_outlined),
                          title: Text('#${e.result.id} · ${e.result.filename}', maxLines: 1, overflow: TextOverflow.ellipsis),
                          subtitle: Text(
                            '${_timeFmt.format(e.receivedAt)} · ${e.originClientId ?? 'HTTP'} · '
                            '${e.result.text.replaceAll('\n', ' ')}',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          onTap: () => Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) => ResultDetailScreen(api: api, result: e.result),
                          )),
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
                    Text('Bitácora del protocolo', style: theme.textTheme.titleSmall),
                    const SizedBox(height: 6),
                    for (final l in socket.log.take(40))
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Text(
                          '${_timeFmt.format(l.at)} ${l.direction} ${l.text}',
                          style: const TextStyle(fontFamily: 'monospace', fontSize: 11),
                        ),
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

  Widget _kv(BuildContext context, String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 150, child: Text(k, style: Theme.of(context).textTheme.bodySmall)),
            Expanded(child: Text(v, style: const TextStyle(fontSize: 13))),
          ],
        ),
      );
}
