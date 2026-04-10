import os
import requests
import glob
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import time
import email.utils
from difflib import SequenceMatcher 

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

   # ⭐ [강력한 시간 필터 장착] q=검색어 뒤에 '+when:7d'를 붙여 철저하게 최근 일주일 기사만 가져옵니다!
    if target_country == "KOREA":
        url = "https://news.google.com/rss/search?q=속보+when:7d&hl=ko&gl=KR&ceid=KR:ko"
    elif target_country == "USA":
        url = "https://news.google.com/rss/search?q=Breaking+when:7d&hl=en-US&gl=US&ceid=US:en"
    else:
        url = "https://news.google.com/rss/search?q=突发新闻+when:7d&hl=zh-CN&gl=CN&ceid=CN:zh-hans"

    now_str = datetime.now(KST).strftime('%H:%M')
    print(f"===================================================")
    print(f"🔄[{now_str} KST] 봇 가동 시작")
    print(f"🎯[타겟 국가] 이전 사이클 확인 완료 -> 이번 수집 국가는 [{target_country}] 입니다.")
    print(f"📡[뉴스 수집] 구글 뉴스 RSS 접속 중...")
    
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        
        news_data = []
        for item in items[:100]:
            title = item.title.text if item.title else "제목 없음"
            link = item.link.text if item.link else "#"
            source_tag = item.find("source")
            source = source_tag.text if source_tag else "글로벌 매체"
            pub_date_tag = item.find("pubDate")
            rss_pub_date = parse_rss_date(pub_date_tag.text) if pub_date_tag else "수집 시간 미상"
            news_data.append({"title": title, "link": link, "source": source, "rss_pub_date": rss_pub_date})
            
        print(f"✅[수집 완료] 총 {len(news_data)}개의 최신 기사를 가져왔습니다.")
        return news_data, target_country
    except Exception as e:
        print(f"❌[수집 에러]: {e}"); return[], "ERROR"

# ⭐[그룹핑 로직 수정] 언론사 꼬리표 제거 & 순수 제목 유사도 50% 판별!
def group_similar_news(news_list):
    print(f"🗂️[그룹핑] 언론사 꼬리표를 제거한 순수 제목의 '유사도 50% 이상' 기준으로 기사들을 묶습니다...")
    groups =[]
    
    for news in news_list:
        raw_title = news['title'].strip()
        if not raw_title: 
            continue
        
        # 1. 꼬리표 자르기: 구글 뉴스 특유의 ' - 언론사명'을 분리하여 앞부분(순수 제목)만 얻습니다.
        core_title = raw_title.rsplit(' - ', 1)[0] if ' - ' in raw_title else raw_title
        
        added_to_group = False
        
        # 2. 기존에 만들어진 그룹들과 하나씩 비교합니다.
        for group in groups:
            # 비교 대상 그룹의 대표 기사(첫 번째 기사) 제목도 꼬리표를 자릅니다.
            rep_raw = group[0]['title']
            rep_core = rep_raw.rsplit(' - ', 1)[0] if ' - ' in rep_raw else rep_raw
            
            # 두 기사의 순수 제목끼리 텍스트 일치율을 계산합니다.
            similarity = SequenceMatcher(None, core_title, rep_core).ratio()
            
            # 3. 일치율이 50%(0.50) 이상이면 같은 핫이슈로 간주하고 묶어버립니다.
            if similarity >= 0.50:
                group.append(news)
                added_to_group = True
                break
                
        # 4. 어디에도 속하지 못한(60% 이상 안 겹치는) 새로운 기사면 새 방을 팝니다.
        if not added_to_group:
            groups.append([news])
            
    # 최종적으로 기사가 3개 이상 모인 것만 진짜 이슈로 필터링 후 덩치(길이)순 정렬합니다.
    valid_groups = sorted([g for g in groups if len(g) >= 3], key=len, reverse=True)
    print(f"✅[그룹핑 완료] 3곳 이상 언론사에서 보도된 핫이슈 그룹: 총 {len(valid_groups)}개 발견")
    
    for i, g in enumerate(valid_groups[:3]):
        print(f"   👉 순위 {i+1}:[ {g[0]['title'][:30]}... ] (관련 기사 {len(g)}개)")

    return valid_groups
    
def generate_post(news_group, country):
    top_3_news = news_group[:3]
    
    print(f"🚀[AI 전송] 1순위 핫이슈 내에서 대표 기사 3개를 선별하여 AI에게 전송합니다.")
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
    
    user_prompt = (
        f"==========[분석할 기사 목록 (팩트 데이터)]==========\n"
        f"{context}\n"
        f"==========\n\n"
        
        f"[출력 형식 (이 HTML 형식을 무조건 따를 것)]\n"
        f"<h2>[{emoji_country} 속보] 핵심 내용을 10자 내외로 작성</h2><br>\n"
        f"요약 문장 첫 번째입니다.<br>\n"
        f"요약 문장 두 번째입니다.<br>\n"
        f"요약 문장 세 번째입니다.<br><br>\n"
        
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
        f"시간 [기사 3 수집일시]<br><br>\n"
        
        f"[매우 중요한 주의사항]\n"
        f"- <h2> 태그 안의 제목은 '[{emoji_country} 속보]' 부분을 제외하고 절대 10글자를 초과하지 마라.\n"
        f"- 요약 본문은 반드시 3줄(3문장) 이상으로 작성해라. 전체 본문 글자 수 총합은 절대 100글자를 초과하지 않도록 압축하라.\n"
        f"- 1, 2, 3번 링크 섹션에 기재하는 모든 기사 제목, 링크, 언론사, 수집일시 데이터는 내가 제공한 '[분석할 기사 목록]' 안에 있는 정보만을 그대로 복사 붙여넣기 해라.\n"
        f"- 절대 임의로 데이터를 지어내거나 변형하지 마라.\n"
        f"- 코드 블럭(```html) 등은 제외하고 별도의 설명 없이 순수 HTML 구조만 출력할 것."
    )

    token = os.environ.get("TOKEN_GITHUB")
    if not token:
        print("❌[에러] TOKEN_GITHUB 환경변수가 설정되지 않았습니다.")
        return None

    # 직접 검증하여 설정해주신 소중한 모델명 (유지)
    model_name = "openai/gpt-4.1"

    try:
        client = ChatCompletionsClient(
            endpoint="https://models.github.ai/inference",
            credential=AzureKeyCredential(token),
        )

        print(f"🤖GitHub AI[{model_name}] 모델에게 답변을 요청중입니다. 기다려주세요...")
        response = client.complete(
            messages=[SystemMessage(content=system_prompt), UserMessage(content=user_prompt)],
            model=model_name
        )
        print(f"✅[답변 완료] {model_name} 모델이 성공적으로 기사를 요약했습니다!")
        return response.choices[0].message.content.replace("```html", "").replace("```", "").strip()
        
    except Exception as e:
        error_short = str(e).split('\n')[0][:80]
        print(f"❌[{model_name}] 통신 실패: {error_short}...")
        return None

def update_news_list():
    print(f"📝[HTML 갱신] 좌측 사이드바 구조(news_list.html) 업데이트를 시작합니다.")
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
                <span class="text-[11px] font-bold text-gray-700">{display_label}</span>
            </div>
            <h2 class="text-[14px] font-bold text-gray-900 leading-snug line-clamp-2 group-hover:text-blue-600 transition-colors">{actual_title}</h2>
            <div class="mt-2.5 text-[11px] text-gray-500 font-medium">{formatted_date} <span class="mx-1">·</span> AI 기자</div>
        </div>
        """
    with open(os.path.join("news", "news_list.html"), "w", encoding="utf-8") as f: f.write(links_html)
    print("✅[HTML 갱신 완료] 목록 디자인(news_list.html)이 저장소에 갱신되었습니다.")

def cleanup_old_news(max_files=100):
    delete_count = 0
    for idx, file_path in enumerate(sorted(glob.glob("news/post_*.html"), reverse=True)):
        if idx >= max_files:
            try: 
                os.remove(file_path)
                delete_count += 1
            except Exception: pass
    if delete_count > 0:
        print(f"🗑️[저장소 관리] 너무 오래된 기사 파일 {delete_count}개를 삭제하여 용량을 확보했습니다.")

if __name__ == "__main__":
    if not os.path.exists("news"): os.makedirs("news")
    
    news_list, target_country = get_global_news()
    groups = group_similar_news(news_list)
    
    if groups:
        now = datetime.now(KST)
        date_str, time_str = now.strftime('%Y%m%d'), now.strftime('%H%M%S')
        for i, group in enumerate(groups[:3]):  
            post_content = generate_post(group, target_country)
            if post_content:
                file_name = f"news/post_{date_str}_{time_str}_{target_country}_0.html"
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(f"<html><body style='line-height:2; padding:20px;'>{post_content}</body></html>")
                print(f"💾 [파일 저장] {file_name} 생성을 완료했습니다.")
                time.sleep(1)
                break 
    else:
        print("⚠️[이슈 부족] 현재 3개 이상의 매체에서 중복 보도된 핫이슈를 찾지 못하여 기사 생성을 건너뜁니다.")
        
    update_news_list()
    cleanup_old_news(max_files=100)
    print("===================================================")
    print("🎉[작업 완전 종료] 이번 시간의 모든 봇 자동화 작업이 성공적으로 끝났습니다!\n")
