import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/signal.dart';
import '../services/api_service.dart';
import '../services/notification_service.dart';
import '../widgets/metric_card.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final ApiService _api = ApiService();
  Timer? _timer;
  String _mode = 'Forex';
  String _pair = 'EUR/USD';
  String _duration = '15 Seconds';
  Map<String, List<String>> _pairs = {
    'Forex': ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD', 'USD/CAD'],
    'Quotex': ['EUR/USD OTC', 'GBP/USD OTC', 'USD/JPY OTC', 'AUD/CAD OTC'],
  };
  List<String> _durations = [
    '5 Seconds',
    '10 Seconds',
    '15 Seconds',
    '30 Seconds',
    '1 Minute',
    '5 Minutes',
  ];
  TradingSignal? _signal;
  List<TradingSignal> _scanner = [];
  List<HistoryRecord> _history = [];
  Map<String, dynamic> _stats = {};
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _bootstrap();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _generate());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    try {
      final config = await _api.config();
      setState(() {
        _pairs = (config['pairs'] as Map<String, dynamic>)
            .map((key, value) => MapEntry(key, List<String>.from(value)));
        _durations = List<String>.from(config['durations']);
        _pair = _pairs[_mode]!.first;
      });
    } catch (_) {
      setState(() => _error = 'Using fallback configuration. Start the backend for live analysis.');
    }
    await Future.wait([_generate(), _loadHistory(), _loadStats()]);
  }

  Future<void> _generate() async {
    if (_busy || !mounted) return;
    setState(() => _busy = true);
    try {
      final signal = await _api.generateSignal(
        mode: _mode,
        pair: _pair,
        duration: _duration,
      );
      setState(() {
        _signal = signal;
        _error = null;
      });
      if (signal.signal != 'NO TRADE' && signal.confidence >= 75) {
        await NotificationService.showSignal(signal.pair, signal.signal, signal.confidence);
      }
      await Future.wait([_loadHistory(), _loadStats()]);
    } catch (error) {
      setState(() => _error = 'Backend connection or analysis error.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _scan() async {
    try {
      final rows = await _api.scanPairs(mode: _mode, duration: _duration);
      setState(() => _scanner = rows);
    } catch (_) {
      setState(() => _error = 'Scanner failed. Check backend logs.');
    }
  }

  Future<void> _loadHistory() async {
    try {
      final history = await _api.history();
      if (mounted) setState(() => _history = history);
    } catch (_) {}
  }

  Future<void> _loadStats() async {
    try {
      final stats = await _api.statistics();
      if (mounted) setState(() => _stats = stats);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final signal = _signal;
    return Scaffold(
      appBar: AppBar(
        title: const Text('AI Trading Signal'),
        actions: [
          IconButton(onPressed: _generate, icon: const Icon(Icons.refresh)),
          IconButton(onPressed: _scan, icon: const Icon(Icons.radar)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await Future.wait([_generate(), _scan()]);
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _controls(),
            const SizedBox(height: 14),
            if (_error != null) _errorBanner(_error!),
            GridView.count(
              crossAxisCount: MediaQuery.sizeOf(context).width > 720 ? 4 : 2,
              crossAxisSpacing: 10,
              mainAxisSpacing: 10,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              childAspectRatio: 1.55,
              children: [
                MetricCard(label: 'Pair', value: signal?.pair ?? _pair),
                MetricCard(label: 'Current Price', value: signal?.currentPrice.toStringAsFixed(5) ?? '--'),
                MetricCard(
                  label: 'Signal',
                  value: signal?.signal ?? 'NO TRADE',
                  accent: _signalColor(signal?.signal ?? 'NO TRADE'),
                ),
                MetricCard(label: 'Confidence', value: '${signal?.confidence ?? 0}%'),
                MetricCard(label: 'Trade Duration', value: _duration),
                MetricCard(label: 'Market Trend', value: signal?.marketTrend ?? '--'),
                MetricCard(label: 'Status', value: signal?.status ?? '--'),
                MetricCard(label: 'Avg Confidence', value: '${_stats['average_confidence'] ?? 0}%'),
              ],
            ),
            const SizedBox(height: 14),
            _analysis(signal),
            const SizedBox(height: 14),
            _scannerList(),
            const SizedBox(height: 14),
            _statsPanel(),
            const SizedBox(height: 14),
            _historyList(),
            const SizedBox(height: 22),
            Text(
              signal?.disclaimer ??
                  'Signals are probabilistic estimates only and do not guarantee profit or winning trades.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }

  Widget _controls() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: _panelDecoration(),
      child: Column(
        children: [
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'Forex', label: Text('Forex')),
              ButtonSegment(value: 'Quotex', label: Text('Quotex')),
            ],
            selected: {_mode},
            onSelectionChanged: (value) {
              final mode = value.first;
              setState(() {
                _mode = mode;
                _pair = _pairs[mode]!.first;
              });
              _generate();
            },
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  value: _pair,
                  decoration: const InputDecoration(labelText: 'Pair'),
                  items: _pairs[_mode]!
                      .map((pair) => DropdownMenuItem(value: pair, child: Text(pair)))
                      .toList(),
                  onChanged: (value) => setState(() => _pair = value ?? _pair),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: DropdownButtonFormField<String>(
                  value: _duration,
                  decoration: const InputDecoration(labelText: 'Duration'),
                  items: _durations
                      .map((duration) => DropdownMenuItem(value: duration, child: Text(duration)))
                      .toList(),
                  onChanged: (value) => setState(() => _duration = value ?? _duration),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _analysis(TradingSignal? signal) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: _panelDecoration(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Analysis', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          ...(signal?.analysis ?? ['Waiting for market analysis.'])
              .map((line) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Text('- $line'),
                  )),
        ],
      ),
    );
  }

  Widget _scannerList() {
    return _section(
      title: 'Multi Pair Scanner',
      children: _scanner
          .map((signal) => ListTile(
                dense: true,
                title: Text(signal.pair),
                subtitle: Text('${signal.marketTrend} | ${signal.status}'),
                trailing: Text('${signal.signal}\n${signal.confidence}%', textAlign: TextAlign.right),
              ))
          .toList(),
    );
  }

  Widget _statsPanel() {
    return _section(
      title: 'Signal Statistics',
      children: [
        Text(
          'Total ${_stats['total_signals'] ?? 0} | Wins ${_stats['wins'] ?? 0} | '
          'Losses ${_stats['losses'] ?? 0} | Tracked Win Rate ${_stats['tracked_win_rate'] ?? 0}%',
        ),
      ],
    );
  }

  Widget _historyList() {
    final dateFormat = DateFormat('MM/dd HH:mm:ss');
    return _section(
      title: 'Signal History',
      children: _history
          .take(20)
          .map((record) => ListTile(
                dense: true,
                title: Text('${record.pair} | ${record.signal} | ${record.confidence}%'),
                subtitle: Text('${dateFormat.format(record.createdAt.toLocal())} | ${record.duration} | ${record.marketTrend}'),
                trailing: Text(record.outcome ?? ''),
              ))
          .toList(),
    );
  }

  Widget _section({required String title, required List<Widget> children}) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: _panelDecoration(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          if (children.isEmpty) const Text('No records yet.') else ...children,
        ],
      ),
    );
  }

  Widget _errorBanner(String text) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF3A1D25),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFFF5C77)),
      ),
      child: Text(text),
    );
  }

  BoxDecoration _panelDecoration() {
    return BoxDecoration(
      color: const Color(0xFF111821),
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: const Color(0xFF263241)),
    );
  }

  Color _signalColor(String signal) {
    if (signal.contains('BUY') || signal.contains('UP')) return const Color(0xFF3EE27A);
    if (signal.contains('SELL') || signal.contains('DOWN')) return const Color(0xFFFF5C77);
    return const Color(0xFFB7C3D0);
  }
}
