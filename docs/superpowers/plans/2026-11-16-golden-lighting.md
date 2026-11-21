# Golden Lighting Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement in this session. Continue the user's explicit visual direction within the approved shader architecture.

**Goal:** Warm golden light and prominent shafts, plus water without the vanilla texture, with exact tuning locations.

**Architecture:** Shared sun/sky palette and ambient/direct lighting; same half-resolution atmosphere; a separate procedural water material helper; existing post bloom/AA/tonemap.

**Tech Stack:** WGSL, Horizon API 0.2, TOML, official checker, Python/wgpu GPU tests, installed current Horizon client.

**Spec:** docs/superpowers/specs/2026-11-16-golden-lighting-design.md

## Global constraints

- No ray tracing, new texture assets, client rebuild, or geometry-wave requirements.
- Existing working non-water material and entity effects remain valid.
- Keep id horizon_lighting; version 0.2.0; preserve 0.1.0 archive and installed backups.
- Actual game testing stays in an isolated world; install the checked result into the existing game pack directory.

## Review focus

- Low positive sun angles must retain light/shafts; night, Nether and End must not turn orange.
- Wave/refraction samples must not pull foreground geometry over shorelines or leave invalid UVs.
- Underwater, side-face and mismatched-height water must remain readable and texture-independent.
- Water already composites opaque background: its returned alpha must not blend that background twice.
- More visible shafts must retain depth rejection, bounded loops and adjustable sample cost.

## Tasks

1. [x] Add meaningful GPU regressions for water colour/tint/alpha independence and time-varying waves. Keep the previous baked-tint regression on solid terrain. Watch new tests fail on the current implementation.
2. [x] Update common.wgsl palette/low-sun curves, lighting.wgsl contrast controls, atmosphere integration/defaults, and a new sky.wgsl horizon stage. Keep quality controls and status fallbacks.
3. [x] Add water.wgsl procedural colour/compositing/waves; material.wgsl delegates water before accessing vanilla colour. Maintain plane/medium guards, clamped depth-aware refraction, Fresnel and sun glints.
4. [x] Update manifest/version, package validation to read version dynamically, and GPU harness resource bindings. Run checker and regressions; repair failures using actual diagnostics.
5. [x] Capture baseline and new noon/sunrise/sunset/water views with the installed current client in an isolated scene. Tune against captures and measure comparable frame stats if available.
6. [x] Fresh independent review, address material findings, package/install with backup, and verify normal saved pack selection with no environment workaround.
7. [x] Document TUNING.md with exact parameters and final line-number links; update validation evidence and README. Run final appropriate checks.

## User scope extension: gloss and reflected light

- [x] Add material classifications/F0 packing helpers and GGX direct-sun highlights; keep default rough surfaces matte. Include a bounded warm indirect fill control.
- [x] Store solid-surface normal/smoothness/F0 through set_surface and add half-resolution screen-space reflection with finite reach/steps, foreground/self-hit guards, roughness filtering and environment fallback. Composite only on matching glossy receivers with depth rejection.
- [x] Add controls and TUNING references. No extra texture assets or ray queries. Validate clear-water invariance, existing effects, all backend translations, and glossy fixture images. Include the new feature in the single final independent review.

Completed: official checks and 13 tests passed; independent review fixes verified; installed with rollback backup and saved-selection smoke test. Comparative performance remains unproven; the short capped fixture timing is recorded without a speedup claim.
