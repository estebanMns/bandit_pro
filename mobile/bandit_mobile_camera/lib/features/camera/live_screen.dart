import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../../services/bandit_api.dart';
import '../../services/device_socket.dart';
import '../../services/models.dart';
import '../../services/whip_publisher.dart';

const _maxReconnects = 3;

/// Transmisión activa: vista previa, indicadores de cámara y micrófono, y botón para detener.
class LiveScreen extends StatefulWidget {
  const LiveScreen({
    super.key,
    required this.api,
    required this.socket,
    required this.sessionId,
    required this.accepted,
    required this.expiresAt,
  });

  final BanditApi api;
  final DeviceSocket socket;
  final String sessionId;
  final AcceptedSession accepted;
  final DateTime expiresAt;

  @override
  State<LiveScreen> createState() => _LiveScreenState();
}

class _LiveScreenState extends State<LiveScreen> with WidgetsBindingObserver {
  final _publisher = WhipPublisher();
  final _preview = RTCVideoRenderer();
  StreamSubscription<PublishState>? _states;
  StreamSubscription<Map<String, dynamic>>? _messages;
  Timer? _limit;
  PublishState _state = PublishState.idle;
  bool _microphoneOn = false;
  bool _finished = false;
  int _reconnects = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _messages = widget.socket.messages.listen((message) {
      if (message['type'] == 'mobile_camera.session_ended' &&
          message['session_id'] == widget.sessionId) {
        _finish(reason: 'La sesión terminó desde Bandit.', notifyServer: false);
      } else if (message['type'] == 'mobile_camera.device_revoked') {
        _finish(reason: 'El teléfono fue desvinculado.', notifyServer: false);
      }
    });
    final remaining = widget.expiresAt.difference(DateTime.now());
    _limit = Timer(remaining.isNegative ? Duration.zero : remaining, () {
      _finish(reason: 'Se alcanzó la duración máxima de la sesión.', notifyServer: false);
    });
    _start();
  }

  Future<void> _start() async {
    try {
      await _preview.initialize();
      WakelockPlus.enable();
      final stream = await _publisher.startCapture(audio: widget.accepted.audioEnabled);
      _preview.srcObject = stream;
      _microphoneOn = _publisher.hasAudio;
      _states = _publisher.states.listen(_onPublishState);
      if (mounted) setState(() {});
      await _publisher.publish(widget.accepted.publish);
    } catch (error) {
      await _fail('$error');
    }
  }

  Future<void> _onPublishState(PublishState state) async {
    if (!mounted || _finished) return;
    setState(() => _state = state);
    switch (state) {
      case PublishState.live:
        _reconnects = 0;
        await _report('live');
      case PublishState.reconnecting:
        await _report('reconnecting');
      case PublishState.failed:
        await _reconnect();
      default:
        break;
    }
  }

  Future<void> _report(String state) async {
    try {
      await widget.api.reportState(widget.sessionId, state);
    } catch (_) {
      // El servidor conoce el estado real por MediaMTX; el aviso es informativo.
    }
  }

  /// Reconecta con un ticket nuevo, sin volver a pedir permiso, mientras la sesión siga abierta.
  Future<void> _reconnect() async {
    if (_finished) return;
    if (_reconnects >= _maxReconnects) {
      await _fail('No se pudo mantener la conexión de video.');
      return;
    }
    _reconnects++;
    await _report('reconnecting');
    await Future<void>.delayed(Duration(seconds: 2 * _reconnects));
    try {
      final grant = await widget.api.renewPublish(widget.sessionId);
      await _publisher.publish(grant);
    } on BanditApiException catch (error) {
      await _finish(reason: error.message, notifyServer: false);
    } catch (_) {
      await _reconnect();
    }
  }

  Future<void> _fail(String message) async {
    await _report('failed');
    await _finish(reason: message, notifyServer: false);
  }

  /// Apaga cámara, micrófono y conexión. Nunca se reactivan solos.
  Future<void> _finish({required String reason, required bool notifyServer}) async {
    if (_finished) return;
    _finished = true;
    _limit?.cancel();
    if (mounted) setState(() => _error = reason);
    await _publisher.stop();
    _preview.srcObject = null;
    WakelockPlus.disable();
    if (notifyServer) {
      try {
        await widget.api.stop(widget.sessionId);
      } catch (_) {
        // La sesión vence sola en el servidor si el aviso no llega.
      }
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(reason)));
      Navigator.of(context).pop();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // En segundo plano el sistema puede cortar la cámara: se detiene de forma explícita y no
    // se reanuda sin una nueva autorización.
    if (state == AppLifecycleState.paused || state == AppLifecycleState.detached) {
      _finish(reason: 'La transmisión se detuvo al salir de la app.', notifyServer: true);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _limit?.cancel();
    _messages?.cancel();
    _states?.cancel();
    if (!_finished) {
      _finished = true;
      widget.api.stop(widget.sessionId).catchError((_) {});
    }
    _publisher.dispose();
    _preview.dispose();
    WakelockPlus.disable();
    super.dispose();
  }

  String get _stateLabel => switch (_state) {
        PublishState.idle || PublishState.capturing => 'Abriendo la cámara…',
        PublishState.connecting => 'Conectando con Bandit…',
        PublishState.live => 'Transmitiendo en vivo',
        PublishState.reconnecting => 'Reconectando…',
        PublishState.failed => 'Falló la conexión',
        PublishState.stopped => 'Detenida',
      };

  @override
  Widget build(BuildContext context) {
    final live = _state == PublishState.live;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _finish(reason: 'Transmisión detenida.', notifyServer: true);
      },
      child: Scaffold(
        backgroundColor: Colors.black,
        body: SafeArea(
          child: Stack(
            children: [
              Positioned.fill(
                child: RTCVideoView(
                  _preview,
                  objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitCover,
                ),
              ),
              Positioned(
                top: 12,
                left: 12,
                right: 12,
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _Indicator(
                      icon: Icons.videocam,
                      label: 'Cámara activa',
                      active: _state != PublishState.stopped,
                    ),
                    _Indicator(
                      icon: _microphoneOn ? Icons.mic : Icons.mic_off,
                      label: _microphoneOn ? 'Micrófono activo' : 'Micrófono apagado',
                      active: _microphoneOn,
                    ),
                    _Indicator(icon: Icons.circle, label: _stateLabel, active: live),
                  ],
                ),
              ),
              if (_error != null)
                Positioned(
                  left: 12,
                  right: 12,
                  bottom: 120,
                  child: Text(_error!, style: const TextStyle(color: Colors.white)),
                ),
              Positioned(
                left: 24,
                right: 24,
                bottom: 24,
                child: Row(
                  children: [
                    if (widget.accepted.audioEnabled)
                      IconButton.filledTonal(
                        tooltip: _microphoneOn ? 'Apagar micrófono' : 'Encender micrófono',
                        icon: Icon(_microphoneOn ? Icons.mic : Icons.mic_off),
                        onPressed: () {
                          setState(() => _microphoneOn = !_microphoneOn);
                          _publisher.setMicrophoneEnabled(_microphoneOn);
                        },
                      ),
                    const SizedBox(width: 8),
                    IconButton.filledTonal(
                      tooltip: 'Cambiar de cámara',
                      icon: const Icon(Icons.cameraswitch),
                      onPressed: () => _publisher.switchCamera(),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(
                          backgroundColor: Colors.redAccent,
                          minimumSize: const Size.fromHeight(56),
                        ),
                        onPressed: () =>
                            _finish(reason: 'Transmisión detenida.', notifyServer: true),
                        icon: const Icon(Icons.stop),
                        label: const Text('Detener'),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Indicator extends StatelessWidget {
  const _Indicator({required this.icon, required this.label, required this.active});

  final IconData icon;
  final String label;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: label,
      child: Chip(
        avatar: Icon(icon, size: 18, color: active ? Colors.redAccent : Colors.white70),
        label: Text(label),
        backgroundColor: Colors.black54,
      ),
    );
  }
}
