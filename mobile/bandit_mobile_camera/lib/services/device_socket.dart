import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:web_socket_channel/io.dart';

import 'models.dart';

/// WebSocket del teléfono con Bandit: solo eventos y señalización, nunca audio ni video.
///
/// Reconecta con espera creciente y envía un latido cada 25 s. Si el servidor responde que la
/// credencial no vale (teléfono desvinculado), deja de reconectar y avisa con [revoked].
class DeviceSocket {
  DeviceSocket(this.credentials, {required this.stillValid});

  final DeviceCredentials credentials;

  /// Si el servidor rechaza el WebSocket antes de aceptarlo, no llega un código de cierre:
  /// tras varios fallos se pregunta por HTTP si el token sigue siendo válido.
  final Future<bool> Function() stillValid;

  final _messages = StreamController<Map<String, dynamic>>.broadcast();
  final _connected = StreamController<bool>.broadcast();
  IOWebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _heartbeat;
  Timer? _retry;
  int _attempt = 0;
  bool _closed = false;
  bool revoked = false;

  Stream<Map<String, dynamic>> get messages => _messages.stream;
  Stream<bool> get connection => _connected.stream;

  void connect() {
    if (_closed) return;
    _retry?.cancel();
    final channel = IOWebSocketChannel.connect(
      credentials.websocketUrl(),
      headers: {HttpHeaders.authorizationHeader: 'Bearer ${credentials.token}'},
      pingInterval: const Duration(seconds: 20),
    );
    _channel = channel;
    _subscription = channel.stream.listen(
      _onData,
      onDone: () => _onClosed(channel.closeCode),
      onError: (Object _) => _onClosed(null),
      cancelOnError: true,
    );
    _heartbeat?.cancel();
    _heartbeat = Timer.periodic(const Duration(seconds: 25), (_) {
      _channel?.sink.add(jsonEncode({'type': 'ping'}));
    });
  }

  void _onData(dynamic data) {
    if (data is! String) return;
    final Object? message;
    try {
      message = jsonDecode(data);
    } on FormatException {
      return;
    }
    if (message is! Map<String, dynamic>) return;
    if (message['type'] == 'hello') {
      _attempt = 0;
      _connected.add(true);
    }
    if (message['type'] == 'mobile_camera.device_revoked') {
      revoked = true;
    }
    _messages.add(message);
  }

  Future<void> _onClosed(int? code) async {
    _heartbeat?.cancel();
    if (_closed) return;
    _connected.add(false);
    if (code == null && _attempt >= 2 && !revoked) {
      if (!await stillValid()) code = 1008;
    }
    // 1008: el servidor rechazó la credencial. No tiene sentido insistir.
    if (_closed || revoked || code == 1008) {
      if (code == 1008) {
        revoked = true;
        _messages.add({'type': 'mobile_camera.device_revoked'});
      }
      return;
    }
    final seconds = min(60, pow(2, _attempt).toInt());
    _attempt++;
    _retry = Timer(Duration(seconds: seconds), connect);
  }

  Future<void> close() async {
    _closed = true;
    _retry?.cancel();
    _heartbeat?.cancel();
    await _subscription?.cancel();
    await _channel?.sink.close();
    await _messages.close();
    await _connected.close();
  }
}
