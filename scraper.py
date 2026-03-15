import os
import requests
import glob
from bs4 import BeautifulSoup
from google import genai
from datetime import datetime
import time

# 1. 뉴스 수집 (국가별)
def get_global_news():
    # 현재 '시(Hour)'를 가져옵니다. (0~23)
    current_hour = datetime.now().hour
    
    # 시간에 따른 사이클 설정 (시간 % 3)
    # 0, 3, 6, 9...시 : 한국
    # 1, 4, 7, 10...시 : 미국
    # 2, 5, 8, 11...시 : 중국
    cycle = current_hour % 3
    
    if cycle == 0:
        url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
        country = "KOREA"
    elif cycle == 1:
        url = "https://news.google.com/rss/search?q=Breaking&hl=en-US&gl=US&ceid=US:en"
        country = "USA"
    else:
        url = "https://news.google.com/rss/search?q=突发新闻&hl=zh-CN&gl=CN&ceid=CN:zh-hans"
        country = "CHINA"

    print(f"[{current_hour}시 정기 업데이트] {country} 뉴스 수집 시작...")
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        news_data = [{"title": item.title.text, "link": item.link.text} for item in items[:100]]
        return news_data, country
    except Exception as e:
        print(f"수집 에러: {e}")
        return [], "ERROR"

# 2. 그룹화 로직
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        words = news['title'].split()
        if len(words) > 1:
            group_key = " ".join(words[:2])
            if group_key not in groups: groups[group_key] = []
            groups[group_key].append(news)
    return sorted([g for g in groups.values() if len(g) >= 3], key=len, reverse=True)

# 3. Gemini 포스팅 생성 (모델명 수정: gemini-2.0-flash)
def generate_post(news_group, country):
    api_key = os.environ.get("GEMINI_API")
    if not api_key: return None
    try:
        client = genai.Client(api_key=api_key)
        context = "\n".join([f"{i+1}. {n['title']} ({n['link']})" for i, n in enumerate(news_group)])
        
        prompt = (
            f"너는 글로벌 뉴스 큐레이터야. 현재 분석 중인 국가는 {country}이야.\n"
            f"제공된 기사들을 한국어로 요약해. 형식은 반드시 순수 HTML로만 출력해.\n"
            f"<h2>[{country} 속보] 핵심 제목</h2><br>\n"
            f"요약 문단 (문장 끝마다 <br> 필수)<br>\n"
            f"<strong>링크 :</strong><br>\n"
            f"1번 <a href='URL' target='_blank'>기사 제목</a><br>\n"
        )
        # 안정적인 모델명으로 변경
        response = client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents=prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        print(f"AI 에러: {e}"); return None

# 4. index.html 업데이트 (에러 방지 로직 강화)
def update_index_html():
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    links_html = ""
    for file in post_files[:25]:
        filename = os.path.basename(file)
        parts = filename.replace(".html", "").split('_')
        
        # 기본값 설정
        country_label = "NEWS"
        time_label = "최신"

        try:
            # 파일명 형식: post_시간_국가_번호.html (예: post_154439_CHINA_0.html)
            if len(parts) >= 3:
                time_label = f"{parts[1][:2]}:{parts[1][2:4]}" # '154439' -> '15:44'
                country_label = parts[2]
        except:
            pass

        links_html += f"""
        <div class="p-4 border-b hover:bg-blue-50 cursor-pointer transition group" onclick="loadNews('./news/{filename}')">
            <span class="text-blue-500 text-[10px] font-bold uppercase">{country_label}</span>
            <h2 class="text-sm font-bold mt-1 line-clamp-2 group-hover:text-blue-700">{time_label} - 속보 요약</h2>
        </div>
        """
    
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        section = soup.find(id='news-list')
        if section:
            section.clear()
            section.append(BeautifulSoup(links_html, 'html.parser'))
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(soup.prettify(formatter="html"))

if __name__ == "__main__":
    if not os.path.exists("news"): os.makedirs("news")
    news_list, country_code = get_global_news()
    groups = group_similar_news(news_list)
    
    if groups:
        for i, group in enumerate(groups[:2]):
            post_content = generate_post(group, country_code)
            if post_content:
                now_time = datetime.now().strftime('%H%M%S')
                file_path = f"news/post_{now_time}_{country_code}_{i}.html"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"<html><body style='line-height:2; padding:20px;'>{post_content}</body></html>")
                time.sleep(1)
    
    # 기사가 새로 생성되지 않더라도 목록은 항상 갱신
    update_index_html()
