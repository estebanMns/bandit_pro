import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../services/bandit_api.dart';
import '../../services/models.dart';
import '../camera/preview_screen.dart';

/// Privacidad y ajustes: permisos, prueba de cámara, renovación del token y desvinculación.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.api,
    required this.device,
    required this.onUnpaired,
    required this.onTokenRotated,
  });

  final BanditApi api;
  final DeviceInfo? device;
  final Future<void> Function() onUnpaired;
  final Future<void> Function(String token) onTokenRotated;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  PermissionStatus? _camera;
  PermissionStatus? _microphone;

  @override
  void initState() {
    super.initState();
    _loadPermissions();
  }

  Future<void> _loadPermissions() async {
    final camera = await Permission.camera.status;
    final microphone = await Permission.microphone.status;
    if (mounted) {
      setState(() {
        _camera = camera;
        _microphone = microphone;
      });
    }
  }

  String _label(PermissionStatus? status) {
    if (status == null) return 'Revisando…';
    if (status.isGranted) return 'Permitido';
    if (status.isPermanentlyDenied) return 'Bloqueado: actívalo en los ajustes del sistema';
    return 'Se pedirá al aceptar una sesión';
  }

  Future<void> _rotate() async {
    try {
      final token = await widget.api.rotateToken();
      widget.api.token = token;
      await widget.onTokenRotated(token);
      _show('Credencial renovada.');
    } catch (error) {
      _show('$error');
    }
  }

  Future<void> _unpair() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('¿Desvincular este teléfono?'),
        content: const Text(
          'Bandit dejará de verlo y tendrás que escanear un QR nuevo para volver a usarlo.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Desvincular')),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await widget.api.unpair();
    } on BanditApiException catch (error) {
      // Si ya estaba desvinculado en el servidor, igual se borran las credenciales locales.
      if (!error.isUnauthorized) {
        _show(error.message);
        return;
      }
    } catch (_) {
      _show('No hay conexión con Bandit. Inténtalo otra vez.');
      return;
    }
    if (!mounted) return;
    Navigator.of(context).pop();
    await widget.onUnpaired();
  }

  void _show(String message) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final device = widget.device;
    return Scaffold(
      appBar: AppBar(title: const Text('Privacidad y ajustes')),
      body: ListView(
        children: [
          if (device != null)
            ListTile(
              leading: const Icon(Icons.smartphone),
              title: Text(device.name),
              subtitle: Text(device.platform == 'ios' ? 'iPhone' : 'Android'),
            ),
          ListTile(
            leading: const Icon(Icons.videocam),
            title: const Text('Cámara'),
            subtitle: Text(_label(_camera)),
            onTap: openAppSettings,
          ),
          ListTile(
            leading: const Icon(Icons.mic),
            title: const Text('Micrófono'),
            subtitle: Text(_label(_microphone)),
            onTap: openAppSettings,
          ),
          ListTile(
            leading: const Icon(Icons.preview),
            title: const Text('Probar la cámara'),
            subtitle: const Text('Vista previa local. No se envía nada a Bandit.'),
            onTap: () async {
              await Navigator.of(context).push(
                MaterialPageRoute<void>(builder: (_) => const PreviewScreen()),
              );
              _loadPermissions();
            },
          ),
          const Divider(),
          const ListTile(
            leading: Icon(Icons.privacy_tip),
            title: Text('Privacidad'),
            subtitle: Text(
              'El teléfono solo transmite durante una sesión que aceptes. El audio y el video '
              'no se graban. El análisis de Bandit, si está activado, usa fotogramas y nunca el '
              'audio.',
            ),
          ),
          ListTile(
            leading: const Icon(Icons.key),
            title: const Text('Renovar credencial del teléfono'),
            onTap: _rotate,
          ),
          ListTile(
            leading: Icon(Icons.link_off, color: Theme.of(context).colorScheme.error),
            title: const Text('Desvincular de Bandit'),
            onTap: _unpair,
          ),
        ],
      ),
    );
  }
}
