# claude-pet — `fix/cross-os-review-2026-07-11` 후속 리뷰 & 수정 (2026-07-11)

> `fix/cross-os-review-2026-07-11` (커밋 `016b766`)에 대한 적대적(adversarial) 코드 리뷰와,
> 그중 실제로 고친 3건을 정리한 문서. 이 브랜치 자체가 이미 별도 크로스-OS 리뷰의 산출물이므로,
> 여기서는 "그 리뷰가 놓친 것"만 다룬다.

## 1. 리뷰 방법

`016b766` 하나의 diff(14개 파일, +525/-98)에 대해 6개의 독립 서브에이전트를 병렬로 돌림
(라인 스캔 / 삭제-행위 감사 / 크로스파일 추적 / 재사용·단순화 / 효율·고도 / CLAUDE.md 컨벤션).
후보 발견 ~25건을 중복 제거 후 직접 소스 확인·재현으로 검증하여 **10건**을 확정.

## 2. 확정 파인딩 10건 (심각도순)

| # | 위치 | 요약 | 상태 |
|---|------|------|------|
| 1 | `src/hostinfo.py:108` | `write_session_port()`의 `os.replace()`가 unguarded — Windows에서 리더가 파일을 열고 있으면 `PermissionError`로 막 뜬 펫이 크래시 (이 머신에서 직접 재현) | **수정함** |
| 2 | `src/pet.py:1169` | Windows 클릭포커스 fallback이 `"konsole"`/`host_classes`(KWin 클래스명)를 써서 Windows에서 항상 매칭 실패 (dead code) | **수정함** |
| 3 | `bin/claude-pet-hook:165` | `pet_alive()`의 timeout(살아있지만 바쁨)과 확정된 죽음을 구분 못 해서, 이미 살아있는 펫에 발생한 이벤트를 조용히 drop | **수정함** |
| 4 | `src/pet.py:1260` | `_pid_alive()` Windows 분기: `proc_table()`이 계속 빈 값이면(AV/EDR 정책 등) orphan reaper가 영원히 작동 안 함 | 미수정 (엣지케이스) |
| 5 | `src/hostinfo.py:105` | 원자적 쓰기의 `.tmp` sibling 파일이 크래시/replace 실패 시 청소 안 되고 영구 잔존 | 미수정 (경미) |
| 6 | `src/windows_win32.py:202` | `_to_logical()`이 모니터별 논리 원점 보정 없이 스케일로만 나눔 — mixed-DPI 멀티모니터에서 좌표 부정확 | 미수정 (`docs/platform.md`에 이미 known-limit로 명시됨) |
| 7 | `src/hostinfo.py:126` | `pet_alive()`의 connect+recv 타임아웃이 각각 적용되어 최악 ~0.6s 지연 | 미수정 (경미) |
| 8 | `docs/platform.ko.md` | 새 "Known limits" 섹션이 한국어 카운터파트에 반영 안 됨 (CLAUDE.md의 `.ko.md` parity 규칙 위반) | 미수정 |
| 9 | `bin/claude-pet-install-hooks:39` | POSIX 분기가 `sys.executable` 없이 shebang에만 의존 — CLAUDE.md의 "always re-exec with sys.executable" 규칙과 상충 (의도적 트레이드오프) | 미수정 (의도적) |
| 10 | `bin/claude-pet-motion:70` | `_read_port()`의 fallback이 `hostinfo.read_port_file()`을 그대로 복붙 | 미수정 (경미, 정리성) |

## 3. 이번에 고친 3건

### ① `write_session_port()` 크래시 (#1)

**증상**: `os.replace(tmp, path)`가 unguarded. Windows에서 다른 프로세스가 `with open(path) as f: ...`로
그 파일을 여는 그 짧은 순간에 replace가 겹치면 `PermissionError`(WinError 5)로 예외가 `Pet.__init__`
밖으로 튀어나가 막 뜬 펫 프로세스가 크래시(stdout/stderr가 DEVNULL로 리다이렉트돼 조용히).

**수정**: `src/hostinfo.py`에 `_replace_retrying(src, dst, attempts=10, delay=0.02)` 추가. 리더는
컨텍스트 매니저로 마이크로초 단위만 파일을 열므로, 짧은 재시도 루프로 경쟁을 해소. 10회 재시도 후에도
실패하면 예외를 그대로 전파(지속적인 문제를 숨기지 않음).

**테스트**: `test_write_session_port_retries_through_transient_replace_failure`,
`test_write_session_port_raises_after_exhausting_retries` (`tests/test_hostinfo.py`).

### ② Windows 클릭포커스 fallback dead code (#2)

**증상**: `_activate_claude_windows()`이 pid로 못 찾으면 `self.host_classes or ["konsole"]`로 폴백하는데,
`host_classes`는 KWin resourceClass용 값(`"code"`, `"konsole"` 등)이라 Windows 실제 창 클래스명과
전혀 안 맞음. `detect_host()`도 cmd.exe/PowerShell/Windows Terminal을 전부 `"unknown"`으로 분류해서
Windows 네이티브 터미널은 처음부터 매칭 대상이 없었음.

**수정**: `src/hostinfo.py`에 `WIN_CLASSES`/`win_classes(host)` 추가 — Windows Terminal
(`cascadia_hosting_window_class`), 클래식 콘솔(`consolewindowclass`), VS Code(`chrome_widgetwin_1`),
그리고 `"unknown"` 폴백이 위 두 터미널 클래스를 가리킴. `src/pet.py`의 `_activate_claude_windows()`가
`hostinfo.win_classes(self.host)`를 쓰도록 변경.

**테스트**: `test_win_classes_vscode_uses_real_win32_class`,
`test_win_classes_falls_back_to_generic_terminal_classes` (`tests/test_hostinfo.py`),
`test_activate_claude_windows_fallback_uses_win32_classes` (`tests/test_pet_smoke.py`).

### ③ 훅의 이벤트 drop (#3)

**증상**: `bin/claude-pet-hook`의 `launched` 플래그가 "막 launch 시도함"과 "그래서 old 포트로 보내면
안 됨"을 항상 같이 취급. 그런데 `_launch_pet()` 호출은 `pet_alive()`가 `False`이기만 하면 일어나고,
`pet_alive()`는 timeout(=살아있지만 바쁨)도 확정된 죽음과 똑같이 `False`를 반환함. 그 결과 세션 재개 시
펫이 잠깐 바쁘면 그 SessionStart 이벤트가 재시도 없이 그냥 사라짐.

**수정**: `launched` → `launched_fresh`로 바꾸고, **세션에 원래 포트파일이 전혀 없던 경우(진짜 새
세션)에만** send를 스킵하도록 변경. 포트파일이 이미 있던 세션(재개)은 `pet_alive()`가 무엇을 반환하든
항상 전송을 시도 — 최악의 경우도 예전 pre-handshake 동작(항상 best-effort 전송)과 동일한 리스크
수준으로 회귀.

**테스트**: `test_session_start_still_sends_when_resumed_pet_times_out`,
`test_session_start_skips_send_for_brand_new_session`,
`test_session_start_sends_when_pet_confirmed_alive` (`tests/test_hook_payload.py`).

## 4. 테스트 결과

```
python -m pytest -q
173 passed, 2 failed (사전부터 존재하던 무관한 flaky 테스트, 이 수정 전에도 실패 확인함)
```

실패한 2건(`test_pet_alive_false_and_removes_stale_file_on_refused`,
`test_send_removes_stale_port_file`)은 Windows 루프백 소켓의 bind→close→connect 타이밍 특성 때문으로,
이번 수정과 무관 — 수정 전 브랜치에서도 동일하게 실패함(`git stash`로 확인).

## 5. 아직 남은 것 (표 4~10)

우선순위가 낮거나(엣지케이스, 경미한 지연/누수) 이미 문서화된 한계(#6)라서 이번엔 넘어감. 필요하면
후속으로 처리 가능:
- `_pid_alive` Windows 분기의 "빈 snapshot → 항상 alive" 로직을 좀 더 보수적으로.
- `.tmp` sibling 파일 청소(`claude-pet-motion`의 glob 확장).
- `docs/platform.ko.md`에 새 "Known limits" 섹션 반영.
- `bin/claude-pet-install-hooks`의 POSIX 분기 vs CLAUDE.md 규칙 문구 정리(또는 CLAUDE.md 갱신).
- `bin/claude-pet-motion`의 `_read_port` fallback 중복 제거.
