# Cursor Auto Prompter (macOS)

Cursor IDE 채팅창에 **설정한 프롬프트를 일정 시간마다 자동으로 입력 + 전송**해주는 macOS 전용 데스크탑 앱입니다.

> 예: "5분마다 `계속 진행해줘.` 라는 프롬프트를 Agent 모드 채팅에 자동 전송"

---

## 주요 기능

- 반복 입력할 **프롬프트**(여러 줄, 한글/이모지 지원) 지정
- 실행 **간격**(초/분/시간) 지정
- Cursor 입력 위치 **모드 선택**:
  - **Composer / Agent (Cmd+I)** (기본) — Command 키와 I 키를 동시에 눌러 채팅창을 열고 프롬프트 입력
  - Ask Chat (Cmd+L)
  - Inline Edit (Cmd+K)
  - 이미 열린 입력칸에 그대로 입력
- **시작 즉시 1회 실행** 옵션
- **최대 실행 횟수** 제한 (비우면 무제한)
- **Enter 자동 전송** on/off
- **즉시 한 번 보내기** (테스트용)
- 실시간 **카운트다운 + 실행 횟수 + 로그**
- 최근 사용 프롬프트 자동 저장 (최근 10개)
- 종료 시 모든 설정 자동 저장 (`~/.cursor_auto_prompter/config.json`)
- 클립보드를 잠시 사용하지만 **작업 후 원복**

## 동작 원리

순수 표준 라이브러리만 사용합니다. macOS의 **AppleScript(`osascript`) + System Events**로 Cursor를 활성화한 뒤, 모드에 따라:

- **Composer / Agent (Cmd+I) 모드 (기본):**
  1. `Command` 키와 `I` 키를 동시에 눌러 채팅 입력창을 연다
  2. 클립보드를 실제 프롬프트로 교체한 뒤 paste
  3. `Return`을 눌러 전송
- **Cursor Agents Window 모드:**
  1. `Cmd+Shift+P`로 Command Palette를 연다
  2. `Open Agents Window` 명령어를 클립보드 paste로 입력
  3. `Return`으로 명령을 실행 → Agents 창이 열리고 새 에이전트 입력칸에 포커스
  4. 클립보드를 실제 프롬프트로 교체한 뒤 paste
  5. `Return`을 눌러 전송
- **Cmd+I / Cmd+L / Cmd+K 모드:** 해당 단축키로 채팅창을 연 뒤 paste & 전송
- **focused 모드:** 이미 입력칸에 포커스가 있다고 가정하고 paste & 전송

> 기본 모드는 AppleScript의 `key code 34 using {command down}`으로 실제 `Command+I` 조합을 보냅니다.

> 클립보드 paste 방식을 쓰기 때문에 길거나 한글이 섞인 프롬프트, 한글 IME가 켜진 상태에서도 정확히 입력됩니다.

## 시스템 요구사항

- macOS 12+ (Monterey 이상 권장)
- Python 3.10+ (Tkinter 포함 빌드)
- Cursor IDE 설치
- **손쉬운 사용(Accessibility) 권한** — 키 입력을 보내려면 필요

### Tkinter가 없다는 오류가 난다면

```bash
brew install python-tk
```

또는 [python.org 공식 인스톨러](https://www.python.org/downloads/macos/)로 Python을 다시 설치하세요.

## 설치 & 실행

```bash
git clone <this-repo>  # 또는 폴더로 이동
cd automation_desktop_macbook
./run.sh
```

또는 직접:

```bash
python3 app.py
```

## 권한 설정 (필수)

처음 실행하고 "시작" 버튼을 누르면 macOS가 **손쉬운 사용** 권한을 요청합니다.

1. **시스템 설정** → **개인정보 보호 및 보안** → **손쉬운 사용** 으로 이동
2. 이 앱을 실행한 프로세스(예: **터미널**, **iTerm**, **Python**)를 추가하고 토글 ON
3. 한 번 끄고 켠 뒤 다시 시작

> Cursor에 보내는 키 입력은 모두 macOS Accessibility API를 통해 발생하므로 권한 없이는 동작하지 않습니다.

## 사용 방법

1. 상단 텍스트 박스에 반복 입력할 프롬프트를 작성합니다.
2. **간격**과 **단위**(초/분/시간)를 지정합니다.
3. 사용할 Cursor **모드**를 선택합니다 (기본: **Composer / Agent (Cmd+I)**).
4. (선택) **최대 실행 횟수**, **시작 즉시 1회 실행**, **Enter 자동 전송** 등의 옵션을 조정합니다.
5. **▶ 시작** 클릭. Cursor가 자동으로 활성화되며 프롬프트가 입력 + 전송됩니다.
6. 진행 상황은 하단 **상태**(다음 전송까지 카운트다운) 와 **로그**에서 확인할 수 있습니다.
7. **⚡ 즉시 한 번 보내기** 로 동작을 미리 테스트할 수 있습니다.

## 팁

- 자동화가 시작되면 **마우스나 키보드를 건드리지 마세요.** 포커스가 빠지면 입력이 다른 앱으로 향할 수 있습니다.
- Cursor 창이 여러 개 열려 있어도 가장 앞으로 활성화된 창에 입력됩니다.
- 기본 모드는 `Cmd+I`로 채팅 입력창을 여는 흐름입니다. Cursor에서 `Cmd+I`가 채팅 입력창을 여는 상태여야 합니다.
- 한글 입력 모드(IME)가 켜져 있어도 paste 방식이라 영향을 받지 않습니다.

## 안전장치

- 빈 프롬프트는 전송되지 않습니다.
- 클립보드는 작업 직후 원래 내용으로 복원합니다 (옵션으로 끌 수 있음).
- 최대 실행 횟수에 도달하면 자동 정지합니다.
- 창을 닫거나 **■ 정지** 버튼을 누르면 즉시 중단됩니다.

## 파일 구성

```
.
├── app.py            # Tkinter 기반 GUI (메인 엔트리)
├── automator.py      # AppleScript 기반 Cursor 자동화
├── scheduler.py      # 반복 실행 스레드
├── config.py         # 설정 영속화
├── requirements.txt
├── run.sh            # 실행 스크립트
└── README.md
```

설정 파일 경로: `~/.cursor_auto_prompter/config.json`

## 알려진 한계

- macOS 전용입니다. Windows/Linux에서는 동작하지 않습니다.
- Cursor 단축키를 사용자가 변경한 경우 동작하지 않을 수 있습니다 (현재 기본 단축키 기준).
- 자동화가 진행되는 동안에는 Cursor가 포커스를 가져가므로, 실행 중 다른 작업이 어렵습니다 — 일반적으로 자리를 비울 때 사용하는 시나리오를 가정합니다.

## 문제 해결

| 증상 | 원인/해결 |
| --- | --- |
| `osascript ... -1719 오류` | 손쉬운 사용 권한 미부여 — 시스템 설정에서 허용 |
| `Cursor가 프론트가 아닙니다 (현재 frontmost: ...)` | Cursor가 최소화/숨김 상태이거나 다른 앱이 포커스를 가로챔. Cursor 창을 한 번 띄워둔 뒤 다시 시도 |
| `Notification processing demo` 같은 엉뚱한 창이 열림 | (1) Cursor 활성화가 늦거나, (2) Command Palette 명령어가 사용자의 Cursor 버전과 안 맞아 fuzzy match가 다른 명령을 실행한 경우. **🔍 채팅창만 열어보기 (진단)** 버튼으로 어디서 어긋나는지 확인하세요. 명령어를 `Open Agents Window` / `Agents Window` 등으로 바꿔가며 테스트 |
| 프롬프트가 다른 앱에 입력됨 | 실행 중 마우스/키보드를 건드림. 다시 시도하세요 |
| Cursor 채팅창이 안 열림 | Cursor에서 `Cmd+I`가 채팅 입력창을 여는지 확인하세요. 앱 설정의 모드는 기본 `Composer / Agent (Cmd+I)`를 사용하세요 |
| Tkinter import 오류 | `brew install python-tk` 또는 python.org 인스톨러 사용 |

### "🔍 채팅창만 열어보기 (진단)" 버튼 사용법

이 버튼은 **채팅창/Agents 창을 여는 단계까지만 실행**하고 프롬프트 입력은 하지 않습니다. 로그에 다음 두 값이 찍힙니다.

- `시작 시 frontmost = '...'` — 자동화 시작 직전 어떤 앱이 활성 상태였는지
- `작업 후 frontmost = '...'` — 자동화 직후 어떤 앱이 활성 상태인지 (Cursor가 아니어야 다른 앱으로 키 입력이 새고 있다는 신호)

이 결과를 보고:
- 작업 후 frontmost가 `Cursor`가 아니라면 → 활성화 자체가 실패. Cursor 창을 보이게 띄워두고 재시도.
- frontmost가 `Cursor`인데도 엉뚱한 창이 떴다면 → Command Palette 명령어가 사용자 Cursor 버전과 안 맞는 것. **Palette 명령어** 칸에 다른 변형(예: `Open Agents Window`, `Cursor: Agents Window`)을 넣어 시도.
