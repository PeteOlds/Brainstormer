import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../../core/widgets/app_shell.dart';
import '../admin/admin_repository.dart';

/// Instance settings: AI provider keys (write-only), budgets, OAuth
/// credentials, spend. Instance admins only — enforced server-side.
class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  final _key = TextEditingController();
  String _provider = 'openai';
  bool _saving = false;
  String? _notice;

  @override
  void dispose() {
    _key.dispose();
    super.dispose();
  }

  String? get _instanceId => ref.watch(currentInstanceProvider);

  @override
  Widget build(BuildContext context) {
    final iid = _instanceId;
    if (iid == null) {
      return const AppShell(
        title: 'Settings',
        child: Center(
            child: Text('Pick an instance first (unscoped legacy session).')),
      );
    }
    final configs = ref.watch(_aiConfigsProvider(iid));
    final spend = ref.watch(_spendProvider(iid));
    return AppShell(
      title: 'Settings',
      child: ListView(
        padding: const EdgeInsets.all(AppSpacing.md),
        children: [
          const Text('AI provider key (write-only, never echoed)',
              style: TextStyle(fontWeight: FontWeight.bold)),
          DropdownButtonFormField<String>(
            initialValue: _provider,
            items: const [
              DropdownMenuItem(
                  value: 'openai', child: Text('OpenAI')),
              DropdownMenuItem(
                  value: 'anthropic', child: Text('Anthropic')),
              DropdownMenuItem(
                  value: 'gemini', child: Text('Gemini')),
              DropdownMenuItem(
                  value: 'ollama', child: Text('Local Ollama')),
            ],
            onChanged: (v) => setState(() => _provider = v ?? 'openai'),
          ),
          TextField(
            controller: _key,
            obscureText: true,
            decoration: const InputDecoration(
                labelText: 'API key (leave blank to keep)'),
          ),
          const SizedBox(height: AppSpacing.sm),
          FilledButton(
            key: const Key('settings_save_key'),
            onPressed: _saving ? null : _saveKey,
            child: const Text('Save key'),
          ),
          if (_notice != null)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: Text(_notice!),
            ),
          const SizedBox(height: AppSpacing.lg),
          const Text('Configured providers',
              style: TextStyle(fontWeight: FontWeight.bold)),
          configs.when(
            loading: () =>
                const Center(child: CircularProgressIndicator()),
            error: (e, _) => Text('Failed: $e'),
            data: (items) => Column(
              children: [
                for (final c in items)
                  ListTile(
                    title: Text((c['provider'] ?? '').toString()),
                    subtitle: Text(
                        'key: ${c['has_key'] == true ? 'set' : 'missing'} · '
                        'budget: ${c['budget_cents'] ?? 'none'}'),
                  ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          const Text('Spend (rolling 30 days)',
              style: TextStyle(fontWeight: FontWeight.bold)),
          spend.when(
            loading: () =>
                const Center(child: CircularProgressIndicator()),
            error: (e, _) => Text('Failed: $e'),
            data: (s) {
              final byProvider =
                  (s['by_provider'] as Map? ?? {}).map(
                      (k, v) => MapEntry(k.toString(), v));
              if (byProvider.isEmpty) {
                return const Text('No spend recorded yet.');
              }
              return Column(
                children: [
                  for (final entry in byProvider.entries)
                    ListTile(
                      title: Text(entry.key),
                      trailing: Text(
                          '${(entry.value as Map)['cost_cents'] ?? 0}¢'),
                    ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _saveKey() async {
    final iid = _instanceId;
    if (iid == null) return;
    setState(() {
      _saving = true;
      _notice = null;
    });
    try {
      await ref.read(adminRepositoryProvider).saveAiConfig(iid, {
        'provider': _provider,
        if (_key.text.isNotEmpty) 'key': _key.text,
      });
      _key.clear();
      ref.invalidate(_aiConfigsProvider(iid));
      setState(() => _notice = 'Saved. Keys are never displayed back.');
    } catch (e) {
      setState(() => _notice = 'Save failed: $e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

final _aiConfigsProvider = FutureProvider.family
    .autoDispose<List<Map<String, dynamic>>, String>((ref, iid) async {
  return ref.watch(adminRepositoryProvider).aiConfigs(iid);
});

final _spendProvider = FutureProvider.family
    .autoDispose<Map<String, dynamic>, String>((ref, iid) async {
  return ref.watch(adminRepositoryProvider).spend(iid);
});
