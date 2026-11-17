import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../services/bandit_api.dart';
import '../../services/models.dart';

/// Escanea el QR temporal de Bandit web y confirma la vinculación.
class PairingScreen extends StatefulWidget {
  const PairingScreen({super.key, required this.onPaired});

  final Future<void> Function(DeviceCredentials credentials) onPaired;

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  final _scanner = MobileScannerController(formats: const [BarcodeFormat.qrCode]);
  bool _handling = false;
  String? _error;

  @override
  void dispose() {
    _scanner.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_handling) return;
    String? raw;
    for (final barcode in capture.barcodes) {
      raw ??= barcode.rawValue;
    }
    if (raw == null) return;
    _handling = true;
    try {
      // En modo debug se admite http:// para probar en la red local.
      final qr = PairingQr.parse(raw, allowInsecureHttp: kDebugMode);
      if (qr.isExpired(DateTime.now())) {
        throw InvalidQrException('Este QR ya venció. Genera uno nuevo en Bandit.');
      }
      await _scanner.stop();
      if (!mounted) return;
      final name = await _confirm(qr);
      if (name == null) {
        await _scanner.start();
        return;
      }
      final api = BanditApi(qr.apiBaseUrl);
      final credentials = await api.register(
        qr,
        deviceName: name,
        platform: Platform.isIOS ? 'ios' : 'android',
      );
      api.close();
      await widget.onPaired(credentials);
    } on InvalidQrException catch (error) {
      setState(() => _error = error.message);
    } on BanditApiException catch (error) {
      setState(() => _error = error.message);
      await _scanner.start();
    } catch (_) {
      setState(() => _error = 'No hay conexión con Bandit. Revisa internet e inténtalo otra vez.');
      await _scanner.start();
    } finally {
      _handling = false;
    }
  }

  Future<String?> _confirm(PairingQr qr) {
    final controller = TextEditingController(text: Platform.isIOS ? 'iPhone' : 'Teléfono Android');
    return showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        title: const Text('¿Vincular este teléfono?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Servidor: ${qr.apiBaseUrl.host}'),
            const SizedBox(height: 12),
            const Text(
              'El teléfono podrá recibir solicitudes de transmisión. Nunca transmitirá sin que '
              'lo autorices en esta pantalla.',
            ),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              maxLength: 120,
              decoration: const InputDecoration(labelText: 'Nombre del teléfono'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancelar')),
          FilledButton(
            onPressed: () {
              final name = controller.text.trim();
              if (name.isNotEmpty) Navigator.pop(context, name);
            },
            child: const Text('Vincular'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Vincular con Bandit')),
      body: Column(
        children: [
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text(
              'En Bandit web abre Ajustes > Cámaras > Cámaras móviles, pulsa "Vincular un '
              'teléfono" y escanea el código.',
            ),
          ),
          Expanded(child: MobileScanner(controller: _scanner, onDetect: _onDetect)),
          if (_error != null)
            Container(
              width: double.infinity,
              color: Theme.of(context).colorScheme.errorContainer,
              padding: const EdgeInsets.all(16),
              child: Text(_error!, semanticsLabel: 'Error: $_error'),
            ),
        ],
      ),
    );
  }
}
