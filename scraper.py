import os
import requests
import glob
from bs4 import BeautifulSoup
from google import genai
from datetime import datetime

# 1. 뉴스 수집 함수
def get_breaking_news():
    url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'xml')
        news_items = []
        for item in soup.find_all('item')[:100]:
            news_items.append({
                "title": item.title.text,
                "link": item.link.text,
                "pubDate": item.pubDate.text
            })
        return news_items
    except Exception as e:
        print(f"뉴스 수집 에러: {e}")
        return []

# 2. 뉴스 그룹화
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        words = news['title'].split()
        if len(words) > 0:
            group_key = words[0]
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(news)
    return [items for items in groups.values() if len(items) >= 1]

# 3. Gemini API 포스팅 생성
def generate_post(news_group):
    api_key = os.environ.get("GEMINI_API")
    if not api_key: 
        print("API 키가 설정되지 않았습니다.")
        return None

    try:
        client = genai.Client(api_key=api_key)
        context = "\n".join([f"- 제목: {n['title']} / 링크: {n['link']}" for n in news_group])
        prompt = f"너는 뉴스 큐레이터야. 다음 기사들을 읽고 HTML 형식으로 제목(h2), 3줄 요약(ul/li), 참조링크를 작성해줘. <html>태그는 쓰지마:\n{context}"
        
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=prompt
        )
        return response.text
    except Exception as e:
        # 할당량 초과(429) 등의 에러가 발생하면 여기서 출력됩니다.
        print(f"AI 에러 발생: {e}")
        return None

# 4. index.html 업데이트 (에러 방지 로직 보강)
def update_index_html():
    post_files = sorted(glob.glob("post_*.html"), reverse=True)
    
    # 1. 만약 생성된 뉴스 파일이 하나도 없다면, 업데이트를 하지 않고 종료합니다.
    if not post_files:
        print("업데이트할 뉴스 파일이 없습니다. (API 제한 등의 사유)")
        return

    links_html = ""
    for file in post_files[:15]:
        display_name = file.replace("post_", "").replace(".html", "")
        links_html += f"""
        <div class="bg-white p-6 rounded-lg shadow-md hover:shadow-xl transition">
            <span class="text-blue-500 text-xs font-bold uppercase">Breaking</span>
            <h2 class="text-xl font-bold mt-2 mb-3">AI 속보 요약 ({display_name})</h2>
            <a href="./{file}" class="text-blue-600 font-semibold hover:underline text-sm">기사 읽기 &rarr;</a>
        </div>
        """

    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()

        soup = BeautifulSoup(content, 'html.parser')
        news_section = soup.find('section', id='news-list')
        
        if news_section:
            news_section.clear()
            # 2. 이번에는 append 대신 직접 HTML을 주입하여 IndexError를 원천 차단합니다.
            new_content = BeautifulSoup(links_html, 'html.parser')
            news_section.append(new_content)
            
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(soup.prettify(formatter="html"))
            print("index.html 업데이트 완료")
        else:
            print("에러: index.html에서 id='news-list'를 찾을 수 없습니다.")
    else:
        print("에러: index.html 파일이 없습니다.")
        
if __name__ == "__main__":
    print("작업 시작...")
    all_news = get_breaking_news()
    groups = group_similar_news(all_news)
    
    if groups:
        # API 할당량 문제(429)를 방지하기 위해 2개로 줄임
        for group in groups[:2]: 
            post = generate_post(group)
            if post:
                filename = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{groups.index(group)}.html"
                with open(filename, "w", encoding="utf-8") as f:
                    # 간단한 디자인을 위한 Tailwind 포함
                    f.write(f"<html><head><meta charset='utf-8'><script src='https://cdn.tailwindcss.com'></script></head><body class='p-10 lg:px-60'>{post}<br><a href='index.html'>← 목록으로</a></body></html>")
            else:
                print("포스팅 생성 실패(API 제한 등)")
        
        # 뉴스 생성 여부와 관계없이 목록 업데이트 시도
        update_index_html()
    else:
        print("수집된 뉴스가 없습니다.")
