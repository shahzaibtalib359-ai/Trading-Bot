import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class NotificationService {
  NotificationService._();

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static Future<void> initialize() async {
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const settings = InitializationSettings(android: android);
    await _plugin.initialize(settings);
    await _plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
  }

  static Future<void> showSignal(String pair, String signal, int confidence) {
    const android = AndroidNotificationDetails(
      'trading_signals',
      'Trading Signals',
      channelDescription: 'Probability-based trading signal alerts',
      importance: Importance.high,
      priority: Priority.high,
      playSound: true,
    );
    return _plugin.show(
      DateTime.now().millisecondsSinceEpoch ~/ 1000,
      'Trading Signal',
      '$pair: $signal at $confidence%',
      const NotificationDetails(android: android),
    );
  }
}

