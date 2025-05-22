from flask import Flask, render_template, request, redirect, url_for, make_response, jsonify
import json
import os
import re
import requests
import markdown
from openai import OpenAI
from dotenv import load_dotenv
from weasyprint import HTML
from datetime import datetime, timedelta
from naver_blog import search_naver_blog
import uuid

# 환경변수(.env)에서 API 키 로드
load_dotenv()
app = Flask(__name__)

# 카카오 길찾기 API 이용(대리요청)
@app.route('/api/directions')
def get_directions():
    origin      = request.args.get('origin')      # "lng,lat"
    destination = request.args.get('destination') # "lng,lat"
    if not origin or not destination:
        return jsonify({'error':'origin, destination 파라미터 필요'}), 400

    kakao_url = 'https://apis-navi.kakaomobility.com/v1/directions'
    params = {'origin': origin, 'destination': destination}
    kakao_key = os.environ.get('KAKAO_REST_API_KEY')
    if not kakao_key:
        return jsonify({'error':'KAKAO_REST_API_KEY 미설정'}), 500

    headers = {'Authorization': f'KakaoAK {kakao_key}'}
    resp = requests.get(kakao_url, params=params, headers=headers, timeout=5)
    return jsonify(resp.json()), resp.status_code

# OpenAI 클라이언트 생성
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
SHARE_FILE = 'share_data.json'    # ✅ 공유된 일정 저장 파일
REVIEW_FILE = 'review_data.json'  # ✅ 리뷰 저장 파일

# ✅ 리뷰 불러오기
def load_reviews():
    if not os.path.exists(REVIEW_FILE):
        return []
    with open(REVIEW_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# ✅ 리뷰 저장
def save_review(new_review):
    reviews = load_reviews()
    reviews.append(new_review)
    with open(REVIEW_FILE, 'w', encoding='utf-8') as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)

# ✅ 공유 일정 저장/불러오기

def save_shared_plan(plan_html):
    share_id = str(uuid.uuid4())[:8]  # 짧은 UUID 생성
    if os.path.exists(SHARE_FILE):
        with open(SHARE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = {}
    data[share_id] = plan_html
    with open(SHARE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return share_id

def load_shared_plan(share_id):
    if not os.path.exists(SHARE_FILE):
        return None
    with open(SHARE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get(share_id)

@app.route("/share/<share_id>")
def shared_plan(share_id):
    html = load_shared_plan(share_id)
    if html is None:
        return "공유된 일정을 찾을 수 없습니다.", 404
    return render_template("shared_plan.html", result=html)

@app.route("/save_share", methods=["POST"])
def save_share():
    html = request.json.get("html", "")
    share_id = save_shared_plan(html)
    return jsonify({"share_id": share_id})

# ✅ 일정 텍스트 생성 (GPT)
def generate_itinerary(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 전문 여행 일정 플래너입니다."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"에러 발생: {e}"

# ✅ 기타 도우미 함수들
# 일정 텍스트에서 "",''로 묶인 장소명 추출
def extract_places(text: str) -> list:
    pattern = r"['‘“\"](.+?)['’”\"]"
    return list(set(re.findall(pattern, text)))

# HTML에서 장소명에 <span> 태그 추가
def linkify_places(html: str, place_names: list) -> str:
    for place in place_names:
        html = html.replace(
            place,
            f'<span class="place-link" data-name="{place}">{place}</span>'
        )
    return html

# 장소명 → 위도/경도 변환
def get_kakao_coords(place_name: str):
    KEY = os.environ["KAKAO_REST_API_KEY"]
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KEY}"}
    params = {"query": place_name}

    res = requests.get(url, headers=headers, params=params).json()
    if res.get('documents'):
        lat = res['documents'][0]['y']
        lng = res['documents'][0]['x']
        return lat, lng
    return None

# GPT 응답 텍스트 → 일정 리스트 추출
def extract_schedule_entries(text: str) -> list:
    pattern = r"(\d+일차)(?:\s*[:\-]?\s*)?(.*?)(?=\n\d+일차|$)"
    entries = re.findall(pattern, text, re.DOTALL)
    schedule = []
    for day, body in entries:
        for line in body.strip().split("\n"):
            time_match = re.match(r"(\d{1,2}:\d{2})", line)
            time = time_match.group(1) if time_match else ""
            place_match = re.search(r'["“‘\'](.+?)["”’\']', line)
            if place_match:
                place = place_match.group(1)
                desc = line.replace(place_match.group(0), "").strip(" :-~")
                schedule.append({
                    "day": day,
                    "time": time,
                    "place": place,
                    "desc": desc
                })
    return schedule

# ✅ 인덱스 페이지: 히어로 섹션만 랜더링
@app.route('/')
def index():
    return render_template('index.html')

# ✅ 리뷰 제출 처리
# @app.route('/submit_review', methods=['POST'])
# def submit_review():
    rating = request.form.get('rating')
    comment = request.form.get('comment')
    result_html = request.form.get('result_html')  # ✅ 숨겨진 값으로 result 받기

    # 추가: 지도 정보와 입력값도 받기
    markers = json.loads(request.form.get('markers', '[]'))
    center_lat = float(request.form.get('center_lat', 36.5))
    center_lng = float(request.form.get('center_lng', 127.5))
    route_data = json.loads(request.form.get('route_data', '{}'))

    # 입력값 유지용
    start_date = request.form.get('start_date', '')
    end_date = request.form.get('end_date', '')
    companions = request.form.get('companions', '')
    people_count = request.form.get('people_count', '')
    user_prompt = request.form.get('user_prompt', '')
    location = request.form.get('location', '')
    transport_mode = request.form.get('transport_mode', '')
    theme = request.form.getlist('theme')

    if rating and comment:
        save_review({"rating": rating, "comment": comment})

    reviews = load_reviews()
    return render_template("plan.html",
                           result=result_html,
                           kakao_key=os.environ["KAKAO_JAVASCRIPT_KEY"],
                           markers=markers,
                           center_lat=center_lat,
                           center_lng=center_lng,
                           route_data=route_data,
                           start_date=start_date,
                           end_date=end_date,
                           companions=companions,
                           people_count=people_count,
                           theme=theme,
                           user_prompt=user_prompt,
                           location=location,
                           transport_mode=transport_mode,
                           reviews=reviews)


# ✅ PDF 다운로드
@app.route("/download_pdf", methods=["POST"])
def download_pdf():
    result_html = request.form.get("result_html")
    rendered = render_template("pdf_template.html", result=result_html)
    pdf = HTML(string=rendered).write_pdf()
    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=travel_plan.pdf"
    return response

# ✅ 일정 생성 및 지도 + YouTube 정보 + 경로 표시
@app.route("/plan", methods=["GET", "POST"])
def plan():
    result = ""
    markers = []
    route_data = {}
    center_lat, center_lng = 36.5, 127.5

    # 폼 입력값 초기화
    start_date = end_date = companions = people_count = user_prompt = location = transport_mode = ""
    theme = []

    if request.method == "POST":
        # ✅ 리뷰 제출 처리
        if request.form.get("result_html"):
            result = request.form.get("result_html")
            markers = json.loads(request.form.get("markers", '[]'))
            center_lat = float(request.form.get("center_lat", 36.5))
            center_lng = float(request.form.get("center_lng", 127.5))
            route_data = json.loads(request.form.get("route_data", '{}'))

            # 기존 입력값 복원
            start_date     = request.form.get("start_date", '')
            end_date       = request.form.get("end_date", '')
            companions     = request.form.get("companions", '')
            people_count   = request.form.get("people_count", '')
            user_prompt    = request.form.get("user_prompt", '')
            location       = request.form.get("location", '')
            transport_mode = request.form.get("transport_mode", '')
            theme          = request.form.getlist("theme")

            # 리뷰 저장
            rating = request.form.get("rating")
            comment = request.form.get("comment")
            if rating and comment:
                save_review({"rating": rating, "comment": comment})

        else:
            # ✅ 일정 생성 처리
            start_date     = request.form.get("start_date")
            end_date       = request.form.get("end_date")
            companions     = request.form.get("companions")
            people_count   = request.form.get("people_count")
            theme          = request.form.getlist("theme")
            theme_str      = ", ".join(theme)
            user_prompt    = request.form.get("user_prompt")
            location       = request.form.get("location")
            transport_mode = request.form.get("transport_mode")

            coords = get_kakao_coords(location)
            if coords:
                center_lat, center_lng = coords

            # ✅ 장소 정보 + 유튜브 영상
            code_map = {"restaurant": "FD6", "cafe": "CE7", "tourism": "AT4"}
            all_places = []
            for code in code_map.values():
                docs = search_category(code, location, size=20, radius=1000)
                all_places += [d["place_name"] for d in docs]
            unique_places = list(dict.fromkeys(all_places))[:10]

            place_videos = {}
            for place in unique_places:
                vids = search_youtube_videos(f"{place} 여행", max_results=3)
                place_videos[place] = [v["title"] for v in vids]

            yt_info_str = "\n".join(
                f"- {p}: " + (", ".join(ts) if ts else "관련 영상 없음")
                for p, ts in place_videos.items()
            )

            # ✅ GPT 프롬프트
            prompt = f"""
            여행 날짜: {start_date} ~ {end_date}
            동행: {companions}, 총 인원: {people_count}명
            여행지: {location}, 테마: {theme_str}
            교통수단: {transport_mode}
            추가 조건: {user_prompt}

            # 장소별 YouTube 참고 영상 제목:
            {yt_info_str}

            **출력 형식**

            여행날짜 (요일)\n            
            1일차:\n
            1) "장소명"\n
            • 한줄 설명.\n
            • 영업시간 :\n
            • 입장료 or 메뉴추천:\n
            2) "장소명"\n
            • 한줄 설명.\n
            • 영업시간 :\n
            • 입장료 or 메뉴추천:\n
            ...
            ----------------------
            여행날짜 (요일)\n            
            2일차:\n
            ...

            **출력조건**
            - 여행일정 모든 장소명 앞에 반드시 {location} 추가.
            - 위 “유튜브 참고 영상”을 참고하여, 각 장소에 대한 추가 설명(추천 이유, 꿀팁 등)을 일정에 반영해주세요.
            - 각 일정에 따라 정해진 장소들 끼리 거리가 멀지않은곳으로 추천해주세요.
            - 교통수단에 따라 일정을 조율해주세요.
            - 가게(음식점, 카페)나 관광지같은경우 영업시간, 입장료, 메뉴추천 등등 정보를 적어주세요.
            - 시간 앞에 적힌 장소명은 반드시 큰따옴표("")로 묶어주세요.
            """

            raw_result = generate_itinerary(prompt)
            result = markdown.markdown(raw_result)
            place_names = extract_places(raw_result)
            result = linkify_places(result, place_names)

            schedule_data = extract_schedule_entries(raw_result)
            for entry in schedule_data:
                coord = get_kakao_coords(entry["place"])
                if coord:
                    markers.append({
                        "name": entry["place"],
                        "lat": coord[0],
                        "lng": coord[1],
                        "day": entry["day"],
                        "time": entry["time"],
                        "desc": entry["desc"]
                    })

            # ✅ 다중 경유지 경로 데이터
            if len(markers) >= 2:
                origin = markers[0]
                destination = markers[-1]
                waypoints = markers[1:-1]
                payload = {
                    "origin":      {"x": origin["lng"],      "y": origin["lat"]},
                    "destination": {"x": destination["lng"], "y": destination["lat"]},
                    "waypoints":   [{"x": m["lng"], "y": m["lat"]} for m in waypoints],
                    "priority":    "RECOMMEND"
                }
                headers = {
                    "Authorization": f"KakaoAK {os.environ['KAKAO_REST_API_KEY']}",
                    "Content-Type":  "application/json"
                }
                resp = requests.post(
                    "https://apis-navi.kakaomobility.com/v1/waypoints/directions",
                    headers=headers,
                    json=payload
                )
                if resp.ok:
                    route_data = resp.json()

    reviews = load_reviews()
    return render_template("plan.html",
                           result=result,
                           kakao_key=os.environ["KAKAO_JAVASCRIPT_KEY"],
                           markers=markers,
                           center_lat=center_lat,
                           center_lng=center_lng,
                           route_data=route_data,
                           start_date=start_date,
                           end_date=end_date,
                           companions=companions,
                           people_count=people_count,
                           theme=theme,
                           user_prompt=user_prompt,
                           location=location,
                           transport_mode=transport_mode,
                           reviews=reviews)


# ✅ 카테고리 검색 (음식점, 카페, 관광지 등)
@app.route("/search/<category>")
def search(category):
    code_map = {"cafe":"CE7", "restaurant":"FD6", "tourism":"AT4"}
    code = code_map.get(category)
    if not code:
        return redirect(url_for("index"))
    
    region = request.args.get("region", "")
    places = search_category(code, region)

    return render_template("search.html", category=category, region=region, places=places)


def search_category(category_code: str, region: str, size=15, radius=1000, use_coords=True) -> list:
    """
    Kakao Local API 카테고리 검색 - 좌표 기반 또는 쿼리 기반 모두 지원

    :param category_code: 카카오 카테고리 코드 (e.g. "FD6", "CE7", "AT4")
    :param region: 검색할 지역명 또는 키워드
    :param size: 최대 결과 수
    :param radius: 반경 (m, use_coords=True일 때만 적용됨)
    :param use_coords: True면 좌표 기반, False면 키워드 기반
    :return: 장소 리스트
    """
    REST_KEY = os.environ["KAKAO_REST_API_KEY"]
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {"Authorization": f"KakaoAK {REST_KEY}"}
    
    if use_coords:
        coords = get_kakao_coords(region)
        if not coords:
            return []
        lat, lng = coords
        params = {
            "category_group_code": category_code,
            "x": lng,
            "y": lat,
            "radius": radius,
            "size": size
        }
    else:
        params = {
            "category_group_code": category_code,
            "query": region,
            "size": size
        }

    res = requests.get(url, headers=headers, params=params).json()
    return res.get("documents", [])


def search_youtube_videos(query, max_results=6):
    api_key = os.environ["YOUTUBE_API_KEY"]
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "key": api_key
    }

    res = requests.get(url, params=params)
    videos = []

    if res.status_code == 200:
        data = res.json()
        for item in data["items"]:
            video_id = item["id"]["videoId"]
            title = item["snippet"]["title"]
            thumbnail = item["snippet"]["thumbnails"]["medium"]["url"]
            videos.append({
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": thumbnail
            })
    return videos

#  음식점 페이지
@app.route("/food", methods=["GET", "POST"])
def food():
    places = []
    youtube_videos = []
    blog_posts = []  #  블로그 리스트 초기화!
    center_lat = 37.241086  # 기본 독도 중심
    center_lng = 131.864436
    selected_category = ""
    region = ""

    if request.method == "POST":
        region = request.form.get("region")
        category = request.form.get("category")
        selected_category = category

        search_query = f"{region} {category}".strip() if category else region

        #  1. Kakao API 음식점 검색
        try:
            REST_KEY = os.environ["KAKAO_REST_API_KEY"]
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            headers = {"Authorization": f"KakaoAK {REST_KEY}"}
            params = {"query": f"{search_query} 맛집", "size": 15}

            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()
            data = res.json()

            places = [
                {
                    "name": doc.get("place_name", ""),
                    "address": doc.get("road_address_name", ""),
                    "lat": doc.get("y", ""),
                    "lng": doc.get("x", ""),
                    "category": doc.get("category_name", "정보 없음"),
                    "phone": doc.get("phone", "정보 없음"),
                    "url": doc.get("place_url", "#")
                }
                for doc in data.get("documents", [])
            ]

            if places:
                center_lat = float(places[0]["lat"])
                center_lng = float(places[0]["lng"])

                #  여기에서 블로그 검색!
                from naver_blog import search_naver_blog  # 상단에 임포트 되어 있어야 함
                blog_query = f"{region} {places[0]['name']}"  # 예: 서울 을지로 한식 우래옥
                blog_posts = search_naver_blog(blog_query)

        except Exception as e:
            places = [{"name": f"에러 발생: {e}", "address": ""}]
            blog_posts = []  # 에러 시 안전하게 초기화

        #  2. 유튜브 검색
        youtube_videos = search_youtube_videos(f"{search_query} 맛집 추천")

    return render_template("food.html",
                           places=places,
                           youtube_videos=youtube_videos,
                           blog_posts=blog_posts,  #  블로그 데이터 넘기기
                           kakao_key=os.environ["KAKAO_JAVASCRIPT_KEY"],
                           center_lat=center_lat,
                           center_lng=center_lng,
                           selected_category=selected_category,
                           region=region)


#  카페 페이지
@app.route("/cafe", methods=["GET", "POST"])
def cafe():
    places = []
    youtube_videos = []
    blog_posts = []  # 블로그 리스트 초기화
    center_lat = 37.241086  # 기본 독도 중심
    center_lng = 131.864436
    selected_category = ""  #  선택된 카테고리 유지용
    region = ""  #  입력값 유지용

    if request.method == "POST":
        region = request.form.get("region")
        category = request.form.get("category")  #  select 박스에서 받아옴
        selected_category = category  #  템플릿에서 선택 유지할 변수로 넘김

        #  검색어 조합 (예: 을지로 디저트카페)
        search_query = f"{region} {category}".strip() if category else region

        #  Kakao API 호출
        try:
            REST_KEY = os.environ["KAKAO_REST_API_KEY"]
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            headers = {"Authorization": f"KakaoAK {REST_KEY}"}
            params = {"query": f"{search_query} 카페", "size": 15}

            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()
            data = res.json()

            places = [
                {
                    "name": doc.get("place_name", ""),
                    "address": doc.get("road_address_name", ""),
                    "lat": doc.get("y", ""),
                    "lng": doc.get("x", ""),
                    "category": doc.get("category_name", "정보 없음"),
                    "phone": doc.get("phone", "정보 없음"),
                    "url": doc.get("place_url", "#")
                }
                for doc in data.get("documents", [])
            ]

            if places:
                center_lat = float(places[0]["lat"])
                center_lng = float(places[0]["lng"])

                from naver_blog import search_naver_blog
                blog_query = f"{region} {places[0]['name']}"
                blog_posts = search_naver_blog(blog_query)

        except Exception as e:
            places = [{"name": f"에러 발생: {e}", "address": ""}]
            blog_posts = [] # 에러 시 안전하게 초기화

        #  YouTube 영상 검색
        youtube_videos = search_youtube_videos(f"{search_query} 카페 추천")

    return render_template("cafe.html",
                           places=places,
                           youtube_videos=youtube_videos,
                           blog_posts=blog_posts,  # 블로그 데이터 넘기기
                           kakao_key=os.environ["KAKAO_JAVASCRIPT_KEY"],
                           center_lat=center_lat,
                           center_lng=center_lng,
                           selected_category=selected_category,  #  템플릿에서 카테고리 유지
                           region=region)  #  템플릿에서 지역 유지


#  숙소 페이지
@app.route("/acc", methods=["GET", "POST"])
def acc():
    places = []
    youtube_videos = []
    blog_posts = []  # 블로그 리스트 초기화
    center_lat = 37.241086  # 기본 독도 중심
    center_lng = 131.864436
    selected_category = ""  # 선택된 숙소 카테고리 유지용
    region = ""  # 지역 입력값 유지용

    if request.method == "POST":
        region = request.form.get("region")
        category = request.form.get("category")
        selected_category = category

        # 검색어 조합 (예: 제주도 리조트)
        search_query = f"{region} {category}".strip() if category else region

        # Kakao API 호출
        try:
            REST_KEY = os.environ["KAKAO_REST_API_KEY"]
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            headers = {"Authorization": f"KakaoAK {REST_KEY}"}
            params = {"query": f"{search_query} 숙소", "size": 15}

            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()
            data = res.json()

            places = [
                {
                    "name": doc.get("place_name", ""),
                    "address": doc.get("road_address_name", ""),
                    "lat": doc.get("y", ""),
                    "lng": doc.get("x", ""),
                    "category": doc.get("category_name", "정보 없음"),
                    "phone": doc.get("phone", "정보 없음"),
                    "url": doc.get("place_url", "#")
                }
                for doc in data.get("documents", [])
            ]

            if places:
                center_lat = float(places[0]["lat"])
                center_lng = float(places[0]["lng"])

                #  네이버 블로그 후기 검색
                from naver_blog import search_naver_blog
                blog_query = f"{region} {places[0]['name']}"
                blog_posts = search_naver_blog(blog_query)

        except Exception as e:
            places = [{"name": f"에러 발생: {e}", "address": ""}]
            blog_posts = []

        # 유튜브 추천 영상
        youtube_videos = search_youtube_videos(f"{search_query} 숙소 추천")

    return render_template("acc.html",
                           places=places,
                           youtube_videos=youtube_videos,
                           blog_posts=blog_posts,  # 블로그 정보 전달
                           kakao_key=os.environ["KAKAO_JAVASCRIPT_KEY"],
                           center_lat=center_lat,
                           center_lng=center_lng,
                           selected_category=selected_category,
                           region=region)

# 네이버 블로그
@app.route("/blog_search", methods=["POST"])
def blog_search():
    try:
        data = request.get_json()
        query = data.get("query", "")

        print("블로그 검색 쿼리:", query)  # 여기에 로깅 추가!

        if not query:
            return jsonify({"error": "검색어 없음"}), 400

        blog_posts = search_naver_blog(query)
        return jsonify(blog_posts)
    except Exception as e:
        print("블로그 검색 오류:", e)  # 에러 로그
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)