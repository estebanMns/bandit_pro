import 'dart:async';

import 'package:flutter/material.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../../services/bandit_api.dart';
import '../../services/device_socket.dart';
import '../../services/models.dart';
import '../settings/settings_screen.dart';
import 'incoming_request_screen.dart';

/// Estado del teléfono y disponibilidad para recibir solicitudes.
class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.credentials,
    required this.onUnpaired,
    required this.onTokenRotated,
  });

  final DeviceCredentials credentials;
  final Future<void> Function() onUnpaired;
  final Future<void> Function(String token) onTokenRotated;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  late final BanditApi _api;
  late final DeviceSocket _socket;
  StreamSubscription<Map<String, dynamic>>? _messages;
  StreamSubscription<bool>? _connection;
  DeviceInfo? _device;
  bool _connected = false;
  bool _keepAwake = false;
  bool _busy = false;
  String? _error;
  String? _activeRequest;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _api = BanditApi(widget.credentials.apiBaseUrl, token: widget.credentials.token);
    _socket = DeviceSocket(widget.credentials, stillValid: _tokenStillValid);
    _messages = _socket.messages.listen(_onMessage);
    _connection = _socket.connection.listen((value) {
      if (mounted) setState(() => _connected = value);
      if (value) _refresh();
    });
    _socket.connect();
    _refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _messages?.cancel();
    _connection?.cancel();
    _socket.close();
    _api.close();
    WakelockPlus.disable();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Al volver al frente se actualiza el estado: puede haber llegado una solicitud.
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<bool> _tokenStillValid() async {
    try {
      await _api.me();
      return true;
    } on BanditApiException catch (error) {
      return !error.isUnauthorized;
    } catch (_) {
      return true;
    }
  }

  Future<void> _refresh() async {
    try {
      final device = await _api.me();
      if (mounted) setState(() => _device = device);
    } on BanditApiException catch (error) {
      if (error.isUnauthorized) {
        await _revoked();
      } else if (mounted) {
        setState(() => _error = error.message);
      }
    } catch (_) {
      // Sin red: el WebSocket reintenta y vuelve a refrescar al conectar.
    }
  }

  Future<void> _revoked() async {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Este teléfono fue desvinculado de Bandit.')),
    );
    await widget.onUnpaired();
  }

  void _onMessage(Map<String, dynamic> message) {
    switch (message['type']) {
      case 'mobile_camera.session_requested':
        _showRequest(SessionRequest.fromMessage(message));
      case 'mobile_camera.availability_changed':
        _refresh();
      case 'mobile_camera.device_revoked':
        _revoked();
      default:
        break;
    }
  }

  Future<void> _showRequest(SessionRequest request) async {
    if (_activeRequest == request.sessionId || !mounted) return;
    _activeRequest = request.sessionId;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        fullscreenDialog: true,
        builder: (_) => IncomingRequestScreen(api: _api, socket: _socket, request: request),
      ),
    );
    _activeRequest = null;
    _refresh();
  }

  Future<void> _setAvailable(bool value) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final device = await _api.setAvailability(value);
      if (mounted) setState(() => _device = device);
    } on BanditApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'No hay conexión con Bandit.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _setKeepAwake(bool value) async {
    await (value ? WakelockPlus.enable() : WakelockPlus.disable());
    if (mounted) setState(() => _keepAwake = value);
  }

  @override
  Widget build(BuildContext context) {
    final device = _device;
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Bandit Mobile Camera'),
        actions: [
          IconButton(
            tooltip: 'Privacidad y ajustes',
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => SettingsScreen(
                  api: _api,
                  device: device,
                  onUnpaired: widget.onUnpaired,
                  onTokenRotated: widget.onTokenRotated,
                ),
              ),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            ListTile(
              leading: Icon(
                _connected ? Icons.cloud_done : Icons.cloud_off,
                color: _connected ? Colors.tealAccent : theme.colorScheme.error,
              ),
              title: Text(device?.name ?? 'Cargando…'),
              subtitle: Text(
                _connected
                    ? 'Conectado con Bandit'
                    : 'Sin conexión con Bandit. Reintentando…',
              ),
            ),
            const Divider(),
            SwitchListTile(
              title: const Text('Disponible para solicitudes'),
              subtitle: const Text(
                'Bandit podrá pedirte una transmisión. Siempre tendrás que aceptarla aquí: '
                'la cámara y el micrófono nunca se activan sin tu autorización.',
              ),
              value: device?.isAvailable ?? false,
              onChanged: device == null || _busy ? null : _setAvailable,
            ),
            SwitchListTile(
              title: const Text('Mantener la pantalla encendida'),
              subtitle: const Text(
                'Útil si dejas el teléfono fijo. Con la app cerrada o el teléfono bloqueado, '
                'las solicitudes esperan a que vuelvas a abrirla.',
              ),
              value: _keepAwake,
              onChanged: _setKeepAwake,
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
              ),
            const SizedBox(height: 24),
            Text(
              'Estar vinculado no significa transmitir. El teléfono solo envía video durante '
              'una sesión que hayas aceptado, y puedes detenerla en cualquier momento.',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}
