"""One-time AgentCore Memory setup. Run from repo root."""

import os
from bedrock_agentcore.memory import MemoryClient

REGION = os.environ.get("AWS_REGION", "ap-south-1")

def main():
    client = MemoryClient(region_name=REGION)
    mem = client.create_memory_and_wait(
        name="SpendAgentMemory",
        description="Session memory for spend analytics agent",
        strategies=[
            {"semanticMemoryStrategy": {"name": "SemanticStrategy"}},
            {"summaryMemoryStrategy": {"name": "SummaryStrategy"}}
        ]
    )
    print("AGENTCORE_MEMORY_ID =", mem["id"])

if __name__ == "__main__":
    main()
