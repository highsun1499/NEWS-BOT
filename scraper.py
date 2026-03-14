import os
import requests
import glob
from bs4 import BeautifulSoup
import google.generativeai as genai
from datetime import datetime

# 1. 뉴스 수집 함수
def get_breaking_news():
    url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'xml')
    
    news_items = []
    for item in soup.find_all('item')[:100]:
        news_items.append({
            "title": item.title.text,
            "link": item.link.text,
            "pubDate": item.pubDate.text
        })
    return news_items

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
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    context = "\n".join([f"- 제목: {n['title']} / 링크: {n['link']}" for n in news_group])
    prompt = f"너는 뉴스 큐레이터야. 다음 기사들을 읽고 HTML 형식으로 제목(h2), 3줄 요약(ul/li), 참조링크를 작성해줘:\n{context}"
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"AI 에러: {e}")
        return None

# 4. 메인 페이지(index.html) 자동 업데이트 함수
def update_index_html():
    post_files = sorted(glob.glob("post_*.html"), reverse=True)
    links_html = ""
    
    for file in post_files[:15]: # 최근 15개만 메인에 노출
        display_name = file.replace("post_", "").replace(".html", "")
        links_html += f"""
        <div class="bg-white p-6 rounded-lg shadow-md hover:shadow-xl transition">
            <span class="text-blue-500 text-xs font-bold uppercase">Breaking</span>
            <h2 class="text-xl font-bold mt-2 mb-3">AI 속보 요약 ({display_name})</h2>
            <a href="./{file}" class="text-blue-600 font-semibold hover:underline text-sm">기사 읽기 &rarr;</a>
        </div>
        """

    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()

    start_tag = ''
    end_tag = ''
    
    if start_tag in content and end_tag in content:
        new_content = content.split(start_tag)[0] + start_tag + links_html + end_tag + content.split(end_tag)[1]
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(new_content)

# 메인 실행부
if __name__ == "__main__":
    print("작업 시작...")
    all_news = get_breaking_news()
    groups = group_similar_news(all_news)
    
    if groups:
        for group in groups:
            post = generate_post(group)
            if post:
                filename = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"<html><head><meta charset='utf-8'><script src='https://cdn.tailwindcss.com'></script></head><body class='p-10 lg:px-60'>{post}<br><a href='index.html'>← 돌아가기</a></body></html>")
        
        update_index_html()
        print("모든 작업이 성공적으로 완료되었습니다.")
    else:
        print("조건에 맞는 기사 그룹이 없어 작업을 종료합니다.")
