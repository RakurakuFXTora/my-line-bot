#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
経済指標Bot (investpy + Twitter + LINE)
- ユーザーが「経済指標」と送ると user_id を登録
- 経済指標速報を Twitter投稿 & 登録ユーザーにプッシュ
"""

import os
import datetime
import time
import schedule
import threading

import tweepy
import investpy
from zoneinfo import ZoneInfo
from collections import defaultdict

from flask import Flask, request, abort

# ==== line-bot-sdk v2 (WebhookHandler, LineBotApi) ====
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage
)

##################################################
# Flaskアプリ
##################################################
app = Flask(__name__)

##################################################
# 1) Twitter API認証
##################################################
API_KEY = '6CwpBJe5TN1OAt6nmN1JEWYSC'
API_SECRET = '2HEVYH3FlpcCYvOr7AxVNs3HptpMbHs3rfQRSQqKp900gApGEf'
ACCESS_TOKEN = '1886311550291697665-Be2FgO6cNdfvBiU070hw4xTghrmGXl'
ACCESS_SECRET = 'eRma5uMivOChCVdHrJ7OnwghiRtYXUJyyjFjC5pFWHhKr'
BEARER_TOKEN = (
    'AAAAAAAAAAAAAAAAAAAAAOGuzQEAAAAAGFInBY6%2FJ5QNAZyh18Ex2QKqTeo%3D'
    'sRPOvcbSFRQkGEfIUef1rgKvObBB0yITaU4zQWpDcCSWBbgo04'
)

client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=API_KEY,
    consumer_secret=API_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_SECRET
)

##################################################
# 2) LINE Bot設定
##################################################
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET", "")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 友だち登録リスト(ユーザーが「経済指標」と送ったら追加)
SAVED_USER_IDS = set()

##################################################
# Flaskルート定義
##################################################
@app.route("/")
def index():
    return "Hello from Economic Indicator Bot (Investpy + Twitter + LINE)."

@app.route("/callback", methods=["POST"])
def callback():
    """LINE Webhookのエンドポイント"""
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400, "Invalid signature")
    return "OK"

# --- メッセージ受信時（テキスト用）---
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text
    user_id   = event.source.user_id

    print(f"[INFO] Received message from user_id={user_id}, text={user_text}")

    # ユーザーが「経済指標」と送ったら user_id を登録
    if user_text.strip() == "経済指標":
        if user_id not in SAVED_USER_IDS:
            SAVED_USER_IDS.add(user_id)
            reply_text = "経済指標速報をお届けするよう登録しました！"
        else:
            reply_text = "すでに登録済みです。"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    else:
        # 上記以外はオウム返し
        reply_text = f"あなたが送ったのは: {user_text}"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )

##################################################
# 3) investpy + schedule + Twitter + LINE push
##################################################

COUNTRY_NAMES_INVESTPY = [
    'united states','japan','euro zone','united kingdom','australia',
]
COUNTRY_NAME_MAP = {
    'united states':"米",'japan':"日",'euro zone':"ユーロ圏",'united kingdom':"英",'australia':"豪",
}
def map_country_name(investpy_zone:str)->str:
    c_low=investpy_zone.lower()
    if c_low in COUNTRY_NAME_MAP:
        return COUNTRY_NAME_MAP[c_low]
    else:
        return investpy_zone.upper()

def get_country_flag(ccy:str)->str:
    flag_map={"USD":"🇺🇸","JPY":"🇯🇵","GBP":"🇬🇧","EUR":"🇪🇺","AUD":"🇦🇺"}
    return flag_map.get(ccy.upper(),"")

IMPORTANT_KEYWORDS = [
    "FOMC","GDP","Nonfarm Payrolls","Unemployment","Average Hourly Earnings",
    "CPI","PPI","Retail Sales","ISM Manufacturing","ISM Non-Manufacturing",
    "Durable Goods","Philadelphia Fed","NY Empire State",
    "Michigan Consumer Sentiment","Consumer Sentiment","Housing Starts","New Home Sales",
    "Existing Home Sales","Initial Jobless Claims","PMI",
    "BoJ","ECB Interest Rate","BoE Interest Rate","RBA Interest Rate","Employment Change",
    "PCE Price Index","Core PCE Price Index","Trade Balance","JOLTS Job Openings",
    "Industrial Production","Capacity Utilization Rate","CB Consumer Confidence",
]
NEGATIVE_KEYWORDS = [
    "speaks","speech","address","testimony","press conference","member","chair","governor"
]
INDICATOR_NAME_MAP = {
    "Nonfarm Payrolls":"雇用統計","Unemployment Rate":"失業率","Average Hourly Earnings":"平均時給",
    "Retail Sales":"小売売上高","ISM Manufacturing":"ISM製造業景況指数","ISM Non-Manufacturing":"ISM非製造業景況指数",
    "Durable Goods":"耐久財受注","Philadelphia Fed":"フィラデルフィア連銀景況指数","NY Empire State":"ニューヨーク連銀製造業景況指数",
    "Michigan Consumer Sentiment":"ミシガン大学消費者信頼感指数","Housing Starts":"住宅着工件数","New Home Sales":"新築住宅販売件数",
    "Existing Home Sales":"中古住宅販売件数","Initial Jobless Claims":"新規失業保険申請件数","Employment Change":"雇用統計",
    "BoJ":"日銀","RBA Interest Rate":"RBA政策金利","BoE Interest Rate":"BOE政策金利","ECB Interest Rate":"ECB政策金利",
    "PCE Price Index":"PCEデフレータ","Core PCE Price Index":"コアPCEデフレータ","JOLTS Job Openings":"JOLTS求人件数",
    "CB Consumer Confidence":"コンファレンスボード消費者信頼感指数",
}
def map_indicator_name(event_en:str)->str:
    lowered= event_en.lower()
    for en_key,jp_value in INDICATOR_NAME_MAP.items():
        if en_key.lower() in lowered:
            return event_en.replace(en_key,jp_value)
    return event_en

def replace_en_with_jp(text:str)->str:
    # 省略( YoY->(前年比), etc.)
    return text

def convert_km_to_jp(num_str:str)->str:
    s=num_str.strip().upper()
    if s.endswith("K"):
        val_str=s[:-1]
        try:
            val=float(val_str)
            result=val*0.1
            return f"{result:.1f}万"
        except: return num_str
    if s.endswith("M"):
        val_str=s[:-1]
        try:
            val=float(val_str)
            result=val*100
            return f"{result:.1f}万"
        except: return num_str
    return num_str

def generate_hashtags(text:str)->str:
    tags=["#経済指標"]
    return " ".join(tags)

SCHEDULED_GROUPS=set()

def parse_investpy_jst(date_str, time_str):
    jst=ZoneInfo("Asia/Tokyo")
    if not time_str or time_str in ['--','All Day','Tentative']:
        hh,mm=0,0
    else:
        if time_str=='24:00':
            hh,mm=23,59
        else:
            if ':' not in time_str:
                hh,mm=0,0
            else:
                hh_,mm_=time_str.split(':')
                hh,mm=int(hh_),int(mm_)

    d,m,y = date_str.split('/')
    dd,mm_,yyyy=int(d),int(m),int(y)
    return datetime.datetime(yyyy,mm_,dd,hh,mm,tzinfo=jst)

def schedule_48h_events():
    jst=ZoneInfo("Asia/Tokyo")
    now=datetime.datetime.now(tz=jst)
    limit48= now+ datetime.timedelta(hours=48)

    from_date= now.strftime("%d/%m/%Y")
    to_date  = (now+datetime.timedelta(days=2)).strftime("%d/%m/%Y")
    print(f"[INFO] schedule 48h => from={from_date} to={to_date}")

    try:
        df = investpy.economic_calendar(
            time_zone='GMT +9:00',
            countries=COUNTRY_NAMES_INVESTPY,
            from_date=from_date, to_date=to_date
        )
    except Exception as e:
        print("[Error] investpy:", e)
        return

    filtered=[]
    jst_now = datetime.datetime.now(tz=jst)
    for _,row in df.iterrows():
        dt_jst=parse_investpy_jst(row['date'],row['time'])
        if not (jst_now <= dt_jst < limit48):
            continue

        ev_low=row['event'].lower()
        if not any(k.lower() in ev_low for k in IMPORTANT_KEYWORDS):
            continue
        if any(neg.lower() in ev_low for neg in NEGATIVE_KEYWORDS):
            continue
        zone_ = (row.get('zone','')or'').lower()
        imp_  = (row.get('importance','')or'').lower()
        if zone_!='united states' and imp_ in ('low','medium'):
            continue

        filtered.append((row, dt_jst))

    global SCHEDULED_GROUPS
    group_map= defaultdict(list)
    for (r, dt_jst) in filtered:
        ccy=r['currency']
        hhmm= dt_jst.strftime("%H:%M")
        group_map[(hhmm, ccy)].append(r)

    for (hhmm, ccy), row_list in group_map.items():
        if (hhmm, ccy) in SCHEDULED_GROUPS:
            continue
        schedule.every().day.at(hhmm).do(fetch_and_post_group, row_list)
        SCHEDULED_GROUPS.add((hhmm, ccy))
        ev_names = [r_['event'] for r_ in row_list]
        print(f"[SCHEDULE] {hhmm} {ccy} => {ev_names}")

def fetch_and_post_group(rows):
    attempts=20
    for i in range(attempts):
        if i>0:
            time.sleep(15)
        result=attempt_group_data(rows)
        if result:
            post_group_tweet(rows, result)
            return
        else:
            print(f"[INFO] attempt {i+1} => not ready => retry")
    print("[SKIP] 20 attempts => no data => skip")

def attempt_group_data(rows):
    jst=ZoneInfo("Asia/Tokyo")
    now=datetime.datetime.now(tz=jst)
    today= now.date()

    from_d= (today - datetime.timedelta(days=1)).strftime("%d/%m/%Y")
    to_d  = (today + datetime.timedelta(days=2)).strftime("%d/%m/%Y")
    try:
        df= investpy.economic_calendar(
            time_zone='GMT +9:00',
            countries=COUNTRY_NAMES_INVESTPY,
            from_date=from_d, to_date=to_d
        )
        df_today=[]
        for _,r in df.iterrows():
            dt_jst=parse_investpy_jst(r['date'],r['time'])
            if dt_jst.date() in [today, today+datetime.timedelta(days=1), today+datetime.timedelta(days=2)]:
                df_today.append(r)
    except Exception as e:
        print("[Error attempt_group_data]:", e)
        return False

    results={}
    for i, row in enumerate(rows):
        e_=row['event']
        c_=row['currency']
        matched=[m for m in df_today if m["event"]==e_ and m["currency"]==c_]
        if not matched:
            results[i]=None
        else:
            m=matched[0]
            act=m['actual']
            fc=m['forecast']
            pv=m['previous']
            if not act or act=='--' or act.upper()=='N/A':
                results[i]=None
            else:
                results[i]={"actual":act,"forecast":fc,"previous":pv}
    if all(v is None for v in results.values()):
        return False
    return results

def post_group_tweet(rows, result_dict):
    valid=[]
    for i,r in enumerate(rows):
        d=result_dict[i]
        if d is not None:
            valid.append((r,d))
    if not valid:
        return

    rep_row= valid[0][0]
    time_str=rep_row['time']
    ccy=rep_row['currency']
    zone_=(rep_row.get('zone','')or'').lower()
    c_name=map_country_name(zone_)
    c_flag=get_country_flag(ccy)

    heading=(
       f"【速報】\n"
       f"{c_flag}{c_name}の経済指標速報です🐯\n"
       f"{time_str} 発表📣\n"
    )
    lines=[]
    for (rw,dat) in valid:
        e_en=rw['event']
        ev_jp=map_indicator_name(e_en)
        ac=dat["actual"]
        fc=dat["forecast"] or ""
        pv=dat["previous"] or ""
        ac_conv=convert_km_to_jp(ac)
        fc_conv=convert_km_to_jp(fc) if fc else ""
        pv_conv=convert_km_to_jp(pv) if pv else ""

        block=f"{ev_jp}\n結果:{ac_conv}"
        if fc_conv and fc_conv!='--':
            block+=f" 予想:{fc_conv}"
        if pv_conv and pv_conv!='--':
            block+=f" 前回:{pv_conv}"
        lines.append(block)

    body="\n\n".join(lines)
    combined_text= heading + body
    combined_text= replace_en_with_jp(combined_text)

    # hashtag
    tags=generate_hashtags(combined_text)
    tweet_text=f"{combined_text}\n{tags}"

    print(f"[TWEET] {tweet_text}")
    # --- Twitter投稿 ---
    try:
        client.create_tweet(text=tweet_text)
        print("[INFO] ツイート完了(まとめ投稿)")
    except Exception as e:
        print(f"[Error] ツイート失敗: {e}")

    # --- LINE push (SAVED_USER_IDS) ---
    if not SAVED_USER_IDS:
        print("[INFO] push先ユーザーがいません")
        return

    line_text= combined_text + "\n(経済指標速報)"
    for uid in SAVED_USER_IDS:
        try:
            line_bot_api.push_message(uid, TextSendMessage(text=line_text))
            print(f"[LINE PUSH] -> {uid}")
        except Exception as e:
            print(f"[Error line push]: {e}")

##################################################
# スケジューリング用ループ
##################################################
def scheduling_loop():
    while True:
        schedule.run_pending()
        time.sleep(20)

def main():
    print("[INFO] investpy + Twitter + LINE Bot start")
    # 起動時 48hスケジュール
    schedule_48h_events()
    # 毎日19:20に再スケジュール登録
    schedule.every().day.at("22:00").do(schedule_48h_events)

    # スケジュールを別スレッドで実行
    t= threading.Thread(target=scheduling_loop, daemon=True)
    t.start()

    # Flaskサーバ起動 (Render想定)
    port= int(os.environ.get("PORT","5000"))
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__=="__main__":
    main()
