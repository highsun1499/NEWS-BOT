import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from datetime import datetime

# 1. 뉴스 수집 함수 (Google News RSS 활용)
def get_breaking_news():
    # '속보' 키워드로 한국 뉴스 RSS 요청
    url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'xml')
    
    news_items = []
    for item in soup.find_all('item')[:100]:  # 최근 100개 분석
        news_items.append({
            "title": item.title.text,
            "link": item.link.text,
            "pubDate": item.pubDate.text
        })
    return news_items

# 2. 제목 유사도 기반 그룹화 로직 (간단한 키워드 매칭)
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        # 제목에서 공백 제거 후 핵심 단어 3개 정도로 그룹 키 생성 (예시 로직)
        # 실제 운영시에는 명사 추출기 등을 쓰면 더 정확합니다.
        words = news['title'].split()
        if len(words) > 3:
            group_key = "".join(words[:3]) # 앞 단어 3개로 그룹핑
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(news)
    
    # 3개 이상 모인 그룹만 반환
    return [items for items in groups.values() if len(items) >= 3]

# 3. Gemini API를 이용한 포스팅 생성
def generate_post(news_group):
    api_key = os.environ.get("GEMINI_API") # GitHub Secrets에서 가져옴
    if not api_key:
        print("API 키가 없습니다.")
        return None

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # AI에게 줄 컨텍스트 작성
    context = "\n".join([f"- 제목: {n['title']} / 링크: {n['link']}" for n in news_group])
    
    prompt = f"""
    너는 전문 뉴스 큐레이터야. 아래의 유사한 속보 기사 3개를 바탕으로 하나의 완벽한 블로그 포스팅을 작성해줘.
    
    [기사 정보]
    {context}
    
    [작성 조건]
    1. 제목: 원문보다 자극적이되 신뢰감 있는 제목으로 재구성할 것.
    2. 요약: 핵심 내용을 3줄의 불렛포인트로 요약할 것.
    3. 링크: 제공된 원문 링크 3개를 '참조 기사' 섹션에 포함할 것.
    4. 어조: 독자에게 유익한 정보를 전달하는 정중한 말투.
    5. 형식: HTML 태그(h2, p, li 등)를 사용해 구성할 것.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"AI 생성 에러: {e}")
        return None

# 4. 메인 실행 로직
def main():
    print(f"--- 뉴스 수집 시작: {datetime.now()} ---")
    all_news = get_breaking_news()
    news_groups = group_similar_news(all_news)
    
    if not news_groups:
        print("조건(3개 이상 중복)에 맞는 기사 그룹이 없습니다.")
        return

    for group in news_groups:
        print(f"그룹 발견! 기사 개수: {len(group)}")
        post_content = generate_post(group)
        
        if post_content:
            # 여기서는 파일로 저장 (GitHub Actions가 이 파일을 Push하도록 설정)
            # 파일명을 날짜_시간으로 해서 포스팅 기록을 남길 수 있습니다.
            filename = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(post_content)
            print(f"포스팅 생성 완료: {filename}")

if __name__ == "__main__":
    main()
