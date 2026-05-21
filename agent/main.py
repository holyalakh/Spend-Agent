import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from fastapi import FastAPI
from strands import Agent
from strands.models import BedrockModel

from hooks import ReadOnlySqlHooks
from memory import create_session_manager
from session_store import SessionStore
from tools.dashboard import _aggregate, get_dashboard_data
from tools.load_data import _load_and_register, load_spend_data
from tools.query import run_analysis_query

SYSTEM_PROMPT = """
You are a spend analytics assistant. You have access to structured spend data loaded
from S3 into an in-memory DuckDB table called 'spend'.

The spend table has columns: date, vendor_name, category, sub_category, amount,
currency, cost_center, description.

When a user asks a question:
1. Use run_analysis_query to run precise SQL against the spend table.
2. Summarise the results clearly in natural language.
3. Always state the time period your answer covers.
4. Format amounts with commas and 2 decimal places.
5. Only answer questions about spend, categories, vendors, and procurement.
6. If a question is ambiguous, ask a clarifying question before querying.
7. Never perform write operations on the data.

Available tools: load_spend_data, run_analysis_query, get_dashboard_data.
"""

model = BedrockModel(
    model_id=os.environ.get(
        "BEDROCK_MODEL_ID",
        "arn:aws:bedrock:ap-south-1:387957186026:inference-profile/global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    ),
    region_name=os.environ.get("AWS_REGION", "ap-south-1"),
    guardrail_id=os.environ["BEDROCK_GUARDRAIL_ID"],
    guardrail_version=os.environ["BEDROCK_GUARDRAIL_VERSION"],
    guardrail_trace="enabled",
    guardrail_redact_input=True,
    guardrail_redact_output=True,
)

app = BedrockAgentCoreApp()
fastapi_app = FastAPI()
store = SessionStore()


@app.entrypoint
async def chat(payload: dict) -> dict:
    if payload.get("action") == "dashboard":
        s3_file_key = payload.get("s3_file_key", "")
        session_id = payload.get("session_id", "default")
        if not s3_file_key:
            return {"status": "error", "message": "Missing s3_file_key"}
        try:
            conn = _load_and_register(s3_file_key, session_id)
            return _aggregate(conn)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    session_id = payload.get("session_id", "default")
    message = payload.get("message", "")
    s3_key = payload.get("s3_file_key")
    user_email = payload.get("user_email", "")

    session_manager = create_session_manager(session_id)

    system_prompt = SYSTEM_PROMPT
    if user_email:
        system_prompt = f"{SYSTEM_PROMPT.strip()}\n\nAuthenticated user email: {user_email}"

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[load_spend_data, run_analysis_query, get_dashboard_data],
        session_manager=session_manager,
        hooks=[ReadOnlySqlHooks()],
    )

    if s3_key:
        store.set(session_id, "s3_key", s3_key)

    result = await agent.invoke_async(message)

    if hasattr(result, "stop_reason") and result.stop_reason == "guardrail_intervened":
        return {
            "session_id": session_id,
            "reply": "Your request was outside the scope of this assistant.",
            "guardrail_blocked": True,
        }

    return {"session_id": session_id, "reply": str(result), "guardrail_blocked": False}


@fastapi_app.get("/dashboard")
async def dashboard(s3_file_key: str, session_id: str = "default"):
    conn = _load_and_register(s3_file_key, session_id)
    return _aggregate(conn)


if __name__ == "__main__":
    app.run()
