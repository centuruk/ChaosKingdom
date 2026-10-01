"""Validate reusable role contracts; this tool does not spawn agents or call an API."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    data = json.loads((ROOT / "docs/production/agents.json").read_text(encoding="utf-8"))
    assert data["execution"] == "single_controller" and data["actual_development_agents"] == 1
    assert len({r["id"] for r in data["roles"]}) == 7
    for role in data["roles"]:
        assert all(role.get(k) for k in ("id", "name", "instructions", "inputs", "outputs", "acceptance"))
        assert all((ROOT / p).is_file() for p in role["inputs"])
        print(f"{role['name']}: {role['instructions']}")
    print("구성 확인: 실제 주 개발 에이전트 1개 / 역할 계약 7개 / 별도 에이전트 실행 없음")
    workflow = json.loads((ROOT / "docs/production/workflow-tools.json").read_text(encoding="utf-8"))
    assert workflow["controller"]["actual_count"] == 1 and not workflow["controller"]["subagents"]
    assert len({s["name"] for s in workflow["skills"]}) == len(workflow["skills"])
    for skill in workflow["skills"]:
        assert skill["status"] in {"applied", "instructions_consulted"}
        assert skill["name"] and skill["source"] and skill["source_sha256"] and skill["purpose"]
        assert all((ROOT / p).is_file() for p in skill["artifacts"])
        if skill["status"] == "instructions_consulted":
            assert not skill["invoked_tools"] and not skill["external_service_execution"]
        print(f"스킬 {skill['name']}: {skill['status']} / {skill['purpose']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
