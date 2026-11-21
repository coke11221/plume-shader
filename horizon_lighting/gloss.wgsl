// Intrinsic dry surface finish. Wetness is applied separately.
override gloss_strength: f32 = 1.0;

fn surface_gloss_strength() -> f32 {
    return 0.75 * gloss_strength;
}

fn surface_finish(id: u32) -> vec2<f32> {
    if id == 10u { return vec2<f32>(0.88, 0.88); } // polished metal: smoothness, metalness
    if id == 20u { return vec2<f32>(0.72, 0.0); }  // polished stone / glazed ceramic
    if id == 30u { return vec2<f32>(0.92, 0.0); }  // glass
    return vec2<f32>(0.0);
}

fn is_thin_plant(id: u32) -> bool {
    return id == 40u || (id >= 43u && id <= 47u);
}

// Broad direct-light glint and thin-material transmission, respectively.
fn dry_light_response(id: u32) -> vec2<f32> {
    if is_thin_plant(id) { return vec2<f32>(0.055, 0.52); } // thin grass, ferns, flowers, vines and aquatic plants
    if id == 48u { return vec2<f32>(0.075, 0.50); } // bamboo stalks: translucent green stems matching their leaves
    if id == 42u { return vec2<f32>(0.125, 0.44); } // leaves
    if id == 60u { return vec2<f32>(0.095, 0.0); } // rough stone and cobble
    if id == 41u { return vec2<f32>(0.095, 0.0); } // grass blocks: textured warm grazing sheen
    if id == 61u { return vec2<f32>(0.042, 0.0); } // earthy soil
    return vec2<f32>(0.060, 0.0);
}

fn surface_f0(base: vec3<f32>, metalness: f32) -> vec3<f32> {
    return mix(vec3<f32>(0.04), clamp(base, vec3<f32>(0.02), vec3<f32>(0.95)), metalness);
}

const SURFACE_DATA_BASE: u32 = 0x00800000u;
const BLOOM_EMISSIVE: u32 = 32u;
const BLOOM_FOLIAGE: u32 = 64u;

// The surface buffer preserves float bits. Store RGB8 F0, five bits of solar
// bloom and two flags. The bias and 30-step range keep the float finite
// and normal. The sign still marks the rain coating.
fn encode_surface_data(colour: vec3<f32>, wet: bool, emissive: bool, foliage: bool, solar_bloom: f32) -> f32 {
    let c = vec3<u32>(round(clamp(colour, vec3<f32>(0.0), vec3<f32>(1.0)) * 255.0));
    let glow = u32(round(sqrt(clamp(solar_bloom / 3.10, 0.0, 1.0)) * 30.0));
    let bloom = glow | select(0u, BLOOM_EMISSIVE, emissive) | select(0u, BLOOM_FOLIAGE, foliage);
    let payload = c.x | (c.y << 8u) | (c.z << 16u) | (bloom << 24u);
    let data = bitcast<f32>(SURFACE_DATA_BASE + payload);
    return select(data, -data, wet);
}

fn surface_data_bits(data: f32) -> u32 {
    return max(bitcast<u32>(abs(data)), SURFACE_DATA_BASE) - SURFACE_DATA_BASE;
}

fn receives_contact_ao(data: f32) -> bool {
    let flags = surface_data_bits(data) >> 24u;
    return (flags & (BLOOM_EMISSIVE | BLOOM_FOLIAGE)) == 0u;
}

fn decode_f0(data: f32) -> vec3<f32> {
    let c = surface_data_bits(data);
    return vec3<f32>(f32(c & 255u), f32((c >> 8u) & 255u), f32((c >> 16u) & 255u)) / 255.0;
}

fn fresnel_schlick(f0: vec3<f32>, cosine: f32) -> vec3<f32> {
    return f0 + (1.0 - f0) * pow(1.0 - clamp(cosine, 0.0, 1.0), 5.0);
}
