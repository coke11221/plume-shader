# Natural Lighting Refinement Implementation Plan

**Goal** · Bring v0.5.1 closer to the four lighting references using the existing Shader API 0.2 stages and fixed exposure.

1. Capture v0.5.1 in GoldenLab at noon, afternoon, golden hour, overcast and midnight. Include an oak canopy, cherry foliage, a sealed room and a shoreline. Measure a five-second GPU flight on Vulkan.
2. In `lighting.wgsl`, use the shared sky dome for cool diffuse fill and ease the squared skylight falloff on outdoor daytime receivers, especially foliage. Keep the cave threshold and retain the existing night calculation. Check canopy texture, orientation and sun/shade contrast before changing pigments.
3. In `common.wgsl` and `lighting.wgsl`, give afternoon sun a gentle warm tint and strengthen the warm key at low elevation. Keep cloud shading and the solar direction shared. In `material.wgsl`, taper the pigment boost on strongly green texels to keep biome variation.
4. In `fog.wgsl`, soften the approach into mid-distance haze and bias clear daylight haze toward the blue sky. Keep height integration, water routing and weather ownership. Review the existing tone mapper and bloom using the rendered comparisons.
5. Package v0.5.2 and repeat the matched fixtures and timing. Check a sunset transition and water crossing in motion, compare Vulkan and DirectX 12 on the pinned client, run `./tools/check.ps1 -Package`, and record screenshots and limits.
