import asyncio
from pathlib import Path

from autoreport.core.tools.manifest_tool import ManifestManager


def test_manifest_clear_resets_files_and_notes(tmp_path: Path):
    manager = ManifestManager(tmp_path)
    agent = "data_analysis"

    async def _run() -> None:
        await manager.touch_files(agent, ["Data/Processed/a.csv"])
        manifest = await manager.load(agent)
        manifest["notes"] = "old notes"
        await manager.save(agent, manifest)

        await manager.clear(agent)
        cleared = await manager.load(agent)

        assert cleared["agent_type"] == agent
        assert cleared["files"] == []
        assert cleared["notes"] == ""

    asyncio.run(_run())
