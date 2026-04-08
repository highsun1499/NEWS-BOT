import os
import requests
import glob
from bs4 import BeautifulSoup
from datetime import datetime
import time
import email.utils

# [GitHub (Azure) LLM 라이브러리]
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

# ---- [추가] 구글 뉴스의 고유 시간 형식을 예쁜 한국 시간(YYYY.MM.DD HH:MM)으로 변환 ----
def parse_rss_date(rss_date_str):
    try:
        time_tuple = email.utils.parsedate_tz(rss_date_str)
        if time_tuple:
            epoch_time = email.utils.mktime_tz(time_tuple)
            dt = datetime.fromtimestamp(epoch_time)
            return dt.strftime("%Y.%m.%d %H:%M")
    except:
        pass
    return "수집 시간 미상"

# 1. 뉴스 수집 (구글 RSS 100% 활용)
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
        
        news_data =[]
        for item in items[:100]:
            title = item.title.text if item.title else "제목 없음"
            link = item.link.text if item.link else "#"
            
            # 구글 뉴스에서 제공해주는 언론사 이름과 수집 시간만 정직하게 빼냅니다.
            source_tag = item.find("source")
            source = source_tag.text if source_tag else "글로벌 매체"
            
            pub_date_tag = item.find("pubDate")
            rss_pub_date = parse_rss_date(pub_date_tag.text) if pub_date_tag else "수집 시간 미상"
            
            news_data.append({"title": title, "link": link, "source": source, "rss_pub_date": rss_pub_date})
            
        return news_data, country
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

# 3. AI 모델 통신 및 기사 포스팅 생성
def generate_post(news_group, country):
    # 상위 3개 기사만 선별해서 철저하게 프롬프트 전달
    top_3_news = news_group[:3]
    context = ""
    
    for i, n in enumerate(top_3_news):
        context += (
            f"----[기사 {i+1}] ----\n"
            f"제목: {n['title']}\n"
            f"링크: {n['link']}\n"
            f"언론사: {n['source']}\n"
            f"수집일시: {n['rss_pub_date']}\n\n"
        )
    
    system_prompt = (
        f"너는 글로벌 뉴스 전문 큐레이터야. 현재 분석 중인 국가는 {country}이야.\n"
        f"다음 제공된 기사의 내용이 해당 국가의 언어라면 한국어로 완벽히 번역해. 그 후 아래 형식을 엄격히 지켜서 요약해."
    )
    
    # ⭐ [핵심 수정] 요청하신 [링크 -> 제목 -> 언론사 -> 수집시간] 순서에 맞춘 완벽한 통일 양식!
    user_prompt = (
        f"=========[분석할 기사 목록 (팩트 데이터)] =========\n"
        f"{context}\n"
        f"======================================\n\n"
        f"[출력 형식 (이 HTML 형식을 무조건 따를 것)]\n"
        f"<h2>[{country} 속보] 핵심 내용을 15자 내외로 작성</h2>\n<br>\n"
        f"요약 문단 (문장 끝마다 <br> 필수)\n<br>\n"
        f"<strong>링크 :</strong><br><br>\n"
        
        f"1번<br>\n"
        f"<a href='[기사 1 링크]' target='_blank'>[기사 1 제목]</a><br>\n"
        f"[기사 1 언론사]<br>\n"
        f"시간 [기사 1 수집일시]<br><br>\n"
        
        f"2번<br>\n"
        f"<a href='[기사 2 링크]' target='_blank'>[기사 2 제목]</a><br>\n"
        f"[기사 2 언론사]<br>\n"
        f"시간 [기사 2 수집일시]<br><br>\n"
        
        f"3번<br>\n"
        f"<a href='[기사 3 링크]' target='_blank'>[기사 3 제목]</a><br>\n"
        f"[기사 3 언론사]<br>\n"
        f"시간 [기사 3 수집일시]<br><br>\n\n"
        
        f"[매우 중요한 주의사항]\n"
        f"- 1, 2, 3번 링크 섹션에 기재하는 모든 기사 제목, 링크, 언론사, 수집일시 데이터는 내가 제공한 '[분석할 기사 목록]' 안에 있는 정보만을 그대로 복사 붙여넣기 해라.\n"
        f"- 절대 임의로 데이터를 지어내거나 변형하지 마라.\n"
        f"- 코드 블럭(```html) 등은 제외하고 별도의 설명 없이 순수 HTML 구조만 출력할 것."
    )

    token = os.environ.get("TOKEN_GITHUB")
    if not token:
        print("에러: TOKEN_GITHUB가 설정되지 않았습니다.")
        return None

    # 질문자님이 쓰시던 작동되는 깃허브 모델명을 이곳에 적어주세요. (우선 메타 모델로 잡아두었습니다.)
    model_name = "openai/gpt-4.1"

    try:
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
                country_label, formatted_date = f"{parts[3]}", f"{year}년 {month}월 {day}일 {hour}:{minute}"
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
            <div class="mt-2.5 text-[11px] text-gray-500 font-medium">{formatted_date} <span class="mx-1">·</span> AI 큐레이터</div>
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
        for i, group in enumerate(groups[:3]):  
            post_content = generate_post(group, country_code)
            if post_content:
                with open(f"news/post_{date_str}_{time_str}_{country_code}_0.html", "w", encoding="utf-8") as f:
                    f.write(f"<html><body style='line-height:2; padding:20px;'>{post_content}</body></html>")
                time.sleep(1)
                break 
    
    update_news_list()
    cleanup_old_news(max_files=100)
