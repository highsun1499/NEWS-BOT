import os
import requests
import glob
from bs4 import BeautifulSoup
import google.generativeai as genai
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
        print(f"뉴스 수집 중 에러: {e}")
        return []

# 2. 제목 유사도 기반 그룹화 (간이 버전)
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        words = news['title'].split()
        if len(words) > 3:
            group_key = "".join(words[:3]) 
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(news)
    return [items for items in groups.values() if len(items) >= 3]

# 3. Gemini API를 이용한 포스팅 생성
def generate_post(news_group):
    api_key = os.environ.get("GEMINI_API")
    if not api_key:
        print("API 키를 찾을 수 없습니다.")
        return None

    genai.configure(api_key=api_key)
    
    # 모델명을 명확히 지정하여 404 에러 방지
    model = genai.GenerativeModel('models/gemini-1.5-flash')
    
    context = "\n".join([f"- 제목: {n['title']} / 링크: {n['link']}" for n in news_group])
    prompt = f"너는 뉴스 큐레이터야. 다음 기사들을 읽고 HTML 형식으로 제목(h2), 3줄 요약(ul/li), 참조링크를 작성해줘. 결과물에 <html>이나 <body> 태그는 포함하지 마:\n{context}"
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"AI 생성 에러: {e}")
        return None

# 4. 메인 페이지(index.html) 자동 업데이트 함수
def update_index_html():
    post_files = sorted(glob.glob("post_*.html"), reverse=True)
    links_html = ""
    
    if not post_files:
        links_html = "<div class='p-6 text-gray-500'>아직 생성된 포스팅이 없습니다.</div>"
    else:
        for file in post_files[:15]:
            display_name = file.replace("post_", "").replace(".html", "").replace("_", " ")
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

        start_tag = ''
        end_tag = ''
        
        if start_tag in content and end_tag in content:
            parts = content.split(start_tag)
            first_half = parts[0]
            second_half = parts[1].split(end_tag)[1]
            
            new_content = first_half + start_tag + links_html + end_tag + second_half
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(new_content)
        else:
            print("index.html에 주석 태그가 없어 업데이트를 건너뜁니다.")
    else:
        print("index.html 파일이 존재하지 않습니다.")

# 메인 실행부
if __name__ == "__main__":
    print("작업 시작...")
    all_news = get_breaking_news()
    groups = group_similar_news(all_news)
    
    if groups:
        print(f"{len(groups)}개의 뉴스 그룹을 찾았습니다.")
        for group in groups:
            post = generate_post(group)
            if post:
                filename = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"<html><head><meta charset='utf-8'><script src='https://cdn.tailwindcss.com'></script></head><body class='p-10 lg:px-60'>{post}<br><br><a href='index.html' class='text-blue-600'>← 목록으로 돌아가기</a></body></html>")
        
        update_index_html()
        print("모든 작업이 성공적으로 완료되었습니다.")
    else:
        print("조건에 맞는 기사 그룹이 없어 새 포스팅을 생성하지 않습니다.")
        # 포스팅은 안 하더라도 기존 목록 업데이트는 시도
        update_index_html()
