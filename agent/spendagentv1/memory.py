import os

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)

MEMORY_ID = os.environ["AGENTCORE_MEMORY_ID"]
REGION = os.environ.get("AWS_REGION", "ap-south-1")


def create_session_manager(session_id: str) -> AgentCoreMemorySessionManager:
    config = AgentCoreMemoryConfig(
        memory_id=MEMORY_ID,
        session_id=session_id,
        actor_id="spend-agent",
        batch_size=5,
    )
    return AgentCoreMemorySessionManager(config, region_name=REGION)
