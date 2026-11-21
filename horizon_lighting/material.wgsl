override wetness_strength: f32 = 1.0;
override wet_in_clear: bool = false;
override dry_sun_strength: f32 = 1.0;
override contact_ao: bool = quality_preset >= PRESET_BALANCED;
override surface_micro_relief: bool = quality_preset >= PRESET_BALANCED;

// Bit 0 is the rooted_grass sprite tag in the manifest.
const ROOTED_GRASS: u32 = 1u;

fn material(input: MaterialInput) -> Surface {
    if input.translucent {
        // Return zero coverage so a clear underwater interface leaves the scene depth intact.
        if input.albedo.a < 0.01 || (pack_underwater() && input.fluid == 1u) {
            return Surface(vec4<f32>(0.0));
        }
        return shade_material(input);
    }
    // Horizon uses this alpha for the original texture cutout and stores covered solids opaque.
    return Surface(vec4<f32>(shade_material(input).color.rgb, input.albedo.a));
}

fn tex_height(texel: vec4<f32>, fallback: f32) -> f32 {
    if texel.a < 0.5 { return fallback; }
    return sqrt(max(dot(texel.rgb, vec3<f32>(0.2126, 0.7152, 0.0722)), 0.0));
}

fn face_fallback_normal(face: u32, position: vec3<f32>) -> vec3<f32> {
    var fallback = vec3<f32>(1.0, 0.0, 0.0);
    switch face {
        case 0u: { fallback = vec3<f32>(0.0, -1.0, 0.0); }
        case 1u: { fallback = vec3<f32>(0.0, 1.0, 0.0); }
        case 2u: { fallback = vec3<f32>(0.0, 0.0, -1.0); }
        case 3u: { fallback = vec3<f32>(0.0, 0.0, 1.0); }
        case 4u: { fallback = vec3<f32>(-1.0, 0.0, 0.0); }
        default: {}
    }
    return select(fallback, -fallback, dot(fallback, position) > 0.0);
}

fn shade_material(input: MaterialInput) -> Surface {
    let vanilla_base = input.albedo.rgb * input.shaded_tint.rgb;
    let alpha = input.albedo.a * input.shaded_tint.a;
    if !uses_pack_lighting() || frame.eye_in == 2u || (frame.dimension == -1 && input.fluid == 1u) {
        let fallback_dynamic = select(vec3<f32>(0.0), input.colored_light * dynamic_light_strength, dynamic_lights);
        return Surface(vec4<f32>(surface_fog(vanilla_base * (input.lightmap + fallback_dynamic), input.position), alpha));
    }
    if input.fluid == 1u && input.translucent { return shade_water(input); }
    // Preserve baked tint, AO and model shade. Normals face the camera and do
    // not identify the model's original shade (notably water viewed from below).
    // Guard against degenerate/NaN derivative normals on subpixel grazing faces (e.g. bamboo stalks).
    let raw_n = input.normal;
    let n_len_sq = dot(raw_n, raw_n);
    let n = select(face_fallback_normal(input.face, input.position),
        raw_n * inverseSqrt(max(n_len_sq, 0.0001)),
        n_len_sq > 0.0001 && n_len_sq < 4.0);
    let grass = is_thin_plant(input.material);
    let leaves = input.material == 42u;
    let stalk = input.material == 48u;
    let grass_surface = grass || input.material == 41u || stalk;
    var wetness = 0.0;
    let overworld = frame.dimension == 0;
    let solid_terrain = overworld && !input.translucent && input.fluid == 0u && frame.eye_in == 0u;
    // Use the original biome-tinted pigment so soil and autumn leaves keep their hues.
    let green_receiver = overworld && (grass_surface || leaves)
        && vanilla_base.g > max(vanilla_base.r, vanilla_base.b);
    if solid_terrain {
        // Free water forms a sheen well before the rain transition reaches its peak.
        let rain = clamp(frame.rain, 0.0, 1.0);
        let moisture = select(rain * (2.0 - rain), 1.0, wet_in_clear);
        // Upward faces collect more water. Exposed sides still develop a film.
        let exposure = select(mix(0.72, 1.0, smoothstep(-0.65, 0.95, n.y)), 1.0, grass || stalk);
        // Baked skylight can lose levels near terrain edges and foliage even on open tops.
        wetness = moisture * wetness_strength * smoothstep(0.55, 0.82, input.light.y) * exposure;
    }
    // Moisture changes the brightness of the original pigment uniformly across RGB.
    let darkening = select(0.32, 0.24, green_receiver);
    let base = vanilla_base * (1.0 - wetness * darkening);
    let soft_foliage = grass || leaves || stalk;
    let wet_smoothness = select(0.86, 0.73, soft_foliage);
    let wet_f0 = select(0.050, 0.030, soft_foliage);
    let coating = wetness;
    let top = n.y >= 0.98;
    let dry_finish = select(vec2<f32>(0.0), surface_finish(input.material), solid_terrain || top);
    var finish = dry_finish;
    finish.x = mix(finish.x, max(finish.x, wet_smoothness), coating);
    let f0 = surface_f0(base, finish.y) + vec3<f32>(coating * (1.0 - finish.y) * wet_f0);
    // Balance diffuse energy cleanly on top metallic faces.
    let local_metalness = select(0.0, finish.y, top);
    var relief_fade = 0.0;
    var n_bump = n;
    var relief_tint = 1.0;
    if surface_micro_relief && solid_terrain && !grass && !leaves && !grass_surface && input.material != 61u && input.emission <= 0.0 && length(input.tangent.xyz) > 0.5 && !block_pbr_maps() {
        let dist_fade = 1.0 - smoothstep(8.0, 26.0, length(input.position));
        let relief_scale = select(0.55, 0.15, dry_finish.x > 0.0);
        relief_fade = dist_fade * relief_scale;
        if relief_fade > 0.0 {
            let tex_size = max(block_texture_size(), vec2<f32>(16.0));
            let inv_tex = 1.0 / tex_size;
            let texel = fract(input.uv * (tex_size / 16.0)) * 16.0;
            let h0 = tex_height(input.albedo, 0.0);
            let h_l = select(h0, tex_height(block_texture_level(input.uv - vec2<f32>(inv_tex.x, 0.0), 0.0), h0), texel.x > 0.75);
            let h_r = select(h0, tex_height(block_texture_level(input.uv + vec2<f32>(inv_tex.x, 0.0), 0.0), h0), texel.x < 15.25);
            let h_u = select(h0, tex_height(block_texture_level(input.uv - vec2<f32>(0.0, inv_tex.y), 0.0), h0), texel.y > 0.75);
            let h_d = select(h0, tex_height(block_texture_level(input.uv + vec2<f32>(0.0, inv_tex.y), 0.0), h0), texel.y < 15.25);
            let dhdx = clamp((h_r - h_l) * select(1.0, 0.5, texel.x > 0.75 && texel.x < 15.25), -0.24, 0.24);
            let dhdy = clamp((h_d - h_u) * select(1.0, 0.5, texel.y > 0.75 && texel.y < 15.25), -0.24, 0.24);
            let ortho_t = input.tangent.xyz - n * dot(n, input.tangent.xyz);
            let ortho_t_sq = dot(ortho_t, ortho_t);
            if ortho_t_sq > 0.0001 && ortho_t_sq < 4.0 {
                let tangent_dir = ortho_t * inverseSqrt(ortho_t_sq);
                let bitangent_dir = cross(n, tangent_dir) * input.tangent.w;
                n_bump = safe_direction(n - (0.65 * relief_fade) * (dhdx * tangent_dir + dhdy * bitangent_dir));
                let avg_h = 0.25 * (h_l + h_r + h_u + h_d);
                let crevice = clamp(avg_h - h0, 0.0, 0.14);
                let ridge = clamp(h0 - avg_h, 0.0, 0.12);
                let sky_tilt = clamp(1.0 + 0.08 * (n_bump.y - n.y) * relief_fade, 0.92, 1.08);
                // Keep stone/mineral micro-relief crisp and clean without muddy crevice smudging.
                relief_tint = clamp((1.0 - crevice * 0.35 * relief_fade + ridge * 0.14 * relief_fade) * sky_tilt, 0.90, 1.08);
            }
        }
    }
    let gloss = surface_gloss_strength();
    let dirt_surface = solid_terrain && (input.material == 61u || (input.material == 41u && !green_receiver));
    var diffuse_base = base * (1.0 - local_metalness * 0.65 * min(gloss, 1.0)) * relief_tint;
    if stalk && abs(n.y) < 0.5 {
        // Bamboo stalks are thin 3D prisms with Minecraft's 0.6/0.8 cardinal darken baked in,
        // while their attached bamboo leaves are unshaded. Recover true pigment on all sides.
        let stalk_tint_peak = max(input.shaded_tint.r, max(input.shaded_tint.g, input.shaded_tint.b));
        if stalk_tint_peak < 0.92 {
            let unshade = mix(1.0 / pow(0.8, 2.2), 1.0 / pow(0.6, 2.2), abs(n.x));
            diffuse_base *= min(unshade, 1.0 / max(stalk_tint_peak, 0.30));
        }
    }
    if dirt_surface {
        // Gently tame only the most extreme dark/bright dirt texels without flattening grain.
        let dirt_sun = sun_presence() * smoothstep(0.30, 0.78, input.light.y)
            * smoothstep(0.0, 0.25, dot(n, frame.light_direction));
        let dirt_tex_luma = dot(input.albedo.rgb, vec3<f32>(0.2126, 0.7152, 0.0722));
        let dirt_balance = mix(1.10, 0.93, smoothstep(0.05, 0.30, dirt_tex_luma));
        diffuse_base *= mix(1.0, dirt_balance, dirt_sun);
    }
    let noon_fill = select(0.0, high_sun(), !grass && input.fluid == 0u && frame.eye_in == 0u);
    let local = local_surface_light(input.position, input.light.x, input.colored_light);
    let dry_material = solid_terrain && input.emission <= 0.0;
    let dry = dry_light_response(input.material);
    var response = vec2<f32>(0.0);
    if dry_material {
        // Keep broad dry highlights out of the wet and polished reflection buffers,
        // and break up flat block faces with micro-relief grain so dry terrain stays rough.
        let base_dry_glint = select(dry.x, 0.022, dirt_surface);
        var dry_glint = base_dry_glint * f32(dry_finish.x == 0.0) * (1.0 - wetness);
        if relief_fade > 0.0 && dry_glint > 0.0 && !soft_foliage {
            let view = safe_direction(-input.position);
            let half_v = safe_direction(view + frame.light_direction);
            let flat_nh = max(dot(n, half_v), 0.0);
            let bump_nh = max(dot(n_bump, half_v), 0.0);
            let micro_grain = clamp(pow(bump_nh / max(flat_nh, 0.08), 2.2) * relief_tint, 0.35, 1.65);
            dry_glint *= mix(1.0, micro_grain, relief_fade);
        }
        response = vec2<f32>(dry_glint, dry.y) * dry_sun_strength;
    }
    let rough_solar = select(0.0, 1.85, input.material == 60u) * dry_sun_strength;
    let coated_solar = 6.5 * gloss;
    let solar = select(0.0, mix(rough_solar, coated_solar, select(coating, 1.0, dry_finish.x > 0.0)), solid_terrain && !soft_foliage);
    let dry_smoothness = max(dry_finish.x, select(0.0, 0.45 + 0.50 * dry.x, rough_solar > 0.0));
    let solar_smoothness = mix(dry_smoothness, max(dry_smoothness, wet_smoothness), coating);
    let smoothness = select(finish.x, solar_smoothness, frame.sun_direction.y > 0.0 && solar > 0.0);
    let highlight = surface_highlight(input.position, n_bump, smoothness, f0, vanilla_base,
        vec2<f32>(solar, select(0.0, gloss, finish.x > 0.0)));
    // Offset 3-texel-wide bamboo stalks slightly toward the light so their side and backlit faces
    // escape self-shadowing while still catching real cast shadows from trees and terrain.
    let shade_position = select(input.position, input.position + frame.light_direction * 0.22, stalk && solid_terrain);
    let lighting = shade_surface_with_celestial_response(shade_position, n, input.light.y, diffuse_base, input.emission, local,
        grass, leaves || stalk, green_receiver, dry_material && !grass && !stalk, noon_fill, response, highlight);
    var root_visibility = 1.0;
    if contact_ao && solid_terrain && grass && (input.tags & ROOTED_GRASS) != 0u {
        // Sprite V grows toward the roots. Cutout grass uses flat baked lighting.
        root_visibility = 1.0 - 0.59 * smoothstep(0.44, 0.98, input.uv.y);
    }
    var lit = lighting.rgb * root_visibility;
    let base_ndotl = dot(n, frame.light_direction);
    let sunlit_sky = sun_presence() * smoothstep(0.30, 0.78, input.light.y);
    if solid_terrain && !soft_foliage && input.emission <= 0.0 && base_ndotl > 0.02 {
        let luma_lit = dot(lighting.rgb, vec3<f32>(0.2126, 0.7152, 0.0722));
        let ambient_floor = dot(vanilla_base, vec3<f32>(0.2126, 0.7152, 0.0722)) * (0.04 + 0.14 * input.light.y);
        let direct_ratio = smoothstep(ambient_floor, ambient_floor + 0.12, luma_lit);
        // Cleanly unshade Minecraft's baked cardinal face darken (0.6 on +-X, 0.8 on +-Z)
        // on directly sunlit walls, without amplifying torch-lit walls.
        let side_axis = smoothstep(0.95, 0.995, max(abs(n.x), abs(n.z))) * (1.0 - smoothstep(0.20, 0.86, abs(n.y)));
        let tint_peak = max(input.shaded_tint.r, max(input.shaded_tint.g, input.shaded_tint.b));
        let mc_darken = smoothstep(0.92, 0.68, tint_peak) * side_axis;
        if mc_darken > 0.0 && sunlit_sky > 0.0 {
            let full_unshade = mix(1.0 / pow(0.8, 2.2), 1.0 / pow(0.6, 2.2), abs(n.x));
            let overhead = max(frame.light_direction.y, 0.0);
            let already = clamp(overhead * full_unshade / max(base_ndotl, 0.001), 1.0, full_unshade);
            let unshade = clamp(full_unshade / already, 1.0, 2.00);
            let block_light_guard = 1.0 - smoothstep(0.32, 0.76, max(input.light.x, 0.0));
            lit *= mix(1.0, unshade, mc_darken * direct_ratio * sunlit_sky * block_light_guard);
        }
        if relief_fade > 0.0 {
            let bump_ndotl = max(dot(n_bump, frame.light_direction), 0.0);
            let dir_delta = clamp((bump_ndotl - base_ndotl) / max(base_ndotl, 0.28), -0.25, 0.25);
            lit *= 1.0 + dir_delta * direct_ratio * 0.45 * relief_fade;
        }
        if dirt_surface && sunlit_sky > 0.0 {
            // Keep sunset/sunrise sunlit dirt a natural warm earthy brown-tan instead of neon orange or flat rose.
            let dirt_luma = dot(lit, vec3<f32>(0.2126, 0.7152, 0.0722));
            let earthy_weight = 0.22 * golden_hour() * sunlit_sky * direct_ratio * smoothstep(0.02, 0.28, base_ndotl);
            lit = mix(lit, vec3<f32>(1.06, 0.99, 0.88) * dirt_luma, earthy_weight);
        }
    }
    // Limit maximum non-polished highlights (both sunlight and combined warm torch light)
    // so bright or warm blocks never blow out or look polished.
    if solid_terrain && !soft_foliage && input.emission <= 0.0 && dry_finish.x <= 0.0 && lighting.a <= 0.05 {
        let lit_peak = max(lit.r, max(lit.g, lit.b));
        let sunlit_face = smoothstep(-0.02, 0.12, base_ndotl) * sunlit_sky;
        let soft_cap = mix(0.84, 0.62, sunlit_face);
        if lit_peak > soft_cap {
            let excess = lit_peak - soft_cap;
            lit *= (soft_cap + excess / (1.0 + 2.65 * excess)) / lit_peak;
        }
    }
    if local_metalness > 0.0 && gloss > 0.0 {
        // The field stores incoming light without a direction. Use a broad reflection.
        let facing = dot(n_bump, safe_direction(-input.position));
        lit += local * fresnel_schlick(f0, facing) * (0.90 * local_metalness * gloss);
    }
    if !input.translucent {
        let effects = clamp(max(frame.night_vision, max(frame.blindness, frame.darkness)), 0.0, 1.0);
        let solar_peak = lighting.a * root_visibility * (1.0 - effects);
        let solar_bloom = solar_peak * smoothstep(0.05, select(0.72, 0.28, soft_foliage), solar_peak);
        set_surface(n_bump, finish.x, encode_surface_data(f0, coating > 0.0, input.emission > 0.0, soft_foliage, solar_bloom));
    }
    if input.emission > 0.0 {
        let texel_peak = max(input.albedo.r, max(input.albedo.g, input.albedo.b));
        let torch = input.material == 50u;
        let hot_texel = smoothstep(select(0.24, 0.45, torch), select(0.68, 0.80, torch), texel_peak);
        var glow = select(1.45, 1.25, torch);
        if frame.dimension == -1 {
            // Lava and fire keep bright cores; glowstone retains its mottled texels.
            glow = select(1.10, 1.25, input.fluid == 2u || input.material == 51u || torch);
        }
        if frame.dimension == 1 { glow = 1.05; }
        lit *= 1.0 + hot_texel * input.emission * glow;
        if input.fluid == 2u {
            // Hot yellow texels add HDR energy for the flame-colored halo.
            let heat = smoothstep(0.105, 0.32, input.albedo.g);
            lit += vec3<f32>(1.0, 0.92, 0.28) * ((0.03 + 2.80 * heat) * input.emission);
        } else if torch {
            let peak = max(lit.r, max(lit.g, lit.b));
            lit = mix(lit, peak * vec3<f32>(1.0, 0.68, 0.30), hot_texel);
        } else {
            // Preserve each emitter's own hue while giving bright texels clean HDR core energy for bloom.
            let colour_peak = max(lit.r, max(lit.g, lit.b));
            let emitter_hue = lit / max(colour_peak, 0.0001);
            let tier = smoothstep(0.20, 0.95, input.emission);
            let core_boost = (0.35 + 1.05 * tier) * hot_texel;
            lit += emitter_hue * core_boost;
        }
    }
    let vanilla_light = input.lightmap + select(vec3<f32>(0.0), input.colored_light, dynamic_lights && !overworld);
    lit = respect_effects(lit, vanilla_base, vanilla_light);
    let with_scatter = apply_block_air_scatter(lit, input.position, input.light.x);
    return Surface(vec4<f32>(surface_fog(sanitize_rgb(with_scatter), input.position), alpha));
}
