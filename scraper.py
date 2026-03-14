import os
import requests
import glob
from bs4 import BeautifulSoup
from google import genai
from datetime import datetime
import time

# 1. 뉴스 수집 함수: 구글 뉴스 RSS에서 '속보' 키워드 필터링
def get_breaking_news():
    # 최신 속보를 가져오기 위한 구글 뉴스 RSS URL
    url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        
        breaking_news = []
        for item in items[:100]: # 최신 100개를 훑어서 필터링
            title = item.title.text
            link = item.link.text
            
            # 제목에 '속보'가 명시적으로 들어간 기사만 선택
            if "속보" in title:
                breaking_news.append({"title": title, "link": link})
        
        return breaking_news
    except Exception as e:
        print(f"수집 에러: {e}")
        return []

# 2. 뉴스 그룹화: 비슷한 뉴스끼리 묶기
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        # '속보' 단어를 제거한 실제 제목 키워드로 그룹핑
        clean_title = news['title'].replace("[속보]", "").replace("속보", "").strip()
        words = clean_title.split()
        
        if len(words) > 0:
            # 첫 세 단어를 조합해서 좀 더 정확하게 그룹화
            group_key = " ".join(words[:3]) 
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(news)
            
    # 관련 기사가 많은 그룹 순서대로 정렬
    sorted_groups = sorted(groups.values(), key=len, reverse=True)
    return sorted_groups

# 3. Gemini API 포스팅 생성 (줄바꿈 스타일 반영)
def generate_post(news_group):
    api_key = os.environ.get("GEMINI_API")
    if not api_key: 
        print("API 키가 설정되지 않았습니다.")
        return None

    try:
        client = genai.Client(api_key=api_key)
        context = "\n".join([f"- 제목: {n['title']} / 링크: {n['link']}" for n in news_group])
        
        today = datetime.now().strftime('%Y년 %m월 %d일')
        prompt = (
            f"너는 뉴스 큐레이터야. 오늘은 {today}이야. 다음 기사들을 읽고 한국어로 요약해줘.\n"
            f"형식: 각 뉴스마다 <h2>제목</h2>, <ul>내용 3줄 요약</ul>, 참조링크 순서로 작성해.\n"
            f"중요: 각 뉴스 아이템 사이에는 반드시 <br><br>를 넣어 간격을 넓혀줘.\n"
            f"<ul> 태그 안의 <li> 문장들 사이에도 줄간격이 느껴지도록 작성해.\n"
            f"<html>이나 ```html 같은 마크다운 태그는 절대 쓰지 말고 순수 HTML 내용만 출력해:\n{context}"
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

# 4. index.html 업데이트 (news 폴더 경로 반영)
def update_index_html():
    # news/ 폴더 안의 파일들을 읽어옵니다.
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    
    if not post_files:
        print("업데이트할 뉴스 파일이 없습니다.")
        return

    links_html = ""
    for file in post_files[:15]: # 최근 15개까지만 노출
        # 파일명에서 시간만 추출 (가독성용)
        raw_name = os.path.basename(file).replace("post_", "").replace(".html", "")
        try:
            # 파일명 형식(20260314_130000)을 시:분으로 변환
            display_time = datetime.strptime(raw_name.split('_')[0] + raw_name.split('_')[1], "%Y%m%d%H%M%S").strftime("%m/%d %H:%M")
        except:
            display_time = raw_name

        links_html += f"""
        <div class="bg-white p-6 rounded-lg shadow-md hover:shadow-xl transition">
            <span class="text-blue-500 text-xs font-bold uppercase">Breaking News</span>
            <h2 class="text-xl font-bold mt-2 mb-3">AI 속보 요약 ({display_time})</h2>
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
            new_content = BeautifulSoup(links_html, 'html.parser')
            news_section.append(new_content)
            
            with open("index.html", "w", encoding="utf-8") as f:
                f.write(soup.prettify(formatter="html"))
            print("index.html 업데이트 완료")
        else:
            print("에러: index.html에서 id='news-list'를 찾을 수 없습니다.")

# 메인 실행부
if __name__ == "__main__":
    print("작업 시작...")
    
    # news 폴더 생성
    folder_name = "news"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    all_news = get_breaking_news()
    groups = group_similar_news(all_news)
    
    if groups:
        # API 할당량 보호를 위해 상위 3개 그룹만 생성
        for group in groups[:3]: 
            post = generate_post(group)
            if post:
                now = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"post_{now}_{groups.index(group)}.html"
                file_path = os.path.join(folder_name, filename)
                
                with open(file_path, "w", encoding="utf-8") as f:
                    # 상세 페이지에서도 '목록으로' 갈 수 있게 경로를 ../index.html로 설정
                    f.write(f"<html><head><meta charset='utf-8'><script src='[https://cdn.tailwindcss.com](https://cdn.tailwindcss.com)'></script></head><body class='p-10 lg:px-60'>{post}<br><br><hr><br><a href='../index.html' class='text-blue-600 font-bold'>← 목록으로 돌아가기</a></body></html>")
                print(f"포스팅 저장 완료: {file_path}")
                
                # API 연속 호출 시 에러 방지를 위해 1초 대기
                time.sleep(1)
        
        # 목록 페이지 업데이트
        update_index_html()
    else:
        print("수집된 뉴스가 없습니다.")
