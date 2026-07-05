# 🚀 Pick Dream AI 챗봇 및 예약 시스템 고도화 총정리

이 문서는 이전 담당자(AI)가 진행한 챗봇의 **전면 리팩토링 및 예약 시스템 버그 수정 내역**을 하나로 통합하여, 다음 담당자가 프로젝트 현황을 완벽하게 파악할 수 있도록 작성한 요약본입니다. (작업 브랜치: `feature/ai-refactoring` -> `main` 병합 완료)

---

## 1. 🤖 AI 챗봇 아키텍처 전면 리팩토링 (가장 큰 변화)
이전에는 챗봇이 단순히 사용자의 말에 한 번 대답하고 끝나는 단발성 스크립트 형태였다면, 이번 업데이트를 통해 진정한 **'비서' 형태의 에이전트 아키텍처**로 완전히 탈바꿈했습니다. (`functions/main.py` 대규모 리팩토링)

### 1.1. Function Calling (도구 호출) 시스템 도입
- **변경 사항**: Gemini API의 최신 기능인 **Function Calling(Tools)**을 전면 도입했습니다. 
- **효과**: 기존에는 정규표현식이나 텍스트 파싱에 의존하여 예약을 처리했다면, 이제 AI가 사용자 의도를 파악해 `recommend_room`, `reserve`, `cancel_reservation` 등의 지정된 파이썬 함수를 스스로 인자를 채워 호출합니다. 

### 1.2. Firestore 기반 대화 기록(Chat History) 유지
- **변경 사항**: 기존에는 사용자가 "예약할래" -> "강의실은?" -> "101호" 처럼 말할 때 문맥이 끊겼습니다. 이를 해결하기 위해 파이어베이스 Firestore에 `ChatHistory` 컬렉션을 만들고, 사용자의 `userID`를 기반으로 이전 대화 내역(History)을 불러와 모델에 주입하도록 수정했습니다.
- **효과**: AI가 "아까 말씀하신 시간대로 예약해드릴까요?"처럼 **멀티 턴(Multi-turn) 대화**를 완벽하게 기억하고 이어갈 수 있게 되었습니다.

### 1.3. RAG(검색 증강 생성) 방식의 데이터 연동
- **변경 사항**: AI가 파이어베이스 `rooms`, `Notices`, `Reservations` 데이터베이스에 직접 접근해 실시간으로 빈 강의실을 찾거나, 중복 예약을 확인하고, 공지사항을 읽어올 수 있도록 RAG 형태의 데이터 파이프라인을 구축했습니다.

---

## 2. 🐛 AI 예약 로직 및 파이어베이스 버그 수정

전면 리팩토링 직후 튀어나온 다양한 디버깅/버그 수정 내역입니다.

### 2.1. 파이어베이스 복합 인덱스 의존성 제거 (에러 해결)
- **문제**: 예약 시 `userID`와 `startTime` 쿼리로 인해 `Failed to pre-condition` (인덱스 필요) 에러가 발생.
- **해결**: `has_conflict()` 함수를 수정하여 특정 조건(예: `roomID`)으로 전체 목록을 불러온 뒤, 파이썬 백엔드(메모리) 상에서 시간을 비교해 겹치는 예약을 검사하도록 변경했습니다. (인덱스 생성 대기 불필요)

### 2.2. "자동으로 빈 방 찾기" 기능 (UX 극대화)
- **문제**: 사용자가 방 번호를 말하지 않았을 때 AI가 계속 되묻거나 예약 진행을 거부하는 문제 발생.
- **해결**: 예약 시 방 번호가 누락되면, `rooms` 컬렉션을 순회하여 인원수(`capacity`)와 예약 겹침(`has_conflict`)을 검사한 뒤 **가장 알맞은 빈 방을 찾아 즉시 예약**하도록 고도화했습니다.

### 2.3. 자동 예약 시 문서 ID 해시 삽입 버그 수정
- **문제**: 빈 방을 자동 예약할 때 실제 방 번호(예: `7202`)가 아닌 Firestore 고유 문서 ID(예: `K95Bhpc...`)가 DB에 저장되는 버그.
- **해결**: `extract_room_id` 함수를 거치게 하여 올바른 방 번호를 파싱하고 삽입하도록 수정했습니다.

### 2.4. Python 문법 오류 (지역 변수 스코프 등) 수정
- **해결**: 자동 예약 과정에서 정규표현식(`import re`)이 로컬 스코프에 갇히는 `UnboundLocalError` 수정 및, 방 정보를 못 가져왔을 때 발생하는 `NoneType` 에러를 모두 예외 처리하여 서버 다운을 방지했습니다.

### 2.5. LLM 모델 교체 (503 / 429 혼잡 에러 회피)
- **해결**: 파이어베이스 요금 한도를 늘린 뒤, 서버가 혼잡한 `gemini-2.5-flash-lite` 대신 더욱 안정적이고 강력한 `gemini-2.5-flash` 모델로 코드를 변경했습니다.

---

## 3. 📱 안드로이드 앱 - 파이어베이스 연동 수정

### 3.1. 앱 내 '대여하기' 클릭 시 보안 규칙(Security Rules) 거절 문제
- **문제**: 안드로이드 앱의 '대여하기' 화면에서 수동으로 예약 시 "예약 중 오류가 발생했습니다." 토스트 메시지 발생.
- **원인 및 해결**: `firestore.rules` 파일에 `request.auth.uid == request.resource.data.userID` (파이어베이스 Auth ID 일치) 권한이 걸려있었습니다. 하지만 안드로이드 앱은 **'학번(예: 20201234)'**을 `userID`로 사용하므로 보안 규칙에 막혔습니다. 이를 해결하기 위해 `Reservations` 컬렉션 권한을 `allow read, write: if request.auth != null;` 로 완화하여 정상 작동하게 만들었습니다.

---

## 4. 최종 인수인계 사항
- **Functions**: `functions/main.py`에 AI 코어 로직이 전부 담겨있습니다. 향후 배포 시 `firebase deploy --only functions` 를 실행하세요.
- **Rules**: 앱에서 수동 예약이 잘 되게 하려면 변경된 `firestore.rules`를 꼭 덮어씌우거나 `firebase deploy --only firestore:rules` 로 배포해야 합니다.
- **Git 통합**: `feature/ai-refactoring` 브랜치의 모든 작업 내역을 `main` 브랜치로 병합(Merge)해 두었습니다!

---

## 5. 2026-06-27 Codex 점검 및 안정화

- 예약·날짜·강의실 ID 처리를 `functions/reservation_utils.py`로 분리하고 순수 단위 테스트를 추가했습니다.
- 방을 지정하지 않은 예약에서 사용자가 전달한 시간을 임의의 기본값으로 덮어쓰던 문제를 제거했습니다. 예약 시간은 필수이며, 이용 시간만 2시간을 기본값으로 사용합니다.
- 자동 배정과 추천이 Firestore 문서 해시가 아니라 앱이 저장하는 정규화된 `roomID`로 충돌을 검사하도록 통일했습니다.
- 예약 취소·변경도 같은 정규화된 `roomID` 기준으로 조회하도록 맞췄습니다. 예약 시간 변경 시 `startTimestamp`/`endTimestamp`도 함께 갱신되도록 수정했습니다.
- 문자열로 저장된 기존 예약 시간도 추천 시 충돌 검사에 반영하고, 취소·거절 예약은 충돌에서 제외했습니다.
- 예약 문서에 Firebase Auth UID인 `ownerUid`를 추가했습니다. Firestore 쓰기 규칙은 생성·수정·삭제를 예약 소유자에게만 허용하며, 기존 문서는 학번으로 소유자를 판별합니다.
- 챗봇 요청 본문과 메시지 길이를 검증하고, 내부 예외 상세가 사용자 응답으로 노출되지 않도록 정리했습니다.
- `ChatHistory` 문서를 최근 10개 메시지로 제한해 문서가 무한히 커지지 않도록 했습니다.
- UTF-16으로 저장되어 Android 테스트 빌드를 깨뜨리던 `DateParseTest.java`를 UTF-8 테스트로 교체했습니다.
- 모든 경로의 `serviceAccountKey.json`을 Git에서 제외하도록 ignore 규칙을 강화했습니다. 이미 노출된 키는 GCP/Firebase에서 폐기하고 새 키로 교체해야 합니다.

### 검증 명령

```bash
python -m unittest discover -s functions/tests -v
./gradlew test
```

---

## 6. 2026-07-05 Codex 후속 점검 메모

### 완료
- 로그인 화면에서 앱 실행 시 Firestore/Auth 테스트 데이터를 자동 삽입하던 `seedDatabaseIfNeeded()` 호출과 구현을 제거했습니다.
  - 제거 이유: 실제 Firebase 데이터 오염, 테스트 계정/임시 데이터 하드코딩, 설치 초기화 시 재실행 가능성.
  - 테스트/초기 데이터가 필요하면 앱 런타임 코드가 아니라 별도 스크립트나 Firebase 콘솔에서 관리하는 방향이 안전합니다.
- `functions/main.py`의 예약 처리 로직에서 죽은 코드와 도달 불가능한 분기를 제거했습니다.
  - `for doc in []:` 임시 루프 제거.
  - `if False and has_conflict(...)` 비활성 분기 제거.
  - 도달 불가능한 중복 `return` 제거.
  - `handle_reserve()` 내부의 인원 정규화, 필수 필드 검사, 시간 파싱, 예약 문서 생성 로직을 작은 헬퍼 함수로 분리했습니다.
- AI 예약의 임시 상태 문서인 `PendingReservations`에 `flowType`을 도입했습니다.
  - `new_reservation`: 새 예약 확인 대기.
  - `alternative_new_reservation`: 빈 강의실 자동 제안 후 새 예약 확인 대기.
  - `change_existing_reservation`: 기존 예약을 다른 조건/강의실로 변경하는 확인 대기.
  - `blocked_existing_reservation`: 같은 시간에 이미 사용자 예약이 있어 새 예약을 만들 수 없는 차단 상태.
  - `blocked_existing_reservation`은 더 이상 `예약 확정`으로 처리되지 않도록 방어 로직을 추가했습니다.
  - 사용자가 단순히 “다른 강의실로 해줘”라고 말한 경우 기존 예약 변경으로 해석하지 않고, “기존 예약을 다른 강의실로 변경해줘”처럼 명시적으로 요청한 경우에만 변경 제안으로 이어지도록 분리했습니다.
- Android 사용자 식별자 접근을 `UserRepository`로 공통화했습니다.
  - `getCurrentUid()`, `getCurrentUser()`, `getCurrentStudentId()`를 추가했습니다.
  - 예약 내역, 후기 내역, 후기 작성, 홈 현재 예약, 수동 예약, 찜 강의실, LLM 알림 후속 처리에서 반복되던 `FirebaseAuth.currentUser`/`User` 문서 조회를 제거했습니다.
  - `LoginActivity`는 인증 자체를 담당하므로 직접 `FirebaseAuth` 사용을 유지했습니다.
  - `LlmFragment`의 메시지 전송은 Firebase ID Token 발급이 필요하므로 직접 `currentUser.getIdToken()` 사용을 유지했습니다.
  - 검증: Android Gradle 테스트 `.\gradlew.bat test` 통과.
- Android 단위 테스트를 보강했습니다.
  - `ReservationTimeUtils`를 추가해 수동 예약의 시간 문자열 생성, 파싱, 과거 시간 판정, 예약 겹침 판정을 ViewModel 밖으로 분리했습니다.
  - `RoomIdUtilsTest`를 추가해 `7202`, `202`, `7강의동` 검색/alias 동작을 검증합니다.
  - `ReservationTimeUtilsTest`를 추가해 시간 파싱, 경계가 맞닿은 예약 허용, 부분 겹침 차단, 취소/거절 예약 제외, 과거 시간 판정을 검증합니다.
  - 검증: Android Gradle 테스트 `.\gradlew.bat test` 통과.

### 다음 우선순위
1. Firestore 보안 규칙 재검토
   - 현재 기능 안정화를 위해 완화된 규칙을 소유자 기반 권한으로 다시 좁히는 작업 필요.
