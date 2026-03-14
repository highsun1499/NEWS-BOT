import os
import requests
import glob
from bs4 import BeautifulSoup
from google import genai
from datetime import datetime

# 1. 뉴스 수집 함수
def get_breaking_news():
    # 구글 뉴스 '속보' 검색 RSS 피드
    url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
    
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "xml") # RSS는 XML 형식입니다
    items = soup.find_all("item")
    
    breaking_news = []
    for item in items[:100]: # 최신 100개 확인
        title = item.title.text
        link = item.link.text
        
        # 제목에 진짜 '속보'라는 단어가 들어간 것만 필터링
        if "[속보]" in title or "속보" in title:
            breaking_news.append({"title": title, "link": link})
            
    return breaking_news

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
        
        # 프롬프트 수정: 가독성을 위한 스타일 지시 추가
        prompt = (
            f"너는 뉴스 큐레이터야. 다음 기사들을 읽고 한국어로 요약해줘.\n"
            f"형식: 각 뉴스마다 <h2>제목</h2>, <ul>내용 3줄 요약</ul>, 참조링크 순서로 작성해.\n"
            f"중요: 각 뉴스 아이템 사이에는 반드시 <br><br>를 넣어 간격을 넓혀줘.\n"
            f"<ul> 태그 안의 <li> 문장들 사이에도 줄간격이 느껴지도록 작성해.\n"
            f"<html>이나 ```html 같은 마크다운 태그는 절대 쓰지 말고 순수 HTML 내용만 출력해:\n{context}"
        )
        
        response = client.models.generate_content(
            model="gemini-3-flash-preview", 
            contents=prompt
        )
        
        # AI가 간혹 앞뒤에 붙이는 ```html 또는 ``` 문구 제거
        result = response.text.replace("```html", "").replace("```", "").strip()
        return result
        
    except Exception as e:
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
