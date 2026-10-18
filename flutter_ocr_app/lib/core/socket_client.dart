import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/ocr_result.dart';

enum SocketStatus { disconnected, connecting, connected, reconnecting }

class SocketRequestException implements Exception {
  final String code;
  final String message;
  SocketRequestException(this.code, this.message);
  @override
  String toString() => '$code: $message';
}

class SocketLogEntry {
  final DateTime at;
  final String direction;
  final String text;
  SocketLogEntry(this.direction, this.text) : at = DateTime.now();
}

class RemoteClient {
  final String clientId;
  final String device;
  const RemoteClient(this.clientId, this.device);
}

class LiveEvent {
  final OcrResult result;
  final String? originClientId;
  final String via;
  final DateTime receivedAt;
  LiveEvent(this.result, this.originClientId, this.via) : receivedAt = DateTime.now();
}

class _Pending {
  final Map<String, dynamic> payload;
  final Completer<OcrResult> completer = Completer<OcrResult>();
  final void Function(String stage)? onProgress;
  Timer? timeout;
  bool sent = false;
  bool acked = false;
  _Pending(this.payload, this.onProgress);
}

typedef ChannelFactory = WebSocketChannel Function(Uri uri);

String randomId([int bytes = 8]) {
  final r = Random.secure();
  return List.generate(bytes, (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
}

class OcrSocketClient extends ChangeNotifier {
  static const requestTimeout = Duration(minutes: 3);
  static const heartbeatEvery = Duration(seconds: 15);
  static const pongTimeout    = Duration(seconds: 10);
  static const maxBackoff     = Duration(seconds: 30);

  String _baseUrl;
  String clientId;
  String device;
  final ChannelFactory _factory;

  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  Timer? _heartbeat;
  Timer? _pongTimer;
  Timer? _reconnectTimer;
  bool _wantConnected = false;
  bool _disposed = false;
  int _attempt = 0;

  SocketStatus status = SocketStatus.disconnected;
  String? sessionId;
  String? lastError;
  int clientsOnline = 0;
  List<RemoteClient> clients = const [];
  int? rttMs;
  int reconnects = 0;
  Duration? nextRetryIn;

  final List<SocketLogEntry> log = [];
  final List<LiveEvent> events = [];
  final Map<String, _Pending> _pending = {};
  final _messages = StreamController<Map<String, dynamic>>.broadcast();

  OcrSocketClient({
    required String baseUrl,
    required this.clientId,
    required this.device,
    ChannelFactory? factory,
  })  : _baseUrl = baseUrl,
        _factory = factory ??
            ((uri) => IOWebSocketChannel.connect(
                  uri,
                  pingInterval: const Duration(seconds: 20),
                  connectTimeout: const Duration(seconds: 8),
                ));

  Stream<Map<String, dynamic>> get messages => _messages.stream;
  int get pendingCount => _pending.length;
  bool get isConnected => status == SocketStatus.connected;
  String get baseUrl => _baseUrl;

  Uri get wsUri {
    final http = Uri.parse(_baseUrl.trim());
    return http.replace(
      scheme: http.scheme == 'https' ? 'wss' : 'ws',
      path: '${http.path.endsWith('/') ? http.path.substring(0, http.path.length - 1) : http.path}/ws/ocr',
      queryParameters: {'client_id': clientId, 'device': device},
    );
  }

  void updateConfig({String? baseUrl, String? device}) {
    final changed = (baseUrl != null && baseUrl != _baseUrl) || (device != null && device != this.device);
    if (baseUrl != null) _baseUrl = baseUrl;
    if (device != null) this.device = device;
    if (changed && _wantConnected) {
      _log('•', 'Configuración cambiada, reconectando');
      _closeChannel();
      _connectNow();
    }
  }

  void connect() {
    _wantConnected = true;
    _attempt = 0;
    _reconnectTimer?.cancel();
    if (_channel == null) _connectNow();
  }

  void disconnect() {
    _wantConnected = false;
    _reconnectTimer?.cancel();
    nextRetryIn = null;
    _closeChannel();
    _setStatus(SocketStatus.disconnected);
    _log('•', 'Desconectado manualmente');
  }

  void simulateNetworkDrop() {
    _log('•', 'Simulando caída de red');
    _closeChannel();
    _scheduleReconnect();
  }

  Future<OcrResult> submit({
    required File file,
    required Set<String> langs,
    required bool handwriting,
    int? docTypeId,
    void Function(String stage)? onProgress,
  }) async {
    final bytes = await file.readAsBytes();
    final requestId = randomId();
    final p = _Pending({
      'type': 'ocr_request',
      'request_id': requestId,
      'filename': file.uri.pathSegments.last,
      'lang': langs.join(','),
      'mode': handwriting ? 'handwriting' : '',
      'doc_type_id': docTypeId,
      'image_b64': base64Encode(bytes),
    }, onProgress);
    _pending[requestId] = p;
    p.timeout = Timer(requestTimeout, () {
      _fail(requestId, SocketRequestException('TIMEOUT', 'Sin respuesta del servidor en ${requestTimeout.inMinutes} min'));
    });
    if (!_wantConnected) connect();
    if (isConnected) {
      _sendRequest(p);
    } else {
      onProgress?.call('waiting_connection');
      _log('•', 'Solicitud $requestId en espera de conexión');
    }
    notifyListeners();
    return p.completer.future;
  }

  void _sendRequest(_Pending p) {
    p.sent = true;
    _send(p.payload, summary: 'ocr_request ${p.payload['request_id']} (${(p.payload['image_b64'] as String).length ~/ 1024} KB)');
    p.onProgress?.call('sent');
  }

  void _connectNow() {
    if (_disposed) return;
    final uri = wsUri;
    _setStatus(_attempt == 0 ? SocketStatus.connecting : SocketStatus.reconnecting);
    _log('•', 'Conectando a $uri');
    final WebSocketChannel ch;
    try {
      ch = _factory(uri);
    } catch (e) {
      _onClosed('Error al conectar: $e');
      return;
    }
    _channel = ch;
    _sub = ch.stream.listen(
      (data) => _onData(data),
      onError: (Object e) {
        if (identical(_channel, ch)) _onClosed('Error de socket: $e');
      },
      onDone: () {
        if (identical(_channel, ch)) {
          _onClosed('Conexión cerrada (código ${ch.closeCode ?? '-'})', closeCode: ch.closeCode);
        }
      },
      cancelOnError: true,
    );
    ch.ready.catchError((Object e) {
      if (identical(_channel, ch)) _onClosed('No se pudo conectar: $e');
    });
  }

  void _onData(dynamic data) {
    final Map<String, dynamic> msg;
    try {
      msg = json.decode(data as String) as Map<String, dynamic>;
    } catch (_) {
      _log('←', 'Mensaje inválido');
      return;
    }
    _messages.add(msg);
    final type = msg['type'] as String?;
    final rid = msg['request_id'] as String?;
    if (type != 'pong') _log('←', _summarize(msg));

    switch (type) {
      case 'welcome':
        sessionId = msg['session_id'] as String?;
        clientsOnline = (msg['clients_online'] as num?)?.toInt() ?? clientsOnline;
        if (_attempt > 0) reconnects++;
        _attempt = 0;
        lastError = null;
        nextRetryIn = null;
        _setStatus(SocketStatus.connected);
        _startHeartbeat();
        _flushPending();
      case 'pong':
        _pongTimer?.cancel();
        final ts = msg['ts'];
        if (ts is int) rttMs = DateTime.now().millisecondsSinceEpoch - ts;
        notifyListeners();
      case 'presence':
        clientsOnline = (msg['clients_online'] as num?)?.toInt() ?? 0;
        clients = [
          for (final c in (msg['clients'] as List? ?? const []))
            RemoteClient('${(c as Map)['client_id']}', '${c['device']}'),
        ];
        notifyListeners();
      case 'ack':
        final p = _pending[rid];
        if (p != null) {
          p.acked = true;
          p.onProgress?.call((msg['status'] as String?) ?? 'queued');
        }
      case 'progress':
        _pending[rid]?.onProgress?.call((msg['stage'] as String?) ?? '');
      case 'result':
        final p = _pending.remove(rid);
        if (p != null) {
          p.timeout?.cancel();
          if (!p.completer.isCompleted) {
            p.completer.complete(OcrResult.fromJson(msg['result'] as Map<String, dynamic>));
          }
          notifyListeners();
        }
      case 'event':
        if (msg['event'] == 'result_created' && msg['result'] is Map) {
          events.insert(0, LiveEvent(
            OcrResult.fromJson(msg['result'] as Map<String, dynamic>),
            msg['origin_client_id'] as String?,
            (msg['via'] as String?) ?? 'websocket',
          ));
          if (events.length > 50) events.removeLast();
          notifyListeners();
        }
      case 'error':
        final code = (msg['code'] as String?) ?? 'ERROR';
        final text = (msg['message'] as String?) ?? '';
        if (rid != null && _pending.containsKey(rid)) {
          if (code == 'NOT_FOUND') {
            _log('•', 'El servidor no conoce $rid, reenviando');
            _sendRequest(_pending[rid]!);
          } else if (code == 'BUSY') {
            final p = _pending[rid]!;
            final wait = (msg['retry_after_seconds'] as num?)?.toInt() ?? 5;
            p.onProgress?.call('busy');
            Timer(Duration(seconds: wait), () {
              if (_pending.containsKey(rid) && isConnected) _sendRequest(p);
            });
          } else {
            _fail(rid, SocketRequestException(code, text));
          }
        } else {
          lastError = '$code: $text';
          notifyListeners();
        }
    }
  }

  void _flushPending() {
    final acked = <String>[];
    for (final e in _pending.entries) {
      if (e.value.acked) {
        acked.add(e.key);
      } else {
        _sendRequest(e.value);
      }
    }
    if (acked.isNotEmpty) {
      _send({'type': 'resume', 'request_ids': acked}, summary: 'resume ${acked.length} solicitud(es)');
    }
  }

  void _fail(String rid, Object error) {
    final p = _pending.remove(rid);
    if (p == null) return;
    p.timeout?.cancel();
    if (!p.completer.isCompleted) p.completer.completeError(error);
    notifyListeners();
  }

  void _startHeartbeat() {
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(heartbeatEvery, (_) {
      if (!isConnected) return;
      _send({'type': 'ping', 'ts': DateTime.now().millisecondsSinceEpoch}, quiet: true);
      _pongTimer?.cancel();
      _pongTimer = Timer(pongTimeout, () {
        _log('•', 'Sin pong en ${pongTimeout.inSeconds}s, la conexión se considera caída');
        _closeChannel();
        _scheduleReconnect();
      });
    });
  }

  void _send(Map<String, dynamic> msg, {String? summary, bool quiet = false}) {
    final ch = _channel;
    if (ch == null) return;
    try {
      ch.sink.add(json.encode(msg));
      if (!quiet) _log('→', summary ?? _summarize(msg));
    } catch (e) {
      _log('•', 'Error al enviar: $e');
    }
  }

  void _onClosed(String reason, {int? closeCode}) {
    _log('•', reason);
    lastError = reason;
    _closeChannel();
    if (closeCode == 4001) {
      _wantConnected = false;
      lastError = 'Otra sesión con el mismo identificador tomó la conexión';
      _setStatus(SocketStatus.disconnected);
      return;
    }
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (!_wantConnected || _disposed) {
      _setStatus(SocketStatus.disconnected);
      return;
    }
    _reconnectTimer?.cancel();
    final secs = min(maxBackoff.inSeconds, pow(2, min(_attempt, 5)).toInt());
    _attempt++;
    nextRetryIn = Duration(seconds: secs);
    _setStatus(SocketStatus.reconnecting);
    _log('•', 'Reintentando en ${secs}s (intento $_attempt)');
    for (final p in _pending.values) {
      p.onProgress?.call('waiting_connection');
    }
    _reconnectTimer = Timer(nextRetryIn!, () {
      nextRetryIn = null;
      _connectNow();
    });
  }

  void _closeChannel() {
    _heartbeat?.cancel();
    _pongTimer?.cancel();
    _sub?.cancel();
    _sub = null;
    final ch = _channel;
    _channel = null;
    sessionId = null;
    if (ch != null) {
      try {
        ch.sink.close(1000);
      } catch (_) {}
    }
  }

  void _setStatus(SocketStatus s) {
    status = s;
    if (!_disposed) notifyListeners();
  }

  void _log(String dir, String text) {
    log.insert(0, SocketLogEntry(dir, text));
    if (log.length > 150) log.removeLast();
    if (!_disposed) notifyListeners();
  }

  String _summarize(Map<String, dynamic> m) {
    final type = m['type'];
    final rid = m['request_id'];
    return switch (type) {
      'welcome'  => 'welcome sesión ${m['session_id']} · ${m['clients_online']} en línea',
      'presence' => 'presence ${m['clients_online']} en línea',
      'ack'      => 'ack $rid · ${m['status']} · cola ${m['queue_position']}',
      'progress' => 'progress $rid · ${m['stage']}',
      'result'   => 'result $rid · #${(m['result'] as Map?)?['id']}${m['recovered'] == true ? ' (recuperado)' : ''}',
      'event'    => 'event ${m['event']} de ${m['origin_client_id'] ?? 'REST'}',
      'error'    => 'error ${m['code']}${rid != null ? ' $rid' : ''}: ${m['message']}',
      _          => '$type',
    };
  }

  @override
  void dispose() {
    _disposed = true;
    _wantConnected = false;
    _reconnectTimer?.cancel();
    _closeChannel();
    for (final rid in _pending.keys.toList()) {
      _fail(rid, SocketRequestException('CLOSED', 'Cliente cerrado'));
    }
    _messages.close();
    super.dispose();
  }
}
