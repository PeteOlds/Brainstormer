import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';

/// Offline banner driven by platform connectivity. Cached content keeps
/// working underneath; mutations queue server-side on reconnect.
class ConnectivityBanner extends StatelessWidget {
  const ConnectivityBanner({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        StreamBuilder<List<ConnectivityResult>>(
          stream: Connectivity().onConnectivityChanged,
          initialData: const [ConnectivityResult.wifi],
          builder: (context, snapshot) {
            final results = snapshot.data ?? const [];
            final offline = results.isEmpty ||
                results.every((r) => r == ConnectivityResult.none);
            if (!offline) return const SizedBox.shrink();
            return Container(
              key: const Key('offline_banner'),
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 6),
              color: Theme.of(context).colorScheme.errorContainer,
              child: const Text(
                'Offline — showing cached content',
                textAlign: TextAlign.center,
              ),
            );
          },
        ),
        Expanded(child: child),
      ],
    );
  }
}
