# claudlet 기여 가이드

[English](CONTRIBUTING.md) | **한국어**

관심 가져줘서 고마워요 — 지금 제일 급한 건 **macOS 검증**이지만(아래 참고), 버그
수정, 문서, 다른 플랫폼 리포트도 다 환영이에요.

## 개발 환경 설정

```bash
git clone https://github.com/YeeDochi/Claudlet.git
cd Claudlet
pip install -e . pytest
# macOS에서 창 통합 기능 테스트할 때만:
pip install pyobjc-framework-Quartz
```

editable 설치(`-e .`)라서 코드 고치면 바로 반영돼요. `pipx install claudlet`과는
달라요 — pipx는 격리된 venv에 복사해 넣고 `pipx upgrade`/`pipx install --force`할
때만 갱신되니, 그 복사본을 직접 고치려고 하지 마세요.

체크아웃한 코드로 펫을 띄우고, 실제 Claude Code 세션을 여기로 연결해서 테스트할 수
있어요:
```bash
claudlet             # 이 체크아웃에서 standalone 펫 실행
claudlet-install     # 훅 + /claudlet 스킬 등록 — 실제 세션이 이 코드로 반응하게
```

## 테스트 실행

```bash
pytest
```
`tests/conftest.py`가 `src/`를 `sys.path`에 넣어줘서, 설치 없이 체크아웃에서 바로
돌아가요. 아직 테스트용 CI는 없어요 — 유일한 GitHub Action(`publish.yml`)은 버전
태그가 붙을 때 PyPI에 빌드/배포만 해요 — 그러니 PR 올리기 전에 로컬에서 테스트
스위트를 꼭 돌려주세요.

## 코드 스타일

- 코드가 *무엇을* 하는지 설명하는 주석은 안 써요 — *왜* 그런지, 그리고 그게 코드만
  봐서는 안 드러날 때만 써요. `state_engine.py`가 이 스타일의 기준이에요 — 짧고,
  what이 아니라 why.
- `state_engine.py`는 일부러 Qt에 의존하지 않고, 벽시계를 직접 읽는 대신 `now`를
  인자로 받아요 — 그래야 화면 없이도 순수하고 유닛테스트 가능한 상태로 남아요. 새
  엔진 로직도 이 형태를 유지해주세요.
- 플랫폼별 코드는 OS별로 분리돼 있어요(`windows_win32.py`, `windows_macos.py`,
  호스트별로 분기하는 `focus.py`) — 공유 모듈에 `sys.platform` 체크를 흩뿌리지
  마세요.

## 브랜치 & 커밋

- `develop`이 작업 브랜치예요 — PR은 `master`가 아니라 `develop`으로 보내주세요.
- `master`엔 릴리즈된 태그만 올라가요(`scripts/release.sh`가 릴리즈할 때
  fast-forward 함) — 직접 커밋하지 마세요.
- 커밋 메시지는 Conventional Commits 형식이에요: `type(scope): summary`
  (`feat`, `fix`, `docs`, `chore`, …) — 실제 예시는 `git log` 참고.
- 릴리즈(버전 업, 태그, 배포)는 메인테이너 전용이고 `scripts/release.sh`로 해요 —
  컨트리뷰터가 버전 관리를 신경 쓸 필요는 없어요.

## 지금 제일 필요한 것

**macOS 검증.** macOS 창 통합 경로 전체(`src/claudlet/windows_macos.py`,
`pet.py`에 연결됨)는 실제 Mac 없이 애플 문서만 보고 작성한 코드라 — 한 번도 실행된
적이 없어요. 정확한 체크리스트(화면 기록 권한, perch, occlusion, click-to-focus,
트레이)는 **[각자 OS에서 테스트 도와주세요](docs/platform.ko.md#각자-os에서-테스트-도와주세요)**를 참고하세요.
공개 발표 전 마지막 관문이라, 여기 리포트가 특히 값져요.

## 버그 제보 / 기능 요청

GitHub 이슈로 올려주세요. OS, `claudlet-version` 출력, (펫 동작 버그라면) 관련된
Claude Code 훅 이벤트를 알고 있다면 같이 적어주세요. 아직 내장 이벤트 로그가 없어서,
정확한 재현 절차가 큰 도움이 돼요.

## 라이선스

기여하면 그 변경사항이 프로젝트의 **MIT** 라이선스(코드)를 따르는 데 동의하는 거예요
— [LICENSE](LICENSE) 참고. 크리처 아트는 **CC0**([NOTICE](NOTICE))이고, 새로
기여하는 아트도 CC0였으면 해요.
