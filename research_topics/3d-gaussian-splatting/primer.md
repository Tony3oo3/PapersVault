---
title: 3D Gaussian Splatting
slug: 3d-gaussian-splatting
scope: For an ML/CV researcher new to 3D vision (no NeRF, volume rendering or SfM background); key equations explained; standard depth
created: 2026-10-16
updated: 2026-10-16
topic_query: '{title key_contribution}: ("gaussian splatting" OR 3dgs OR "3d gaussians" OR "3d-gs" OR "gaussian splats" OR "gaussian surfels" OR "gaussian primitives" OR 2dgs OR 4dgs OR "4d gaussians" OR "2d gaussians" OR "dynamic gaussians" OR "gaussian avatar" OR "gaussian avatars" OR "street gaussians")'
precision: 34/40 strict, 40/40 lenient (two 20-paper samples, seeds 1 and 7)
recall: 91% of vault papers building on the original 3DGS paper (1128/1239); 90% of those building on its 5 most built-upon descendants (241/268)
papers_in_topic: 1486
editions_covered: [CVPR2024, CVPR2025, CVPR2026, ECCV2024, ECCV2026, ICCV2025, ICLR2024, ICLR2025, ICLR2026, ICML2024, ICML2025, ICML2026, NEURIPS2024, NEURIPS2025]
updates: []
artifact: https://claude.ai/artifact/Q53tnVtDozCacJdcohiGRB
---

# 3D Gaussian Splatting

The full primer is the page [index.html](index.html): explanations, diagrams, four interactive figures, the trend chart and the lineage graph. This note is its companion.

**In five lines**
1. 3DGS represents a scene as millions of anisotropic 3D Gaussians (position, covariance $RSS^\top R^\top$, opacity, spherical-harmonic colour) and renders them by projecting each one to a 2D Gaussian, sorting by depth and alpha-compositing, which is the same compositing equation NeRF uses.
2. Everything is differentiable, so the Gaussians are fitted to posed photos by gradient descent. Heuristic clone/split/prune ("adaptive density control") manages how many there are. It renders in real time and trains in minutes.
3. 2024 work fixed its weaknesses: aliasing (Mip-Splatting), memory (LightGaussian, HAC), surfaces (SuGaR, 2DGS), motion (Deformable 3DGS, 4DGS). It also turned it into a substrate for semantics, SLAM, physics and generation.
4. The fastest-growing line predicts the Gaussians feed-forward (pixelSplat → MVSplat → NoPoSplat), and by 2026 it sits on geometry foundation models such as VGGT. VGGT went from 2 topic papers building on it in 2025 to 33 in 2026.
5. Gaussian splatting is ~7% of CVPR/ICCV/ECCV papers and has plateaued since 2025. The open problems are generalisation, unseen regions, casual dynamic video, geometry vs appearance, and exact rendering.

**Reading path** (the original paper, Kerbl et al. SIGGRAPH 2023, is not in the vault: read it first)

Start here
- [ ] [[CVPR20241019|Mip-Splatting]]
- [ ] [[NEURIPS20242572|3DGS as MCMC]]
- [ ] [[CVPR20241339|pixelSplat]]
- [ ] [[ICLR20240365|4DGS (Yang et al.)]]

Core
- [ ] [[CVPR20242478|Scaffold-GS]]
- [ ] [[NEURIPS20244446|LightGaussian]]
- [ ] [[ECCV20240185|HAC]]
- [ ] [[CVPR20242220|SuGaR]]
- [ ] [[ECCV20242381|GS2Mesh]]
- [ ] [[CVPR20242189|Deformable 3DGS]]
- [ ] [[CVPR20240949|4DGS (Wu et al.)]]
- [ ] [[CVPR20241842|SC-GS]]
- [ ] [[ICCV20251580|Shape of Motion]]
- [ ] [[ECCV20240557|MVSplat]]
- [ ] [[ECCV20240564|GS-LRM]]
- [ ] [[ICLR20251940|NoPoSplat]]
- [ ] [[CVPR20240858|LangSplat]]
- [ ] [[CVPR20240557|Gaussian Splatting SLAM]]
- [ ] [[CVPR20241250|PhysGaussian]]
- [ ] [[ECCV20240081|LGM]]
- [ ] [[CVPR20241188|GaussianAvatars]]

Frontier
- [ ] [[CVPR20250750|VGGT]]
- [ ] [[ICLR20252162|LVSM]]
- [ ] [[ICLR20261363|YoNoSplat]]
- [ ] [[ECCV20262102|GlobalSplat]]
- [ ] [[CVPR20261737|MoVieS]]
- [ ] [[CVPR20252768|FreeTimeGS]]
- [ ] [[CVPR20263296|Stochastic Ray Tracing]]
- [ ] [[CVPR20262382|FastGS]]
- [ ] [[ICML20262652|AmbiSuR]]

Check your understanding: [[quiz]] (or ask "quiz me on 3d-gaussian-splatting").
