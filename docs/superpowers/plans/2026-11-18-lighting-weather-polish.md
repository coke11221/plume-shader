# Lighting and weather polish

Build from v0.5.10 for the installed Horizon Shader API 0.2 client. Compare against the existing GoldenLab fixtures with ray tracing off.

1. Test that the sky draws a bright round sun with a broad halo independently of rain, and that dense cloud along the same ray dims the solar disk and ground light. Implement the analytic sun in `sky.wgsl`, disable the client sun in the manifest, and integrate optical depth from the shared cloud volume in `common.wgsl`. Retain a cheaper plane mode.
2. Test a mid-range RGB setting on neutral terrain and glow on a receiver with zero block light. Give the RGB controls a stronger response, let storm transmission drive direct solar terms, and gate local lighting with the client's propagated block-light level. Keep true source-to-receiver occlusion as a native dependency.
3. Ship a moon-only resource pack using the client's eight lunar phase sprites if runtime loading is verified. Keep its installation independent of the shader archive.
4. Package the new release, run the official checker and GPU suite, and compare fixed sky, storm, and wall scenes with v0.5.10. Record compatibility and measured limits in the release review.
