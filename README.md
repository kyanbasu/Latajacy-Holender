# Latajacy-Holender

## Performance notes (6-core / 12-thread laptop)

The shipped configs are tuned to keep **all visual fidelity** (256-chunk Distant Horizons radius,
BLOCK-resolution LODs, Medium LOD quality, trees/structures in LODs, SSAO, anti-aliasing, clouds
and shaders) while reducing CPU oversubscription. Vanilla render distance is deliberately 8 -
Distant Horizons covers everything beyond that:

- Distant Horizons: 2 generation threads at 60% runtime, priority 3 (was 6 threads at 100%).
  LODs generate a bit slower; final detail is unchanged. Noisy per-event logging is muted.
- C2ME: pinned to 2 worker threads, low priority.
- Sodium: 4 chunk-builder threads on a 6-core client (scaled by `config_scale.py`) —
  `ChunkBuilderMeshingTask.execute` was the dominant chunk-crossing stall — and
  `cpu_render_ahead_limit=2` to shorten CPU work per frame.
- World Preview: 2 threads instead of 11.
- Sable: 50 sub-level split steps/tick instead of 200 (smoother frames with many airships).
- ModernFix: lazy model loading (`mixin.perf.dynamic_resources=true`) to cut startup time and GC.
- Sable physics: 1 substep/tick instead of 2 - roughly halves the current #1 server-thread
  hotspot (`SubLevelPhysicsSystem.tick`), at the cost of slightly less accurate airship physics.
- ServerCore activation range: enabled with conservative 64-96 block radii and Create
  contraptions/minecarts exempt. Distant entities skip ticks; nearby gameplay is unchanged.
- Distant Horizons network load: real-time LOD radius 256→128, sync-on-load off,
  request rate 20→10, bandwidth 500→300 KB/s, adaptive transfer on. Final LOD detail
  (BLOCK / 256-chunk radius) is unchanged; only live LOD updates arrive more gently.
- Removed unused visual mods from the pack: Create Sable Dynamic Lights, Sodium
  Dynamic Lights and Interactive Foliage (you had already disabled them).
- EntityCulling occlusion work trimmed: tracing distance 128→64, capture rate 5→10,
  sleep delay 10→20. Safe mode and tick culling stay on.
- Default FPS cap: 90; on a CPU bottleneck an uncapped cap only adds frame-time variance.

Launcher-side (not part of the packwiz pack) recommended JVM flags for this machine:
`-XX:+UseZGC -XX:+ZGenerational -Xms6016m -Xmx11008m` (already using ZGC; raising only the
initial heap avoids heap-growth churn).

## Role-aware scaling

C2ME now scales its worker count at startup from its own parallelism expression, using
`cores`, `cpus`, `mem_gb` and `is_client`. On a 6-core client it resolves to ~2 workers;
on a dedicated server it resolves to ~5. ServerCore's `dynamic` block also lowers entity
ticking automatically when MSPT exceeds `target-mspt` (17 ms on client, 50 ms on server).

Mods with only fixed integer configs are scaled by `tools/config_scale.py`:

```bash
python3 tools/config_scale.py --role client   # current repo state
python3 tools/config_scale.py --role server
```

It sets DH/Sodium/World Preview thread caps, Sable physics substeps and ServerCore
activation ranges for the chosen role and detected core count. Two ready-to-install
variants are exported: `Latajacy Holender-0.2-client.mrpack` and
`Latajacy Holender-0.2-server.mrpack`. After running the script, `packwiz refresh` and
`packwiz modrinth export` are needed. Metrics/tooling files are excluded from the pack via
`.packwizignore`.

## Crash note

Sodium 0.8.14-beta.x renames fluid-render mixin targets (`getTexU/getTexV` →
`sodium$getTexU/sodium$getTexV`) that Veil 4.3.2 (embedded in Sable) requires. The pack therefore
pins the proven-stable Sodium 0.8.13 / Sodium Extra 0.9.5 / Reese's 2.2.6 trio. Flerovium must
also stay at 1.2.0: version 1.2.1 hard-requires Sodium >= 0.8.14-beta.2 and refuses to load with
the stable Sodium needed by Veil. Do not run `packwiz update --all` without checking these four
pins again.

