override shadows: bool = true;
// PCF taps by preset: Lite 1 (engine bilinear), Balanced 5, High and Ultra 9.
override shadow_quality: i32 = select(select(3, 2, quality_preset == PRESET_BALANCED), 1,
    quality_preset == PRESET_LITE);

fn shadow_edge_fade(clip_xy: vec2<f32>) -> f32 {
    // Horizon culls casters against the square before warping shadow texels.
    let edge = max(abs(clip_xy.x), abs(clip_xy.y));
    return smoothstep(0.88, 1.0, edge);
}

fn shadow_uv(clip_xy: vec2<f32>) -> vec2<f32> {
    return shadow_distort(clip_xy) * vec2<f32>(0.5, -0.5) + vec2<f32>(0.5);
}

fn shadow_fallback() -> f32 {
    // Long cast shadows are most likely to leave coverage when the sun is low.
    let low_sun = sun_presence() * (1.0 - smoothstep(0.14, 0.36, frame.sun_direction.y));
    return mix(1.0, 0.28, low_sun);
}

// Used in surface and post stages; all three expose the engine's shadow helpers.
fn shadow_visibility(position: vec3<f32>, normal: vec3<f32>) -> f32 {
    if !shadows || frame.has_shadow == 0u || frame.dimension != 0 {
        return 1.0;
    }
    // Keep ground receivers tight to plant stems and walls; apply larger grazing clearance
    // only on steep/vertical block sides where PCF taps otherwise self-shadow.
    let radius = length(position.xz) / max(frame.shadow_distance, 1.0);
    let texel_world = max(frame.shadow_center_texel, 0.005) * (1.0 + radius * 3.0);
    let ndl = dot(normal, frame.light_direction);
    let slope = 1.0 - abs(ndl);
    let vertical = 1.0 - abs(normal.y);
    let away = 1.0 - max(ndl, 0.0);
    let normal_scale = mix(0.26 + 0.36 * slope, 0.75 + 1.50 * slope, vertical);
    let sun_pullback = vertical * (0.35 + 1.25 * away);
    let offset = normal * (texel_world * normal_scale)
        + frame.light_direction * (texel_world * sun_pullback);
    let clip = frame.shadow_view_proj * vec4<f32>(position + offset, 1.0);
    let edge_fade = shadow_edge_fade(clip.xy);
    if edge_fade >= 1.0 || clip.z >= 1.0 { return shadow_fallback(); }
    if clip.z <= 0.0 { return 1.0; }
    let p = vec3<f32>(shadow_uv(clip.xy), clip.z);
    let margin = 2.0 / max(frame.shadow_resolution, 1.0);
    if any(p.xy <= vec2<f32>(margin)) || any(p.xy >= vec2<f32>(1.0 - margin)) {
        return shadow_fallback();
    }
    let pcf = select(0.5, select(1.0, 1.45, shadow_quality >= 3), shadow_quality >= 2);
    let texel_scale = clamp(frame.shadow_center_texel / 0.031, 0.5, 4.0);
    let wall_bias = vertical * (0.00006 + 0.00080 * slope * slope) * (0.65 + 0.35 * pcf) * texel_scale;
    let z = p.z - (0.00009 + wall_bias);
    let step_uv = 1.0 / max(frame.shadow_resolution, 1.0);
    var lit = textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy, z);
    var count = 1.0;
    if shadow_quality >= 2 {
        lit += textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy + vec2<f32>(step_uv, 0.0), z);
        lit += textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy - vec2<f32>(step_uv, 0.0), z);
        lit += textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy + vec2<f32>(0.0, step_uv), z);
        lit += textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy - vec2<f32>(0.0, step_uv), z);
        count = 5.0;
    }
    if shadow_quality >= 3 {
        lit += textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy + vec2<f32>(step_uv, step_uv), z);
        lit += textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy + vec2<f32>(-step_uv, step_uv), z);
        lit += textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy + vec2<f32>(step_uv, -step_uv), z);
        lit += textureSampleCompareLevel(shadow_map, shadow_sampler, p.xy - vec2<f32>(step_uv, step_uv), z);
        count = 9.0;
    }
    if edge_fade <= 0.0 { return lit / count; }
    return mix(lit / count, shadow_fallback(), edge_fade);
}
