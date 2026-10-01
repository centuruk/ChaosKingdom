"""Validate author-editable realm content and its generated world."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chaos_kingdom.core.generation import content, generate_world


def main() -> int:
    config = content()
    errors = []
    for field, count in (("names", 50), ("given_names", 20), ("houses", 10), ("factions", 6)):
        if len(config.get(field, [])) != count:
            errors.append(f"{field}: 정확히 {count}개 필요")
    for field in ("names", "given_names", "houses"):
        if len(set(config[field])) != len(config[field]):
            errors.append(f"{field}: 중복 이름")
    for f in config["factions"]:
        if not 0 <= f["capital"] < 50:
            errors.append(f"{f['name']}: 잘못된 수도")
        if len(f["color"]) != 3 or any(not 0 <= c <= 255 for c in f["color"]):
            errors.append(f"{f['name']}: 잘못된 색상")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    generate_world().validate()
    print("콘텐츠 검증 통과: 장수 200명 · 성 20개 · 거점 30개 · 세력 6개 · 연결된 지도")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
