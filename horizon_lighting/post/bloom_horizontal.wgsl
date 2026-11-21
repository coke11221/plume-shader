override bloom_strength: f32 = select(0.0, 0.40, quality_preset >= PRESET_BALANCED);

fn post(input: PostInput) -> vec4<f32> {
    if bloom_strength <= 0.0 { return vec4<f32>(0.0, 0.0, 0.0, 1.0); }
    return vec4<f32>(blur_bloom(bloom_source, input.uv, vec2<f32>(1.0, 0.0)), 1.0);
}
