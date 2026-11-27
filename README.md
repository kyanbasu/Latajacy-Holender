# Latajacy-Holender

## Performance notes (6-core / 12-thread laptop)

The shipped configs are tuned to keep **all visual fidelity** (256-chunk Distant Horizons radius,
BLOCK-resolution LODs, Medium LOD quality, trees/structures in LODs, SSAO, anti-aliasing, clouds,
shaders and vanilla render distance 12) while reducing CPU oversubscription:

- Distant Horizons: 3 generation threads at 70% runtime, priority 3 (was 6 threads at 100%).
  LODs generate a bit slower; final detail is unchanged. Noisy per-event logging is muted.
- C2ME: pinned to 3 worker threads, low priority.
- Sodium: 3 chunk-builder threads instead of "auto" (which used ~all cores here).
- World Preview: 4 threads instead of 11.
- Sable: 100 sub-level split steps/tick instead of 200 (smoother frames with many airships).
- ModernFix: lazy model loading (`mixin.perf.dynamic_resources=true`) to cut startup time and GC.

Launcher-side (not part of the packwiz pack) recommended JVM flags for this machine:
`-XX:+UseZGC -XX:+ZGenerational -Xms6144m -Xmx10112m` (already using ZGC; raising only the
initial heap avoids heap-growth churn). Keep `maxFps` around 144 rather than uncapped.

## Crash note

Sodium 0.8.14-beta.x renames fluid-render mixin targets (`getTexU/getTexV` →
`sodium$getTexU/sodium$getTexV`) that Veil 4.3.2 (embedded in Sable) requires. The pack therefore
pins the proven-stable Sodium 0.8.13 / Sodium Extra 0.9.5 / Reese's 2.2.6 trio. Flerovium must
also stay at 1.2.0: version 1.2.1 hard-requires Sodium >= 0.8.14-beta.2 and refuses to load with
the stable Sodium needed by Veil. Do not run `packwiz update --all` without checking these four
pins again.

