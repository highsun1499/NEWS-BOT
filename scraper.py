import os
import requests
import glob
from bs4 import BeautifulSoup
from datetime import datetime
import time

# [새로 추가된 GitHub (Azure) LLM 라이브러리]
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

# 1. 뉴스 수집 (국가별)
def get_global_news():
    current_hour = datetime.now().hour
    cycle = current_hour % 3
    
    if cycle == 0:
        url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
        country = "KOREA"
    elif cycle == 1:
        url = "https://news.google.com/rss/search?q=Breaking&hl=en-US&gl=US&ceid=US:en"
        country = "USA"
    else:
        url = "https://news.google.com/rss/search?q=突发新闻&hl=zh-CN&gl=CN&ceid=CN:zh-hans"
        country = "CHINA"

    print(f"[{current_hour}시 정기 업데이트] {country} 뉴스 수집 시작...")
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        news_data =[{"title": item.title.text, "link": item.link.text} for item in items[:100]]
        return news_data, country
    except Exception as e:
        print(f"수집 에러: {e}")
        return[], "ERROR"

# 2. 그룹화 로직
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        words = news['title'].split()
        if len(words) > 1:
            group_key = " ".join(words[:2])
            if group_key not in groups: groups[group_key] =[]
            groups[group_key].append(news)
    return sorted([g for g in groups.values() if len(g) >= 3], key=len, reverse=True)

# 3. GitHub GPT-5 포스팅 생성 (수정된 핵심 부분)
def generate_post(news_group, country):
    # 환경 변수에서 GITHUB_TOKEN을 가져옵니다.
    token = os.environ.get("TOKEN_GITHUB")
    if not token: 
        print("에러: TOKEN_GITHUB 설정되지 않았습니다.")
        return None
        
    try:
        endpoint = "https://models.github.ai/inference"
        model_name = "openai/gpt-5"  # 요청하신 모델 지정
        
        # 클라이언트 초기화
        client = ChatCompletionsClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(token),
        )
        
        # 기사 목록 문자열 생성
        context = "\n".join([f"{i+1}. {n['title']} ({n['link']})" for i, n in enumerate(news_group)])
        
        # System 역할: AI의 페르소나 및 기본 지시사항
        system_prompt = (
            f"너는 글로벌 뉴스 전문 큐레이터야. 현재 분석 중인 국가는 {country}이야.\n"
            f"다음 기사들이 해당 국가의 언어라면 한국어로 먼저 번역해.\n"
            f"그 후 아래 형식을 엄격히 지켜서 요약해."
        )
        
        # User 역할: 구체적인 데이터 및 출력 형식 요구
        user_prompt = (
            f"========= [분석할 기사 목록] =========\n"
            f"{context}\n"
            f"======================================\n\n"
            f"[출력 형식]\n"
            f"<h2>[{country} 속보] 핵심 제목</h2>\n<br>\n"
            f"요약 문단 (문장 끝마다 <br> 필수)\n<br>\n"
            f"<strong>링크 :</strong><br><br>\n"
            f"1번<br><a href='URL' target='_blank'>기사 제목</a><br><br>\n"
            f"2번<br><a href='URL' target='_blank'>기사 제목</a><br><br>\n"
            f"3번<br><a href='URL' target='_blank'>기사 제목</a><br><br>\n\n"
            f"순수 HTML만 출력해."
        )
        
        # API 통신 (메시지 배열로 구성)
        response = client.complete(
            messages=[
                SystemMessage(content=system_prompt),
                UserMessage(content=user_prompt),
            ],
            model=model_name
        )
        
        # 응답 추출 및 마크다운 정리
        output = response.choices[0].message.content
        return output.replace("```html", "").replace("```", "").strip()
        
    except Exception as e:
        print(f"AI 에러: {e}")
        return None

# ⭐ [디자인 업그레이드] 구글 뉴스 스타일로 사이드바 목록 생성
def update_news_list():
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    links_html = ""
    for file in post_files[:100]:
        filename = os.path.basename(file)
        parts = filename.replace(".html", "").split('_')
        
        formatted_date = "날짜 미상"
        country_label = "글로벌"

        try:
            # 1. 파일명에서 날짜를 파싱해 0을 뺀 깔끔한 "X월 X일" 형태로 가공
            if len(parts) >= 5:
                date_val = parts[1]    
                time_val = parts[2]    
                country_label = parts[3] 
                
                year = date_val[0:4]
                month = str(int(date_val[4:6]))
                day = str(int(date_val[6:8]))
                hour = time_val[0:2]
                minute = time_val[2:4]
                formatted_date = f"{year}년 {month}월 {day}일 {hour}:{minute}"
        except Exception:
            pass
            
        # 2. [특별 기능 추가] 파이썬이 생성된 HTML 파일을 뜯어서 실제 AI가 지은 핵심 제목을 목록에 노출
        actual_title = f"[{country_label}] 분야별 핵심 속보 AI 요약"
        try:
            with open(file, "r", encoding="utf-8") as f_html:
                soup = BeautifulSoup(f_html.read(), "html.parser")
                h2_tag = soup.find("h2")
                if h2_tag:
                    actual_title = h2_tag.text.strip()
        except Exception:
            pass

        # 3. 요청하신 구글 뉴스 양식에 맞춘 HTML HTML 카드 구조
        links_html += f"""
        <div class="px-5 py-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition group" onclick="loadNews('./news/{filename}')">
            <!-- 신문사 영역 -->
            <div class="flex items-center space-x-1.5 mb-2">
                <svg class="w-3.5 h-3.5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9.5L18.5 7H20a2 2 0 012 2v9a2 2 0 01-2 2z"></path></svg>
                <span class="text-[11px] font-bold text-gray-700">{country_label} 속보</span>
            </div>
            
            <!-- 기사 제목 영역 -->
            <h2 class="text-[14px] font-bold text-gray-900 leading-snug line-clamp-2 group-hover:text-blue-600 transition-colors">
                {actual_title}
            </h2>
            
            <!-- 날짜 및 기자 영역 -->
            <div class="mt-2.5 text-[11px] text-gray-500 font-medium">
                {formatted_date} <span class="mx-1">·</span> AI 기자
            </div>
        </div>
        """
    
    list_path = os.path.join("news", "news_list.html")
    with open(list_path, "w", encoding="utf-8") as f:
        f.write(links_html)
    print("목록 디자인(news_list.html) 업그레이드 갱신 완료!")

def cleanup_old_news(max_files=150):
    all_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    files_to_delete = all_files[max_files:]
    for file_path in files_to_delete:
        try:
            os.remove(file_path)
            print(f"🗑️ 자동 삭제 완료: {os.path.basename(file_path)}")
        except Exception as e:
            pass

if __name__ == "__main__":
    if not os.path.exists("news"): os.makedirs("news")
    news_list, country_code = get_global_news()
    groups = group_similar_news(news_list)
    
    if groups:
        now = datetime.now()
        date_str = now.strftime('%Y%m%d')
        time_str = now.strftime('%H%M%S')
        
        for i, group in enumerate(groups[:1]):
            post_content = generate_post(group, country_code)
            if post_content:
                file_path = f"news/post_{date_str}_{time_str}_{country_code}_0.html"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"<html><body style='line-height:2; padding:20px;'>{post_content}</body></html>")
                time.sleep(1)
    
    update_news_list()
    cleanup_old_news(max_files=200)
