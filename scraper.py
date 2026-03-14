import google.generativeai as genai

# 1. 뉴스 수집 (Scraping)
# BeautifulSoup 등으로 뉴스 제목과 링크를 긁어옵니다.

# 2. 중복 기사 필터링 (Logic)
# 리스트에 담긴 뉴스들 중 제목 키워드가 겹치는 것을 그룹화합니다.
def check_threshold(news_group):
    if len(news_group) >= 3: # 3개 이상 모이면 AI 실행
        return summarize_with_ai(news_group)

# 3. Gemini API를 이용한 요약 (AI)
def summarize_with_ai(news_list):
    genai.configure(api_key="내_API_키")
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"다음 3개 기사를 읽고 새로운 제목 1개, 요약 3줄을 써줘: {news_list}"
    response = model.generate_content(prompt)
    return response.text
