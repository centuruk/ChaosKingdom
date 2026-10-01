# 3장. OOP로 구성한 세계와 실행 구조

## 화면을 빼도 게임이 남아야 한다

PyGame 프로젝트를 시작할 때 모든 것을 게임 루프 파일에 넣기 쉽다. 입력을 읽고 장수의 명성을 올리고 피해를 계산하고 그림을 그리는 함수가 하나가 되면, 창 없이 역사를 생성하거나 저장한 세계를 다시 실행하기 어렵다. 이 게임은 AI가 판세를 만든 뒤 그 상태에서 캠페인을 시작한다. 화면을 열지 않고 세계를 진행할 수 있어야 한다는 요구가 코드 구조의 출발점이었다.

`core`는 상태·콘텐츠·저장 형식을, `simulation`은 행동과 전투 계산을, `ui`는 입력과 표시를 맡는다. 세계 모델과 시뮬레이션은 `pygame`을 import하지 않는다. 진단 도구는 환경 보고를 요청받을 때만 PyGame 버전을 읽는다. 편찬·콘텐츠 검사·장기 실행·패키징은 `tools`에 둔다.

```text
chaos_kingdom/
  core/
    models.py          세계·장수·지역·세력 데이터와 검증
    generation.py      콘텐츠에서 초기 세계 생성
    campaign.py        세계를 진행해 캠페인 생성
    battlefields.py    전장 데이터·A*·시야·파일 입출력
    storage.py         세계·전투 저장과 복원
    story.py           역사에 연결된 개인 과업
    diagnostics.py     환경과 재현 자료 수집
  simulation/
    ai.py              장수의 행동 후보 평가와 선택
    engine.py          주간 진행·경제·외교·전투 결산
    battle.py          부대와 전술 시뮬레이션
  ui/
    app.py             실행 루프·명령 전달·화면 전환
    theme.py           글꼴·버튼·패널 그리기
    map_view.py        전략 지도 표시
    battlefield_view.py  전장 재질 합성과 표시 캐시
    editor.py          지형·출진·거점 편집과 되돌리기
    assets.py          생성 자산의 주소·읽기·표시
  data/                왕국 콘텐츠와 지역 전장 50개
  assets/              생성 PNG와 출처 명세
```

## 이 프로젝트에서 OOP란 무엇인가

객체 지향 프로그래밍은 상태를 가진 대상과 그 상태를 다루는 책임을 나누는 방법이다. `Officer`는 장수 한 명을, `World`는 그 장수가 살아가는 세계를, `Engine`은 세계의 규칙을 실행하는 서비스를 표현한다. 클래스를 많이 만드는 것이 목적은 아니다. 무엇이 어디에 저장되고 어느 코드가 바꿀 수 있는지 읽을 수 있게 만드는 것이 목적이다.

현재 구현은 데이터 객체, 계산 함수, 상태를 가진 서비스 객체를 함께 쓴다. 장수의 모든 판단을 `Officer` 안에 넣거나 `Knight`, `Lord`, `Prisoner`라는 하위 클래스를 만들지 않았다. 신분과 포로 상태는 플레이 중 바뀌므로 필드로 표현한다. 공통 판단은 `ai.evaluate`와 `ai.choose` 함수가 맡는다. 보병·궁병·기병·창병 역시 `Unit.kind`와 `PROFILES` 데이터로 구분한다.

이 코드에는 게임 객체의 상속 계층이 없다. 대신 `App`이 `World`와 `Engine`을 보유하고, `World`가 장수 사전을 보유하는 합성을 쓴다. “A는 B의 한 종류다”가 상속의 관계라면, 여기서는 주로 “A가 B를 가지고 사용한다”라는 관계다. 클래스·함수·데이터 중 규칙을 가장 간단히 표현하는 형태를 선택했다.

| OOP 개념 | 현재 코드의 예 | 적용 범위와 한계 |
| --- | --- | --- |
| 책임 분리 | World는 상태와 검증, Engine은 상태 전이 | 경제·외교 서비스는 아직 Engine 내부 메서드 |
| 합성 | App → Engine → 같은 World 참조 | 새 World를 읽으면 Engine도 다시 연결해야 함 |
| 캡슐화 | remember·change_bond·resolve_battle에 변경 규칙 집중 | 필드는 공개·가변이며 외부 변경 자체를 막지는 않음 |
| 생성자 주입 | Engine(world), Battle(..., battlefield=field) | 별도 DI 프레임워크나 서비스 컨테이너 없음 |
| 데이터와 행위 | Officer 데이터와 remember, Battlefield와 path | AI 점수 계산은 모듈 함수로 유지 |
| 타입 표현 | ActionResult·Decision 데이터 클래스 | 런타임 유효성은 별도의 validate가 확인 |

MVC라는 이름을 엄격하게 적용한 구조는 아니다. `App`은 입력 제어와 화면 전환, 일부 화면 그리기를 함께 맡는다. 계층을 나눈 실제 효과와 아직 큰 클래스의 책임을 모두 설명해야 구조를 과장하지 않을 수 있다.

## 실제 클래스의 책임

| 클래스·파일 | 가진 상태 | 주요 책임 |
| --- | --- | --- |
| Officer / core/models.py | 능력·성격·소속·위치 ID·기억·충성·피로 | 장수 한 명의 상태, remember로 최근 기억 12개 유지 |
| Memory / core/models.py | 발생 주·종류·상대 ID·가중치·문장 | 판단에 쓸 경험 한 건 |
| Settlement / core/models.py | 병력·식량·재정·방어·민심·이웃 ID | 성 또는 거점의 상태 |
| Faction / core/models.py | 수도·군주 ID·방침·색·멸망 여부 | 세력의 상태 |
| Chronicle·Quest / core/models.py | 사건과 과업 진행 데이터 | 역사와 개인 목표의 기록 |
| World / core/models.py | 장수·지역·세력 사전, 관계·조약·역사·난수 | 전체 상태, 조회·관계 변경·기록·직렬화·검증 |
| Engine / simulation/engine.py | World 참조, 행동 집계 | 명령 허용·행동·주간 진행·결산 |
| Decision / simulation/ai.py | 행동·점수·이유·대상 | 판단 후보의 반환값 |
| ActionResult / simulation/engine.py | 성공 여부·메시지·선택적 Battle | 명령 실행 결과와 화면에 필요한 정보 |
| Unit / simulation/battle.py | 병력·위치·사기·명령·경로·지휘관 ID | 전술 부대 한 개의 상태와 alive 판정 |
| Battle / simulation/battle.py | 부대·전장·시간·거점 확보·승패 | 명령 처리와 0.2초 단위 전술 계산 |
| Battlefield / core/battlefields.py | 지형 배열·출진·거점·경로 캐시 | 통행·A*·시야·전장 검증 |
| App / ui/app.py | 세계·엔진·선택·모달·현재 화면·선택적 전투 | PyGame 실행과 UI 동작 연결 |
| Painter / ui/theme.py | 화면 Surface·글꼴·버튼 목록 | 같은 스타일의 텍스트·버튼·초상 그리기 |
| MapView / ui/map_view.py | 지도 표시용 캐시 | 좌표 투영과 전략 지도 표시 |
| BattlefieldRenderer / ui/battlefield_view.py | 평면 합성과 아이소 투영 캐시 각 최대 12개 | 재질·경계·건축물 표시, 전술 판정에는 관여하지 않음 |
| IsometricProjection / ui/battlefield_view.py | 화면 사각형·타일 폭·원점 | 2:1 투영과 역변환, 전투 입력과 편집기 공유 |
| MapEditor / ui/editor.py | 전장 작업 사본·브러시·되돌리기·격자 표시 | 편집·검증·저장, 캠페인과 분리된 시험 전투 |

파일 입출력은 `save_world`, `load_world`, `save_battlefield` 같은 모듈 함수다. 구현하지 않은 데이터베이스 Repository, 이벤트 버스, ECS를 구조도에 넣지 않는다. 필요할 때 경계를 유지하며 도입할 수 있다는 설명과 현재 존재한다는 설명은 다르다.

## dataclass를 쓰는 이유

`Officer`, `Memory`, `World`, `Unit` 같은 데이터 클래스는 `@dataclass`로 선언한다. Python이 생성자와 표현·비교의 기본 코드를 만들어 주므로 필드를 한눈에 읽을 수 있다. 실제 `Officer`의 일부를 발췌하면 다음과 같다. 다른 필드와 메서드는 이 설명에서 생략했다.

```python
@dataclass
class Officer:
    # id, name, location, stats 등의 필드는 앞에 선언되어 있다.
    memories: list[Memory] = field(default_factory=list)

    def remember(self, memory: Memory) -> None:
        self.memories.append(memory)
        self.memories = self.memories[-12:]
```

`default_factory=list`는 장수마다 새 기억 목록을 만든다. 가변 목록을 여러 장수가 공유하면 한 명의 패전 기억이 다른 장수에게도 들어가는 결함이 생긴다. `remember`에 길이 제한을 모으면 행동 코드가 기억을 넣을 때마다 같은 제한을 다시 구현할 필요가 없다.

데이터 클래스가 게임의 유효성을 자동으로 보장하지는 않는다. `World`의 필드는 가변이고, 병력 상한·존재하지 않는 지역·잘못된 관계 ID는 별도의 검증이 확인한다. `_paths`처럼 밑줄이 붙은 필드는 내부 사용이라는 관례이지 Python의 접근 차단 장치가 아니다.

## 안정적인 ID로 연결한다

장수의 표시 이름과 식별자는 다르다. `o024`는 장수 ID이고 `s00`은 지역 ID, `f0`은 세력 ID다. `Officer.location`은 `Settlement` 객체 자체를 저장하지 않고 지역 ID를 저장한다. 실제 지역이 필요하면 `world.locations[officer.location]`으로 찾는다. 군주와 수도, 기억의 상대와 연대기 등장인물도 같은 방식이다.

이 구조는 이름을 수정해도 연결을 유지하고 JSON 저장에서 순환 참조를 피한다. 반면 없는 ID를 직접 대입할 수 있으므로 `World.validate`가 참조를 검사해야 한다. 관계 키는 두 ID를 정렬한 `a:b`다. 현재 친밀도는 대칭이며 비대칭 감정을 구현하려면 키와 규칙을 바꿔야 한다.

한 세계에는 장수 객체 200개와 지역 객체 50개가 존재한다. 장수마다 외부 AI 프로세스나 스레드가 따로 실행되는 구조는 아니다. `Engine.step`이 장수를 순서대로 처리하며 공용 판단 함수를 호출한다. 독립된 개성은 데이터와 기억에서 나오고, 실행 흐름은 공유한다.

## 참조를 공유하고, 계산 상태를 분리한다

`App`과 `Engine`은 같은 `World` 객체를 참조한다. `Engine(world)`는 세계를 복사하지 않는다. 엔진이 그 객체의 식량을 바꾸면 다음 화면은 바뀐 값을 읽는다. 이것이 이 코드의 생성자 주입이다. 세계를 교체해서 테스트할 수 있고, GUI 없이 엔진만 실행할 수도 있다.

전투는 경계가 다르다. `Battle`은 생성할 때 세계의 편성·장수·사기를 읽지만 `self.world`를 보유하지 않는다. 진행 중 손실과 이동은 `Unit`과 `Battle` 상태에만 반영된다. 끝난 전투를 `Engine.resolve_battle`이 받아 세계의 병력·점령·기억 등에 적용한다. `resolved` 플래그는 같은 결과가 두 번 반영되는 것을 막는다.

`Battlefield`는 지형 데이터와 판정만 가진다. 이번 평면 지형 개선에서 추가한 `BattlefieldRenderer`는 그 데이터를 읽어 그림을 합성한다. 재질 그림을 바꾸어도 통행 배열은 바뀌지 않는다. 이 분리는 테스트와 맵 에디터가 화면과 같은 전장을 사용하게 한다.

`MapEditor.open`은 읽은 전장을 데이터로 바꾼 뒤 작업 사본을 만든다. 편집 중에는 연결이 끊긴 임시 상태를 허용하고, 저장과 시험 전투 직전에 검증한다. 되돌리기는 JSON 스냅샷을 최대 64개 보관한다. 격자 표시 여부는 보기 상태이며 지형 파일이나 캠페인 저장에 들어가지 않는다.

## 한 번의 클릭이 세계를 바꾸는 과정

일반 전략 행동의 실행 흐름은 다음과 같다.

```text
Painter.button의 action/payload
  → App.dispatch / App.do_action
  → Engine.player_action: 조건 확인
  → Engine.perform: 선택한 행동의 효과
  → Engine.step: 다른 장수·경제·외교·주간 진행
  → ActionResult: 성공 여부와 설명
  → App: 방어전 대기 확인·자동 저장·화면 표시
```

진군은 `ActionResult.battle`로 전투를 반환하며 즉시 한 주를 진행하지 않는다. `App`이 전투 화면을 열고 `Battle.issue`와 `Battle.update`를 호출한다. 종료 후 `Engine.resolve_battle`이 세계에 반영한다. 진행 중 방어전은 `World.pending_battle`에 스냅샷을 두고 주간 진행을 멈춘다. 공격과 방어의 주차 처리 차이는 6장과 저장 검사에서 다룬다.

거부된 명령은 일반적인 플레이 결과이므로 `ActionResult(False, message)`를 반환한다. 손상된 저장이나 불가능한 데이터는 예외로 거부한다. “할 수 없는 행동을 눌렀다”와 “저장 형식이 깨졌다”를 같은 오류 처리로 다루지 않는다. 거부된 전략 명령은 세계와 난수 상태를 바꾸지 않아야 한다.

## 저장과 복원은 객체를 다시 만든다

`World.data`는 데이터 클래스를 사전으로 바꾸고 현재 난수 상태를 저장한다. 현재 시드만 저장하면 수백 주 뒤 다음 난수를 재현할 수 없다. `World.from_data`는 `Memory`, `Officer`, `Settlement`, `Faction`, `Chronicle`, `Quest`와 새 `World`를 만들고 난수 상태를 복원한 뒤 검증한다. 화면의 Surface, 글꼴, 버튼, 선택 상태는 세계 데이터에 들어가지 않는다.

불러오기 뒤 중요한 연결은 `App.world = loaded`와 `App.engine = Engine(loaded)`다. 기존 엔진을 남겨 두면 화면은 새 세계를 보여 주는데 명령은 옛 세계에 반영될 수 있다. 현재 `App.load`는 두 참조를 함께 교체한다. 진행 중 전투도 저장된 전장과 부대 상태로 복원하고 일시정지 상태에서 연다.

전략 판단은 World의 난수를 사용한다. 전투는 별도 시드로 초기 사기에 작은 변화를 준다. 현재 피해 계산은 초기 편성 뒤 새로운 난수를 쓰지 않으므로 저장된 전투 상태를 그대로 이어갈 수 있다. 렌더링은 전략 난수를 소비하지 않는다. 창을 더 자주 그렸다는 이유로 판세가 바뀌면 안 된다.

## 화면 없는 작은 실행 예제

다음 코드는 프로젝트 루트에서 실행할 수 있다. 동일한 내용의 파일은 `docs/examples/oop_flow.py`에 둔다. 난수 시드 742의 세계에서 플레이어를 선택하고 휴식 한 번을 실행한 뒤, 저장 없이 데이터 왕복을 확인한다.

```python
from chaos_kingdom.core.generation import generate_world, select_player
from chaos_kingdom.core.models import World
from chaos_kingdom.core.storage import digest
from chaos_kingdom.simulation.engine import Engine

world = generate_world(742)
select_player(world, "o024")
engine = Engine(world)
assert engine.world is world
result = engine.player_action("rest")
assert result.ok
world.validate()
restored = World.from_data(world.data())
assert restored is not world
assert digest(restored.data()) == digest(world.data())
print(world.turn, result.message, len(world.officers))
```

객체 동일성 `is`와 데이터의 일치가 다른 개념이라는 점도 보여 준다. 엔진은 원래 세계를 공유하고 복원한 세계는 새 객체다. 같은 데이터로 미래 진행을 재현하는 검사는 별도의 자동 테스트가 담당한다.

## 지금의 구조가 가진 부담

현재 `App`에는 화면별 그리기와 문자열 action 분기가 많이 모여 있다. `Engine`에는 경제·외교·경력·결산이 모여 있다. 규모가 커지면 화면 객체와 도메인 서비스로 나눌 후보지만, 이 버전에서 이미 State 패턴이나 독립 경제 서비스를 구현했다고 설명하지 않는다.

먼저 지켜야 할 경계는 새 화면이 엔진을 우회해 자원을 바꾸지 않는 것, 새 지형 그림이 전술 규칙을 바꾸지 않는 것, 새 행동이 허용 조건·비용·AI 평가·저장·검증을 함께 갖추는 것이다. 객체 지향의 효과는 용어보다 이런 변경을 어디에서 안전하게 수행할 수 있는지에서 드러난다.

## 아이소 전투가 바꾼 객체 책임

0.3 베타에서는 `IsometricProjection`을 추가했다. `Battlefield.point`는 게임 좌표 100×60을 반환하고, 투영 객체가 화면으로 바꾼다. `App.field_point`, 부대 선택·이동 입력, `MapEditor.cell`이 같은 변환을 사용한다. 화면만 아이소로 바꾸고 클릭을 옛 직사각형 계산으로 남겨 두면 다른 칸을 선택하게 되므로 양방향 변환을 한 책임에 모았다.

렌더러는 연속 재질을 합성한 뒤 회전·압축하여 평면 바닥을 표시한다. 건축물과 부대는 깊이 순으로 함께 정렬하고 상태 표시는 마지막에 그린다. 투영과 그림 캐시는 세계 저장에 들어가지 않는다. `Battlefield.traversable`은 이동 선분이 건너는 모든 칸을 검사한다. 부대가 비켜 선 뒤 성문 모서리를 자르는 결함은 이 판정과 경로 중심 복귀로 수정했다. 통행은 이미지 픽셀이나 알파에 의존하지 않는다.

`World.unified_by`는 50개 지역의 실제 소유권을 조회하고 `Engine._finish_chapter`가 최종 승리 또는 중간 연대기를 기록한다. 멸망 플래그 개수만으로 통일을 선언하지 않는다. `victor`와 `chapter_report`는 기본값이 있는 필드라 기존 저장을 읽을 수 있다. 이미 96주에 멈춘 옛 저장은 결말 문장을 중간 기록으로 보존하고 다음 연대기로 이어 준다.
