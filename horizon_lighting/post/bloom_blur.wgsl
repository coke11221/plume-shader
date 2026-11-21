fn bloom_tap_pair(source: texture_2d<f32>, uv: vec2<f32>, offset: vec2<f32>) -> vec3<f32> {
    return textureSampleLevel(source, linear_sampler, uv - offset, 0.0).rgb
        + textureSampleLevel(source, linear_sampler, uv + offset, 0.0).rgb;
}

fn blur_bloom(source: texture_2d<f32>, uv: vec2<f32>, axis: vec2<f32>) -> vec3<f32> {
    let texel = axis / vec2<f32>(textureDimensions(source));
    let centre = textureSampleLevel(source, linear_sampler, uv, 0.0).rgb;
    let step_uv = texel * select(1.35, 1.22, frame.dimension == 0 && frame.eye_in == 0u);
    return 0.227027 * centre
        + 0.316216 * bloom_tap_pair(source, uv, step_uv * 1.384615)
        + 0.070270 * bloom_tap_pair(source, uv, step_uv * 3.230769);
}
