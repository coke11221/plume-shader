fn entity_overlay(base: vec3<f32>, overlay: vec4<f32>) -> vec3<f32> {
    return pow(mix(pow(max(base, vec3<f32>(0.0)), vec3<f32>(1.0 / 2.2)),
                   pow(max(overlay.rgb, vec3<f32>(0.0)), vec3<f32>(1.0 / 2.2)),
                   overlay.a), vec3<f32>(2.2));
}

fn entity(input: EntityInput) -> Surface {
    let base = input.albedo.rgb * input.tint.rgb;
    // Custom directional light replaces vanilla shade; vanilla fallback must
    // retain that shade BEFORE applying vanilla's gamma-space hurt/TNT overlay.
    let flashed = entity_overlay(base, input.overlay);
    let vanilla_flashed = entity_overlay(base * input.shade, input.overlay);
    let alpha = input.albedo.a * input.tint.a;
    if !uses_pack_lighting() || frame.eye_in == 2u {
        let fallback_dynamic = select(vec3<f32>(0.0), input.colored_light * dynamic_light_strength, dynamic_lights);
        let lit = vanilla_flashed * (input.lightmap + fallback_dynamic);
        return Surface(vec4<f32>(surface_fog(max(lit, vec3<f32>(0.0)), input.position), alpha));
    }
    let dimension_lighting = frame.dimension != 0;
    let local = local_surface_light(input.position, input.light.x, input.colored_light);
    let albedo = select(flashed, vanilla_flashed, dimension_lighting);
    let entity_emission = select(0.0, clamp(f32(input.light_source_tier) / 3.0, 0.0, 1.0), input.light_source_tier > 0u);
    let raw_n = input.normal;
    let n_len_sq = dot(raw_n, raw_n);
    let n = select(safe_direction(-input.position), raw_n * inverseSqrt(max(n_len_sq, 0.0001)),
        n_len_sq > 0.0001 && n_len_sq < 4.0);
    let lit = shade_surface(input.position, n, input.light.y, albedo, entity_emission, local,
        false, false, 0.0);
    let vanilla_light = input.lightmap + select(vec3<f32>(0.0), input.colored_light, dynamic_lights && dimension_lighting);
    let with_effects = respect_effects(lit, vanilla_flashed, vanilla_light);
    let with_scatter = apply_block_air_scatter(with_effects, input.position, input.light.x);
    let colour = sanitize_rgb(with_scatter);
    return Surface(vec4<f32>(surface_fog(colour, input.position), alpha));
}
