# Horizon Lighting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a validated, installable, raster-only Horizon lighting pack.

**Architecture:** Shared lighting WGSL feeds terrain and entity adapters, with engine shadow maps and planar water reflection. Five ordered post passes produce half-resolution atmosphere and quarter-resolution bloom, composite them, and hand linear colour to a dedicated tone mapper.

**Tech Stack:** Horizon shader API 0.2, WGSL, TOML, Python unittest for package contracts, official Rust horizon-shader checker.

**Spec:** docs/superpowers/specs/2026-11-16-horizon-lighting-design.md (approved by user).

## Global Constraints

- Native Horizon API 0.2; no ray queries or special texture packs.
- Source/checker baseline: 85b5bcca7c79bb470b90bdb5914b413aa66fe7ae.
- Broad raster compatibility; never assert cross-GPU performance without measurements.
- Neutral textures, readable nights/interiors, adjustable quality.
- Use the current user-supplied empty workspace; no new worktree is needed.

## Review Focus

- Sky, far terrain, and shadow-map edges must not produce invalid coordinates or hard lighting seams.
- Water viewed underwater, from side faces, or outside the mirror plane must retain readable transparency.
- Rain, night, Nether, and End must not inherit inappropriate daylight shafts.
- Disabling shadows and reflections must stop their engine passes; disabled effects must remain valid.
- Linear lighting must preserve block light and emission and avoid duplicate vanilla face shading or fog.

## Task 1: Reproducible tooling and package contract

Files: `.gitignore`, `tools/check.ps1`, `tests/test_pack.py`, `.tools/` (ignored upstream checker/reference/toolchain).

Interfaces: `tools/check.ps1` runs the pinned official checker and Python package tests; tests inspect `horizon_lighting/horizon-shaders.toml` and the packaged archive.

- [x] Fetch the pinned shader-api source and documentation; preserve upstream licence and record provenance.
- [x] Locate or install a workspace-local toolchain and build the official authoring CLI without changing machine PATH or global configuration.
- [x] Add contract tests for no ray-tracing dependency, required stages/options, valid named-target ordering, all referenced files, engine pass gates, and archive root contents. Run before creating the pack; expect missing-pack failures.
- [x] Write validation tooling with a clear error if the checker is unavailable.

## Task 2: Surface lighting and water

Files: `horizon_lighting/horizon-shaders.toml`, `common.wgsl`, `lighting.wgsl`, `material.wgsl`, `entity.wgsl`.

Interfaces: `shade_surface(position: vec3<f32>, normal: vec3<f32>, light: vec2<f32>, albedo: vec3<f32>, emission: f32) -> vec3<f32>`; shared shadow function returns 0..1 visibility. Stage-local adapters supply texture/tint/coverage. Shared files avoid resource names absent from another stage.

- [x] Implement schema 1, API 0.2, linear blending, typed options/pages, gated 2048/96 shadow map, and gated water reflection.
- [x] Implement bounded PCF with angle/texel bias, map bounds and distance fades, and distinct ambient/block/direct/emission contributions.
- [x] Add terrain/entity adapters; preserve engine coverage and fog, account for existing face shade in tint.
- [x] Add water Fresnel/procedural ripple reflection, safe plane/face/underwater guards, and unchanged alpha coverage.
- [x] Run the official checker; fix signature, resource, uniformity, and option validation errors before continuing.

## Task 3: Atmosphere, bloom, and tone mapping

Files: `post/atmosphere.wgsl`, `post/bloom_extract.wgsl`, `post/bloom_horizontal.wgsl`, `post/bloom_vertical.wgsl`, `post/composite.wgsl`, `tonemap.wgsl`.

Interfaces: named targets `atmosphere`, `bloom_source`, `bloom_horizontal`, `bloom_vertical`; final composite reads `scene_color` and those targets. Atmospheric target stores additive scattering RGB; ordinary post outputs force alpha to 1, so existing engine fog provides extinction. Blur targets store linear bloom.

- [x] Add half-resolution shadow-map view integration with 12 default samples, finite sky reach, bounded density/phase, and dimension/weather/eye-medium guards.
- [x] Add depth-aware upsampling and subtle quarter-resolution bright extraction with horizontal/vertical blur.
- [x] Add full-resolution composition and a display-headroom-aware tone mapper; retain engine distance fog without a second full extinction pass.
- [x] Run contract tests and checker at default and low/high/disabled option combinations. Keep actual checker JSON reports.

## Task 4: Delivery and independent review

Files: `README.md`, `LICENSE`, `dist/horizon_lighting-0.1.0.hshader`, `validation/` reports, design/plan progress.

- [x] Package with the official CLI; inspect archive root/files and test archive equivalence to the source pack.
- [x] Document install path, effect limits, low/balanced/high settings, exact source/checker revision, commands/results, and runtime visual checklist.
- [x] Locate an available Horizon runtime for rendering; if absent, explicitly mark visual/performance verification pending.
- [x] Request one fresh independent code review, resolve material defects, rerun checks affected by changes, and regenerate the archive.
- [x] Run final package/contract/checker verification and link the installable archive.

## Execution decisions

User explicitly approved the design and said go ahead. Execute inline in this workspace without another plan approval. Do not initialise git or create an unrelated worktree merely for bookkeeping; retain progress here and in `docs/superpowers/progress.md`.
