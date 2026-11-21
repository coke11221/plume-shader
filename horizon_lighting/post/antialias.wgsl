override edge_smoothing: bool = quality_preset >= PRESET_BALANCED;

fn post(input: PostInput) -> vec4<f32> {
    if !edge_smoothing { return input.color; }
    let texel = 1.0 / vec2<f32>(textureDimensions(previous));
    let nw = textureSampleLevel(previous, linear_sampler, input.uv + texel * vec2<f32>(-1.0, -1.0), 0.0).rgb;
    let ne = textureSampleLevel(previous, linear_sampler, input.uv + texel * vec2<f32>(1.0, -1.0), 0.0).rgb;
    let sw = textureSampleLevel(previous, linear_sampler, input.uv + texel * vec2<f32>(-1.0, 1.0), 0.0).rgb;
    let se = textureSampleLevel(previous, linear_sampler, input.uv + texel * vec2<f32>(1.0, 1.0), 0.0).rgb;
    // Perceptual luminance for edge detection; RGB sampling/averaging stays linear.
    let luma = vec4<f32>(sqrt(max(dot(nw, frame.luminance), 0.0)),
                         sqrt(max(dot(ne, frame.luminance), 0.0)),
                         sqrt(max(dot(sw, frame.luminance), 0.0)),
                         sqrt(max(dot(se, frame.luminance), 0.0)));
    let centre = sqrt(max(dot(input.color.rgb, frame.luminance), 0.0));
    let low = min(centre, min(min(luma.x, luma.y), min(luma.z, luma.w)));
    let high = max(centre, max(max(luma.x, luma.y), max(luma.z, luma.w)));
    if high - low < max(0.035, high * 0.125) { return input.color; }
    var direction = vec2<f32>(-((luma.x + luma.y) - (luma.z + luma.w)),
                               (luma.x + luma.z) - (luma.y + luma.w));
    let reduce = max(dot(luma, vec4<f32>(0.03125)), 0.0078125);
    let scale = 1.0 / (min(abs(direction.x), abs(direction.y)) + reduce);
    direction = clamp(direction * scale, vec2<f32>(-6.0), vec2<f32>(6.0)) * texel;
    let a = 0.5 * (textureSampleLevel(previous, linear_sampler, input.uv + direction * (-1.0 / 6.0), 0.0).rgb
                 + textureSampleLevel(previous, linear_sampler, input.uv + direction * (1.0 / 6.0), 0.0).rgb);
    let b = a * 0.5 + 0.25 * (textureSampleLevel(previous, linear_sampler, input.uv - direction * 0.5, 0.0).rgb
                           + textureSampleLevel(previous, linear_sampler, input.uv + direction * 0.5, 0.0).rgb);
    let b_luma = sqrt(max(dot(b, frame.luminance), 0.0));
    return vec4<f32>(select(b, a, b_luma < low || b_luma > high), 1.0);
}
