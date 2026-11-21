# Wet-surface recovery and aerial perspective implementation plan

**Goal:** Keep rain visible on exposed terrain and add distance separation between Overworld ridges.

**Architecture:** Diagnose the 0.4.1 wet finish using its archived pack and a matched clear/rain fixture. Integrate a height-varying air density along the camera ray in material fog, where terrain already contributes to the pre-water snapshot. Use the same air transmission for the reflected light added later by the solid-surface post pass. Keep optional custom fog as a separate, explicit final grade.

**Spec:** [Roadmap milestone 2](2026-11-17-photon-inspired-roadmap.md#milestone-2--add-height-dependent-aerial-perspective) and [handoff](../../NEXT-SESSION.md).

- [x] Capture archived 0.4.1 in the isolated raster fixture, including rain, valley, shoreline, and submerged views.
- [x] Verify wetness eligibility and reflection strength from material inputs through the final pass; reproduce weak wetness in the relevant input range before changing the response.
- [x] Add GPU checks for near/mid/far air haze, ray height and direction, and preserved water and status effect routing.
- [x] Implement bounded height integration with the shared sky tint and no new passes. Validate both material and post contributions.
- [x] Package a new version and compare paired captures and timings. [Results and limits](../../../validation/0.4.2/REVIEW.md)
