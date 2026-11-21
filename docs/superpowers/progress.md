# Execution ledger: 2026-11-16-horizon-lighting

- Design approved; user requested implementation.
- Native inline execution; final fresh review follows implementation.
- Workspace has no git repository; use existing user workspace without creating a worktree or committing.
- Pre-flight: material/entity share lighting helper signatures; post passes share named texture targets in manifest order. No interface conflict found.
- Task 1 complete: downloaded pinned upstream checker/reference source, installed workspace-local Rust 1.100 GNU, built official CLI; contract suite failed on missing pack before implementation.
- Task 2 complete: terrain/entity raster lighting, PCF, gated shadows/mirror, and water guards pass official checker. Entity fog is engine-managed: the entity stage accepts no fog key. Explicit coverage keys omitted for older parser compatibility; engine coverage remains default.
- Task 3 complete: six post passes including spatial AA, with all minimum/default/maximum backend translations passing. Ordinary post outputs force alpha to 1, so atmosphere carries additive RGB only and retains engine fog extinction. This replaces the proposed RGB/transmittance signal.
- Compatibility extension: installed nightly 9f42064 lacks entity rendering and gates API 0.2 behind HORIZON_HDR_FRAME=float. Generate a separately named compatibility archive omitting only entity stage/file. Source main pack remains latest API with custom entities. This is covered by archive equivalence tests.
- User's clone at C:\Users\asdf\Documents\GitHub\main\horizon has ref 85b5bcca7c79bb470b90bdb5914b413aa66fe7ae, matching the checker baseline. No compiled client found. Read-only inspection; no clone updates, builds, or configuration changes.
- Fresh independent review: two Important findings, no Critical or Minor findings. Verified both against API/source and reproduced in GPU shader-output tests before fixing.
- Fixed entity vanilla fallback: apply vanilla shade before gamma-space overlay in Nether/End/status paths. GPU regression RED to GREEN.
- Fixed material tint transfer: preserve baked tint instead of inferring face shade from camera-facing normals (underwater and diagonal surfaces). GPU regression RED to GREEN. This refines the spec's attempted shade removal, whose provenance is unavailable.
- Full validation after fixes: 8/8 tests pass, including 2 GPU adapter tests covering 6 scenarios. Main default/Low/High/disabled plus compatibility/source and both distributions pass official validation.
- Initial No AI setting prevented control; user explicitly enabled it. Subsequent test control worked without changing that preference ourselves. Compatibility archive rendered in isolated offscreen world on RTX4050/Vulkan, no ray tracing; daylight/water/night/underwater/rain captured. Test process exited through quit.
- Visual/performance limits: screenshots cover compatibility terrain/post stages only; current-client entity visuals, Nether/End, and comparative performance are not claimed. No deferred review minors.
