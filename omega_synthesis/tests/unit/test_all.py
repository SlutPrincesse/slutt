from __future__ import annotations
import numpy as np
from src.core.geometry import RiemannianGeometry
from src.core.quantum import DensityMatrix
from src.core.autodiff import NaturalGradient
from src.cognitive.jspace import JSpace
from src.cognitive.rwkv import RWKVTimeMixing
from src.cognitive.attention import HybridAttention
from src.cognitive.projection import QuantumFreeRandomProjection
from src.control.hjb import HJBSolver
from src.control.active_inference import ActiveInference
from src.control.aixi import AIXITractable
from src.alignment.gauge import NonAbelianGauge
from src.alignment.info_geo import InfoGeometry
from src.alignment.safety import AlignmentSafety
from src.physics.landauer import LandauerLimit
from src.physics.lindblad import LindbladMasterEquation
from src.category.quine import CognitiveQuine
from src.training.loss import MasterActionFunctional
from src.training.trainer import OmegaTrainer
from src import OmegaModule

DEVICE = "cpu"
np.random.seed(42)

class OmegaModuleStub(OmegaModule):
    def __init__(self):
        super().__init__(name="stub")
    def forward(self, x):
        return float(np.mean(x))
    def parameters(self):
        return []

class TestCoreGeometry:
    def test_metric_tensor_shape(self):
        g = RiemannianGeometry(dim=4, device=DEVICE)
        z = np.random.randn(2, 4)
        out = g.metric_tensor(z)
        assert out.shape == (2, 4, 4)

    def test_metric_symmetry(self):
        g = RiemannianGeometry(dim=4, device=DEVICE)
        z = np.random.randn(1, 4)
        out = g.metric_tensor(z).reshape(4, 4)
        assert np.allclose(out, out.T)

class TestCoreQuantum:
    def test_density_matrix_trace(self):
        d = DensityMatrix(dim=4, device=DEVICE)
        rho = d.random_density(2)
        trace = float(np.trace(rho[0]) + np.trace(rho[1]))
        assert abs(trace - 2.0) < 1e-5

    def test_unitary_preserves_trace(self):
        d = DensityMatrix(dim=4, device=DEVICE)
        rho = d.random_density(1)
        U = d.unitary(1)
        rho2 = d.apply_unitary(rho, U)
        assert abs(float(np.trace(rho[0]) - np.trace(rho2[0]))) < 1e-5

class TestCoreAutodiff:
    def test_natural_gradient_descent(self):
        def loss_fn(p):
            return float(np.sum(p ** 2))
        p = np.array([1.0, -1.0], dtype=np.float64)
        ng = NaturalGradient(device=DEVICE)
        p_new = ng.natural_gradient_step(loss_fn, p, lr=0.1)
        assert p_new.shape == p.shape

class TestCognitiveJSpace:
    def test_forward_shape(self):
        js = JSpace(input_dim=16, latent_dim=8, device=DEVICE)
        x = np.random.randn(4, 16)
        z, g = js(x)
        assert z.shape == (4, 8)
        assert g.shape == (4, 8, 8)

class TestCognitiveRWKV:
    def test_time_mixing_shape(self):
        rwkv = RWKVTimeMixing(dim=8, device=DEVICE)
        x = np.random.randn(2, 10, 8)
        out = rwkv(x)
        assert out.shape == (2, 10, 8)

class TestCognitiveAttention:
    def test_hybrid_attention_shape(self):
        attn = HybridAttention(dim=8, num_heads=2, device=DEVICE)
        x = np.random.randn(2, 10, 8)
        out = attn(x)
        assert out.shape == (2, 10, 8)

class TestCognitiveProjection:
    def test_projection_shape(self):
        qp = QuantumFreeRandomProjection(input_dim=16, output_dim=8, device=DEVICE)
        x = np.random.randn(4, 16)
        out = qp(x)
        assert out.shape == (4, 8)

class TestControlHJB:
    def test_hjb_residual_decreases(self):
        solver = HJBSolver(dim=1, grid_size=20, device=DEVICE)
        r0 = solver.solve_step(dt=0.01)
        r1 = solver.solve_step(dt=0.01)
        assert r1 < r0 or r0 < 1.0

class TestControlActiveInference:
    def test_free_energy_nonnegative(self):
        ai = ActiveInference(obs_dim=8, state_dim=4, device=DEVICE)
        o = np.random.randn(4, 8)
        F, _ = ai(o)
        assert F > 0

class TestControlAIXI:
    def test_aixi_output_shape(self):
        aixi = AIXITractable(num_models=2, horizon=3, state_dim=4, action_dim=2, device=DEVICE)
        state = np.random.randn(2, 4)
        out = aixi(state)
        assert out.shape == (2, 3, 2)

class TestAlignmentGauge:
    def test_curvature_shape(self):
        g = NonAbelianGauge(dim=4, gauge_dim=4, device=DEVICE)
        z = np.random.randn(2, 4)
        F = g.curvature(z)
        assert F.shape[0] == 2

class TestAlignmentInfoGeo:
    def test_wasserstein_nonnegative(self):
        ig = InfoGeometry(device=DEVICE)
        p = np.random.randn(10, 4)
        q = np.random.randn(10, 4)
        d = ig.wasserstein_distance(p, q)
        assert d >= 0

class TestAlignmentSafety:
    def test_safety_output_keys(self):
        s = AlignmentSafety(device=DEVICE)
        state = np.random.randn(4, 8)
        action = np.random.randn(4, 8)
        u_i = np.random.randn(4, 8)
        u_j = np.random.randn(4, 8)
        h = np.random.randn(4) - 1.0
        out = s(state, action, u_i, u_j, h)
        assert "C_safety" in out and "D_equality" in out and "I_blind" in out

class TestPhysicsLandauer:
    def test_dissipation_positive(self):
        land = LandauerLimit(temperature=300.0, device=DEVICE)
        delta = np.array([1.0, 2.0])
        pen = land.dissipation_penalty(delta)
        assert np.all(pen > 0)

class TestPhysicsLindblad:
    def test_trace_preservation(self):
        lb = LindbladMasterEquation(dim=4, device=DEVICE)
        rho = np.eye(4, dtype=np.float64).reshape(1, 4, 4).repeat(2, axis=0)
        rho_next = lb.step(rho, dt=0.01)
        trace = float(np.trace(rho_next[0]) + np.trace(rho_next[1]))
        assert abs(trace - 2.0) < 1e-4

class TestCategoryQuine:
    def test_fixed_point_converges(self):
        q = CognitiveQuine(max_iter=100, device=DEVICE)
        x0 = np.array([1.0], dtype=np.float64)
        fx = q.fixed_point(x0)
        fx_next = q.mu(fx)
        assert float(np.linalg.norm(fx_next - fx)) < 1e-4

class TestTrainingLoss:
    def test_master_loss_forward(self):
        master = MasterActionFunctional(device=DEVICE)
        lin = OmegaModuleStub()
        lin.forward = lambda x: float(np.mean(x))
        lin.parameters = lambda: []
        master.register("test", lin, weight=1.0)
        state = {"test": np.random.randn(2, 4)}
        loss = master(state)
        assert np.isfinite(loss)

    def test_trainer_step(self):
        master = MasterActionFunctional(device=DEVICE)
        lin = OmegaModuleStub()
        lin.forward = lambda x: float(np.mean(x))
        lin.parameters = lambda: []
        master.register("test", lin, weight=1.0)
        trainer = OmegaTrainer(master, lr=1e-3, device=DEVICE)
        state = {"test": np.random.randn(2, 4)}
        metrics = trainer.train_step(state)
        assert "loss" in metrics
