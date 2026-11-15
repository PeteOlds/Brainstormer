> **Status: Aspirational.** Applies when a Flutter client is built (e.g. the planned replatforming). Not applicable to the current Jinja2 + Alpine.js frontend. Companion guides: `Guide_UITesting.md` (testing), `Guide_ProjectOverview.md` §3 (backend contract).
>
> This guide defines the UI, state management, and idiomatic Flutter patterns necessary for maintainable and performant front-end development.

1. Strict Separation of UI and Logic
To prevent AI from generating unmaintainable monolithic files, enforce a hard boundary between visual rendering and business operations.

Dumb Widgets: Widgets must only render UI. Never place API calls, complex state mutations, or business calculations inside a widget.

Logic Controllers: Delegate all state management to dedicated controllers (e.g., Riverpod, Bloc, or Signals). When a bug occurs, you can prompt the AI to "Identify the root cause in the controller layer before touching any UI code," which prevents brittle, surface-level band-aids.

Micro-Widgets: Instruct the AI to keep widget files brief. If a widget grows beyond 100-150 lines, mandate that the AI extract sub-components into separate private classes or files.

2. Idiomatic Flutter Patterns

Relentless const Usage: Mandate that the AI uses const constructors for all static widgets to minimize garbage collection overhead and hit the display's native refresh rate (typically 60 or 120 Hz) without jank.

Design Tokens: Never let the AI hardcode strings, colors, or padding. Pre-define your design tokens (e.g., AppColors.primary, AppSpacing.md) and strictly instruct the AI to map all generated UI elements directly to these tokens. This prevents UI inconsistencies when using generative tools.

Resource Lifecycle: Ensure your AI rules explicitly state that all AnimationController, ScrollController, and stream subscriptions must be properly cleaned up in the dispose() method to prevent memory leaks.

3. Backend Contract

Before generating UI, generate and validate strict Dart domain models for the API contract (see `Guide_ProjectOverview.md` §3 and `Guide_UITesting.md` §2). Route all network access through a single client with token-refresh handling — never scatter raw `http` calls across widgets or controllers.