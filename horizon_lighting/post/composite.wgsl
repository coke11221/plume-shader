override bloom_strength: f32 = select(0.0, 0.40, quality_preset >= PRESET_BALANCED);
override surface_reflections: bool = quality_preset >= PRESET_BALANCED;
override underwater_shafts: f32 = 2.0;
override contact_ao: bool = quality_preset >= PRESET_BALANCED;

fn upsample_contact_ao(uv: vec2<f32>, depth: f32) -> f32 {
    if !contact_ao || frame.dimension != 0 || frame.eye_in != 0u || depth <= 0.0 { return 0.0; }
    let distance = length(view_position(uv, depth));
    if distance >= 26.0 { return 0.0; }
    let full_size = vec2<f32>(textureDimensions(scene_depth));
    let receiver = surface_at(vec2<i32>(uv * full_size));
    if !receiver.present || !receives_contact_ao(receiver.data) { return 0.0; }

    let size = vec2<f32>(textureDimensions(contact_occlusion));
    let pixel = uv * size - 0.5;
    let base = floor(pixel);
    let fraction = fract(pixel);
    var contact = 0.0;
    var total = 0.0;
    for (var y = 0; y < 2; y++) {
        for (var x = 0; x < 2; x++) {
            let offset = vec2<f32>(f32(x), f32(y));
            let tap = vec2<i32>(clamp(base + offset, vec2<f32>(0.0), size - 1.0));
            let sample = textureLoad(contact_occlusion, tap, 0).rg;
            let spatial = mix(1.0 - fraction, fraction, offset);
            let depth_weight = 1.0 - smoothstep(0.04, 0.22 + 0.018 * distance, abs(sample.y - distance));
            let weight = spatial.x * spatial.y * depth_weight;
            contact += sample.x * weight;
            total += weight;
        }
    }
    return contact / max(total, 0.35);
}

fn apply_air_shafts_headroom(colour: vec3<f32>, scattering: vec3<f32>, strength: f32, headroom: f32) -> vec3<f32> {
    let luma = vec3<f32>(0.2126, 0.7152, 0.0722);
    let haze = mix(vec3<f32>(dot(scattering, luma)), scattering, 0.80);
    let peak = max(haze.r, max(haze.g, haze.b));
    let shoulder = (0.0165 + 0.070 * dot(max(colour, vec3<f32>(0.0)), luma)) * headroom;
    // Soft toe keeps dim background air and shadow gaps crystal clear while bright shafts shine cleanly.
    let contrast = peak / (peak + 0.032);
    return colour + haze * contrast * (shoulder / (shoulder + peak)) * (2.0 * strength);
}

fn apply_air_shafts(colour: vec3<f32>, scattering: vec3<f32>, strength: f32) -> vec3<f32> {
    return apply_air_shafts_headroom(colour, scattering, strength, 1.0);
}

fn distance_at_uv(uv: vec2<f32>) -> f32 {
    let d = depth_at(uv);
    if d == 0.0 { return max(frame.far, 1024.0); }
    return length(view_position(uv, d));
}

fn ray_distance_clamped(view_zero: vec4<f32>, view_dz: vec4<f32>, depth: f32, reach: f32) -> f32 {
    if depth <= 0.0 { return reach; }
    let view = view_zero + view_dz * depth;
    return min(length(view.xyz) / max(abs(view.w), 0.000001), reach);
}

fn upsample_atmosphere(uv: vec2<f32>, depth: f32, air_shafts: bool) -> vec3<f32> {
    let size = vec2<f32>(textureDimensions(atmosphere));
    let reach = atmosphere_reach(!air_shafts);
    let clip_zero = vec4<f32>(uv.x * 2.0 - 1.0, 1.0 - uv.y * 2.0, 0.0, 1.0);
    let view_zero = frame.projection_inverse * clip_zero;
    let view_dz = frame.projection_inverse[2];
    let here = ray_distance_clamped(view_zero, view_dz, depth, reach);

    // Continuous 5x5 convolution of a 4x4 box with linear interpolation:
    // gives all 16 phases of the 4x4 Bayer dither identical weight at every subpixel
    // with zero spatial shift, eliminating beam grain without stairstepping.
    let p = uv * size;
    let base = floor(p);
    let fraction = fract(p);
    var colour = vec3<f32>(0.0);
    var total = 0.0;
    var fallback_colour = vec3<f32>(0.0);
    var fallback_total = 0.0;
    for (var y = -2; y <= 2; y++) {
        let wy = select(1.0, select(fraction.y, 1.0 - fraction.y, y == -2), y == -2 || y == 2);
        for (var x = -2; x <= 2; x++) {
            let wx = select(1.0, select(fraction.x, 1.0 - fraction.x, x == -2), x == -2 || x == 2);
            let spatial = wx * wy;
            let tap = clamp(base + vec2<f32>(f32(x), f32(y)), vec2<f32>(0.0), size - 1.0);
            let tap_uv = (tap + 0.5) / size;
            let tap_dist = ray_distance_clamped(view_zero, view_dz, depth_at(tap_uv), reach);
            let sample_rgb = textureSampleLevel(atmosphere, nearest_sampler, tap_uv, 0.0).rgb;
            let delta = abs(tap_dist - here);
            let sigma = max(1.5, min(here, tap_dist) * 0.14);
            let weight = spatial * exp(-delta / sigma);
            colour += sample_rgb * weight;
            total += weight;

            // Path-length-scaled fallback for 1px geometry (bamboo stalks, distant leaves, vines)
            // whose depth falls between half-res depth taps: prevents both near-edge halos and black dropouts.
            let path_scale = min(here / max(tap_dist, 0.5), 1.0);
            fallback_colour += sample_rgb * (spatial * path_scale);
            fallback_total += spatial;
        }
    }
    let bilateral = colour / max(total, 0.0001);
    let fallback = fallback_colour / max(fallback_total, 0.0001);
    let support = smoothstep(0.15, 1.5, total);
    return mix(fallback, bilateral, support);
}

fn upsample_reflection(uv: vec2<f32>) -> vec3<f32> {
    if !surface_reflections || gloss_strength <= 0.0 || !uses_pack_lighting()
        || frame.eye_in != 0u || max(frame.night_vision, max(frame.blindness, frame.darkness)) > 0.01 {
        return vec3<f32>(0.0);
    }
    let full_size = vec2<i32>(textureDimensions(scene_depth));
    let receiver = surface_at(clamp(vec2<i32>(uv * vec2<f32>(full_size)), vec2<i32>(0), full_size - 1));
    if !receiver.present || receiver.smoothness <= 0.0 { return vec3<f32>(0.0); }
    let size = vec2<f32>(textureDimensions(surface_reflection));
    let pixel = uv * size - 0.5;
    let base = floor(pixel);
    let fraction = fract(pixel);
    let here = distance_at_uv(uv);
    var colour = vec3<f32>(0.0);
    var total = 0.0;
    for (var y = 0; y < 2; y++) {
        for (var x = 0; x < 2; x++) {
            let offset = vec2<f32>(f32(x), f32(y));
            let tap_uv = clamp((base + offset + 0.5) / size, 0.5 / size, 1.0 - 0.5 / size);
            let sample_surface = surface_at(clamp(vec2<i32>(tap_uv * vec2<f32>(full_size)), vec2<i32>(0), full_size - 1));
            if !sample_surface.present || sample_surface.smoothness <= 0.0
                || dot(receiver.normal, sample_surface.normal) < 0.95
                || abs(receiver.smoothness - sample_surface.smoothness) > 0.04 { continue; }
            let delta = abs(distance_at_uv(tap_uv) - here);
            let spatial = mix(1.0 - fraction, fraction, offset);
            let weight = spatial.x * spatial.y * exp(-delta / max(0.15, here * 0.01));
            colour += textureSampleLevel(surface_reflection, nearest_sampler, tap_uv, 0.0).rgb * weight;
            total += weight;
        }
    }
    let position = view_position(uv, depth_at(uv));
    let view = safe_direction(-position);
    let fresnel = fresnel_schlick(decode_f0(receiver.data), max(dot(view, receiver.normal), 0.0));
    let visibility = surface_visibility(position);
    return colour / max(total, 0.0001) * fresnel * receiver.smoothness * receiver.smoothness
        * surface_gloss_strength() * visibility;
}

fn post(input: PostInput) -> vec4<f32> {
    var c = textureSampleLevel(scene_color, linear_sampler, input.uv, 0.0).rgb;
    c *= 1.0 - upsample_contact_ao(input.uv, input.depth);
    if pack_underwater() && input.depth == 0.0 {
        let effects = clamp(max(frame.blindness, frame.darkness), 0.0, 1.0);
        c = mix(c, underwater_haze(), 1.0 - effects);
    }
    c += upsample_reflection(input.uv);
    let shaft_strength = air_shaft_strength();
    let air_shafts = frame.eye_in == 0u && frame.has_shadow != 0u && shaft_strength > 0.0;
    let water_shafts = frame.eye_in == 1u && underwater_shafts > 0.0;
    if frame.dimension == 0 && (air_shafts || water_shafts) {
        let scattering = upsample_atmosphere(input.uv, input.depth, air_shafts);
        if air_shafts {
            let night_headroom = select(1.30, 1.75, quality_preset >= PRESET_ULTRA);
            let headroom = select(night_headroom, shaft_headroom, frame.sun_direction.y >= 0.0);
            c = apply_air_shafts_headroom(c, scattering, shaft_strength, headroom);
        } else {
            c += scattering;
        }
    }
    if bloom_strength > 0.0 {
        c += textureSampleLevel(bloom_vertical, linear_sampler, input.uv, 0.0).rgb * bloom_strength;
    }
    // Fog the resolved scene once, including reflection and bloom.
    if custom_fog && frame.dimension == 0 && frame.eye_in == 0u && input.depth > 0.0 {
        let point = view_position(input.uv, input.depth);
        let size = vec2<i32>(textureDimensions(scene_depth));
        let pixel = clamp(vec2<i32>(input.uv * vec2<f32>(size)), vec2<i32>(0), size - 1);
        // The client's cloud layer can write depth. Keep high backdrop pixels out of the fog.
        if point.y <= 16.0 || surface_at(pixel).present {
            c = apply_custom_fog(c, length(point));
        }
    }
    return vec4<f32>(sanitize_rgb(c), 1.0);
}
