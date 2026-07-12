import 'package:flutter/material.dart';

import 'screens/dashboard_screen.dart';
import 'services/notification_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationService.initialize();
  runApp(const TradingSignalApp());
}

class TradingSignalApp extends StatelessWidget {
  const TradingSignalApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'AI Trading Signal',
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0F141B),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF3EE27A),
          brightness: Brightness.dark,
          surface: const Color(0xFF141B24),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF111821),
          foregroundColor: Colors.white,
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFF1B2532),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
        ),
        textTheme: const TextTheme(
          labelMedium: TextStyle(color: Color(0xFF9FB2C8)),
        ),
      ),
      home: const DashboardScreen(),
    );
  }
}

