# naver_blog.py
import os
import requests

def search_naver_blog(query, max_results=4):
    client_id = os.environ["NAVER_CLIENT_ID"]
    client_secret = os.environ["NAVER_CLIENT_SECRET"]
    
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    params = {
        "query": query,
        "display": max_results,
        "sort": "sim"  # 최신순
    }

    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        return res.json()["items"]
    except Exception as e:
        print("네이버 블로그 검색 에러:", e)
        return []
