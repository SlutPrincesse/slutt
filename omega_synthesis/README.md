# Omega-Synthesis ASI Framework

Unified mathematical framework for Artificial Superintelligence, implemented in Python/PyTorch.

## Structure
- `src/` — core implementation
- `tests/` — pytest suite
- `paper/` — LaTeX manuscript
- `experiments/` — benchmarks and figures
- `spec/` — canonical equation registry (`omega_synthesis.xml`)

## Quickstart
```bash
cd omega_synthesis
pip install -e .
python demo.py
pytest tests/ -v
```

## Components
| Module | Mathematical Object |
|---|---|
| `core/geometry` | Riemannian metric `g_ij`, Christoffel symbols `Γ^λ_μν`, geodesic ODE |
| `core/quantum` | Density matrix `ρ`, unitary evolution, measurement collapse |
| `core/autodiff` | Fisher info metric, natural gradient `G^{-1}∇L` |
| `cognitive/jspace` | Topological latent manifold `J`, Wasserstein distance |
| `cognitive/rwkv` | RWKV time-mixing `wkv_t`, channel-mixing `x_t` |
| `cognitive/attention` | Hybrid attention `H(X) = α·RWKV + (1-α)·softmax(QK^T)V` |
| `cognitive/projection` | Quantum free random projection `Ω` |
| `control/hjb` | Stochastic HJB PDE solver |
| `control/active_inference` | Variational free energy `F` |
| `control/aixi` | Tractable AIXI via Bayesian mixture + Thompson sampling |
| `alignment/gauge` | Non-Abelian curvature `F_μν`, covariant derivative `D_μ` |
| `alignment/info_geo` | Fisher metric, natural gradient descent |
| `alignment/safety` | Constraints `C_safety`, `D_equality`, `I_blind` |
| `physics/landauer` | Thermodynamic dissipation penalty `ΔQ ≥ k_B T ln2 · ΔI` |
| `physics/lindblad` | Lindblad master equation `dρ/dt` |
| `category/cats` | Categories, functors, monads |
| `category/quine` | Cognitive quine fixed point `Fix(T) = lim T^n(0)` |
| `training/loss` | `MasterActionFunctional` composing all `L_*` terms |
| `training/trainer` | Optimization loop with constraint projection |

## License
MIT
