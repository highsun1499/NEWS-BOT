import os
import requests
import glob
from bs4 import BeautifulSoup
from datetime import datetime
import time

# [GitHub (Azure) LLM 라이브러리]
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

# 1. 뉴스 수집
def get_global_news():
    current_hour = datetime.now().hour
    cycle = current_hour % 3
    if cycle == 0: url, country = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko", "KOREA"
    elif cycle == 1: url, country = "https://news.google.com/rss/search?q=Breaking&hl=en-US&gl=US&ceid=US:en", "USA"
    else: url, country = "https://news.google.com/rss/search?q=突发新闻&hl=zh-CN&gl=CN&ceid=CN:zh-hans", "CHINA"

    print(f"[{current_hour}시 정기 업데이트] {country} 뉴스 수집 시작...")
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        return[{"title": item.title.text, "link": item.link.text} for item in items[:100]], country
    except Exception as e:
        print(f"수집 에러: {e}"); return[], "ERROR"

# 2. 그룹화 로직
def group_similar_news(news_list):
    groups = {}
    for news in news_list:
        words = news['title'].split()
        if len(words) > 1:
            group_key = " ".join(words[:2])
            if group_key not in groups: groups[group_key] = []
            groups[group_key].append(news)
    return sorted([g for g in groups.values() if len(g) >= 3], key=len, reverse=True)

# 3. 오직 GPT-5만 사용하는 요약 생성
def generate_post(news_group, country):
    context = "\n".join([f"{i+1}. {n['title']} ({n['link']})" for i, n in enumerate(news_group)])
    
    system_prompt = (
        f"너는 글로벌 뉴스 전문 큐레이터야. 현재 분석 중인 국가는 {country}이야.\n"
        f"다음 기사들이 해당 국가의 언어라면 한국어로 먼저 번역해. 그 후 아래 형식을 엄격히 지켜서 요약해."
    )
    user_prompt = (
        f"=========[분석할 기사 목록] =========\n"
        f"{context}\n"
        f"======================================\n\n"
        f"[출력 형식]\n"
        f"<h2>[{country} 속보] 핵심 내용을 15자 내외로 작성</h2>\n<br>\n"
        f"요약 문단 (문장 끝마다 <br> 필수)\n<br>\n"
        f"<strong>링크 :</strong><br><br>\n"
        f"1번<br><a href='URL' target='_blank'>기사 제목</a><br><br>\n"
        f"2번<br><a href='URL' target='_blank'>기사 제목</a><br><br>\n"
        f"3번<br><a href='URL' target='_blank'>기사 제목</a><br><br>\n\n"
        f"순수 HTML만 출력해."
    )

    token = os.environ.get("TOKEN_GITHUB")
    if not token:
        print("에러: TOKEN_GITHUB가 설정되지 않았습니다.")
        return None

    try:
        model="openai/gpt-4o"
        client = ChatCompletionsClient(
            endpoint="https://models.github.ai/inference",
            credential=AzureKeyCredential(token),
        )

        print(f"🤖 GitHub AI [{model_name}] 모델 통신 시도 중...")
        response = client.complete(
            messages=[SystemMessage(content=system_prompt), UserMessage(content=user_prompt)],
            model=model_name
        )
        print(f"✅ 성공! [{model_name}] 모델이 기사를 생성했습니다.")
        return response.choices[0].message.content.replace("```html", "").replace("```", "").strip()
        
    except Exception as e:
        error_short = str(e).split('\n')[0][:80]
        print(f"❌ [{model_name}] 통신 실패: {error_short}...")
        return None

def update_news_list():
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    links_html = ""
    for file in post_files[:100]:
        filename = os.path.basename(file)
        parts = filename.replace(".html", "").split('_')
        formatted_date, country_label = "날짜 미상", "글로벌"
        try:
            if len(parts) >= 5:
                year, month, day, hour, minute = parts[1][0:4], str(int(parts[1][4:6])), str(int(parts[1][6:8])), parts[2][0:2], parts[2][2:4]
                country_label, formatted_date = parts[3], f"{year}년 {month}월 {day}일 {hour}:{minute}"
        except Exception: pass
            
        actual_title = f"[{country_label}] 분야별 핵심 속보 AI 요약"
        try:
            with open(file, "r", encoding="utf-8") as f_html:
                soup = BeautifulSoup(f_html.read(), "html.parser")
                h2_tag = soup.find("h2")
                if h2_tag: actual_title = h2_tag.text.strip()
        except Exception: pass

        links_html += f"""
        <div class="px-5 py-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition group" onclick="loadNews('./news/{filename}')">
            <div class="flex items-center space-x-1.5 mb-2">
                <svg class="w-3.5 h-3.5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9.5L18.5 7H20a2 2 0 012 2v9a2 2 0 01-2 2z"></path></svg>
                <span class="text-[11px] font-bold text-gray-700">{country_label} 데스크</span>
            </div>
            <h2 class="text-[14px] font-bold text-gray-900 leading-snug line-clamp-2 group-hover:text-blue-600 transition-colors">{actual_title}</h2>
            <div class="mt-2.5 text-[11px] text-gray-500 font-medium">{formatted_date} <span class="mx-1">·</span> AI 기자</div>
        </div>
        """
    with open(os.path.join("news", "news_list.html"), "w", encoding="utf-8") as f: f.write(links_html)
    print("목록 디자인(news_list.html) 갱신 완료!")

def cleanup_old_news(max_files=150):
    for idx, file_path in enumerate(sorted(glob.glob("news/post_*.html"), reverse=True)):
        if idx >= max_files:
            try: os.remove(file_path)
            except Exception: pass

if __name__ == "__main__":
    if not os.path.exists("news"): os.makedirs("news")
    news_list, country_code = get_global_news()
    groups = group_similar_news(news_list)
    
    if groups:
        now = datetime.now()
        date_str, time_str = now.strftime('%Y%m%d'), now.strftime('%H%M%S')
        for i, group in enumerate(groups[:1]):
            post_content = generate_post(group, country_code)
            if post_content:
                with open(f"news/post_{date_str}_{time_str}_{country_code}_0.html", "w", encoding="utf-8") as f:
                    f.write(f"<html><body style='line-height:2; padding:20px;'>{post_content}</body></html>")
                time.sleep(1)
    
    update_news_list()
    cleanup_old_news(max_files=100)
