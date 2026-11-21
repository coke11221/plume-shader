override exposure: f32 = 1.0;

fn roll_off(value: vec3<f32>, shoulder: f32, peak: f32) -> vec3<f32> {
    let room = peak - shoulder;
    return min(value, vec3<f32>(shoulder)) + room
        * (vec3<f32>(1.0) - exp(-max(value - shoulder, vec3<f32>(0.0)) / room));
}

fn tonemap(input: TonemapInput) -> vec3<f32> {
    let c = max(input.color * exposure, vec3<f32>(0.0));
    let peak = max(frame.headroom, 1.0);
    let effect = clamp(max(frame.night_vision, max(frame.blindness, frame.darkness)), 0.0, 1.0);
    if frame.dimension != 0 || frame.eye_in != 0u || effect >= 1.0 {
        return roll_off(c, peak * 0.6, peak);
    }
    // Clean natural contrast, balanced saturation, and warm midtones without overexposing highlights.
    let luma = dot(c, vec3<f32>(0.2126, 0.7152, 0.0722));
    let toe = smoothstep(0.015, 0.14, luma);
    let mid = smoothstep(0.05, 0.48, luma);
    let graded_scalar = mix(0.86, 0.95, toe) + 0.07 * mid;
    var graded = c * graded_scalar;
    let sat_weight = 1.0 - smoothstep(0.50, 0.98, luma);
    let g_luma = luma * graded_scalar;
    graded = max(mix(vec3<f32>(g_luma), graded, 1.0 + 0.14 * sat_weight), vec3<f32>(0.0));
    let warm_weight = smoothstep(0.025, 0.24, luma) * (1.0 - smoothstep(0.55, 0.98, luma));
    graded *= mix(vec3<f32>(1.0), vec3<f32>(1.03, 1.005, 0.955), warm_weight);
    // Time-of-day outdoor world color grade: warm golden amber at sunrise, deeper
    // orange-red at sunset. Zero effect at midday, night, heavy rain, or in caves.
    let sun_y = frame.sun_direction.y;
    let sun_horiz = length(frame.sun_direction.xz);
    let golden_band = smoothstep(-0.08, 0.05, sun_y) * (1.0 - smoothstep(0.24, 0.56, sun_y))
        * smoothstep(0.10, 0.50, sun_horiz);
    let outdoors = smoothstep(0.08, 0.65, frame.eye_light_smooth.y);
    let clear_sky = (1.0 - 0.70 * clamp(frame.rain, 0.0, 1.0))
        * (1.0 - 0.50 * clamp(frame.thunder, 0.0, 1.0));
    let golden_grade = golden_band * outdoors * clear_sky;
    if golden_grade > 0.0 {
        // Sunrise (+X): warm honey-gold; Sunset (-X): richer warm orange-red.
        let sunset_t = 1.0 - smoothstep(-0.55, 0.55, frame.sun_direction.x);
        let grade_mask = smoothstep(0.004, 0.08, luma) * (1.0 - smoothstep(0.58, 0.96, luma));
        let sunrise_tint = vec3<f32>(1.14, 0.99, 0.78);
        let sunset_tint = vec3<f32>(1.24, 0.91, 0.66);
        graded *= mix(vec3<f32>(1.0), mix(sunrise_tint, sunset_tint, sunset_t), golden_grade * grade_mask);
        // Subtle warm split-tone in shadows so water reflections and dark foliage join the warm mood.
        let shadow_mask = smoothstep(0.002, 0.03, luma) * (1.0 - smoothstep(0.04, 0.34, luma));
        let shadow_tint = mix(vec3<f32>(1.08, 0.99, 0.86), vec3<f32>(1.16, 0.92, 0.76), sunset_t);
        graded *= mix(vec3<f32>(1.0), shadow_tint, golden_grade * shadow_mask * 0.75);
    }
    let brightest = max(graded.r, max(graded.g, graded.b));
    let shoulder = peak * 0.54;
    var mapped = graded;
    if brightest > shoulder {
        // Compress one shared multiplier to preserve color ratios up to display peak.
        let room = peak - shoulder;
        let highlight = shoulder + room * (1.0 - exp((shoulder - brightest) / room));
        mapped *= highlight / brightest;
    }
    if effect > 0.0 { return mix(mapped, roll_off(c, peak * 0.6, peak), effect); }
    return mapped;
}
