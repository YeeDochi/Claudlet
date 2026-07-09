# claude-pet — 리뷰 대기 기능 목록

> Claude가 TODO 기반으로 자율 개발한 피처들. 각 피처는 전용 브랜치에 있고,
> 네가 "이 피처 보자" 하면 같이 훑고 `main`(현재 `master`)에 머지한다.
> ✅ = 브랜치에서 완성·테스트 통과, 리뷰 대기 | 🚧 = 작업 중 | 📋 = 계획(아직 안 만듦)

## 리뷰 대기 (완성됨)

_(아래로 채워짐)_

## 계획 — Claude 추천 우선순위

| 우선 | 브랜치 | 내용 | 왜 추천 |
|---|---|---|---|
| 1 | `feat/session-bound-pets` 🚧 | **핵심 재설계**: 세션당 펫 1마리, 세션 안에서 실행(SessionStart 훅). 세션별 소켓, 호스트 감지 흡수(VS Code/IntelliJ/Konsole 창에 활성화·포커스 맞춤), SessionEnd 시 종료. 설계: `docs/superpowers/specs/2026-07-09-session-bound-pets.md` | 사용자 결정(2번). host-detection·좌클릭 버그·celebrate 켜기까지 여기 다 흡수 |
| 2 | `feat/bubble-text` | 말풍선에 상태별 실제 텍스트("고민중...", "이거 맞아?", "다 됐다!") 한 글자씩 타이핑 | 체감 즐거움 큼, creature.py 내 자기완결 |
| 3 | `feat/held-render` | 드래그 중(held) 렌더 상태 정리 — 들려있을 때 팔다리 버둥/놀란 표정 | 지금 어정쩡한 렌더 개선, 작고 안전 |
| 4 | `feat/multimonitor` | 배회·바닥 계산을 전체 모니터 기준으로 (3모니터 대응) | 멀티모니터 실사용, 명확히 테스트 가능 |
| 5 | `feat/auto-run-state` | 오토/plan 등 "혼자 쭉 작업" 전용 상태/애니 | 상태 표현 확장 |
| 6 | `feat/walk-polish` | 걷기 사이클·좌우 반전 자연스럽게 (아트) | 아트라 네 눈 필요 → 후순위 |
| — | `/claude-pet` 스킬 | 세션 펫 수동 on/off 스킬 (session-bound의 follow-up) | v1 후 |
