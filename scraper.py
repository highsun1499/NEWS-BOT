import os
import requests
import glob
from bs4 import BeautifulSoup
from google import genai
from datetime import datetime
import time

# 1. 시간대별 국가 설정 및 뉴스 수집
def get_global_news():
    current_minute = datetime.now().minute
    
    if 0 <= current_minute < 20:
        url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
        country, lang = "KOREA", "ko"
    elif 20 <= current_minute < 40:
        url = "https://news.google.com/rss/search?q=Breaking&hl=en-US&gl=US&ceid=US:en"
        country, lang = "USA", "en"
    else:
        url = "https://news.google.com/rss/search?q=突发新闻&hl=zh-CN&gl=CN&ceid=CN:zh-hans"
        country, lang = "CHINA", "zh-CN"

    print(f"[{datetime.now().strftime('%H:%M')}] {country} 뉴스 수집 중...")
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        news_data = [{"title": item.title.text, "link": item.link.text} for item in items[:100]]
        return news_data, country
    except Exception as e:
        print(f"수집 에러: {e}")
        return [], "ERROR"

# 2. 뉴스 그룹화 (기사 3개 이상)
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        words = news['title'].split()
        if len(words) > 1:
            group_key = " ".join(words[:2])
            if group_key not in groups: groups[group_key] = []
            groups[group_key].append(news)
    return sorted([g for g in groups.values() if len(g) >= 3], key=len, reverse=True)

# 3. Gemini 포스팅 생성 (국가 정보 포함)
def generate_post(news_group, country):
    api_key = os.environ.get("GEMINI_API")
    if not api_key: return None
    try:
        client = genai.Client(api_key=api_key)
        context = "\n".join([f"{i+1}. {n['title']} ({n['link']})" for i, n in enumerate(news_group)])
        
        prompt = (
            f"너는 글로벌 뉴스 전문 큐레이터야. 현재 분석 중인 국가는 {country}이야.\n"
            f"다음 기사들이 해당 국가의 언어라면 한국어로 먼저 번역해.\n"
            f"그 후 아래 형식을 엄격히 지켜서 요약해.\n\n"
            f"<h2>[{country} 속보] 핵심 제목</h2>\n<br>\n"
            f"요약 문단 (문장 끝마다 <br> 필수)\n<br>\n"
            f"<strong>링크 :</strong><br>\n"
            f"1번 <a href='URL' target='_blank'>기사 제목</a><br>\n"
            f"2번 <a href='URL' target='_blank'>기사 제목</a><br>\n"
            f"3번 <a href='URL' target='_blank'>기사 제목</a><br>\n\n"
            f"순수 HTML만 출력해."
        )
        response = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        print(f"AI 에러: {e}"); return None

# 4. index.html 업데이트 (국가 라벨 추가)
def update_index_html():
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    links_html = ""
    for file in post_files[:25]:
        filename = os.path.basename(file)
        # 파일명에서 국가 정보 추출 시도 (예: post_시간_KOREA_0.html)
        parts = filename.split('_')
        country_label = parts[2] if len(parts) > 3 else "News"
        time_label = datetime.strptime(parts[1], "%H%M%S").strftime("%H:%M") if len(parts) > 1 else "속보"

        links_html += f"""
        <div class="p-4 border-b hover:bg-blue-50 cursor-pointer transition group" onclick="loadNews('./news/{filename}')">
            <span class="text-blue-500 text-[10px] font-bold uppercase">{country_label}</span>
            <h2 class="text-sm font-bold mt-1 line-clamp-2 group-hover:text-blue-700">{time_label} - AI 요약 속보</h2>
        </div>
        """
    # (이후 BeautifulSoup 로직은 동일...)
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
                now_date = datetime.now().strftime('%Y%m%d')
                now_time = datetime.now().strftime('%H%M%S')
                # 파일명에 국가 코드 포함
                file_path = f"news/post_{now_time}_{country_code}_{i}.html"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"<html><body style='line-height:2; padding:20px;'>{post_content}</body></html>")
        update_index_html()
