# PickDream

PickDream은 빈 강의실을 검색하고 대여 예약을 관리할 수 있는 Android 앱입니다. 수동 예약과 Firebase Functions 기반 AI 예약 채팅을 함께 제공합니다.

## 주요 기능

- 강의실 목록 및 상세 정보 조회
- 기자재 조건 기반 강의실 검색
- 즐겨찾기 강의실 관리
- 날짜/시간 기반 강의실 예약
- 과거 시간 및 중복 예약 방지
- 현재 예약, 예정 예약, 지난 예약 조회
- 예약 상세 확인 및 취소
- 리뷰 작성 및 공지사항 조회
- AI 채팅 기반 예약 생성, 조회, 변경, 취소
- 예약 확정, 대체 강의실, 취소 후보를 카드/버튼으로 표시
- 오래된 AI 채팅 기록 자동 정리

## AI 예약 예시

```text
사용자: 모레 오전 11시에 7202 강의실 5명 예약해줘
AI: 예약 내용을 확인해 주세요.
버튼: 예약 확정
```

이미 요청한 강의실이 예약되어 있으면 AI가 먼저 예약 불가를 안내하고, 같은 시간대에 이용 가능한 다른 강의실을 제안합니다.

## 기술 스택

- Android: Kotlin, XML View Binding, Material Components, Navigation Component
- Firebase: Authentication, Firestore, Cloud Functions Gen2, Cloud Scheduler
- AI: Gemini API, Python 3.12 Functions runtime

## 프로젝트 구조

```text
.
├── app/                 # Android 앱
│   └── src/main/
│       ├── java/        # Kotlin 소스 코드
│       └── res/         # layout, drawable, navigation 리소스
├── functions/           # Firebase Functions Python 코드
│   ├── main.py
│   ├── reservation_utils.py
│   └── tests/
├── scripts/             # 배포 보조 스크립트
├── firebase.json
├── firestore.rules
└── firestore.indexes.json
```

## 주요 Firestore 컬렉션

- `Reservations`: 강의실 예약 정보
- `ChatHistory`: AI 채팅 기록
- `PendingReservations`: 확정 전 AI 예약 후보
- `rooms`: 강의실 정보
- `User`: 사용자 정보
- `Reviews`: 강의실 리뷰
- `Notices`: 공지사항

## 개발 환경 설정

1. Firebase 프로젝트에서 `google-services.json`을 다운로드합니다.
2. `app/google-services.json` 위치에 파일을 추가합니다.
3. `functions/.env`에 Gemini API 키를 설정합니다.
4. Android Studio에서 Gradle Sync 후 앱을 실행합니다.

```env
GEMINI_API_KEY=your_gemini_api_key
```

## 테스트

```powershell
.\gradlew.bat :app:assembleDebug
.\functions\venv\Scripts\python.exe -m unittest discover -s .\functions\tests -v
```

## Firebase Functions 배포

Firebase CLI 로그인 문제가 있을 경우 서비스 계정 기반 배포 스크립트를 사용할 수 있습니다.

```powershell
.\scripts\deploy-functions-with-service-account.ps1 -CredentialPath .\.secrets\pickdreamtest-service-account.json
```

## 보안 주의사항

- `.secrets/` 디렉토리는 Git에 포함하지 않습니다.
- 서비스 계정 JSON 키는 외부에 공유하지 않습니다.
- `GEMINI_API_KEY` 같은 민감 정보는 코드에 직접 작성하지 않습니다.
