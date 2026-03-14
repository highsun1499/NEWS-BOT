import os
import google.generativeai as genai

# 1. 뉴스 수집 (Scraping) 
# (이 부분은 기존에 사용하시던 크롤링 로직을 그대로 넣으시면 됩니다)
def get_latest_news():
    # 예시 데이터: 실제 크롤링 코드로 대체하세요
    return [
        {"title": "속보 기사 A", "link": "https://news.com/a"},
        {"title": "속보 기사 B", "link": "https://news.com/b"},
        {"title": "속보 기사 C", "link": "https://news.com/c"}
    ]

# 2. 중복 기사 필터링 및 실행 로직
def check_threshold(news_group):
    # 그룹 내 기사가 3개 이상일 때만 요약 진행
    if len(news_group) >= 3:
        summary = summarize_with_ai(news_group)
        return summary
    return None

# 3. Gemini API를 이용한 요약
def summarize_with_ai(news_list):
    # 깃허브 시크릿(GEMINI_API)에서 키를 가져옵니다.
    api_key = os.environ.get("GEMINI_API")
    
    if not api_key:
        print("에러: API 키가 설정되지 않았습니다.")
        return None

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # AI에게 전달할 프롬프트 (뉴스 리스트를 텍스트로 변환)
    news_text = "\n".join([f"- {n['title']} ({n['link']})" for n in news_list])
    
    prompt = f"""
    아래 3개 이상의 뉴스 기사를 읽고 다음 조건에 맞춰 가공해줘:
    1. 클릭을 유도하는 새로운 제목 1개
    2. 핵심 내용을 담은 요약 문장 3줄
    3. 아래에 기사 원문 링크 3개를 포함할 것
    
    기사 목록:
    {news_text}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"AI 요약 중 에러 발생: {e}")
        return None

# 메인 실행부
if __name__ == "__main__":
    news_data = get_latest_news()
    result = check_threshold(news_data)
    if result:
        print("--- 생성된 포스팅 내용 ---")
        print(result)
        # 여기에 index.html 파일을 업데이트하거나 저장하는 코드를 추가하세요.
