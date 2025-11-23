import streamlit as st
import yfinance as yf
import pandas as pd

# --- 1. 回測函數 (修改後的策略) ---
def run_backtest(df, initial_capital):
    capital = initial_capital
    shares = 0
    trade_log = []
    
    # 初始化欄位
    df['Portfolio_Value'] = initial_capital
    df['Shares_Held'] = 0
    df['Cash'] = initial_capital
    
    # 設定回測起始點 (確保有 MA60 資料)
    start_index = 60 
    
    for i in range(start_index, len(df)):
        date = df.index[i]
        price = df['Close'].iloc[i]
        
        # 取得當日均線
        ma5 = df['MA5'].iloc[i]
        ma10 = df['MA10'].iloc[i]
        ma20 = df['MA20'].iloc[i]
        ma60 = df['MA60'].iloc[i]
        
        # 取得前一日收盤價與均線 (用於判斷是否「跌破」)
        prev_close = df['Close'].iloc[i-1]
        prev_ma5 = df['MA5'].iloc[i-1]
        prev_ma10 = df['MA10'].iloc[i-1]
        prev_ma20 = df['MA20'].iloc[i-1]
        prev_ma60 = df['MA60'].iloc[i-1]

        # --- 策略邏輯區 ---
        # 定義「跌破」：昨天收盤價 > 昨天均線  AND  今天收盤價 < 今天均線
        # 注意：為了避免大跌時同時觸發買賣，我們使用 if-elif 結構設定優先權
        # 優先權：停損 (MA60 > MA20) -> 買進 (MA10 > MA5)
        
        action_taken = False # 標記當天是否已執行動作

        # 1. 跌破季線 (MA60) -> 全部賣出 (優先級最高，視為趨勢反轉/大逃殺)
        if shares > 0 and (prev_close > prev_ma60) and (price < ma60):
            amount_to_sell = shares
            cash_gain = amount_to_sell * price
            capital += cash_gain
            trade_log.append({
                'Date': date, 'Action': 'SELL ALL (Break MA60)', 'Price': price, 
                'Shares': -amount_to_sell, 'Value': cash_gain, 'Capital_After': capital
            })
            shares = 0
            action_taken = True

        # 2. 跌破月線 (MA20) -> 賣出當時股份的 50% (減碼)
        elif shares > 0 and (prev_close > prev_ma20) and (price < ma20):
            amount_to_sell = int(shares * 0.5 / 1000) * 1000 # 轉為整張
            if amount_to_sell > 0:
                cash_gain = amount_to_sell * price
                capital += cash_gain
                shares -= amount_to_sell
                trade_log.append({
                    'Date': date, 'Action': 'SELL 50% (Break MA20)', 'Price': price, 
                    'Shares': -amount_to_sell, 'Value': cash_gain, 'Capital_After': capital
                })
            action_taken = True

        # 3. 跌破 10日線 -> 買入剩餘資金的 10%
        elif (prev_close > prev_ma10) and (price < ma10):
            invest_amount = capital * 0.10
            shares_to_buy = int(invest_amount / price / 1000) * 1000
            
            if shares_to_buy > 0 and capital >= shares_to_buy * price:
                cost = shares_to_buy * price
                capital -= cost
                shares += shares_to_buy
                trade_log.append({
                    'Date': date, 'Action': 'BUY 10% (Break MA10)', 'Price': price, 
                    'Shares': shares_to_buy, 'Value': cost, 'Capital_After': capital
                })
            action_taken = True

        # 4. 跌破 5日線 -> 買入當下剩餘資金的 5%
        elif (prev_close > prev_ma5) and (price < ma5):
            invest_amount = capital * 0.05
            shares_to_buy = int(invest_amount / price / 1000) * 1000
            
            if shares_to_buy > 0 and capital >= shares_to_buy * price:
                cost = shares_to_buy * price
                capital -= cost
                shares += shares_to_buy
                trade_log.append({
                    'Date': date, 'Action': 'BUY 5% (Break MA5)', 'Price': price, 
                    'Shares': shares_to_buy, 'Value': cost, 'Capital_After': capital
                })
            action_taken = True
        
        # --- 紀錄每日狀態 ---
        df.loc[date, 'Portfolio_Value'] = capital + (shares * price)
        df.loc[date, 'Shares_Held'] = shares
        df.loc[date, 'Cash'] = capital

    # 回測結束結算
    if shares > 0:
        final_price = df['Close'].iloc[-1]
        final_value = shares * final_price
        capital += final_value
        trade_log.append({
            'Date': df.index[-1], 'Action': 'Final Liquidation', 'Price': final_price, 
            'Shares': -shares, 'Value': final_value, 'Capital_After': capital
        })
        shares = 0

    return capital, trade_log, df

# --- 2. 網頁介面與資料下載 ---

st.title("股票回測系統 (逆勢買進策略)")

# 設定輸入選項
col1, col2 = st.columns(2)
with col1:
    ticker = st.text_input("輸入股票代號", "2330.TW")
with col2:
    initial_capital = st.number_input("初始本金", value=1000000)

start_date = st.date_input("開始日期", pd.to_datetime("2020-01-01"))
end_date = st.date_input("結束日期", pd.to_datetime("today"))

st.caption("策略說明：跌破MA5買5%資金 / 跌破MA10買10%資金 / 跌破MA20賣50%持股 / 跌破MA60清倉")

if ticker:
    try:
        # 下載資料
        df = yf.download(ticker, start=start_date, end=end_date)
        
        if df.empty:
            st.error("找不到資料，請檢查股票代號。")
        else:
            # 處理格式
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # 計算所有需要的均線
            df['MA5'] = df['Close'].rolling(window=5).mean()
            df['MA10'] = df['Close'].rolling(window=10).mean()
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA60'] = df['Close'].rolling(window=60).mean()
            
            # 畫出股價與均線 (輔助觀察)
            st.subheader(f"{ticker} 股價與均線")
            chart_data = df[['Close', 'MA20', 'MA60']]
            st.line_chart(chart_data)
            
            # 移除 NaN 並執行回測
            df_clean = df.dropna()

            st.divider()
            st.subheader("回測結果")
            
            final_capital, log, result_df = run_backtest(df_clean, initial_capital)

            # 顯示結果
            roi = ((final_capital - initial_capital) / initial_capital) * 100
            
            col1, col2 = st.columns(2)
            col1.metric("最終總資產", f"${int(final_capital):,}")
            col2.metric("投資報酬率 (ROI)", f"{roi:.2f}%", delta=f"{roi:.2f}%")

            st.line_chart(result_df['Portfolio_Value'])

            if log:
                with st.expander("查看詳細交易紀錄"):
                    st.dataframe(pd.DataFrame(log))
            else:
                st.info("這段期間沒有觸發任何交易。")

    except Exception as e:
        st.error(f"發生錯誤: {e}")
