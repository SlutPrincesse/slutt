from __future__ import annotations
import numpy as np
import json
from src import (
    TensorBackend,
    OmegaModule,
    RiemannianGeometry,
    DensityMatrix,
    NaturalGradient,
    JSpace,
    RWKVTimeMixing,
    RWKVChannelMixing,
    HybridAttention,
    QuantumFreeRandomProjection,
    HJBSolver,
    ActiveInference,
    AIXITractable,
    NonAbelianGauge,
    InfoGeometry,
    AlignmentSafety,
    LandauerLimit,
    LindbladMasterEquation,
    Category,
    Functor,
    Monad,
    CognitiveQuine,
    MasterActionFunctional,
    OmegaTrainer,
)

class Wrapper(OmegaModule):
    def __init__(self, fn, name="wrapper"):
        super().__init__(name=name)
        self.fn = fn
    def forward(self, state):
        return self.fn(state)

def run_demo():
    device = "cpu"
    batch_size = 4
    dim = 8
    seq_len = 10
    state = {
        "observation": np.random.randn(batch_size, seq_len, dim),
        "action": np.random.randn(batch_size, dim),
        "user_intent": np.random.randn(batch_size, dim),
        "safety_signal": np.random.randn(batch_size, dim),
        "human_regression": np.random.randn(batch_size) - 1.0,
    }

    obs = state["observation"][:, 0, :]

    master = MasterActionFunctional(device=device)
    master.register("jspace", Wrapper(lambda s: float(np.mean(JSpace(input_dim=dim, latent_dim=dim, device=device)(obs)[0])), name="jspace"), weight=1.0)
    master.register("rwkv", Wrapper(lambda s: float(np.mean(RWKVTimeMixing(dim=dim, device=device)(s["observation"]))), name="rwkv"), weight=1.0)
    master.register("hjb", Wrapper(lambda s: HJBSolver(dim=dim, grid_size=20, device=device).solve_step(), name="hjb"), weight=1.0)
    master.register("active_inference", Wrapper(lambda s: float(ActiveInference(obs_dim=dim, state_dim=dim, device=device)(obs)[0]), name="active_inference"), weight=1.0)
    master.register("aixi", Wrapper(lambda s: float(np.mean(AIXITractable(state_dim=dim, action_dim=dim, num_models=3, device=device)(obs))), name="aixi"), weight=1.0)
    master.register("gauge", Wrapper(lambda s: float(np.mean(NonAbelianGauge(dim=dim, gauge_dim=dim, device=device).curvature(obs))), name="gauge"), weight=1.0)
    master.register("info_geo", Wrapper(lambda s: InfoGeometry(device=device).wasserstein_distance(obs, obs), name="info_geo"), weight=1.0)
    master.register("safety", Wrapper(lambda s: float(np.mean(AlignmentSafety(device=device)(obs, s["action"], s["user_intent"], s["safety_signal"], s["human_regression"])["C_safety"])), name="safety"), weight=1.0)
    master.register("landauer", Wrapper(lambda s: float(np.mean(LandauerLimit(temperature=300.0, device=device).dissipation_penalty(np.array([1.0])))), name="landauer"), weight=1.0)
    master.register("lindblad", Wrapper(lambda s: float(np.mean(LindbladMasterEquation(dim=dim, device=device).step(np.eye(dim, dtype=np.float64).reshape(1, dim, dim).repeat(batch_size, axis=0), dt=0.01))), name="lindblad"), weight=1.0)
    master.register("quine", Wrapper(lambda s: float(np.mean(CognitiveQuine(device=device)(np.array([1.0])))), name="quine"), weight=1.0)

    trainer = OmegaTrainer(master, lr=1e-3, device=device)
    history = trainer.fit(state, steps=5)

    with open("experiments/benchmarks/run_001.json", "w") as f:
        json.dump({k: [float(v) for v in vals] for k, vals in history.items()}, f, indent=2)

    print("=== Omega-Synthesis S_total Components ===")
    for k, v in master.breakdown.items():
        print(f"  {k}: {float(v):.6f}")
    print(f"\nTotal S_total: {float(master(state)):.6f}")
    print("Benchmark saved to experiments/benchmarks/run_001.json")

if __name__ == "__main__":
    run_demo()
