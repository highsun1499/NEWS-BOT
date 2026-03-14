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

# 2. 뉴스 그룹화
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        clean_title = news['title'].replace("[속보]", "").replace("속보", "").strip()
        words = clean_title.split()
        if len(words) > 0:
            group_key = " ".join(words[:3]) 
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(news)
    sorted_groups = sorted(groups.values(), key=len, reverse=True)
    return sorted_groups

# 3. Gemini API 포스팅 생성 (요청하신 통합 요약 형식)
def generate_post(news_group):
    api_key = os.environ.get("GEMINI_API")
    if not api_key: 
        print("API 키가 설정되지 않았습니다.")
        return None

    try:
        client = genai.Client(api_key=api_key)
        # 기사 정보를 텍스트로 정리
        context = "\n".join([f"- 제목: {n['title']} / 링크: {n['link']}" for n in news_group])
        today = datetime.now().strftime('%Y년 %m월 %d일')
        
        # 출력 형식을 고정하기 위한 매우 구체적인 프롬프트
        prompt = (
            f"너는 뉴스 큐레이터야. 다음 기사들을 읽고 아래의 [출력 형식]과 완전히 똑같이 한국어로 요약해.\n\n"
            f"[출력 형식]:\n"
            f"<h2>핵심 제목</h2>\n\n"
            f"요약 문장들 (전체 내용을 통합하여 하나의 문단으로 작성하되, 문장 사이 적절한 띄어쓰기 유지)\n\n"
            f"링크 :\n"
            f"1번 <a href='URL'>기사 제목 그대로</a>\n"
            f"2번 <a href='URL'>기사 제목 그대로</a>\n"
            f"3번 <a href='URL'>기사 제목 그대로</a>\n\n"
            f"작성 규칙:\n"
            f"1. 반드시 링크는 한 줄에 하나씩 작성해.\n"
            f"2. '1번', '2번' 뒤에는 원본 기사의 제목을 그대로 적고 거기에 링크를 걸어.\n"
            f"3. <html>이나 ```html 같은 마크다운 태그는 절대 쓰지 말고 순수 HTML만 출력해.\n\n"
            f"기사 데이터:\n{context}"
        )
        
        response = client.models.generate_content(
            model="gemini-3-flash-preview", 
            contents=prompt
        )
        
        result = response.text.replace("```html", "").replace("```", "").strip()
        return result
        
    except Exception as e:
        print(f"AI 에러 발생: {e}")
        return None

# 4. index.html 업데이트 (경로 문제 해결 핵심 부분)
def update_index_html():
    # news/ 폴더 내부의 파일 목록을 가져옵니다.
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    
    if not post_files:
        print("업데이트할 뉴스 파일이 없음.")
        return

    links_html = ""
    for file in post_files[:15]:
        # 파일 경로에서 파일명만 추출 (예: post_2026...html)
        filename_only = os.path.basename(file)
        
        # 가독성을 위한 시간 표시 생성
        raw_name = filename_only.replace("post_", "").replace(".html", "")
        try:
            display_time = datetime.strptime(raw_name.split('_')[0] + raw_name.split('_')[1], "%Y%m%d%H%M%S").strftime("%m/%d %H:%M")
        except:
            display_time = raw_name

        # 중요: index.html에서 news 폴더 안의 파일을 가리키도록 경로를 './news/파일명'으로 설정
        links_html += f"""
        <div class="bg-white p-6 rounded-lg shadow-md hover:shadow-xl transition">
            <span class="text-blue-500 text-xs font-bold uppercase">Breaking News</span>
            <h2 class="text-xl font-bold mt-2 mb-3">AI 속보 요약 ({display_time})</h2>
            <a href="./news/{filename_only}" class="text-blue-600 font-semibold hover:underline text-sm">기사 읽기 &rarr;</a>
        </div>
        """

    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            content = f.read()

        soup = BeautifulSoup(content, 'html.parser')
        news_section = soup.find('section', id='news-list')
        
        if news_section:
            news_section.clear()
            # 새로운 링크 구조 주입
            new_content = BeautifulSoup(links_html, 'html.parser')
            news_section.append(new_content)
            
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(soup.prettify(formatter="html"))
            print("index.html 업데이트 완료")

# 메인 실행부
if __name__ == "__main__":
    folder_name = "news"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    all_news = get_breaking_news()
    groups = group_similar_news(all_news)
    
    if groups:
        for group in groups[:2]: 
            post = generate_post(group)
            if post:
                now = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"post_{now}_{groups.index(group)}.html"
                file_path = os.path.join(folder_name, filename)
                
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"""
                    <html>
                    <head>
                        <meta charset='utf-8'>
                        <script src='[https://cdn.tailwindcss.com](https://cdn.tailwindcss.com)'></script>
                        <style>
                            body {{ line-height: 1.8; }}
                            a {{ color: #2563eb; text-decoration: underline; }}
                            h2 {{ font-size: 1.5rem; font-weight: bold; margin-bottom: 1.5rem; }}
                        </style>
                    </head>
                    <body class='p-10 lg:px-60'>
                        <div style='white-space: pre-wrap;'>{post}</div>
                        <br><br><hr><br>
                        <a href='../index.html' style='font-weight: bold; text-decoration: none;'>← 목록으로 돌아가기</a>
                    </body>
                    </html>
                    """)
        
        update_index_html()
    else:
        print("수집된 뉴스가 없습니다.")
