import asyncio
import tempfile

from agent_system_v9.coding.coding_agent import CodingAgent


def test_loop_terminates():
    async def main():
        ws = tempfile.mkdtemp(prefix="v9test_")
        agent = CodingAgent(max_iterations=2)
        res = await agent.solve("task", workspace=ws)
        assert res.iterations <= 2
    asyncio.run(main())


def test_failure_path_records_error():
    async def main():
        ws = tempfile.mkdtemp(prefix="v9test_")
        agent = CodingAgent(max_iterations=1)
        res = await agent.solve("task", workspace=ws)
        # pytest missing in env -> error recorded
        assert res.error is not None or res.test_passed is False
    asyncio.run(main())
