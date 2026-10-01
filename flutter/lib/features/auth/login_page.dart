import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import 'auth_controller.dart';

/// Sign-in screen. Dumb by design: renders AuthState, delegates to the
/// controller, navigates on success.
class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final _email = TextEditingController(text: 'admin@example.com');
  final _password = TextEditingController(text: 'admin123');
  bool _remember = false;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(authControllerProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Sign in')),
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
                    key: const Key('login_error'),
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
                  key: const Key('login_email'),
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(labelText: 'Email'),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  key: const Key('login_password'),
                  controller: _password,
                  obscureText: true,
                  decoration:
                      const InputDecoration(labelText: 'Password'),
                  onSubmitted: (_) => _submit(),
                ),
                CheckboxListTile(
                  value: _remember,
                  onChanged: (v) =>
                      setState(() => _remember = v ?? false),
                  title: const Text('Remember me (30 days)'),
                  controlAffinity: ListTileControlAffinity.leading,
                  contentPadding: EdgeInsets.zero,
                ),
                const SizedBox(height: AppSpacing.sm),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    key: const Key('login_submit'),
                    onPressed: state.loading ? null : _submit,
                    child: state.loading
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2),
                          )
                        : const Text('Sign in'),
                  ),
                ),
                TextButton(
                  onPressed: () =>
                      Navigator.of(context).pushNamed('/register'),
                  child: const Text('Create an account'),
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
        .login(_email.text.trim(), _password.text, remember: _remember);
    if (ok && mounted) {
      Navigator.of(context).pushReplacementNamed('/instances');
    }
  }
}
