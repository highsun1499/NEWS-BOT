import os
import requests
import glob
from bs4 import BeautifulSoup
from google import genai
from datetime import datetime
import time

# 1. 뉴스 수집 함수
def get_breaking_news():
    url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        breaking_news = []
        for item in items[:100]:
            title = item.title.text
            link = item.link.text
            if "속보" in title:
                breaking_news.append({"title": title, "link": link})
        return breaking_news
    except Exception as e:
        print(f"수집 에러: {e}")
        return []

# 2. 뉴스 그룹화 (최소 3개 이상 필터링)
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        clean_title = news['title'].replace("[속보]", "").replace("속보", "").strip()
        words = clean_title.split()
        if len(words) > 0:
            group_key = " ".join(words[:2]) 
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(news)
    
    filtered_groups = [g for g in groups.values() if len(g) >= 3]
    return sorted(filtered_groups, key=len, reverse=True)

# 3. Gemini API 포스팅 생성
def generate_post(news_group):
    api_key = os.environ.get("GEMINI_API")
    if not api_key: return None
    try:
        client = genai.Client(api_key=api_key)
        context = "\n".join([f"{i+1}. 제목: {n['title']} / 링크: {n['link']}" for i, n in enumerate(news_group)])
        today = datetime.now().strftime('%Y년 %m월 %d일')
        
        prompt = (
            f"너는 뉴스 큐레이터야. 다음 기사들을 읽고 아래 [형식]을 엄격히 지켜서 한국어로 요약해.\n\n"
            f"[형식]:\n"
            f"<h2>핵심 제목</h2>\n<br>\n"
            f"요약 문단 (문장 끝마다 <br> 필수)\n<br>\n"
            f"<strong>링크 :</strong><br>\n"
            f"1번 <a href='URL' target='_blank'>기사 제목</a><br>\n"
            f"2번 <a href='URL' target='_blank'>기사 제목</a><br>\n"
            f"3번 <a href='URL' target='_blank'>기사 제목</a><br>\n\n"
            f"마크다운(```) 쓰지 말고 순수 HTML만 출력해.\n\n"
            f"데이터:\n{context}"
        )
        response = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        print(f"AI 에러: {e}"); return None

# 4. index.html 업데이트 (번역 기능 포함된 index용)
def update_index_html():
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    if not post_files: 
        print("표시할 뉴스 파일이 없습니다.")
        return

    links_html = ""
    for file in post_files[:20]:
        filename_only = os.path.basename(file)
        raw_name = filename_only.replace("post_", "").replace(".html", "")
        try:
            display_time = datetime.strptime(raw_name.split('_')[0] + raw_name.split('_')[1], "%Y%m%d%H%M%S").strftime("%m/%d %H:%M")
        except:
            display_time = "최근 속보"

        links_html += f"""
        <div class="p-4 border-b hover:bg-blue-50 cursor-pointer transition group" onclick="loadNews('./news/{filename_only}')">
            <span class="text-blue-500 text-[10px] font-bold uppercase">Breaking</span>
            <h2 class="text-sm font-bold mt-1 line-clamp-2 group-hover:text-blue-700">{display_time} - AI 요약 속보</h2>
            <p class="text-[11px] text-gray-400 mt-1">클릭하여 읽기 &rarr;</p>
        </div>
        """

    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()

        soup = BeautifulSoup(content, 'html.parser')
        
        # ID가 'news-list'인 태그를 찾아서 내용을 갈아끼웁니다.
        news_section = soup.find(id='news-list')
        
        if news_section:
            news_section.clear()
            new_content = BeautifulSoup(links_html, 'html.parser')
            news_section.append(new_content)
            
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(soup.prettify(formatter="html"))
            print("index.html 업데이트 완료!")
        else:
            print("에러: index.html에서 id='news-list'를 찾을 수 없습니다.")

if __name__ == "__main__":
    if not os.path.exists("news"): os.makedirs("news")
    all_news = get_breaking_news()
    groups = group_similar_news(all_news)
    
    if groups:
        for group in groups[:2]: 
            post = generate_post(group)
            if post:
                now = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_path = f"news/post_{now}_{groups.index(group)}.html"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"<html><body style='line-height:2; font-family:sans-serif; padding:20px;'>{post}</body></html>")
                time.sleep(1)
        update_index_html()
    else:
        print("조건에 맞는 뉴스가 없어 목록 업데이트만 시도합니다.")
        update_index_html() # 새 기사가 없어도 기존 목록이라도 띄우기 위해 호출
