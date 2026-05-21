# Spend Analytics Agent

Production spend analytics agent built with **Strands Agents SDK**, **Amazon Bedrock AgentCore Runtime**, and a React dashboard.

## Project structure

```
spend-analytics-agent/
├── agent/          # Strands agent + BedrockAgentCoreApp
├── lambda/         # API Gateway → AgentCore adapter
├── infra/          # WAF + API Gateway setup scripts
└── frontend/     # React + Recharts UI
```

## Prerequisites

- Python 3.12+
- Node.js 18+
- AWS CLI configured
- `agentcore` CLI (from `bedrock-agentcore`)

## Configuration

Source `deploy/aws.env` (or copy `.env.example` to `.env`) and set any missing values:

| Variable | Description |
|----------|-------------|
| `S3_BUCKET_NAME` | `spend-data-q` |
| `AWS_ACCOUNT_ID` | Your AWS account ID |
| `AWS_REGION` | `ap-south-1` (configured in `deploy/aws.env`) |
| `BEDROCK_GUARDRAIL_ID` | Bedrock guardrail ID |
| `BEDROCK_GUARDRAIL_VERSION` | Guardrail version (not draft) |
| `AGENTCORE_MEMORY_ID` | From memory setup step |
| `AGENTCORE_ENDPOINT` | From `agentcore launch` output |
| `VITE_API_BASE_URL` | API Gateway invoke URL (stage included) |

## Deploy order

1. Create Bedrock guardrail and version
2. Create AgentCore Memory (`agent/memory.py` setup script in spec)
3. `cd agent && agentcore configure --entrypoint main.py && agentcore launch`
4. Deploy Lambda (`lambda/handler.py`)
5. `python infra/waf.py` → save `WAF_WEB_ACL_ARN`
6. `python infra/api_gateway.py` with Lambda ARN and WAF ARN
7. `cd frontend && npm install && npm run build` → upload `dist/` to S3 + CloudFront

## API authentication (v1)

API Gateway uses **API key** auth (`x-api-key` header). The React app reads `VITE_API_KEY` from `frontend/.env`.

To rotate or recreate keys:

```bash
source deploy/aws.env
python infra/enable_api_key_auth.py
```

## Local frontend

```bash
cd frontend
cp .env.example .env   # set VITE_API_BASE_URL and VITE_API_KEY
npm install
npm run dev
```

## S3 data layout

```
s3://spend-data-q/spend-data/raw/spend_2024_q1.xlsx
```

Required columns: `date`, `vendor_name`, `category`, `amount`.
