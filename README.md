<DZ_MINI_PROJECT_TEAM3>
AI 여행 일정 생성기

AI(Generative AI)를 활용해 여행 일정을 자동으로 생성하고, 다양한 검색 API를 통해 맛집·카페·숙소 추천과 영상 링크를 제공하는 Flask 웹 애플리케이션입니다. Kakao Maps와 연동하여 지도에 마커를 표시하고, 유저 인터랙션을 통해 손쉽게 일정을 관리할 수 있습니다.

주요 기능

• GPT 기반 일정 생성: OpenAI API를 사용해 입력된 여행 정보(일자, 동행, 인원, 장소, 테마 등)에 따른 세부 일정을 생성합니다.

• 지도 표시 & 마커 관리: Kakao JavaScript API로 일정별 마커를 지도에 찍고, 클릭 시 정보창(InfoWindow)을 표시합니다.

• 장소 검색 페이지: /food, /cafe, /acc 경로로 이동 시 각각 맛집, 카페, 숙소를 Kakao Local API로 검색하여 결과를 보여줍니다.

• YouTube 영상 추천: 생성된 일정에 맞춰 관련 유튜브 영상을 YouTube Data API로 조회하여 링크와 썸네일을 제공합니다.

• 다양한 검색 연동 (선택): Naver 블로그, Google Custom Search API, SerpAPI 등을 통해 추가적인 콘텐츠 검색이 가능합니다.

# 구성
```
travelapp/
├── app.py                 # 메인 플라스크 애플리케이션
├── requirements.txt       # 파이썬 패키지 목록
├── .env                   # 환경 변수 파일
├── review_data.json       # 여행지 만족도 리뷰
├── share_data.json        # pdf저장후 공유
│
├── templates/             # Jinja2 템플릿
│   │
│   ├── acc.html           # 숙소 검색 페이지
│   ├── base.html          # 공통 레이아웃
│   ├── cafe.html          # 카페 검색 페이지
│   ├── food.html          # 맛집 검색 페이지
│   ├── index.html         # 홈화면 상단 박스
│   ├── nav.html           # 홈화면 상단 Happy Imagination
│   ├── plan.html          # 일정 생성 & 지도 페이지
│   └── sidebar.html       # 일정 생성 페이지(사이드바)
│
└── static/
│   │
│   ├── acc.css            # 숙소 검색 페이지
│   ├── base.css           # 일정 생성 & 지도 페이지
│   ├── card.css           # 메인 페이지 카드(음식점,카페,숙소소)
│   ├── cafe.css           # 카페 검색 페이지
│   ├── food.css           # 맛집 검색 페이지
│   ├── hero.css           # 홈화면 상단 박스
│   ├── nav.css            # 홈화면 상단 Happy Imagination
│   ├── plan.css           # 일정 생성 & 지도 페이지
│   ├── sidebar.css        # 일정 생성 페이지(사이드바)
│   └── style.css          # 추가 커스터마이징
```

---------------------↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓---------------------
# 배포
```
requirements.txt
L Flask             # 웹 프레임워크
L python-dotenv     # .env 환경변수 로드
L openai            # OpenAI API 클라이언트
L requests          # Kakao REST API 호출용
L markdown          # GPT 응답(마크다운→HTML) 변환
L WeasyPrint        #
```

# 설치
```
MSYS2 설치 : https://www.msys2.org/
- msys2-x86_64-*.exe 다운로드
# 1 패키지 데이터베이스 및 기본 패키지 업데이트
pacman -Syu
# 2 터미널을 닫았다가 다시 열고
pacman -Su

MSYS2에는 mingw64와 mingw32 환경이 있는데, Python 64비트라면 mingw64를 사용하세요.
# mingw64용 GTK3, Pango, Cairo, GDK-Pixbuf 등 설치
pacman -S --needed \
  mingw-w64-x86_64-toolchain \
  mingw-w64-x86_64-gtk3 \
  mingw-w64-x86_64-pango \
  mingw-w64-x86_64-gdk-pixbuf2 \
  mingw-w64-x86_64-cairo
```
