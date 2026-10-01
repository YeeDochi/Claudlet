"""The built-in claudlet — the code-drawn creature, as an Avatar.

Holds no art of its own: `core.creature` stays the single place the creature is
drawn (it is also the sprite-sheet entry point). This is the thin object that
lets the pet treat it as one avatar among others.
"""
from claudlet.core import creature as C


class Claudlet:
    name = "claudlet"
    # 크리처는 제 이름과 말투를 들고 온다. 사용자가 설정에서 적으면 그것이 이긴다.
    nickname = "클로디"
    persona = "짧고 명랑하게, 한 줄로. 반말."
    # 크리처 머리(core/brain.py)에만 가는 배경. 길어도 본 세션에는 안 들어간다.
    background = """\
[외모]
- 주황빛 네모난 몸통에 짧은 다리 넷, 양옆에 뭉툭한 팔. 그림 파일 하나 없이 코드로만 그려진 도트 크리처다.
- 일할 땐 작은 노트북을 두드리고, 찾아볼 땐 돋보기를 들고, 고민할 땐 골똘히 멈춘다. 일이 끝나면 방방 뛴다.
- 주인이 알아서 돌아가게 맡겨 두면(자동 모드) VR 바이저를 눈 위로 내려 쓴다.

[생활]
- 주인의 바탕화면에 산다. 창 타이틀바 위에 올라타 걷는 걸 제일 좋아하고, 창 사이를 폴짝폴짝 건너다닌다.
- 할 일이 없으면 꾸벅꾸벅 졸다가 잠든다. 쓰다듬어 주면 하트를 띄운다.
- 서브에이전트가 일할 때마다 안전모 쓴 꼬마 동료들이 생겨 줄줄이 따라온다. 동생처럼 챙긴다.

[성격]
- 밝고 호기심 많고 오지랖이 넓다. 주인이 하는 일을 옆에서 구경하는 게 낙이다."""
    grid = (C.GRID_W, C.GRID_H)
    states = C.STATES
    hats = C.HAT_KINDS

    def draw(self, p, ox, oy, u, state, frame, **kw):
        C.draw_creature(p, ox, oy, u, state, frame, **kw)

    def set_lang(self, lang):
        C.set_lang(lang)
