import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/providers.dart';
import '../../core/theme/tokens.dart';

/// Instance member roster. Server enforces the guards (never self,
/// never the last admin); the UI surfaces the messages.
class UsersPage extends ConsumerStatefulWidget {
  const UsersPage({super.key});

  @override
  ConsumerState<UsersPage> createState() => _UsersPageState();
}

class _UsersPageState extends ConsumerState<UsersPage> {
  @override
  Widget build(BuildContext context) {
    final iid = ref.watch(currentInstanceProvider);
    if (iid == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Users')),
        body: const Center(child: Text('Pick an instance first.')),
      );
    }
    final members = ref.watch(_membersProvider(iid));
    return Scaffold(
      appBar: AppBar(title: const Text('Users')),
      body: members.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Failed to load: $e')),
        data: (items) => ListView.builder(
          padding: const EdgeInsets.all(AppSpacing.md),
          itemCount: items.length,
          itemBuilder: (context, i) {
            final m = items[i];
            return Card(
              child: ListTile(
                title: Text(
                    ((m['email'] ?? m['user_id']) ?? '').toString()),
                subtitle: Text((m['role'] ?? '').toString()),
                trailing: PopupMenuButton<String>(
                  onSelected: (v) => _act(
                      context, iid, (m['user_id'] ?? '').toString(), v),
                  itemBuilder: (context) => const [
                    PopupMenuItem(
                        value: 'INSTANCE_ADMIN',
                        child: Text('Make admin')),
                    PopupMenuItem(
                        value: 'USER', child: Text('Make user')),
                    PopupMenuItem(
                        value: 'remove', child: Text('Remove')),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Future<void> _act(BuildContext context, String iid, String memberId,
      String action) async {
    final api = ref.read(apiClientProvider);
    try {
      if (action == 'remove') {
        await api.delete('/api/v1/instances/$iid/members/$memberId');
      } else {
        await api.patch('/api/v1/instances/$iid/members/$memberId',
            body: {'role': action});
      }
      ref.invalidate(_membersProvider(iid));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.message)),
        );
      }
    }
  }
}

final _membersProvider = FutureProvider.family
    .autoDispose<List<Map<String, dynamic>>, String>((ref, iid) async {
  final data =
      await ref.watch(apiClientProvider).get('/api/v1/instances/$iid/members');
  final list = ((data as Map<String, dynamic>)['members'] as List? ?? []);
  return [
    for (final e in list)
      (e as Map).map((k, v) => MapEntry(k.toString(), v))
  ];
});
