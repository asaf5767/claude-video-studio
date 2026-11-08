# AI Video Studio — 0.1.0-he.1

Beta.11 adds a media-setup preflight that refuses dependency replacement while this installation has live HyperFrames previews, or when that inventory cannot be verified. Other installations and studio-only mode are unaffected. The existing renderer and pins are retained.

Prepared: 2026-11-05. HyperFrames 0.8.144 → 0.9.16 with a scoped Undici 7.30.2 override. The renderer and its browser tooling require Node 22.12.0 or newer; setup checks the full minimum before installing. GSAP and Python locks are unchanged. The local render wrapper retains no-update/no-telemetry behavior.

CI cleanup was separately reviewed in PR #26: one run per PR update, retained main/v* tag verification, manual dispatch and cancellation of superseded PR runs. Linux/macOS Intel Python 3.11/3.13, all tests, audits and the required release gate remain. Apple Silicon media/setup verification is a separate local pilot; Intel CI does not establish that coverage.

Upgrade reviewed source and pinned media dependencies only, keeping the installation's capability mode. Preserve all owner projects/media/library/techniques/scripts/settings/feedback/approvals/memory and editor working copies; there is no owner-data migration or automatic creative re-render. Read docs/UPDATING.md. Source rollback retains newer owner data and restores the previous renderer lock with npm ci for a media installation. Cloud rendering is optional and untested here; 0.9 uses distributed Plan v2 and owners of custom 0.8 cloud stacks must follow upstream migration guidance before using those stacks.

See docs/VALIDATION.md for observed checks and limits. The numbered GitHub release is authoritative for publication state.
