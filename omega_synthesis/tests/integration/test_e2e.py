from __future__ import annotations
import numpy as np
from src import (
    OmegaModule,
    JSpace, RWKVTimeMixing, HybridAttention, QuantumFreeRandomProjection,
    HJBSolver, ActiveInference, AIXITractable, NonAbelianGauge,
    AlignmentSafety, LandauerLimit, LindbladMasterEquation, CognitiveQuine,
    MasterActionFunctional, OmegaTrainer,
)

def test_end_to_end_forward():
    device = "cpu"
    batch_size = 2
    dim = 8
    state = {
        "observation": np.random.randn(batch_size, dim),
        "action": np.random.randn(batch_size, dim),
        "user_intent": np.random.randn(batch_size, dim),
        "safety_signal": np.random.randn(batch_size, dim),
        "human_regression": np.random.randn(batch_size) - 1.0,
    }
    master = MasterActionFunctional(device=device)
    master.register("jspace", JSpace(dim, dim, device=device), weight=1.0)
    master.register("rwkv", RWKVTimeMixing(dim, device=device), weight=1.0)
    master.register("hjb", HJBSolver(dim, grid_size=10, device=device), weight=1.0)
    master.register("active_inference", ActiveInference(dim, dim, device=device), weight=1.0)
    master.register("aixi", AIXITractable(num_models=2, device=device), weight=1.0)
    master.register("gauge", NonAbelianGauge(dim, device=device), weight=1.0)
    master.register("safety", AlignmentSafety(device=device), weight=1.0)
    master.register("landauer", LandauerLimit(temperature=300.0, device=device), weight=1.0)
    master.register("lindblad", LindbladMasterEquation(dim, device=device), weight=1.0)
    master.register("quine", CognitiveQuine(device=device), weight=1.0)
    loss = master(state)
    assert np.isfinite(loss)

def test_trainer_history():
    device = "cpu"
    master = MasterActionFunctional(device=device)
    lin = OmegaModule.__new__(OmegaModule)
    lin.forward = lambda x: float(np.mean(x))
    lin.parameters = lambda: []
    master.register("test", lin, weight=1.0)
    trainer = OmegaTrainer(master, lr=1e-3, device=device)
    state = {"test": np.random.randn(2, 4)}
    history = trainer.fit(state, steps=3)
    assert len(history["loss"]) == 3
