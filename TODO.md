# claude-pet TODO

> 프로토타입. 아래는 완료/남은 작업. 리뷰 대기·머지 이력은 `FEATURES_FOR_REVIEW.md`.

## ✅ 완료 (2026-07-09~10)

**상태/반응 (state_engine)**
- 훅→상태 정책 전면 재설계 (`src/state_engine.py`, 순수·유닛테스트). tool_name별 working
  세분화(편집/탐색/웹·전화/서브에이전트/스킬), 우선순위, 디바운스 0.8s, idle→sleeping 60s,
  work/thinking liveness 타임아웃(ESC 중단 대비).
- thinking=전구 → "골똘히 고민" 포즈. celebrate = Stop+비포커스일 때만(매턴 방방 해결).
- 에러 상태 `StopFailure`→`error` 연결. 권한요청/유휴 `Notification` 구분(attention/sleeping).
- 상태별 **타이핑 말풍선** (고민중…/이거 맞아?/다 됐다!/으악!).

**세션/실행 (session-bound)**
- 세션당 펫 1마리. `SessionStart` 훅이 세션 안에서 detached 실행 → **호스트 자동 감지**
  (VS Code/JetBrains/Konsole), 세션별 소켓, `SessionEnd` 종료(취소가능), 시작 위치 분산.
- 호스트 창 기준 좌클릭 활성화 + 포커스 판정(`focus.py`, xprop/kdotool). SIGTERM 클린업.
- `/claude-pet` 스킬 — 기본 **현재 세션에 attach** + `standalone` 옵션.

**상호작용/물리/창**
- 드래그-던지기 **물리** (`src/physics.py`): 중력·공기저항·벽/바닥/천장 반발·속도상한. 모든
  상태에서 중력 적용(공중이면 낙하).
- **창 올라타기/담기** (`src/windows.py`, KDE 전용·게이팅): KWin+DBus 지오메트리 피드(Wayland
  창까지 봄). 자동등정 없음(착지/드롭으로만), minimized 제외, 발 정렬, sticky(전 데스크톱).
- **held**(잡히면 웃으며 대롱), **falling**(떨어지면 쭉) 애니.
- 좌우반전 시 몸만 반전(텍스트/말풍선 정상). 트레이 아이콘(상태 반영) + 작업표시줄 숨김.

## 🐞 남은 버그 / 다듬기
- [x] **우클릭 메뉴 동작** — 새 모션/float 메뉴 라이브 검증됨 (2026-07-10).
- [x] `_activate_claude` 일회성 KWin 스크립트 — 고정 플러그인명 + unload + _cleanup 정리로 누적 제거.
- [x] perching 마이너: 작은 창 삐져나옴 → 펫보다 작으면 가운데 정렬; windowList 스택순서 →
      `workspace.stackingOrder` 사용; 담긴 창이 다른 데스크톱 → geom 스크립트가 현재 데스크톱만 push.
- [x] session-bound 마이너: SIGKILL orphan → `--claude-pid` 리퍼(부모 죽으면 종료);
      동시 SessionStart 이중실행 → 세션별 flock(중복 실행 즉시 종료, 라이브 검증).
- [x] 리퍼 오판 수정: 훅이 넘기던 `os.getppid()`는 일회성 shell이라 세션 시작 ~3s 후 펫이
      자멸 → `/proc` 부모 체인을 타고 진짜 `claude` PID를 잡아 넘김. (2026-07-10 `feat/reaper-pid-fix`)
- [x] work_search 좌우 뛰기: 앵커 고정으로 로컬 양방향 (화면 가로지르기/한쪽 드리프트 제거).
- [x] 배회 중 창 이동/왼쪽 벽 뚫기: 담긴 창이 움직이면 펫도 같이 이동(ride-along) +
      매 틱 x를 bounds로 클램프. (2026-07-10)

## 📋 다음 계획 (미착수)
- [x] **멀티모니터** — 배회/바닥 계산 전체 모니터 기준 (3모니터). (2026-07-10 완료, `b08c46e`)
- [x] **모션 강제 실행 커맨드** `/claude-pet <motion>` — jump/wave/sing/juggle/float +
      기존 상태 노출. (2026-07-10 머지 `2b015c6`) + 우클릭/트레이 모션 메뉴, float 토글,
      커서 따라오기(KWin 커서 피드), 창 안 튕기기까지. 73 테스트 통과.
- [x] **이벤트→모션 매핑 커스텀** — `~/.config/claude-pet/config.json`의 `tools`/`events`로
      도구·이벤트→모션 오버라이드. `petconfig.py` 로더(검증), `StateEngine` 인자 주입(순수 유지).
      README 문서화. (2026-07-10)
- [x] **오토 진행 전용 상태/애니** — `permission_mode` auto/bypass면 VR 바이저 착용.
      작업 종류별 변형(auto_computer=파란 코드창 / auto_search=돋보기 / auto_web=폰 /
      auto_agent=바이저 낀 분신 / auto_skill=붉은 안광), 웹·검색만 배회. 바이저는
      **모든 상태에서 유지**(작업=내려씀 / 그 외=머리 위로 젖힘, `auto_active`). (2026-07-10)
- [x] **걷기 폴리시** — 걷기 사이클 자연스럽게. (2026-07-10 머지 `feat/walk-policy`)
- [x] **새 상태 아트 튜닝** — 돋보기/전화/분신 prop 대비·형태·미세 애니로 또렷하게. (2026-07-10)
- [x] plan 승인/AskUserQuestion "답 기다림" 세분화 — `asking` 상태("응?", attention보다
      상위 우선순위), `PreToolUse`의 `ExitPlanMode`/`AskUserQuestion` tool_name 매핑. (2026-07-10)
- [~] 진짜 도트 스프라이트 / GIF override — 만들었다가 **제거**(별로여서). 전부 코드 렌더로 복귀. (2026-07-10)

## 🪟 창/세션/포커스 (2026-07-10 — `feat/host-window-focus`)
공통 기반: geom 피드에 **pid** 추가 → claude_pid의 `/proc` 조상들과 매칭해 **이 세션의 호스트
창(internalId)**을 특정. (`windows.find_host`/`covered_by_higher` 순수함수, 유닛테스트)
- [x] **포커스 대상 콘솔 혼선** — `_activate_claude`가 첫 클래스 매칭 대신 **호스트 창(internalId)
      우선** 활성화, 못 찾으면 클래스 폴백. 콘솔 2개도 각 세션이 자기 창을 콕.
- [x] **올라탄/담긴 창 내려가면 펫 숨김** — `_update_visibility`: 펫이 **올라타 있거나(perch)
      담긴(contain) 그 창**이 최소화/닫힘(피드에서 사라짐)되거나 상위 창에 완전히 가리면 `hide()`,
      돌아오면 `show()`. **배경화면을 배회 중(창 밖)이면 최대화가 떠도 안 숨김.** 비-KDE 피드
      없으면 no-op(안전). windowActivated에도 재덤프(raise 감지). (`window_under_feet` 순수함수)
- [~] **IDE 세션별 별도 펫** — 조사 결론: IntelliJ 등은 **프로젝트당 최상위 창 1개**뿐이라, 한 IDE
      창 안 여러 터미널 탭(=여러 세션)을 WM 레벨에서 창으로 분리할 수 없음(탭 단위 창이 없음).
      → 세션별 펫은 이미 각자 뜨고, 전부 같은 IDE 창을 호스트로 올바르게 인식/포커스/숨김함.
      **탭 단위 시각 분리는 WM 한계로 불가** (사용자 예상과 동일). 별도 코드 없음.
- [ ] Mac / Windows 이식 — 코어(state_engine/creature/hook)는 이식가능. 창 활성화·포커스·
      perching만 OS별(Win32/AppleScript). GNOME 제외. perching은 KDE 전용 유지.

## 🧰 배포/운영
- [ ] GitHub 공개 전 점검(README 경로, 라이선스 홀더). 설치 스크립트 의존성 체크(PyQt6, wmctrl).
- [ ] 비-KDE/X11 순정 폴백 동작 확인.

---
_검증된 것_: 유닛테스트 114개 통과. session-bound 펫 2마리 독립 반응·SessionEnd 퇴장(라이브),
perching(창 담기/착지/minimized 제외/sticky, 라이브), 물리(던지기·천장·전상태 중력, 라이브),
말풍선·잡기/낙하 애니(라이브), `/claude-pet` attach, 트레이·하단바숨김, 훅 자동실행.
_미검증_: Mac/Windows, 우클릭 펫메뉴 안정성.
