# Bandit Mobile Camera (Flutter)

Aplicación Android e iOS que convierte un teléfono en una cámara bajo demanda de Bandit.
Es parte del módulo descrito en [`docs/BANDIT_MOBILE_CAMERA.md`](../../docs/BANDIT_MOBILE_CAMERA.md).

> **Estado:** código de la Fase 2 y de la parte móvil de la Fase 3. No se ha compilado ni
> probado todavía en dispositivos físicos: hazlo antes de usarlo con datos reales.

## Qué hace

1. **Vinculación:** escanea el QR temporal de Bandit web (Ajustes › Cámaras › Cámaras móviles),
   muestra a qué servidor se vincula y guarda el token del teléfono en Keychain/Keystore.
2. **Disponibilidad:** el interruptor *Disponible para solicitudes* avisa al backend.
3. **Solicitud visible:** al llegar una solicitud por WebSocket se abre una pantalla con quién la
   pide, los permisos que necesita y una cuenta regresiva. Se acepta o se rechaza a mano.
4. **Transmisión:** al aceptar pide permisos del sistema, abre cámara (y micrófono si se
   autorizó) y publica por **WHIP** en MediaMTX con un ticket temporal. La pantalla muestra
   vista previa, indicadores de cámara y micrófono activos, y un botón grande para detener.
5. **Cierre:** al detener, al vencer la sesión, al pararla desde el dashboard o al pasar la app
   a segundo plano, se cierran la conexión y todas las pistas. Nunca se reactivan solas.

## Estructura

```
lib/
├── app/app.dart                     # Tema y puerta de entrada (vinculado o no)
├── features/
│   ├── pairing/pairing_screen.dart   # Escaneo del QR y confirmación
│   ├── sessions/home_screen.dart     # Estado y disponibilidad
│   ├── sessions/incoming_request_screen.dart
│   ├── camera/live_screen.dart       # Transmisión activa
│   ├── camera/preview_screen.dart    # Prueba local de cámara (sin red)
│   └── settings/settings_screen.dart # Permisos, privacidad, desvincular
└── services/
    ├── bandit_api.dart              # REST con token del dispositivo
    ├── device_socket.dart           # WebSocket de eventos con reconexión y latidos
    ├── whip_publisher.dart          # flutter_webrtc + WHIP hacia MediaMTX
    ├── credential_store.dart        # flutter_secure_storage
    └── models.dart
```

## Preparar el proyecto

El repositorio incluye `lib/`, `test/`, el `AndroidManifest.xml` y el `Info.plist` con los
permisos. Las demás carpetas nativas las genera Flutter:

```bash
cd mobile/bandit_mobile_camera
./setup.sh          # flutter create + pub get + minSdk 23
flutter test
flutter run         # con un teléfono conectado
```

Pasos manuales en iOS (`ios/Podfile`):

```ruby
platform :ios, '15.0'

post_install do |installer|
  installer.pods_project.targets.each do |target|
    flutter_additional_ios_build_settings(target)
    target.build_configurations.each do |config|
      config.build_settings['GCC_PREPROCESSOR_DEFINITIONS'] ||= ['$(inherited)',
        'PERMISSION_CAMERA=1', 'PERMISSION_MICROPHONE=1']
    end
  end
end
```

Después de probar, fija las versiones exactas: `pubspec.yaml` usa rangos amplios y el
`pubspec.lock` resultante debe subirse al repositorio.

## Comportamiento por plataforma

| | Android | iOS |
|---|---|---|
| Recibir solicitudes | Con la app abierta (WebSocket). | Con la app abierta (WebSocket). |
| App en segundo plano | La transmisión se detiene. | La transmisión se detiene; iOS suspende la cámara. |
| Avisos push | Pendiente (FCM). | Pendiente (APNs). |
| Pantalla encendida | Opción *Mantener la pantalla encendida*. | Igual. |

La primera versión **no** usa servicio en primer plano en Android ni modos de segundo plano en
iOS: es la opción más honesta con las reglas de ambos sistemas. Si en el futuro se agrega un
servicio en primer plano, debe declarar `foregroundServiceType="camera|microphone"`, mostrar la
notificación persistente e iniciarse solo desde una acción del usuario.

Para pruebas en red local sin HTTPS, compila en modo debug: solo entonces se aceptan QR con
`http://`.

## Seguridad

* El QR es de un solo uso, vence en minutos y no contiene contraseñas.
* El token del teléfono se guarda cifrado por el sistema y se puede renovar o revocar.
* El ticket de publicación dura 2 minutos y solo sirve para la ruta de esa sesión; MediaMTX lo
  valida contra el backend en cada conexión.
* Las credenciales TURN llegan con cada sesión y caducan.
