import os
import requests
import glob
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import time
import email.utils
import re  # ⭐ 괄호 및 특수문자 제거를 위해 정규식 라이브러리를 추가했습니다!

#[GitHub (Azure) LLM 라이브러리]
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

KST = timezone(timedelta(hours=9))

def parse_rss_date(rss_date_str):
    try:
        time_tuple = email.utils.parsedate_tz(rss_date_str)
        if time_tuple:
            epoch_time = email.utils.mktime_tz(time_tuple)
            dt = datetime.fromtimestamp(epoch_time, tz=timezone.utc).astimezone(KST)
            return dt.strftime("%Y.%m.%d %H:%M")
    except:
        pass
    return "수집 시간 미상"

def get_global_news():
    sequence = ["KOREA", "USA", "CHINA"]
    target_country = "KOREA" 
    
    post_files = sorted(glob.glob("news/post_*.html"), reverse=True)
    if post_files:
        latest_file = os.path.basename(post_files[0]) 
        parts = latest_file.replace(".html", "").split('_')
        if len(parts) >= 4:
            last_country = parts[3]
            if last_country in sequence:
                next_index = (sequence.index(last_country) + 1) % len(sequence)
                target_country = sequence[next_index]

    if target_country == "KOREA":
        url = "https://news.google.com/rss/search?q=속보&hl=ko&gl=KR&ceid=KR:ko"
    elif target_country == "USA":
        url = "https://news.google.com/rss/search?q=Breaking&hl=en-US&gl=US&ceid=US:en"
    else:
        url = "https://news.google.com/rss/search?q=突发新闻&hl=zh-CN&gl=CN&ceid=CN:zh-hans"

    now_str = datetime.now(KST).strftime('%H:%M')
    print(f"[{now_str} 업데이트] {target_country} 뉴스 수집을 시작합니다...")
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        
        news_data =[]
        for item in items[:100]:
            title = item.title.text if item.title else "제목 없음"
            link = item.link.text if item.link else "#"
            source_tag = item.find("source")
            source = source_tag.text if source_tag else "글로벌 매체"
            pub_date_tag = item.find("pubDate")
            rss_pub_date = parse_rss_date(pub_date_tag.text) if pub_date_tag else "수집 시간 미상"
            news_data.append({"title": title, "link": link, "source": source, "rss_pub_date": rss_pub_date})
            
        return news_data, target_country
    except Exception as e:
        print(f"수집 에러: {e}"); return[], "ERROR"

# ⭐ [핵심 수정: 중국어 묶음 오류 해결]
def group_similar_news(news_list, target_country):
    groups = {}
    for news in news_list:
        # 뉴스 제목에서 쓸데없는 특수기호, [속보], 【突发】 같은 괄호들을 싹 다 날리고 순수 글자만 남깁니다.
        clean_title = re.sub(r'\[.*?\]|【.*?】|\(.*?\)|\-.*', '', news['title'])
        clean_title = re.sub(r'[^\w\s]', '', clean_title).strip()
        
        if not clean_title: continue

        # 중국어는 띄어쓰기가 없으므로 앞의 10글자가 일치하면 무조건 같은 뉴스(핫이슈)로 인식시킵니다.
        if target_country == "CHINA":
            group_key = clean_title[:10]
        # 한국어, 영어는 기존처럼 앞의 2단어를 기준으로 자릅니다.
        else:
            words = clean_title.split()
            group_key = " ".join(words[:2]) if len(words) > 1 else clean_title
            
        if group_key not in groups: groups[group_key] = []
        groups[group_key].append(news)
        
    # 3개 이상 중복 보도된 가짜 아닌 "진짜 핫이슈"만 걸러냅니다.
    valid_groups = sorted([g for g in groups.values() if len(g) >= 3], key=len, reverse=True)
    return valid_groups

def generate_post(news_group, country):
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
    
    if country == "KOREA": emoji_country = "🇰🇷 한국"
    elif country == "USA": emoji_country = "🇺🇸 미국"
    elif country == "CHINA": emoji_country = "🇨🇳 중국"
    else: emoji_country = f"🌐 {country}"

    system_prompt = (
        f"너는 글로벌 뉴스 전문 큐레이터야. 현재 분석 중인 국가는 {country}이야.\n"
        f"다음 제공된 기사의 내용이 해당 국가의 언어라면 한국어로 완벽히 번역해. 그 후 아래 형식을 엄격히 지켜서 요약해."
    )
    
    # ⭐ [핵심 수정: AI 바보 현상 차단]
    user_prompt = (
        f"=========[분석할 기사 목록 (팩트 데이터)] =========\n"
        f"{context}\n"
        f"======================================\n\n"
        f"[출력 형식 (이 HTML 형식을 무조건 따를 것)]\n"
        f"<h2>[{emoji_country} 속보] 실제 기사를 바탕으로 한 요약 제목</h2>\n<br>\n"
        f"첫 번째 핵심 요약 문장입니다.<br>\n"
        f"두 번째 핵심 요약 문장입니다.<br>\n"
        f"세 번째 핵심 요약 문장입니다.<br><br>\n"
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
        f"- <h2> 태그 안에는 '실제 기사를 바탕으로 한 요약 제목' 이라는 글자를 절대 그대로 출력하지 마라! 반드시 네가 기사를 분석해서 새롭게 지어낸 '진짜 제목'으로 교체해서 써넣을 것.\n"
        f"- 제목의 길이는 핵심만 담아 절대 10자를 초과하지 마라.\n"
        f"- 요약 본문은 반드시 3줄(3문장) 이상으로 작성해라. 하지만 전체 본문 글자 수의 총합이 100글자를 초과하지 않도록 압축하라.\n"
        f"- 1, 2, 3번 링크 섹션의[제목, 링크, 언론사, 수집일시] 데이터는 내가 제공한 '[분석할 기사 목록]' 안에 있는 원본 데이터만 그대로 복사 붙여넣기 해라.\n"
        f"- 코드 블럭(```html) 등은 제외하고 별도의 설명 없이 오직 쓸 수 있는 순수 HTML 코드만 출력할 것."
    )

    token = os.environ.get("TOKEN_GITHUB")
    if not token:
        print("에러: TOKEN_GITHUB가 설정되지 않았습니다.")
        return None

    model_name = "gpt-4o"

    try:
        client = ChatCompletionsClient(
            endpoint="https://models.github.ai/inference",
            credential=AzureKeyCredential(token),
        )

        print(f"🤖 GitHub AI[{model_name}] 모델 통신 시도 중...")
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
        
        if country_label == "KOREA": display_label = "🇰🇷 한국 속보"
        elif country_label == "USA": display_label = "🇺🇸 미국 속보"
        elif country_label == "CHINA": display_label = "🇨🇳 중국 속보"
        else: display_label = f"🌐 {country_label} 속보"

        actual_title = "분야별 핵심 속보 AI 요약"
        try:
            with open(file, "r", encoding="utf-8") as f_html:
                soup = BeautifulSoup(f_html.read(), "html.parser")
                h2_tag = soup.find("h2")
                if h2_tag: 
                    raw_title = h2_tag.text.strip()
                    if "]" in raw_title:
                        actual_title = raw_title.split("]", 1)[1].strip()
                    else:
                        actual_title = raw_title
        except Exception: pass

        links_html += f"""
        <div class="px-5 py-4 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition group" onclick="loadNews('./news/{filename}')">
            <div class="flex items-center space-x-1.5 mb-2">
                <svg class="w-3.5 h-3.5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9.5L18.5 7H20a2 2 0 012 2v9a2 2 0 01-2 2z"></path></svg>
                <span class="text-[11px] font-bold text-gray-700">{display_label}</span>
            </div>
            <h2 class="text-[14px] font-bold text-gray-900 leading-snug line-clamp-2 group-hover:text-blue-600 transition-colors">{actual_title}</h2>
            <div class="mt-2.5 text-[11px] text-gray-500 font-medium">{formatted_date} <span class="mx-1">·</span> AI 기자</div>
        </div>
        """
    with open(os.path.join("news", "news_list.html"), "w", encoding="utf-8") as f: f.write(links_html)
    print("목록 디자인(news_list.html) 갱신 완료!")

def cleanup_old_news(max_files=100):
    for idx, file_path in enumerate(sorted(glob.glob("news/post_*.html"), reverse=True)):
        if idx >= max_files:
            try: os.remove(file_path)
            except Exception: pass

if __name__ == "__main__":
    if not os.path.exists("news"): os.makedirs("news")
    
    news_list, target_country = get_global_news()
    
    # ⭐ [호출부 수정] 그룹을 묶을 때 이것이 중국어(CHINA)인지 아닌지 알려줍니다!
    groups = group_similar_news(news_list, target_country)
    
    if groups:
        now = datetime.now(KST)
        date_str, time_str = now.strftime('%Y%m%d'), now.strftime('%H%M%S')
        for i, group in enumerate(groups[:3]):  
            post_content = generate_post(group, target_country)
            if post_content:
                with open(f"news/post_{date_str}_{time_str}_{target_country}_0.html", "w", encoding="utf-8") as f:
                    f.write(f"<html><body style='line-height:2; padding:20px;'>{post_content}</body></html>")
                time.sleep(1)
                break 
    else:
        print("⚠️ 3곳 이상 중복 보도된 핫이슈를 찾지 못하여 기사 생성을 건너뜁니다.")
        
    update_news_list()
    cleanup_old_news(max_files=100)
