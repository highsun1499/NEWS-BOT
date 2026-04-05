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

# 왼쪽 사이드바 목록 생성
def update_news_list():
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    links_html = ""
    
    for file in post_files[:100]:
        filename = os.path.basename(file)
        parts = filename.replace(".html", "").split('_')
        
        date_label = ""
        time_label = "시간미상"
        country_label = "NEWS"

        try:
            if len(parts) >= 5:
                date_val = parts[1]    
                time_val = parts[2]    
                country_label = parts[3] 
                
                date_label = f"{date_val[4:6]}/{date_val[6:8]}" 
                time_label = f"{time_val[:2]}:{time_val[2:4]}"
            elif len(parts) == 3:
                time_val = parts[1]
                country_label = parts[2]
                time_label = f"{time_val[:2]}:{time_val[2:4]}"
                
            if not time_label.replace(":", "").isdigit():
                time_label = "확인중"

        except Exception as e:
            pass

        links_html += f"""
        <div class="p-4 border-b hover:bg-blue-50 cursor-pointer transition group" onclick="loadNews('./news/{filename}')">
            <div class="flex justify-between items-start">
                <span class="text-blue-500 text-[10px] font-bold uppercase">{country_label}</span>
                <span class="text-gray-400 text-[10px]">{date_label}</span>
            </div>
            <h2 class="text-sm font-bold mt-1 line-clamp-2 group-hover:text-blue-700">
                {time_label} - AI 요약 속보
            </h2>
        </div>
        """
    
    list_path = os.path.join("news", "news_list.html")
    with open(list_path, "w", encoding="utf-8") as f:
        f.write(links_html)
    print("목록 파일(news_list.html) 갱신 완료!")

# 용량 관리
def cleanup_old_news(max_files=200):
    all_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    
    files_to_delete = all_files[max_files:]
    for file_path in files_to_delete:
        try:
            os.remove(file_path)
            print(f"🗑️ 자동 삭제 완료: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"파일 삭제 에러 ({file_path}): {e}")

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
