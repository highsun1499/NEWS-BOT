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
        for item in items[:100]: # 더 많은 기사를 훑어서 3개 이상 묶음을 찾을 확률을 높임
            title = item.title.text
            link = item.link.text
            if "속보" in title:
                breaking_news.append({"title": title, "link": link})
        return breaking_news
    except Exception as e:
        print(f"수집 에러: {e}")
        return []

# 2. 뉴스 그룹화 (최소 3개 이상인 그룹만 필터링)
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        clean_title = news['title'].replace("[속보]", "").replace("속보", "").strip()
        words = clean_title.split()
        if len(words) > 0:
            # 첫 세 단어로 좀 더 범용적으로 그룹화 (3개 이상 모이게 하기 위함)
            group_key = " ".join(words[:3]) 
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(news)
            
    # 기사가 3개 이상인 그룹만 남기고 정렬
    filtered_groups = [g for g in groups.values() if len(g) >= 3]
    sorted_groups = sorted(filtered_groups, key=len, reverse=True)
    return sorted_groups

# 3. Gemini API 포스팅 생성 (강제 줄바꿈 반영)
def generate_post(news_group):
    api_key = os.environ.get("GEMINI_API")
    if not api_key: return None
    try:
        client = genai.Client(api_key=api_key)
        # 링크 정보를 번호를 매겨 정리
        context = "\n".join([f"{i+1}. 제목: {n['title']} / 링크: {n['link']}" for i, n in enumerate(news_group)])
        today = datetime.now().strftime('%Y년 %m월 %d일')
        
        prompt = (
            f"너는 뉴스 큐레이터야. 다음 기사들을 읽고 아래 [형식]을 엄격히 지켜서 한국어로 요약해.\n\n"
            f"[형식]:\n"
            f"<h2>핵심 제목</h2>\n"
            f"<br>\n"
            f"전체 내용을 통합한 핵심 요약 문단 (문장 끝마다 <br>를 넣어 줄바꿈해)\n"
            f"<br>\n"
            f"<strong>링크 :</strong><br>\n"
            f"1번 <a href='URL' target='_blank'>기사 제목 그대로</a><br>\n"
            f"2번 <a href='URL' target='_blank'>기사 제목 그대로</a><br>\n"
            f"3번 <a href='URL' target='_blank'>기사 제목 그대로</a><br>\n\n"
            f"작성 규칙:\n"
            f"1. 모든 링크는 반드시 한 줄에 하나씩 <br> 태그를 붙여서 작성해.\n"
            f"2. 제공된 모든 기사 링크(최소 3개)를 리스트에 포함시켜.\n"
            f"3. 절대 마크다운(```)을 쓰지 말고 순수 HTML 태그만 출력해.\n\n"
            f"기사 데이터:\n{context}"
        )
        
        response = client.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
        return response.text.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        print(f"AI 에러: {e}"); return None

# 4. index.html 업데이트
def update_index_html():
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    if not post_files: return

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
        news_section = soup.find(id='news-list')
        if news_section:
            news_section.clear()
            new_content = BeautifulSoup(links_html, 'html.parser')
            news_section.append(new_content)
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(soup.prettify(formatter="html"))
            print("index.html 업데이트 완료")

if __name__ == "__main__":
    if not os.path.exists("news"): os.makedirs("news")
    
    print("뉴스 수집 및 필터링 시작...")
    all_news = get_breaking_news()
    # 3개 이상 기사가 모인 그룹만 추출
    groups = group_similar_news(all_news)
    
    if groups:
        # 상위 3개 뉴스 그룹에 대해서만 포스팅 생성
        for group in groups[:3]: 
            post = generate_post(group)
            if post:
                now = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_path = f"news/post_{now}_{groups.index(group)}.html"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"<html><body style='line-height:2; font-family:sans-serif; padding:20px;'>{post}</body></html>")
                print(f"저장 완료: {file_path} (기사 {len(group)}개 포함)")
                time.sleep(1)
        update_index_html()
    else:
        print("조건(기사 3개 이상 묶음)을 만족하는 뉴스가 없습니다.")
