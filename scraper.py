import os
import requests
import glob
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import time
import email.utils
import re
from difflib import SequenceMatcher

#[GitHub (Azure) LLM 라이브러리]
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential

KST = timezone(timedelta(hours=9))

def parse_rss_date(rss_date_str):
    """RSS의 시간 포맷을 파싱하여 정렬을 위한 (datetime객체)와 (포맷팅 텍스트)를 동시에 반환합니다."""
    try:
        time_tuple = email.utils.parsedate_tz(rss_date_str)
        if time_tuple:
            epoch_time = email.utils.mktime_tz(time_tuple)
            dt = datetime.fromtimestamp(epoch_time, tz=timezone.utc).astimezone(KST)
            return dt, dt.strftime("%Y.%m.%d %H:%M")
    except:
        pass
    # 에러 및 파싱 실패 시, 최신순 정렬에서 맨 꼴찌로 밀려나도록 옛날 날짜 셋팅
    return datetime(1970, 1, 1, tzinfo=KST), "수집 시간 미상"

# 🔴 [로직 1단계 & 2단계] 수집 및 최신순 정렬
def get_global_news():
    sequence =["KOREA", "USA", "CHINA"]
    target_country = "KOREA" 
    
    # ⭐ [변경됨] 폴더 감지 기준을 Jekyll 기준인 _posts 폴더로 변경했습니다!
    post_files = sorted(glob.glob("_posts/*.md"), reverse=True)
    if post_files:
        latest_file = os.path.basename(post_files[0]) 
        parts = latest_file.replace(".md", "").split('-')
        if len(parts) >= 5:
            last_country = parts[4]
            if last_country in sequence:
                next_index = (sequence.index(last_country) + 1) % len(sequence)
                target_country = sequence[next_index]

    # [로직 1] '속보' + 최근 7일(when:7d) 피드 연결 세팅
    if target_country == "KOREA":
        url = "https://news.google.com/rss/search?q=속보+when:7d&hl=ko&gl=KR&ceid=KR:ko"
    elif target_country == "USA":
        url = "https://news.google.com/rss/search?q=Breaking+when:7d&hl=en-US&gl=US&ceid=US:en"
    else:
        url = "https://news.google.com/rss/search?q=突发新闻+when:7d&hl=zh-CN&gl=CN&ceid=CN:zh-hans"

    now_str = datetime.now(KST).strftime('%H:%M')
    print(f"===================================================")
    print(f"🔄 [{now_str} KST] 봇 가동 시작")
    print(f"🎯 [타겟 국가] 이번 수집 순서는 [{target_country}] 입니다.")
    print(f"📡 [1단계] 구글 뉴스 RSS(최근 7일 제한) 최대 100개 확보 시도 중...")
    
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
            
            # 파싱된 datetime 객체를 통해 이따 '최신순 정렬'에 써먹을 예정입니다.
            dt_obj, rss_pub_date = parse_rss_date(pub_date_tag.text) if pub_date_tag else (datetime(1970, 1, 1, tzinfo=KST), "수집 시간 미상")
            
            news_data.append({
                "title": title, 
                "link": link, 
                "source": source, 
                "rss_pub_date": rss_pub_date,
                "dt_obj": dt_obj
            })
            
        print(f"✅ [1단계 완료] 구글 뉴스 한도인 {len(news_data)}개의 최신 기사를 수집했습니다.")
        
        # [로직 2] 수집된 데이터를 즉시 최신 시간 기준으로 내림차순 정렬
        print(f"🗂️ [2단계] 수집된 100개의 데이터를 '최신 발생 시간순'으로 정렬합니다...")
        news_data.sort(key=lambda x: x['dt_obj'], reverse=True)
        print(f"✅ [2단계 완료] 최신순 정렬이 완벽하게 끝났습니다.")
        
        return news_data, target_country
    except Exception as e:
        print(f"❌ [수집 에러]: {e}"); return[], "ERROR"

# 🔴 [로직 3단계 & 4단계] 유사도 50% 그룹화 및 총량 정렬
def group_similar_news(news_list):
    print(f"🗂️ [3단계] 꼬리표를 제외한 순수 기사 제목 '50% 이상 유사도'를 기준으로 모든 기사를 그룹화합니다...")
    groups =[]
    
    for news in news_list:
        raw_title = news['title'].strip()
        if not raw_title: continue
        
        # 언론사 꼬리표( - 중앙일보 등)만 날려서 비교 확률을 높입니다.
        core_title = raw_title.rsplit(' - ', 1)[0] if ' - ' in raw_title else raw_title
        
        added_to_group = False
        for group in groups:
            rep_raw = group[0]['title']
            rep_core = rep_raw.rsplit(' - ', 1)[0] if ' - ' in rep_raw else rep_raw
            similarity = SequenceMatcher(None, core_title, rep_core).ratio()
            
            # [로직 3] 기준 50%를 조금이라도 넘기면 해당 그룹으로 묶습니다!
            if similarity >= 0.50:
                group.append(news)
                added_to_group = True
                break
                
        # 유사도 50% 미만이라면 단 1개의 기사라도 무조건 자기가 속할 새로운 방(그룹)을 팝니다.
        if not added_to_group:
            groups.append([news])
            
    # ⭐ [핵심 수정: 로직 4] 생성된 모든 그룹을 정렬합니다!
    print(f"🗂️ [4단계] 완료된 그룹들을 '기사가 많은 순위' ➔ (동률 시) '가장 최신 기사가 포함된 순'으로 줄 세웁니다...")
    
    # 튜플 (len(g), max(시간))을 키로 주어, 1순위: 덩치큰 순, 2순위: 최신순으로 완벽하게 내림차순(reverse=True) 정렬합니다.
    sorted_groups = sorted(groups, key=lambda g: (len(g), max(n['dt_obj'] for n in g)), reverse=True)
    
    print(f"✅ [3,4단계 완료] 단 1개의 기사도 버려짐 없이 총 {len(sorted_groups)}개의 그룹이 형성되었습니다.")
    
    # 봇이 로그에서 확인할 수 있도록 상위 5위권까지의 랭킹과 '가장 최신 보도 시간'을 출력합니다.
    for i, g in enumerate(sorted_groups[:5]):
        latest_time_in_group = max(n['dt_obj'] for n in g).strftime('%m.%d %H:%M')
        print(f"   👉 {i+1}위 그룹:[ {g[0]['title'][:30]}... ] (소속: {len(g)}개 / 최신보도: {latest_time_in_group})")

    return sorted_groups

# 🔴 [로직 5단계] 1번 그룹 내 최신&다양성 필터 적용 후 3개 선별
def filter_top_news(sorted_groups):
    print(f"🎯 [5단계] 1위 그룹의 기사들을 최신순으로 다시 다듬고, '서로 다른 3개의 언론사' 기사를 조달합니다.")
    
    selected_news =[]
    unique_sources = set()
    
    try:
        # 무조건 가장 기사가 많은 1위(인덱스 0) 그룹 선택
        top_group = sorted_groups[0]
        
        # [로직 5.1] 그룹 안의 기사들을 다시 팩트 기반, 최신순으로 예쁘게 정렬합니다.
        top_group.sort(key=lambda x: x['dt_obj'], reverse=True)
        
        #[로직 5.2] 위에서부터 꺼내면서 다른 언론사의 기사인지 교차 검증을 합니다.
        for news in top_group:
            if news['source'] not in unique_sources:
                unique_sources.add(news['source'])
                selected_news.append(news)
                
            # 3개가 모이면 즉시 스탑!
            if len(selected_news) == 3:
                break
                
        # (방어 조치) 1번 그룹이 온통 한 언론사 도배라 3개를 못 모았다면 빈자리를 순차적으로 채웁니다.
        if len(selected_news) < 3:
            print("⚠️ 1위 그룹 내 서로 다른 언론사가 부족하여 예비 기사를 추가 선별합니다.")
            for news in top_group:
                if news not in selected_news:
                    selected_news.append(news)
                if len(selected_news) == 3:
                    break
                    
        print(f"✅ [5단계 완료] AI에게 보낼 완벽한 최신 기사 3개가 선별되었습니다.")
        for idx, n in enumerate(selected_news):
            print(f"   ✅ 발탁된 기사 {idx+1}: [{n['source']}] {n['title'][:20]}...")
            
    except Exception as e:
        print(f"❌ [필터링 실패]: {e}")

    return selected_news

# 🔴 [로직 6단계] AI 요약 명령 전송
def generate_post(top_3_news, country):
    print(f"🚀 [6단계] 선별된 3개의 기사를 LLM에게 넘기고 요약을 명령을 전송합니다.")
    
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
        f"<h2>[{emoji_country} 속보] 핵심 내용을 100자 내외로 작성</h2><br>\n"
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
        f"- <h2> 태그 안의 제목은 '[{emoji_country} 속보]' 부분을 제외하고 절대 100글자를 초과하지 마라.\n"
        f"- 요약 본문은 반드시 3줄(3문장) 이상으로 작성해라. 전체 본문 글자 수 총합은 절대 1000글자를 초과하지 않도록 압축하라.\n"
        f"- 1, 2, 3번 링크 섹션에 기재하는 모든 기사 제목, 링크, 언론사, 수집일시 데이터는 내가 제공한 '[분석할 기사 목록]' 안에 있는 정보만을 그대로 복사 붙여넣기 해라.\n"
        f"- 절대 임의로 데이터를 지어내거나 변형하지 마라.\n"
        f"- 코드 블럭(```html) 등은 제외하고 별도의 설명 없이 순수 HTML 구조만 출력할 것."
    )

    token = os.environ.get("TOKEN_GITHUB")
    if not token:
        print("❌ [에러] TOKEN_GITHUB 환경변수가 설정되지 않았습니다.")
        return None

    # 직접 검증하여 설정해주신 소중한 모델명 (유지)
    model_name = "openai/gpt-4.1"

    try:
        client = ChatCompletionsClient(
            endpoint="https://models.github.ai/inference",
            credential=AzureKeyCredential(token),
        )

        print(f"🤖 GitHub AI [{model_name}] 통신 연결 중...")
        response = client.complete(
            messages=[SystemMessage(content=system_prompt), UserMessage(content=user_prompt)],
            model=model_name
        )
        print(f"✅ [6단계 완료] {model_name} 가 성공적으로 요약을 조판했습니다!")
        return response.choices[0].message.content.replace("```html", "").replace("```", "").strip()
        
    except Exception as e:
        error_short = str(e).split('\n')[0][:80]
        print(f"❌ [{model_name}] 통신 실패: {error_short}...")
        return None

def cleanup_old_news(max_files=100):
    delete_count = 0
    # ⭐ [변경됨] 이전의 news 폴더가 아닌 언론사 공식 규격인 _posts 폴더를 관리합니다! 
    for idx, file_path in enumerate(sorted(glob.glob("_posts/*.md"), reverse=True)):
        if idx >= max_files:
            try: os.remove(file_path); delete_count += 1
            except Exception: pass

if __name__ == "__main__":
    # ⭐ [변경됨] Jekyll 표준 저장소인 _posts 폴더를 만듭니다.
    if not os.path.exists("_posts"): os.makedirs("_posts")
    
    news_list, target_country = get_global_news()
    if news_list:
        sorted_groups = group_similar_news(news_list)
        top_3_news = filter_top_news(sorted_groups)
        
        if top_3_news:
            now = datetime.now(KST)
            # ⭐ [핵심 변경] Jekyll의 엄격한 날짜 포맷 규칙(YYYY-MM-DD-제목.md)을 준수하여 설계합니다.
            date_str = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H%M%S')
            
            post_content = generate_post(top_3_news, target_country)
            
            if post_content:
                # AI가 생성한 <h2>안의 제목 텍스트만 빼서 구글 검색 잡히도록(Title) 적용
                actual_title = f"{target_country} 속보"
                try:
                    soup = BeautifulSoup(post_content, "html.parser")
                    h2_tag = soup.find("h2")
                    if h2_tag: 
                        raw_title = h2_tag.text.strip()
                        actual_title = raw_title.split("]", 1)[1].strip() if "]" in raw_title else raw_title
                except: pass

                # ⭐ [가장 중요한 변경] HTML 파일이 아니라 Jekyll(블로그) 마크다운 문서를 만듭니다!
                file_name = f"_posts/{date_str}-{time_str}-{target_country}.md"
                
                front_matter = f"""---
layout: post
title: "{actual_title}"
date: {now.strftime('%Y-%m-%d %H:%M:%S')} +0900
category: {target_country}
---
{post_content}
"""
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(front_matter)
                    
                print(f"💾 [블로그 포스팅 완료!] {file_name}")
                time.sleep(1)
                
    # update_news_list() 함수는 완벽히 삭제되었습니다! (이제 깃허브 엔진이 알아서 해줍니다)
    cleanup_old_news(max_files=100)
