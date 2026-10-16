---
slug: 3d-gaussian-splatting
---
## q1 · covariance-parameterisation
Why does 3DGS parameterise each covariance as a rotation and a scale instead of optimising the
3x3 matrix directly?
- key: gradient steps on a raw matrix can leave the symmetric positive semi-definite set, and then no ellipsoid exists
- key: R S S^T R^T is PSD by construction for any quaternion and scales, so the optimiser moves freely (scales kept positive with exp)
- see: #step2

## q2 · nerf-vs-3dgs-compositing
NeRF and 3DGS use the same compositing equation. What exactly differs?
- key: where the alphas come from: NeRF uses 1 - exp(-sigma delta) from a network's density at ray samples; 3DGS uses opacity times a projected 2D Gaussian falloff
- key: direction: NeRF marches rays from pixels (backward); 3DGS projects primitives onto pixels (forward), so it can be rasterised
- see: #volrend, #step5

## q3 · sorting-and-popping
What breaks if Gaussians are blended in the wrong depth order, and why is 3DGS's sort only approximate?
- key: compositing is order-dependent: each weight alpha_i T_i depends on everything in front
- key: 3DGS sorts once per image by centre depth; overlapping Gaussians can be mis-ordered per pixel and flip as the camera moves (popping); EVER and ray tracing fix it at a speed cost
- see: #step5, ICCV20251851

## q4 · why-density-control
Why can't gradient descent alone decide how many Gaussians a scene needs, and what does adaptive density control do?
- key: Gaussians have local support: regions with no Gaussian nearby give no gradient, and one large Gaussian cannot become several
- key: ADC accumulates screen-space positional gradients: clone small high-gradient Gaussians, split large ones, prune near-transparent ones, with periodic opacity resets
- see: #step6, CVPR20241339

## q5 · mcmc-relocation
What does 3DGS-MCMC replace the clone/split heuristics with, and what does it buy?
- key: training viewed as SGLD sampling: gradient step plus covariance-shaped, opacity-gated noise on positions
- key: densification becomes relocation of dead Gaussians onto live ones that keeps the rendering unchanged; gives a user-set budget and robustness to random initialisation
- see: #fidelity, NEURIPS20242572

## q6 · aliasing-mip-splatting
Why does vanilla 3DGS look wrong when you zoom out (or in), and what are Mip-Splatting's two fixes?
- key: the fixed 0.3 px screen-space dilation lets Gaussians become sub-pixel; zooming out over-brightens and thickens thin structures, zooming in erodes them
- key: a 3D smoothing filter bounds each Gaussian's frequency by its training cameras' Nyquist rate (added to Sigma, free after training), plus a 2D Mip filter approximating the pixel box filter
- see: #fidelity, CVPR20241019

## q7 · where-the-bytes-go
About 81% of a Gaussian's bytes are one attribute. Which one, and what do compression methods do about it?
- key: degree-3 spherical harmonics: 48 of 59 floats
- key: distil SH to a lower degree, vector-quantise into codebooks, or replace with a shared hash grid or anchor MLP; entropy coding with context models (HAC) exploits correlation between neighbours
- see: #compact, NEURIPS20244446, ECCV20240185

## q8 · surfels
Why does flattening Gaussians into 2D disks help surface reconstruction, and what does it cost?
- key: a ray meets a disk at one point with an explicit normal, so depth and normal are well-defined; a 3D blob spreads density along the ray
- key: image quality drops on volumetric/fuzzy content that the volumetric blobs were faking (SuGaR refined 27.27 vs 28.69 dB for 3DGS in its note)
- see: #surfaces, CVPR20242220

## q9 · 4d-conditioning
In Yang et al.'s 4DGS, which part of the 4D covariance encodes motion, and how does a primitive appear and disappear?
- key: the space-time block Sigma_{1:3,4}: the conditional mean moves as Sigma_{1:3,4} Sigma_{4,4}^{-1} (t - mu_t), a velocity
- key: the marginal p(t) = N(t; mu_t, Sigma_{4,4}) multiplies the opacity, so the primitive fades in and out; p(t) < 0.05 is skipped
- see: #dynamic, ICLR20240365

## q10 · canonical-vs-spacetime
Contrast canonical-space deformation with native space-time primitives for dynamic scenes. When does each struggle?
- key: canonical + deformation (Deformable 3DGS, Wu 4DGS, SC-GS) shares geometry over time and is compact, but fast or complex motion needs ill-posed long-range correspondence to a rest pose
- key: space-time primitives (Yang 4DGS, STG, FreeTimeGS) handle fast motion and appearing content but have weaker long-range consistency; FreeTimeGS models only short-range linear motion
- see: #dynamic, CVPR20242189, CVPR20252768

## q11 · pixelsplat-depth
Why does pixelSplat sample a depth bucket and set the Gaussian's opacity to its probability, instead of regressing depth directly?
- key: regressed positions get stuck in local minima: gradients vanish a few standard deviations away and moving through empty space occludes other content
- key: opacity = sampled bucket's probability lets gradients raise the probability of good depths: a reparameterisation acting like differentiable spawn/delete (~1 dB)
- see: #feedforward, CVPR20241339

## q12 · pose-free
What does NoPoSplat change about where Gaussians are predicted, and why does that remove the need for poses?
- key: all views' Gaussians are predicted directly in the first camera's frame instead of per view and transformed with known poses
- key: relative geometry is learned implicitly; intrinsics still enter (as a token) to fix scale
- see: #feedforward, ICLR20251940

## q13 · lvsm-vs-explicit
LVSM beats GS-LRM on PSNR without any 3D representation. Give two reasons the field still builds explicit Gaussians.
- key: explicit 3D can be edited, segmented, simulated and rendered in real time; LVSM runs a large transformer per frame
- key: LVSM is deterministic and weak on unseen regions and new resolutions/aspect ratios (flicker); Gaussians are multi-view consistent by construction
- see: #feedforward, ICLR20252162

## q14 · beyond-pixel-aligned
What goes wrong with one Gaussian per input pixel as the number of views grows, and what replaces it?
- key: the count grows linearly with views, mostly duplicating surfaces: memory and render cost blow up
- key: decode a fixed budget from latent scene tokens (GlobalSplat) or detect sub-pixel primitives with adaptive counts (Off The Grid)
- see: #feedforward, ECCV20262102, CVPR20262098

## q15 · physgaussian
Why can PhysGaussian render the simulated state directly, without converting to a mesh?
- key: each Gaussian is an MPM particle; under the local affine deformation gradient F a Gaussian stays Gaussian with covariance F Sigma F^T (SH rotated by F's rotation)
- key: the simulated primitives are the rendered ones, so geometry and appearance cannot mismatch
- see: #substrate, CVPR20241250
