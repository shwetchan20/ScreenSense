from screensense.agents.router import AgentRouter


def test_router_defaults_to_general() -> None:
    router = AgentRouter()
    agent = router.get("unknown")
    assert agent.name == "general"

