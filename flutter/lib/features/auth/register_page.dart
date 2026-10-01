import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import 'auth_controller.dart';
import 'auth_models.dart';

class RegisterPage extends ConsumerStatefulWidget {
  const RegisterPage({super.key});

  @override
  ConsumerState<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends ConsumerState<RegisterPage> {
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(authControllerProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Create account')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (state.error != null)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(AppSpacing.sm),
                    margin:
                        const EdgeInsets.only(bottom: AppSpacing.md),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.errorContainer,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(state.error!),
                  ),
                TextField(
                  controller: _name,
                  decoration:
                      const InputDecoration(labelText: 'Name (optional)'),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(labelText: 'Email'),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  controller: _password,
                  obscureText: true,
                  decoration: const InputDecoration(
                      labelText: 'Password (min 8 chars)'),
                ),
                const SizedBox(height: AppSpacing.md),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    key: const Key('register_submit'),
                    onPressed: state.loading ? null : _submit,
                    child: const Text('Register'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    final ok = await ref
        .read(authControllerProvider.notifier)
        .register(_email.text.trim(), _password.text,
            _name.text.trim().isEmpty ? null : _name.text.trim());
    if (ok && mounted) {
      Navigator.of(context).pushReplacementNamed('/instances');
    }
  }
}

/// Post-login tenant picker. Single-membership users skip straight
/// through; everyone else picks an instance (replaces the web login's
/// implicit unscoped session).
class InstancePickerPage extends ConsumerStatefulWidget {
  const InstancePickerPage({super.key});

  @override
  ConsumerState<InstancePickerPage> createState() =>
      _InstancePickerPageState();
}

class _InstancePickerPageState extends ConsumerState<InstancePickerPage> {
  late final Future<List<InstanceSummary>> _future;

  @override
  void initState() {
    super.initState();
    _future =
        ref.read(authControllerProvider.notifier).instances();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Choose workspace')),
      body: FutureBuilder<List<InstanceSummary>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(child: Text('Failed to load: ${snapshot.error}'));
          }
          final items = snapshot.data ?? [];
          if (items.length == 1) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              _enter(context, items.first);
            });
          }
          return ListView.builder(
            itemCount: items.length + 1,
            itemBuilder: (context, i) {
              if (i == items.length) {
                return ListTile(
                  leading: const Icon(Icons.public),
                  title: const Text('Continue unscoped (legacy)'),
                  onTap: () =>
                      Navigator.of(context).pushReplacementNamed('/ideas'),
                );
              }
              final inst = items[i];
              return ListTile(
                key: Key('instance_${inst.number}'),
                leading: CircleAvatar(child: Text('${inst.number}')),
                title: Text(inst.name),
                subtitle: Text('Instance ${inst.number}'),
                onTap: () => _enter(context, inst),
              );
            },
          );
        },
      ),
    );
  }

  void _enter(BuildContext context, InstanceSummary inst) {
    ref.read(currentInstanceProvider.notifier).state = inst.id;
    Navigator.of(context).pushReplacementNamed('/ideas');
  }
}
