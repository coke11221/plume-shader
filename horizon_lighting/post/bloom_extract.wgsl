override bloom_strength: f32 = select(0.0, 0.40, quality_preset >= PRESET_BALANCED);

fn bloom_response(colour: vec3<f32>, threshold: f32, knee_half: f32, peak_weight: f32) -> vec3<f32> {
    let c = max(colour, vec3<f32>(0.0));
    // Preserve colored highlights that carry more energy in one channel than in luma.
    let brightness = max(dot(c, frame.luminance), peak_weight * max(c.r, max(c.g, c.b)));
    let knee = clamp(brightness - (threshold - knee_half), 0.0, 2.0 * knee_half);
    let amount = max(brightness - threshold, knee * knee / (4.0 * knee_half)) / max(brightness, 0.0001);
    return c * amount;
}

fn bright_part(colour: vec3<f32>) -> vec3<f32> {
    var threshold = 0.85;
    if frame.dimension == -1 { threshold = 0.95; }
    if frame.dimension == 1 { threshold = 0.90; }
    return bloom_response(colour, threshold, 0.27, 0.72);
}

fn emissive_part(colour: vec3<f32>) -> vec3<f32> {
    var threshold = 0.56;
    if frame.dimension == -1 { threshold = 0.65; }
    if frame.dimension == 1 { threshold = 0.60; }
    return bloom_response(colour, threshold, 0.18, 0.85);
}

fn terrain_bloom(colour: vec3<f32>, source: u32, foliage_edge: f32) -> vec3<f32> {
    let level = f32(source & 31u) / 30.0;
    let glint = level * level * 3.10;
    let peak = max(colour.r, max(colour.g, colour.b));
    let pigment = colour / max(peak, 0.0001);
    let sun = sun_colour();
    let sun_tint = sun / max(max(sun.r, max(sun.g, sun.b)), 0.0001);
    var solar = mix(sun_tint, pigment, 0.60) * min(peak, glint);
    if (source & BLOOM_FOLIAGE) != 0u {
        // Seed the glow on the visible leaves and grass, using sun colour with a light pigment tint.
        solar = mix(vec3<f32>(1.0), pigment, 0.16) * sun_tint * (foliage_edge * glint);
    }
    if (source & BLOOM_EMISSIVE) != 0u { return max(solar, 1.50 * emissive_part(colour)); }
    return solar;
}

fn foliage_edge_at(pixel: vec2<i32>, depth: f32, size: vec2<i32>) -> f32 {
    let low = vec2<i32>(0);
    let high = size - 1;
    let left = textureLoad(scene_depth, clamp(pixel - vec2<i32>(2, 0), low, high), 0);
    let right = textureLoad(scene_depth, clamp(pixel + vec2<i32>(2, 0), low, high), 0);
    let above = textureLoad(scene_depth, clamp(pixel - vec2<i32>(0, 2), low, high), 0);
    let below = textureLoad(scene_depth, clamp(pixel + vec2<i32>(0, 2), low, high), 0);
    let gap = 1.0 - min(min(left, right), min(above, below)) / max(depth, 0.000001);
    return smoothstep(0.025, 0.13, gap);
}

fn post(input: PostInput) -> vec4<f32> {
    if bloom_strength <= 0.0 { return vec4<f32>(0.0, 0.0, 0.0, 1.0); }
    let size = vec2<i32>(textureDimensions(scene_color));
    let first = vec2<i32>(floor(input.uv * vec2<f32>(size) - 1.5));
    let geometry_only = frame.dimension == 0 && frame.eye_in == 0u;
    var sum = vec3<f32>(0.0);
    // Extract highlights before averaging so single-pixel flames survive the downsample.
    for (var y = 0; y < 4; y++) {
        for (var x = 0; x < 4; x++) {
            let pixel = clamp(first + vec2<i32>(x, y), vec2<i32>(0), size - 1);
            if geometry_only {
                // The sun disc and procedural clouds already carry their own glare.
                let depth = textureLoad(scene_depth, pixel, 0);
                if depth == 0.0 { continue; }
                let surface = surface_at(pixel);
                if surface.present {
                    let source = surface_data_bits(surface.data) >> 24u;
                    if (source & (BLOOM_EMISSIVE | 31u)) == 0u { continue; }
                    var foliage_edge = 0.0;
                    if (source & BLOOM_FOLIAGE) != 0u { foliage_edge = foliage_edge_at(pixel, depth, size); }
                    sum += terrain_bloom(textureLoad(scene_color, pixel, 0).rgb, source, foliage_edge);
                    continue;
                }
            }
            sum += bright_part(textureLoad(scene_color, pixel, 0).rgb);
        }
    }
    return vec4<f32>(sum / 16.0, 1.0);
}
