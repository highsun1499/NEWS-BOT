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
        for item in soup.find_all('item')[:20]:
            news_items.append({
                "title": item.title.text,
                "link": item.link.text,
                "pubDate": item.pubDate.text
            })
        return news_items
    except Exception as e:
        print(f"뉴스 수집 에러: {e}")
        return []

# 2. 뉴스 그룹화 (테스트를 위해 1개 이상이면 무조건 그룹화)
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        words = news['title'].split()
        if len(words) > 1:
            group_key = words[0] # 첫 단어로 간단히 그룹핑
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(news)
    # 테스트를 위해 1개 이상이면 모두 반환 (나중에 3으로 바꾸셔도 됩니다)
    return [items for items in groups.values() if len(items) >= 1]

# 3. Gemini API 포스팅 생성
def generate_post(news_group):
    api_key = os.environ.get("GEMINI_API")
    if not api_key: return None

    genai.configure(api_key=api_key)
    # 모델 경로 에러 수정
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    context = "\n".join([f"- 제목: {n['title']} / 링크: {n['link']}" for n in news_group])
    prompt = f"너는 뉴스 큐레이터야. 다음 기사들을 읽고 HTML 형식으로 제목(h2), 3줄 요약(ul/li), 참조링크를 작성해줘. <html>태그는 쓰지마:\n{context}"
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"AI 에러: {e}")
        return None

# 4. index.html 업데이트
def update_index_html():
    post_files = sorted(glob.glob("post_*.html"), reverse=True)
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

        start_tag = ''
        end_tag = ''
        
        if start_tag in content and end_tag in content:
            # 주석 사이의 내용 교체 로직
            before = content.split(start_tag)[0]
            after = content.split(end_tag)[1]
            new_content = before + start_tag + links_html + end_tag + after
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(new_content)
            print("index.html 업데이트 완료")

if __name__ == "__main__":
    print("작업 시작...")
    all_news = get_breaking_news()
    groups = group_similar_news(all_news)
    
    if groups:
        for group in groups[:5]: # 너무 많으면 API 할당량이 부족하므로 5개만
            post = generate_post(group)
            if post:
                filename = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{groups.index(group)}.html"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"<html><head><meta charset='utf-8'><script src='https://cdn.tailwindcss.com'></script></head><body class='p-10 lg:px-60'>{post}<br><a href='index.html'>← 목록으로</a></body></html>")
        
        update_index_html()
