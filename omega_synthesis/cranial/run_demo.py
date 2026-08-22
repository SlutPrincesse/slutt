import sys
from pathlib import Path

# Add omega_synthesis to path so 'cranial' package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cranial.event_bus import EventBus
from cranial.task_dag import TaskDAG
from cranial.harvester import HarvesterEngine
from cranial.shadow_broker import ShadowBroker
from cranial.conscious_layer import ConsciousLayer
from cranial.subconscious_layer import SubconsciousLayer
from cranial.ast_merger import SpeculativeExecutor
from cranial.cranial_hud import CranialHUD


def demo() -> None:
    bus = EventBus()
    dag = TaskDAG()
    broker = ShadowBroker()
    hud = CranialHUD(bus)

    conscious = ConsciousLayer(bus)
    conscious.attach_dag(dag)
    subconscious = SubconsciousLayer(bus, broker)

    hud.start()
    conscious.start()
    subconscious.start()

    try:
        task1 = conscious.submit("ingest-tool", {"query": "demo-cli"})
        task2 = conscious.submit("research", {"query": "find rust binaries"})

        dag.add_dependency(task2, task1)

        executor = SpeculativeExecutor(dag)

        def worker(node):
            print(f"[Exec] Running {node.id}")
            import time
            time.sleep(0.1)
            node.result = {"output": f"result-{node.id}"}
            return node.result

        executor.mode_shadow_clones(task1, worker, count=2)
        executor.mode_schizophrenia(task2, lambda n, index: {"variant": index}, count=2)

        print("\n=== DAG Status ===")
        print(dag.status())
        print("\n=== Topological Order ===")
        print(dag.topological_order())

        harvester = HarvesterEngine()
        sample = "hello_world = 1\n\n\n\nbye_world = 2"
        print("\n=== Harvester Output ===")
        print(harvester.process(sample))

        print("\n=== HUD Render ===")
        print(hud.render())

    finally:
        conscious.stop()
        subconscious.stop()
        hud.stop()


if __name__ == "__main__":
    demo()
