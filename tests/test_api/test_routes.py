import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    # runtime_profile lets ops verify "are we really on V2" with one curl
    # during a rollback (see chat-bot-build/chat-bot-v3/docs/runtime_config_v3.md
    # SS13.1) -- must stay v2_only until a real V3 runtime exists.
    assert data["runtime_profile"] == "v2_only"


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200
