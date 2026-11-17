import 'dart:async';

import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../services/bandit_api.dart';
import '../../services/device_socket.dart';
import '../../services/models.dart';
import '../camera/live_screen.dart';

/// Solicitud visible: quién pide la sesión, qué permisos necesita y cuánto tiempo queda.
class IncomingRequestScreen extends StatefulWidget {
  const IncomingRequestScreen({
    super.key,
    required this.api,
    required this.socket,
    required this.request,
  });

  final BanditApi api;
  final DeviceSocket socket;
  final SessionRequest request;

  @override
  State<IncomingRequestScreen> createState() => _IncomingRequestScreenState();
}

class _IncomingRequestScreenState extends State<IncomingRequestScreen> {
  late bool _audio = widget.request.audioRequested;
  Timer? _countdown;
  StreamSubscription<Map<String, dynamic>>? _messages;
  int _secondsLeft = 0;
  bool _working = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _secondsLeft = _remaining();
    _countdown = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
    // Si la sesión vence o el dashboard la cancela, la solicitud desaparece.
    _messages = widget.socket.messages.listen((message) {
      if (message['type'] == 'mobile_camera.session_ended' &&
          message['session_id'] == widget.request.sessionId &&
          mounted &&
          !_working) {
        Navigator.of(context).pop();
      }
    });
  }

  @override
  void dispose() {
    _countdown?.cancel();
    _messages?.cancel();
    super.dispose();
  }

  int _remaining() {
    final left = widget.request.answerBy.difference(DateTime.now()).inSeconds;
    return left < 0 ? 0 : left;
  }

  void _tick() {
    if (!mounted) return;
    final left = _remaining();
    setState(() => _secondsLeft = left);
    if (left <= 0 && !_working) {
      _countdown?.cancel();
      Navigator.of(context).pop();
    }
  }

  Future<bool> _permissions() async {
    final camera = await Permission.camera.request();
    if (!camera.isGranted) {
      setState(() => _error = camera.isPermanentlyDenied
          ? 'Activa el permiso de cámara en los ajustes del sistema.'
          : 'Bandit necesita la cámara para transmitir.');
      if (camera.isPermanentlyDenied) await openAppSettings();
      return false;
    }
    if (_audio) {
      final microphone = await Permission.microphone.request();
      // Sin micrófono se transmite solo video: los permisos del sistema mandan.
      if (!microphone.isGranted) setState(() => _audio = false);
    }
    return true;
  }

  Future<void> _accept() async {
    setState(() {
      _working = true;
      _error = null;
    });
    try {
      if (!await _permissions()) return;
      final accepted = await widget.api.accept(widget.request.sessionId, audio: _audio);
      if (!mounted) return;
      await Navigator.of(context).pushReplacement(
        MaterialPageRoute<void>(
          builder: (_) => LiveScreen(
            api: widget.api,
            socket: widget.socket,
            sessionId: widget.request.sessionId,
            accepted: accepted,
            expiresAt: widget.request.expiresAt,
          ),
        ),
      );
    } on BanditApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'No hay conexión con Bandit.');
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _reject() async {
    setState(() => _working = true);
    try {
      await widget.api.reject(widget.request.sessionId);
    } catch (_) {
      // Si no llega, la solicitud vence sola en el servidor.
    }
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PopScope(
      canPop: !_working,
      child: Scaffold(
        appBar: AppBar(title: const Text('Solicitud de transmisión')),
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Icon(Icons.videocam, size: 64, color: theme.colorScheme.primary),
              const SizedBox(height: 16),
              Text(
                '${widget.request.requestedBy} quiere ver esta cámara en vivo.',
                style: theme.textTheme.titleLarge,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                'Permisos: cámara${widget.request.audioRequested ? ' y micrófono' : ''}. '
                'Nada se graba. Podrás detenerla cuando quieras.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                'Responde en $_secondsLeft s',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall,
              ),
              if (widget.request.audioRequested)
                SwitchListTile(
                  title: const Text('Compartir también el audio'),
                  value: _audio,
                  onChanged: _working ? null : (value) => setState(() => _audio = value),
                ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
                ),
              const Spacer(),
              FilledButton.icon(
                onPressed: _working ? null : _accept,
                icon: const Icon(Icons.check),
                label: const Text('Aceptar y transmitir'),
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _working ? null : _reject,
                icon: const Icon(Icons.close),
                label: const Text('Rechazar'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
