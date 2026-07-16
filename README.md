# Kurage FX Brain

[English README](README.en.md)

FX自動売買ボディから独立して利用できる、Gemma 4による構造化判断API集です。
`vendor/`に固定したTradingAgents、FinGPT、AI Hedge FundのLLM知能機能をFX向けHTTP APIとして公開します。

## Vendored intelligence APIs

- `POST /v1/vendor/tradingagents/run` - `TradingAgentsGraph.propagate()`による分析、討論、売買案、リスク討論、最終判断、記憶
- `POST /v1/vendor/fingpt/{task}` - `sentiment`、`headline`、`relations`、`entities`、`qa`、`forecast`、`report`
- `POST /v1/vendor/ai-hedge-fund/persona/{persona}` - 上流13投資家エージェントの`generate_*_output()`
- `POST /v1/vendor/ai-hedge-fund/news-sentiment` - ニュース感情分類と集約
- `POST /v1/vendor/ai-hedge-fund/portfolio` - 複数分析結果の最終統合
- `POST /v1/vendor/finrobot/forecast` - FinRobotのMarket Forecaster(材料2-4個+翌週の値動き%予測)
- `POST /v1/vendor/finrobot/report/{section}` - FinRobotのアナリスト指示8種(損益計算書/バランスシート/キャッシュフロー/セグメント/リスク/競合/ハイライト/企業概要)
- `POST /v1/vendor/finmem/decide` - FinMemの階層メモリ判断(short/mid/long/reflection記憶+リスク選好の性格切替)
- `POST /v1/vendor/finmem/reflect` - FinMemの反省ループ(結果から教訓を抽出し記憶化)

TradingAgentsは上流グラフをパッチせず実行します。AI Hedge Fundは上流のプロンプト生成関数を直接呼び、LLM輸送層だけをGemma 4へ差し替えます。FinGPTは上流の金融NLP、Forecaster、Financial Report AnalysisタスクをGemma 4用の構造化APIとして実行します。

**正直な注意事項:**

- AI Hedge Fundの13人格は株式ファンダメンタルズ前提のプロンプトをFXに適用したものです。人格として誠実に応答するため、専門外は専門外と答えます(例: Buffett人格は通貨ペアを「circle of competence外」としてneutral・低確信度を返す。実測済み)。マクロ・ニュース系のevidenceを渡した上で、FXシグナルではなく「人格つきセカンドオピニオン」として扱ってください。
- `/v1/vendor/tradingagents/run` は上流のマルチエージェント討論グラフを実データ(yfinance `USDJPY=X`形式)で完走させるため、**応答は秒ではなく分単位**です。レポートの価格水準はキャッシュされた実データと照合済みで、データ接地を確認しています。

## API

- `POST /v1/analyze/technical` - テクニカル分析
- `POST /v1/analyze/macro` - 金利・景気・通貨差の分析
- `POST /v1/analyze/sentiment` - ニュースと市場心理の分析
- `POST /v1/debate/bull-bear` - 強気・弱気論点の対立整理
- `POST /v1/decide/trade` - BUY / SELL / HOLD判断
- `POST /v1/assess/risk` - 許可 / 縮小 / 拒否のリスク判定
- `POST /v1/decide/portfolio` - 保有ポジションの管理判断
- `POST /v1/review/trade` - 取引後レビュー
- `POST /v1/analyze/full` - 全観点を1回で返す総合分析

APIは判断だけを返し、ブローカー認証情報、注文API、注文数量の決定権を持ちません。
Gemmaが失敗した場合にテンプレートや別LLMへフォールバックせず、明示的なエラーを返します。

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
scripts/install_vendor.sh
cp .env.sample .env
# KFXBRAIN_API_TOKENを設定
set -a; source .env; set +a
.venv/bin/uvicorn kfxbrain.api:app --host 0.0.0.0 --port 18326
```

Ollamaには`gemma4:12b-it-qat`が必要です。Gemma 4は思考型モデルのため、API呼び出しでは常に`think: false`を指定します。

`GET /v1/meta`で全タスクとAI Hedge Fundの全persona、`GET /health`でvendor配置状態を確認できます。

## Public test UI

`public/kfxbrain.php`は共通ログイン済み管理者だけがPOSTを実行できるテスト画面です。
ブラウザからはPHPプロキシを経由し、APIトークンを公開しません。

## Safety

- 本サービスは投資助言ではありません。
- 出力は入力された証拠だけを使い、不足情報を明示します。
- 実注文の前には別系統の固定リスク制御と人間の確認が必要です。
