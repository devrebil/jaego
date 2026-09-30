# 📦 재고 관리 Pro

매입·매출·재고를 관리하는 사내용 웹앱입니다. 도메인별로 SQLite DB 파일을 분리해
**위급 시 특정 DB만 따로 백업/복원**할 수 있고, **모든 쓰기 액션이 감사 로그(히스토리)** 로 남습니다.

## 설치형(트레이 상주형) 배포판 — PRO_Ins

이 폴더는 콘솔창·배치파일 대신 **Setup.exe 클릭 설치 + 시스템 트레이 아이콘**으로
서버를 관리하는 방식입니다. FREE/PRO의 `ONE_CLICK_START.bat` 방식과는 별개의
배포판이며, 서버로 쓸 PC에서 아래 순서로 사용합니다.

1. `Output/PRO재고관리_Setup.exe`를 실행합니다. 관리자 권한이 필요 없는 사용자 폴더
   (`%LOCALAPPDATA%\PRO재고관리`)에 설치되며, 원하면 "Windows 시작 시 자동으로 서버
   실행" 옵션을 체크할 수 있습니다.
2. 설치가 끝나면 자동으로 실행되고, 시스템 트레이(작업 표시줄 오른쪽 아이콘 모음)에
   파란 아이콘이 나타납니다.
3. 트레이 아이콘을 우클릭하면:
   - **웹 화면 열기** — 브라우저로 접속 (더블클릭해도 동일)
   - **Windows 시작 시 자동 실행** — 체크박스, 언제든 켜고 끌 수 있음 (관리자 권한 불필요)
   - **서버 종료** — 서버를 완전히 끕니다 (종료 전 전체 DB 자동 백업)
4. 포트는 5000(HTTP)·5443(모바일 카메라용 HTTPS)로 고정되어 있어 재부팅해도 항상
   같은 주소로 접속할 수 있습니다.
5. 접속: `http://localhost:5000` (같은 네트워크의 다른 PC/휴대폰은
   `http://<이 PC의 IP>:5000` 또는 설정의 QR코드).
6. 최초 로그인 계정은 **admin / admin**이며, 첫 로그인 직후 반드시 비밀번호를 변경하세요.
7. 제거하려면 Windows 설정의 "앱" 목록(또는 시작 메뉴의 제거 아이콘)에서 삭제합니다.
   **업무 데이터(db 폴더)는 제거 후에도 남아있어** 재설치하면 그대로 이어집니다.
   완전히 지우려면 설치 폴더를 직접 삭제하세요.

### 이 배포판을 다시 빌드하는 방법 (개발자용)

```bash
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt pyinstaller
./.venv/Scripts/pyinstaller --noconfirm --name "PRO재고관리" --onedir --windowed \
  --icon app_icon.ico --add-data "templates;templates" --add-data "static;static" \
  --collect-data holidays tray_app.py
"경로\Inno Setup 6\ISCC.exe" installer.iss
```
결과물은 `Output/PRO재고관리_Setup.exe`에 생성됩니다.

## 주요 기능
- **로그인 / 회원가입** : 이름·비밀번호·생일·부서로 가입
- **홈 대시보드** : 달력+오늘일정 / 공지(권한자만 작성)+매입매출현황(일·주·월) / 프로젝트·메모
- **캘린더(월간)** : 네모박스 달력, 날짜 아래에 일정 표시, 날짜 드래그로 여러 날 일정 추가, 진행중/완료 탭, 관리자 출퇴근 표시 토글
- **프로젝트** : 히스토리 카드 누적 + Slack식 댓글/대댓글, 시작/완료가 달력에 표시
- **메모** : 개인 메모, 태그+Enter 작성, 드래그 정렬, 완료목록 검색·날짜필터
- **관리**
  - 거래처 등록(사진·사업자등록증 첨부)
  - 품목 등록(엑셀/CSV 일괄 업로드: SKU|품목명|규격|단위|매입가|판매가, 컬럼 ON/OFF)
  - 매입·매출 등록(구분 추가 가능, 컬럼 ON/OFF)
  - 재고 현황 / 월간·년간 입출 현황(표 + 그래프)
- **입출고 관리** : 매입=입고·매출=출고로 재고 반영
- **설정** : 회사명·권한 관리, DB 백업/복원, 전체 히스토리 조회

## DB 구조 (도메인별 파일 분리)
`db/` 폴더 안에 도메인마다 별도 `.db` 파일:
`users / contacts / items / transactions / inventory / calendar / projects / memo / attendance / notice / audit`

- 백업: 설정 화면에서 DB별 [받기] → `.db` 파일 다운로드
- 복원: DB별 [복원] → 해당 파일만 교체 (기존 파일은 `.bak`로 보관)

## 폴더 구조
```
app.py              # Flask 라우팅 / API
db.py               # 도메인별 DB 연결 + 감사로그
templates/index.html# 단일 페이지 프론트엔드
db/                 # SQLite 파일들 (최초 실행 시 생성)
uploads/            # 첨부파일 (사진/사업자등록증)
```
