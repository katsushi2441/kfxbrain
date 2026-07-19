<?php
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/auth_common.php';
require_once __DIR__ . '/kfxbrain_config.php';
date_default_timezone_set('Asia/Tokyo');

$THIS_FILE = 'kfxbrain.php';
if (isset($_GET['login'])) {
    header('Location: ' . url2ai_auth_login_url('/' . $THIS_FILE));
    exit;
}
if (isset($_GET['logout'])) {
    header('Location: ' . url2ai_auth_logout_url('/' . $THIS_FILE));
    exit;
}

$auth = url2ai_auth_bootstrap();
$is_admin = !empty($auth['is_admin']);
$logged_in = !empty($auth['logged_in']);
if (empty($_SESSION['kfxbrain_csrf'])) {
    $_SESSION['kfxbrain_csrf'] = bin2hex(random_bytes(24));
}
$csrf = $_SESSION['kfxbrain_csrf'];

function kfxb_h($value) {
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function kfxb_api($method, $path, $payload = null, $timeout = 240) {
    $base = rtrim(KFXBRAIN_API_BASE, '/');
    $headers = array('Accept: application/json', 'Content-Type: application/json');
    if (KFXBRAIN_API_TOKEN !== '') {
        $headers[] = 'X-KFXBrain-Token: ' . KFXBRAIN_API_TOKEN;
    }
    $ch = curl_init($base . $path);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 8);
    curl_setopt($ch, CURLOPT_TIMEOUT, $timeout);
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    if ($payload !== null) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));
    }
    $body = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    if ($body === false || $error !== '') {
        return array('status' => 502, 'data' => array('ok' => false, 'detail' => $error ?: 'API connection failed'));
    }
    $decoded = json_decode($body, true);
    if (!is_array($decoded)) {
        $decoded = array('ok' => false, 'detail' => 'API returned invalid JSON');
        $status = 502;
    }
    return array('status' => $status ?: 502, 'data' => $decoded);
}

$endpoint_map = array(
    'technical' => '/v1/analyze/technical',
    'macro' => '/v1/analyze/macro',
    'sentiment' => '/v1/analyze/sentiment',
    'debate' => '/v1/debate/bull-bear',
    'trade' => '/v1/decide/trade',
    'risk' => '/v1/assess/risk',
    'portfolio' => '/v1/decide/portfolio',
    'review' => '/v1/review/trade',
    'full' => '/v1/analyze/full',
    'opportunity-ranking' => '/v1/market/opportunity-ranking',
    'flow-ranking' => '/v1/market/flow-ranking',
    'market-anomaly' => '/v1/market/anomaly',
    'margin-risk' => '/v1/market/margin-risk',
    'pair-signal' => '/v1/signal/pair/{pair}',
    'tradingagents' => '/v1/vendor/tradingagents/run',
    'fingpt-sentiment' => '/v1/vendor/fingpt/sentiment',
    'fingpt-headline' => '/v1/vendor/fingpt/headline',
    'fingpt-relations' => '/v1/vendor/fingpt/relations',
    'fingpt-entities' => '/v1/vendor/fingpt/entities',
    'fingpt-qa' => '/v1/vendor/fingpt/qa',
    'fingpt-forecast' => '/v1/vendor/fingpt/forecast',
    'fingpt-report' => '/v1/vendor/fingpt/report',
    'aihf-news' => '/v1/vendor/ai-hedge-fund/news-sentiment',
    'aihf-portfolio' => '/v1/vendor/ai-hedge-fund/portfolio',
    'aihf-damodaran' => '/v1/vendor/ai-hedge-fund/persona/aswath-damodaran',
    'aihf-graham' => '/v1/vendor/ai-hedge-fund/persona/ben-graham',
    'aihf-ackman' => '/v1/vendor/ai-hedge-fund/persona/bill-ackman',
    'aihf-wood' => '/v1/vendor/ai-hedge-fund/persona/cathie-wood',
    'aihf-munger' => '/v1/vendor/ai-hedge-fund/persona/charlie-munger',
    'aihf-burry' => '/v1/vendor/ai-hedge-fund/persona/michael-burry',
    'aihf-pabrai' => '/v1/vendor/ai-hedge-fund/persona/mohnish-pabrai',
    'aihf-taleb' => '/v1/vendor/ai-hedge-fund/persona/nassim-taleb',
    'aihf-lynch' => '/v1/vendor/ai-hedge-fund/persona/peter-lynch',
    'aihf-fisher' => '/v1/vendor/ai-hedge-fund/persona/phil-fisher',
    'aihf-jhunjhunwala' => '/v1/vendor/ai-hedge-fund/persona/rakesh-jhunjhunwala',
    'aihf-druckenmiller' => '/v1/vendor/ai-hedge-fund/persona/stanley-druckenmiller',
    'aihf-buffett' => '/v1/vendor/ai-hedge-fund/persona/warren-buffett',
);

if (isset($_GET['proxy'])) {
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, max-age=0');
    $proxy = (string)$_GET['proxy'];
    if ($proxy === 'health') {
        $response = kfxb_api('GET', '/health', null, 10);
    } elseif ($proxy === 'meta') {
        $response = kfxb_api('GET', '/v1/meta', null, 10);
    } elseif ($proxy === 'run' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_admin) {
            http_response_code(403);
            echo json_encode(array('ok' => false, 'detail' => '管理者ログインが必要です'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $sent_csrf = isset($_SERVER['HTTP_X_CSRF_TOKEN']) ? (string)$_SERVER['HTTP_X_CSRF_TOKEN'] : '';
        if (!hash_equals($csrf, $sent_csrf)) {
            http_response_code(403);
            echo json_encode(array('ok' => false, 'detail' => 'CSRF検証に失敗しました'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $endpoint = isset($_GET['endpoint']) ? (string)$_GET['endpoint'] : '';
        if (!isset($endpoint_map[$endpoint])) {
            http_response_code(400);
            echo json_encode(array('ok' => false, 'detail' => '未対応のAPIです'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $raw = file_get_contents('php://input');
        if (strlen($raw) > 60000) {
            http_response_code(413);
            echo json_encode(array('ok' => false, 'detail' => '入力が大きすぎます'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $payload = json_decode($raw);
        if (!is_object($payload)) {
            http_response_code(400);
            echo json_encode(array('ok' => false, 'detail' => 'JSONを確認してください'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $api_path = $endpoint_map[$endpoint];
        if ($endpoint === 'pair-signal') {
            $pair = isset($payload->pair) ? strtoupper(str_replace(array('/', '-'), '_', trim((string)$payload->pair))) : '';
            if (!preg_match('/^[A-Z0-9]{2,10}_[A-Z0-9]{2,10}$/', $pair)) {
                http_response_code(422);
                echo json_encode(array('ok' => false, 'detail' => 'pairを確認してください'), JSON_UNESCAPED_UNICODE);
                exit;
            }
            $api_path = str_replace('{pair}', rawurlencode($pair), $api_path);
        }
        $timeout = $endpoint === 'tradingagents' ? 1200 : 300;
        if ($endpoint === 'tradingagents') {
            @set_time_limit(0);
        }
        $response = kfxb_api('POST', $api_path, $payload, $timeout);
    } else {
        $response = array('status' => 404, 'data' => array('ok' => false, 'detail' => 'unknown proxy'));
    }
    http_response_code((int)$response['status']);
    echo json_encode($response['data'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}
?><!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kurage FX Brain | Gemma FX判断API</title>
<meta name="description" content="Gemma 4を使ったFX分析・討論・売買判断・リスク判定APIのテストコンソール。">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23008da3'/%3E%3Ctext x='32' y='39' text-anchor='middle' font-family='sans-serif' font-size='22' font-weight='700' fill='white'%3EKFX%3C/text%3E%3C/svg%3E">
<style>
:root{--bg:#f3f7f6;--surface:#fff;--ink:#102b33;--muted:#60777d;--line:#d9e5e3;--aqua:#008da3;--navy:#153f55;--mint:#dff4ef;--coral:#d75a4a;--code:#f7faf9;--shadow:0 12px 34px rgba(22,66,72,.08)}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:radial-gradient(circle at 84% 4%,#dff5f0 0,transparent 28%),linear-gradient(135deg,#f8faf7 0,#eef6f6 100%);color:var(--ink);font-family:"Noto Sans JP","Avenir Next","Yu Gothic",sans-serif;font-size:14px}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background-image:linear-gradient(rgba(0,141,163,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,141,163,.025) 1px,transparent 1px);background-size:34px 34px}
header{height:58px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.88);backdrop-filter:blur(12px);display:flex;align-items:center;justify-content:space-between;padding:0 24px;position:relative;z-index:2}
.brand{display:flex;align-items:center;gap:11px}.mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(145deg,var(--aqua),var(--navy));display:grid;place-items:center;color:#fff;font-size:13px;font-weight:900}.brand strong{font-size:16px;letter-spacing:.01em}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:.16em;margin-top:1px}.user{display:flex;align-items:center;gap:9px;color:var(--muted);font-size:12px}.user a{color:var(--navy);text-decoration:none;border:1px solid var(--line);background:#fff;padding:6px 10px;border-radius:7px}
.shell{position:relative;z-index:1;max-width:1240px;margin:0 auto;padding:18px 22px 28px}.intro{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:14px}.intro h1{font-size:23px;line-height:1.25;margin:0 0 5px;letter-spacing:-.02em}.intro p{margin:0;color:var(--muted);font-size:12px;line-height:1.6}.health{display:flex;align-items:center;gap:7px;background:#fff;border:1px solid var(--line);padding:7px 11px;border-radius:9px;font-size:11px;font-weight:800;white-space:nowrap}.dot{width:8px;height:8px;border-radius:50%;background:#9aa}.dot.ok{background:#27a56d;box-shadow:0 0 0 4px rgba(39,165,109,.12)}.dot.bad{background:var(--coral)}
.workspace{display:grid;grid-template-columns:minmax(420px,.94fr) minmax(440px,1.06fr);gap:14px;min-height:590px}.panel{background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:13px;box-shadow:var(--shadow);overflow:hidden;min-width:0}.panel-head{height:46px;display:flex;align-items:center;justify-content:space-between;padding:0 15px;border-bottom:1px solid var(--line);background:#fbfdfc}.panel-head strong{font-size:13px}.panel-head span{color:var(--muted);font-size:10px}.panel-body{padding:14px}
.steps{display:flex;align-items:center;gap:6px;margin-bottom:10px;color:var(--muted);font-size:10px}.steps b{display:inline-grid;place-items:center;width:19px;height:19px;border-radius:50%;background:var(--mint);color:var(--aqua);font-size:10px}.steps i{height:1px;flex:1;background:var(--line)}
.function-tabs{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-bottom:8px}.function-tab{border:1px solid var(--line);border-radius:8px;background:#f8fbfa;color:var(--muted);padding:8px 4px;font:800 11px/1.2 inherit;cursor:pointer}.function-tab.active{background:var(--navy);border-color:var(--navy);color:#fff}.function-pane{display:none;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;max-height:210px;overflow:auto;padding:1px 3px 3px 1px}.function-pane.active{display:grid}.function-card{min-height:61px;border:1px solid var(--line);border-radius:9px;background:#fff;padding:8px 9px;text-align:left;color:var(--ink);cursor:pointer}.function-card:hover{border-color:#85c5cd;background:#fbfefd}.function-card.active{border-color:var(--aqua);background:#eef9f7;box-shadow:inset 3px 0 0 var(--aqua)}.function-card strong{display:block;color:var(--navy);font-size:12px;line-height:1.25}.function-card small{display:block;margin-top:4px;color:var(--muted);font-size:10px;line-height:1.4}.selected-function{margin:9px 0;padding:9px 11px;border:1px solid #b8dcd8;border-radius:9px;background:linear-gradient(135deg,#f3fbf9,#f8fbfd)}.selected-function span{color:var(--aqua);font-size:9px;font-weight:900;letter-spacing:.12em}.selected-function strong{display:block;margin-top:2px;font-size:13px}.selected-function p{margin:3px 0 0;color:var(--muted);font-size:11px;line-height:1.45}.input-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px}.input-head strong{font-size:11px}.toolbar{display:flex;gap:6px}.tool{border:1px solid var(--line);background:#fff;color:var(--muted);border-radius:7px;padding:5px 8px;font:700 10px inherit;cursor:pointer}.editor{display:block;width:100%;height:270px;resize:vertical;border:1px solid #cadbd8;border-radius:9px;background:var(--code);padding:12px;color:#1c3840;font:12px/1.55 "IBM Plex Mono","SFMono-Regular",Consolas,monospace;outline:none;tab-size:2}.editor:focus{border-color:var(--aqua);box-shadow:0 0 0 3px rgba(0,141,163,.09)}.run{margin-top:10px;width:100%;border:0;border-radius:9px;background:linear-gradient(135deg,var(--navy),var(--aqua));color:#fff;padding:11px 16px;font:800 13px inherit;cursor:pointer;box-shadow:0 8px 18px rgba(0,111,137,.18)}.run:disabled{opacity:.55;cursor:wait}
.result{height:622px;overflow:auto;margin:0;background:#102d35;color:#d7f0eb;padding:15px;font:12px/1.6 "IBM Plex Mono","SFMono-Regular",Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.result.empty{color:#8fb1b3}.result.error{color:#ffd0c9}.metrics{display:flex;gap:12px;color:var(--muted);font-size:10px}.notice{background:#fff8e8;border:1px solid #ecdbaa;border-radius:10px;padding:12px 14px;color:#705d25;line-height:1.7;font-size:12px}.login-box{max-width:520px;margin:90px auto;background:#fff;border:1px solid var(--line);border-radius:14px;padding:28px;box-shadow:var(--shadow);text-align:center}.login-box h2{margin:0 0 8px;font-size:19px}.login-box p{color:var(--muted);line-height:1.7}.login-box a{display:inline-block;margin-top:8px;background:var(--navy);color:#fff;text-decoration:none;padding:10px 20px;border-radius:8px;font-weight:800}
.quick-input{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:9px 0}.quick-input strong{font-size:11px}.quick-input p{margin:3px 0 0;color:var(--muted);font-size:10px}.tool{padding:7px 10px;font-size:11px}.tool.active{background:var(--mint);border-color:#8bc9c4;color:var(--navy)}.advanced{margin-top:8px;border:1px solid var(--line);border-radius:9px;background:#fafcfb}.advanced summary{padding:9px 11px;color:var(--muted);font-size:11px;font-weight:800;cursor:pointer}.advanced-body{padding:0 10px 10px}.advanced-head{display:flex;justify-content:flex-end;margin-bottom:6px}.advanced .editor{height:220px}.run{padding:12px 16px}
.result-wrap{height:622px;overflow:auto;background:#f7faf9;padding:14px}.result-view{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.result-view.empty{display:block;color:var(--muted);padding:20px 4px;line-height:1.7}.result-view.error{display:block;background:#fff2ef;border:1px solid #efc5bd;border-radius:10px;color:#8b3025;padding:14px}.result-card{border:1px solid var(--line);border-radius:10px;background:#fff;padding:11px;min-width:0}.result-card.wide{grid-column:1/-1}.result-card h3{margin:0 0 7px;color:var(--navy);font-size:12px}.result-card p{margin:0;color:#28434a;font-size:12px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere}.result-card ul{margin:0;padding-left:18px;color:#28434a;font-size:12px;line-height:1.65}.result-card dl{margin:0;display:grid;grid-template-columns:minmax(90px,.45fr) 1fr;gap:6px 9px}.result-card dt{color:var(--muted);font-size:10px}.result-card dd{margin:0;color:#28434a;font-size:12px;overflow-wrap:anywhere}.result-badge{display:inline-block;border-radius:999px;background:var(--mint);color:var(--navy);padding:4px 8px;font-size:11px;font-weight:900}.raw-result{margin-top:10px;border-top:1px solid var(--line);padding-top:9px}.raw-result summary{color:var(--muted);font-size:10px;cursor:pointer}.raw-result .result{height:auto;max-height:300px;margin:8px 0 0;padding:12px;font-size:11px}
footer{position:relative;z-index:1;text-align:center;color:var(--muted);font-size:10px;padding:0 20px 22px}footer a{color:var(--aqua);text-decoration:none}
@media(max-width:900px){header{padding:0 14px}.shell{padding:14px}.workspace{grid-template-columns:1fr}.result{height:390px}.intro{align-items:flex-start;flex-direction:column}}
@media(max-width:520px){.function-tabs{grid-template-columns:repeat(2,1fr)}.function-pane{grid-template-columns:1fr;max-height:230px}.editor{height:290px}.user span{display:none}.intro h1{font-size:20px}.steps span{display:none}}
@media(max-width:900px){.result-wrap{height:auto;min-height:390px}}
@media(max-width:520px){.result-view{grid-template-columns:1fr}.result-card.wide{grid-column:auto}.quick-input{align-items:flex-start;flex-direction:column}}
</style>
</head>
<body>
<header>
  <div class="brand"><div class="mark">KFX</div><div><strong>Kurage FX Brain</strong><small>GEMMA DECISION API</small></div></div>
  <div class="user"><span><?php echo $logged_in ? kfxb_h($auth['session_user']) : 'guest'; ?></span><?php if ($logged_in): ?><a href="?logout=1">ログアウト</a><?php else: ?><a href="?login=1">ログイン</a><?php endif; ?></div>
</header>
<?php if (!$is_admin): ?>
<main class="shell"><div class="login-box"><h2>管理者用APIテスト画面</h2><p>Gemma FX判断APIの実行には、共通管理者ログインが必要です。</p><a href="?login=1">共通ログインへ</a></div></main>
<?php else: ?>
<main class="shell">
  <div class="intro"><div><h1>FX Intelligence Workbench</h1><p>構造化した市場情報をGemma 4へ渡し、分析役ごとのJSON判断を確認します。注文は実行しません。</p></div><div class="health"><i class="dot" id="healthDot"></i><span id="healthText">API確認中</span></div></div>
  <div class="workspace">
    <section class="panel">
      <div class="panel-head"><strong>Request</strong><span id="endpointPath">/v1/analyze/technical</span></div>
      <div class="panel-body">
        <div class="steps"><b>1</b><span>機能を選ぶ</span><i></i><b>2</b><span>入力を確認</span><i></i><b>3</b><span>実行する</span></div>
        <div class="function-tabs" role="tablist" aria-label="機能カテゴリ">
          <button class="function-tab active" data-tab="basic" role="tab" aria-selected="true">基本分析</button>
          <button class="function-tab" data-tab="decision" role="tab" aria-selected="false">売買判断</button>
          <button class="function-tab" data-tab="market" role="tab" aria-selected="false">市場スキャン</button>
          <button class="function-tab" data-tab="oss" role="tab" aria-selected="false">OSSエージェント</button>
        </div>
        <div class="function-pane active" data-pane="basic">
          <button class="function-card active" data-key="technical" data-path="/v1/analyze/technical" data-preset="eur" data-title="テクニカル分析" data-description="価格・RSI・移動平均から相場の方向を分析します。"><strong>テクニカル分析</strong><small>値動きと指標から方向を確認</small></button>
          <button class="function-card" data-key="macro" data-path="/v1/analyze/macro" data-preset="eur" data-title="マクロ分析" data-description="金利差・中央銀行・経済イベントから通貨の方向を分析します。"><strong>マクロ分析</strong><small>金利と経済イベントを評価</small></button>
          <button class="function-card" data-key="sentiment" data-path="/v1/analyze/sentiment" data-preset="eur" data-title="センチメント分析" data-description="ニュースと市場情報から通貨への市場心理を整理します。"><strong>センチメント分析</strong><small>ニュースから市場心理を確認</small></button>
          <button class="function-card" data-key="full" data-path="/v1/analyze/full" data-preset="eur" data-title="総合分析" data-description="テクニカル・マクロ・ニュースをまとめて総合評価します。"><strong>総合分析</strong><small>複数の材料をまとめて評価</small></button>
        </div>
        <div class="function-pane" data-pane="decision">
          <button class="function-card" data-key="debate" data-path="/v1/debate/bull-bear" data-preset="eur" data-title="強気・弱気討論" data-description="上昇派と下落派の根拠を比較します。"><strong>強気・弱気討論</strong><small>上昇・下落の両方の根拠</small></button>
          <button class="function-card" data-key="trade" data-path="/v1/decide/trade" data-preset="eur" data-title="売買判断" data-description="入力した市場情報から売買・待機の判断を返します。"><strong>売買判断</strong><small>買う・売る・待つを判断</small></button>
          <button class="function-card" data-key="risk" data-path="/v1/assess/risk" data-preset="eur" data-title="リスク評価" data-description="値動きやポジションの危険要因を評価します。"><strong>リスク評価</strong><small>損失につながる要因を確認</small></button>
          <button class="function-card" data-key="portfolio" data-path="/v1/decide/portfolio" data-preset="eur" data-title="保有管理" data-description="現在の保有内容を継続・縮小・整理する判断を返します。"><strong>保有管理</strong><small>保有ポジションを見直す</small></button>
          <button class="function-card" data-key="review" data-path="/v1/review/trade" data-preset="eur" data-title="取引レビュー" data-description="過去の取引結果を振り返り、改善点を抽出します。"><strong>取引レビュー</strong><small>取引結果から改善点を抽出</small></button>
        </div>
        <div class="function-pane" data-pane="market">
          <button class="function-card" data-key="opportunity-ranking" data-path="/v1/market/opportunity-ranking" data-preset="market" data-title="市場機会ランキング" data-description="複数通貨ペアを比較し、有望な機会を順位付けします。"><strong>市場機会ランキング</strong><small>有望な通貨ペアを順位付け</small></button>
          <button class="function-card" data-key="flow-ranking" data-path="/v1/market/flow-ranking" data-preset="market" data-title="通貨フローランキング" data-description="資金が向かっている通貨ペアを比較します。"><strong>通貨フローランキング</strong><small>資金の流れを比較</small></button>
          <button class="function-card" data-key="market-anomaly" data-path="/v1/market/anomaly" data-preset="market" data-title="市場異常検出" data-description="急変や通常と異なる市場状態を検出します。"><strong>市場異常検出</strong><small>急変と異常な動きを検出</small></button>
          <button class="function-card" data-key="margin-risk" data-path="/v1/market/margin-risk" data-preset="market" data-title="証拠金リスク" data-description="証拠金維持率とストップアウトの危険度を評価します。"><strong>証拠金リスク</strong><small>ロスカットの危険度を確認</small></button>
          <button class="function-card" data-key="pair-signal" data-path="/v1/signal/pair/{pair}" data-preset="eur" data-title="個別通貨ペアシグナル" data-description="指定した1通貨ペアの現在のシグナルを分析します。"><strong>個別通貨ペアシグナル</strong><small>1通貨ペアを詳しく判断</small></button>
        </div>
        <div class="function-pane" data-pane="oss">
          <button class="function-card" data-key="tradingagents" data-path="/v1/vendor/tradingagents/run" data-preset="tradingagents" data-title="TradingAgents 全体分析" data-description="複数エージェントの調査・討論・リスク判断を一括実行します。"><strong>TradingAgents</strong><small>複数エージェントを一括実行</small></button>
          <button class="function-card" data-key="fingpt-sentiment" data-path="/v1/vendor/fingpt/sentiment" data-preset="eur" data-title="FinGPT 金融センチメント" data-description="金融テキストの感情と方向性を分析します。"><strong>FinGPT センチメント</strong><small>金融テキストの感情分析</small></button>
          <button class="function-card" data-key="fingpt-headline" data-path="/v1/vendor/fingpt/headline" data-preset="eur" data-title="FinGPT 見出し判断" data-description="ニュース見出しが相場に与える方向を判定します。"><strong>FinGPT 見出し判断</strong><small>ニュース見出しの方向判定</small></button>
          <button class="function-card" data-key="fingpt-relations" data-path="/v1/vendor/fingpt/relations" data-preset="eur" data-title="FinGPT 関係抽出" data-description="金融テキストから企業・通貨・要因の関係を抽出します。"><strong>FinGPT 関係抽出</strong><small>対象同士の関係を抽出</small></button>
          <button class="function-card" data-key="fingpt-entities" data-path="/v1/vendor/fingpt/entities" data-preset="eur" data-title="FinGPT 対象抽出" data-description="金融テキストから通貨・企業・指標などを抽出します。"><strong>FinGPT 対象抽出</strong><small>通貨・企業・指標を抽出</small></button>
          <button class="function-card" data-key="fingpt-qa" data-path="/v1/vendor/fingpt/qa" data-preset="eur" data-title="FinGPT 金融Q&A" data-description="入力データに基づいて金融の質問へ回答します。"><strong>FinGPT 金融Q&amp;A</strong><small>金融情報について質問</small></button>
          <button class="function-card" data-key="fingpt-forecast" data-path="/v1/vendor/fingpt/forecast" data-preset="eur" data-title="FinGPT 市場予測" data-description="金融データとニュースから今後の方向を予測します。"><strong>FinGPT 市場予測</strong><small>今後の相場方向を予測</small></button>
          <button class="function-card" data-key="fingpt-report" data-path="/v1/vendor/fingpt/report" data-preset="eur" data-title="FinGPT レポート分析" data-description="金融レポートを要約し重要な判断材料を抽出します。"><strong>FinGPT レポート分析</strong><small>レポートの重要点を抽出</small></button>
          <button class="function-card" data-key="aihf-news" data-path="/v1/vendor/ai-hedge-fund/news-sentiment" data-preset="eur" data-title="AI Hedge Fund ニュース分析" data-description="AI Hedge Fund由来の方法でニュース感情を評価します。"><strong>AIHF ニュース分析</strong><small>ニュースの市場影響を評価</small></button>
          <button class="function-card" data-key="aihf-portfolio" data-path="/v1/vendor/ai-hedge-fund/portfolio" data-preset="eur" data-title="AI Hedge Fund 保有統合" data-description="複数の分析結果をまとめて保有判断を返します。"><strong>AIHF 保有統合</strong><small>複数判断をポートフォリオへ統合</small></button>
          <button class="function-card" data-key="aihf-damodaran" data-path="/v1/vendor/ai-hedge-fund/persona/aswath-damodaran" data-preset="eur" data-title="Damodaran視点" data-description="価値評価を重視するDamodaran型の視点で分析します。"><strong>Damodaran視点</strong><small>価値評価を重視</small></button>
          <button class="function-card" data-key="aihf-graham" data-path="/v1/vendor/ai-hedge-fund/persona/ben-graham" data-preset="eur" data-title="Ben Graham視点" data-description="安全余裕を重視するBen Graham型の視点で分析します。"><strong>Ben Graham視点</strong><small>安全余裕を重視</small></button>
          <button class="function-card" data-key="aihf-ackman" data-path="/v1/vendor/ai-hedge-fund/persona/bill-ackman" data-preset="eur" data-title="Bill Ackman視点" data-description="集中投資と事業品質を重視する視点で分析します。"><strong>Bill Ackman視点</strong><small>集中投資と品質を重視</small></button>
          <button class="function-card" data-key="aihf-wood" data-path="/v1/vendor/ai-hedge-fund/persona/cathie-wood" data-preset="eur" data-title="Cathie Wood視点" data-description="成長テーマと変革性を重視する視点で分析します。"><strong>Cathie Wood視点</strong><small>成長テーマを重視</small></button>
          <button class="function-card" data-key="aihf-munger" data-path="/v1/vendor/ai-hedge-fund/persona/charlie-munger" data-preset="eur" data-title="Charlie Munger視点" data-description="合理性と品質を重視する視点で分析します。"><strong>Charlie Munger視点</strong><small>合理性と品質を重視</small></button>
          <button class="function-card" data-key="aihf-burry" data-path="/v1/vendor/ai-hedge-fund/persona/michael-burry" data-preset="eur" data-title="Michael Burry視点" data-description="逆張りと隠れたリスクを重視する視点で分析します。"><strong>Michael Burry視点</strong><small>逆張りと隠れたリスク</small></button>
          <button class="function-card" data-key="aihf-pabrai" data-path="/v1/vendor/ai-hedge-fund/persona/mohnish-pabrai" data-preset="eur" data-title="Mohnish Pabrai視点" data-description="損失を抑えた非対称な機会を重視します。"><strong>Mohnish Pabrai視点</strong><small>非対称な機会を重視</small></button>
          <button class="function-card" data-key="aihf-taleb" data-path="/v1/vendor/ai-hedge-fund/persona/nassim-taleb" data-preset="eur" data-title="Nassim Taleb視点" data-description="テールリスクと頑健性を重視する視点で分析します。"><strong>Nassim Taleb視点</strong><small>テールリスクを重視</small></button>
          <button class="function-card" data-key="aihf-lynch" data-path="/v1/vendor/ai-hedge-fund/persona/peter-lynch" data-preset="eur" data-title="Peter Lynch視点" data-description="理解可能性と成長余地を重視する視点で分析します。"><strong>Peter Lynch視点</strong><small>理解可能性と成長を重視</small></button>
          <button class="function-card" data-key="aihf-fisher" data-path="/v1/vendor/ai-hedge-fund/persona/phil-fisher" data-preset="eur" data-title="Phil Fisher視点" data-description="定性的な品質と長期成長を重視します。"><strong>Phil Fisher視点</strong><small>品質と長期成長を重視</small></button>
          <button class="function-card" data-key="aihf-jhunjhunwala" data-path="/v1/vendor/ai-hedge-fund/persona/rakesh-jhunjhunwala" data-preset="eur" data-title="Rakesh Jhunjhunwala視点" data-description="成長市場と確信度を重視する視点で分析します。"><strong>Jhunjhunwala視点</strong><small>成長市場と確信度を重視</small></button>
          <button class="function-card" data-key="aihf-druckenmiller" data-path="/v1/vendor/ai-hedge-fund/persona/stanley-druckenmiller" data-preset="eur" data-title="Druckenmiller視点" data-description="マクロ環境と流動性を重視する視点で分析します。"><strong>Druckenmiller視点</strong><small>マクロと流動性を重視</small></button>
          <button class="function-card" data-key="aihf-buffett" data-path="/v1/vendor/ai-hedge-fund/persona/warren-buffett" data-preset="eur" data-title="Warren Buffett視点" data-description="長期価値と事業の強さを重視する視点で分析します。"><strong>Warren Buffett視点</strong><small>長期価値と強さを重視</small></button>
        </div>
        <div class="selected-function"><span>選択中</span><strong id="selectedTitle">テクニカル分析</strong><p id="selectedDescription">価格・RSI・移動平均から相場の方向を分析します。</p></div>
        <div class="quick-input"><div><strong>分析対象</strong><p>通貨ペアを選び、そのまま実行できます。</p></div><div class="toolbar"><button class="tool active" id="eurPreset">EUR/USD</button><button class="tool" id="jpyPreset">USD/JPY</button></div></div>
        <details class="advanced"><summary>詳細な市場データを編集</summary><div class="advanced-body"><div class="advanced-head"><button class="tool" id="formatBtn">入力を整形</button></div><textarea class="editor" id="payload" spellcheck="false"></textarea></div></details>
        <button class="run" id="runBtn">テクニカル分析を実行</button>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><strong>Response</strong><div class="metrics"><span id="statusMetric">READY</span><span id="latencyMetric">- ms</span><span id="modelMetric">gemma4:12b</span></div></div>
      <div class="result-wrap"><div class="result-view empty" id="resultView">「テクニカル分析を実行」を押すと、ここに結論・根拠・リスクが表示されます。</div><details class="raw-result" id="rawResult" hidden><summary>APIの詳細データ</summary><pre class="result" id="result"></pre></details></div>
    </section>
  </div>
  <div class="notice" style="margin-top:14px">出力は分析材料です。実注文、注文数量、損失上限はFX Brainではなく、呼び出し側の固定リスク制御が決定します。</div>
</main>
<?php endif; ?>
<footer><a href="https://kurage.exbridge.jp/kfxai.php">Kurage FX AI Trade</a> / <a href="https://exbridge.jp/">株式会社エクスブリッジ</a></footer>
<?php if ($is_admin): ?>
<script>
const csrf=<?php echo json_encode($csrf, JSON_UNESCAPED_SLASHES); ?>;
const presets={
eur:{pair:"EUR_USD",timeframe:"H1",as_of:new Date().toISOString(),market:{price:1.0862,spread_pips:0.8,atr_pips:14.2,session:"London"},technicals:{return_1h_pct:0.18,return_24h_pct:0.42,rsi_14:57.2,ema_20:1.0841,ema_50:1.0818,macd_histogram:0.00031,support:1.0825,resistance:1.0890},macro:{ecb_policy:"restrictive but easing bias",fed_policy:"data dependent",rate_differential_pct:1.4,next_events:["US CPI in 18 hours"]},news:[{title:"ECB officials signal decisions remain data dependent",sentiment:"neutral"}],position:{side:"flat",account_risk_remaining_pct:0.7},history:[],prior_reports:{},question:"次の4時間で新規エントリーを検討できるか"},
jpy:{pair:"USD_JPY",timeframe:"H1",as_of:new Date().toISOString(),market:{price:156.42,spread_pips:1.0,atr_pips:22.6,session:"Tokyo"},technicals:{return_1h_pct:-0.12,return_24h_pct:0.68,rsi_14:66.5,ema_20:155.94,ema_50:154.88,macd_histogram:0.061,support:155.70,resistance:157.10},macro:{boj_policy:"normalization risk",fed_policy:"data dependent",intervention_risk:"elevated",next_events:["BOJ governor speech in 6 hours"]},news:[{title:"Officials reiterate readiness to respond to excessive FX moves",sentiment:"negative for USD_JPY"}],position:{side:"long",unrealized_pips:18,account_risk_remaining_pct:0.3},history:[],prior_reports:{},question:"保有継続か縮小かを評価"},
market:{timeframe:"H1",as_of:new Date().toISOString(),global_context:{dxy_return_24h_pct:0.35,risk_sentiment:"mixed",next_events:["US CPI in 18 hours"]},account_context:{leverage:25,equity:100000,used_margin:12000,free_margin:88000,margin_level_pct:833,stop_out_level_pct:100},pairs:[{pair:"EUR_USD",market:{price:1.0862,spread_pips:0.8,atr_pips:14.2,return_24h_pct:0.42},technicals:{rsi_14:57.2},macro:{rate_differential_pct:1.4},flows:{futures_net_change_pct:2.1,real_money_flow:"moderate EUR buying"},positioning:{cot_percentile:62}},{pair:"USD_JPY",market:{price:156.42,spread_pips:1.0,atr_pips:22.6,return_24h_pct:0.68},technicals:{rsi_14:66.5},macro:{intervention_risk:"elevated",rate_differential_pct:4.1},flows:{carry_flow:"strong"},positioning:{speculative_net_percentile:87}},{pair:"GBP_USD",market:{price:1.294,spread_pips:1.1,atr_pips:18.4,return_24h_pct:-0.25},technicals:{rsi_14:43.8},macro:{rate_differential_pct:1.1},flows:{futures_net_change_pct:-3.4},positioning:{cot_percentile:38}}],question:"機会、フロー、異常、証拠金リスクを比較"},
tradingagents:{pair:"EUR_USD",trade_date:new Date().toISOString().slice(0,10),debate_rounds:1,risk_rounds:1,output_language:"Japanese"}
};
let endpoint="technical";
const editor=document.querySelector('#payload'),result=document.querySelector('#result'),resultView=document.querySelector('#resultView'),rawResult=document.querySelector('#rawResult'),run=document.querySelector('#runBtn');
function setPreset(value){editor.value=JSON.stringify(value,null,2)}setPreset(presets.eur);
let selectedTitle="テクニカル分析";
function setTarget(name){document.querySelectorAll('.quick-input .tool').forEach(x=>x.classList.remove('active'));if(name==='eur')document.querySelector('#eurPreset').classList.add('active');if(name==='jpy')document.querySelector('#jpyPreset').classList.add('active')}
function resetResult(){resultView.className='result-view empty';resultView.textContent=`「${selectedTitle}を実行」を押すと、ここに結論・根拠・リスクが表示されます。`;rawResult.hidden=true;result.textContent=''}
function selectFunction(card){document.querySelectorAll('.function-card').forEach(x=>x.classList.remove('active'));card.classList.add('active');endpoint=card.dataset.key;selectedTitle=card.dataset.title;document.querySelector('#endpointPath').textContent=card.dataset.path;document.querySelector('#selectedTitle').textContent=selectedTitle;document.querySelector('#selectedDescription').textContent=card.dataset.description;run.textContent=`${selectedTitle}を実行`;setPreset(presets[card.dataset.preset]||presets.eur);setTarget(card.dataset.preset);resetResult()}
document.querySelectorAll('.function-card').forEach(card=>card.addEventListener('click',()=>selectFunction(card)));
document.querySelectorAll('.function-tab').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('.function-tab').forEach(x=>{x.classList.remove('active');x.setAttribute('aria-selected','false')});document.querySelectorAll('.function-pane').forEach(x=>x.classList.remove('active'));tab.classList.add('active');tab.setAttribute('aria-selected','true');const pane=document.querySelector(`[data-pane="${tab.dataset.tab}"]`);pane.classList.add('active');selectFunction(pane.querySelector('.function-card'))}));
document.querySelector('#eurPreset').onclick=()=>{setPreset(presets.eur);setTarget('eur')};document.querySelector('#jpyPreset').onclick=()=>{setPreset(presets.jpy);setTarget('jpy')};
document.querySelector('#formatBtn').onclick=()=>{try{setPreset(JSON.parse(editor.value))}catch(e){showError('JSON: '+e.message)}};
const fieldLabels={action:'判断',signal:'シグナル',verdict:'判定',confidence:'確信度',summary:'要約',market_summary:'市場要約',rationale:'判断理由',reasoning:'判断理由',evidence:'根拠',facts:'確認できた事実',risks:'リスク',risk:'リスク',risk_score:'リスクスコア',hazards:'注意点',safeguards:'対策',missing_data:'不足データ',uncertainties:'不確実性',drivers:'主な要因',opportunities:'機会',recommendation:'推奨',entry_condition:'実行条件',invalidation:'無効条件',technical:'テクニカル',macro:'マクロ',sentiment:'市場心理',debate:'強気・弱気の比較',trade:'売買判断',portfolio:'保有判断',bull_case:'強気材料',bear_case:'弱気材料',balance:'総合方向',direction:'方向',analysis:'分析',output:'分析結果',feature:'分析機能',source:'参照機能',vendor:'OSS情報'};
function labelFor(key){return fieldLabels[key]||String(key).replaceAll('_',' ')}
function displayValue(value){if(value===null||value===undefined)return '情報なし';if(typeof value==='boolean')return value?'はい':'いいえ';if(Array.isArray(value))return value.length?value.map(displayValue).join('\n'):'なし';if(typeof value==='object')return Object.entries(value).map(([k,v])=>`${labelFor(k)}: ${displayValue(v)}`).join('\n');return String(value)}
function renderReadable(data){const payload=data.result??data;resultView.className='result-view';resultView.replaceChildren();if(!payload||typeof payload!=='object'){const card=makeCard('分析結果',payload);card.classList.add('wide');resultView.append(card);return}Object.entries(payload).forEach(([key,value])=>{if(['request_id','endpoint','model','latency_ms','ok'].includes(key))return;resultView.append(makeCard(labelFor(key),value))});if(!resultView.children.length)resultView.append(makeCard('分析結果','結果がありません'))}
function makeCard(title,value){const card=document.createElement('section');card.className='result-card';if(typeof value==='string'&&value.length>120)card.classList.add('wide');const heading=document.createElement('h3');heading.textContent=title;card.append(heading);if(Array.isArray(value)){const list=document.createElement('ul');(value.length?value:['なし']).forEach(item=>{const li=document.createElement('li');li.textContent=displayValue(item);list.append(li)});card.append(list)}else if(value&&typeof value==='object'){const dl=document.createElement('dl');Object.entries(value).forEach(([key,item])=>{const dt=document.createElement('dt');dt.textContent=labelFor(key);const dd=document.createElement('dd');dd.textContent=displayValue(item);dl.append(dt,dd)});card.append(dl)}else{const p=document.createElement('p');const badge=document.createElement('span');badge.className='result-badge';badge.textContent=displayValue(value);p.append(badge);card.append(p)}return card}
function errorText(data){if(Array.isArray(data?.detail))return data.detail.map(item=>`${labelFor(item.loc?.at(-1)||'入力')}: ${item.msg}`).join('\n');return data?.detail||data?.message||'処理を実行できませんでした。'}
function showError(message,data=null){resultView.className='result-view error';resultView.textContent=message;rawResult.hidden=data===null;if(data!==null)result.textContent=JSON.stringify(data,null,2);document.querySelector('#statusMetric').textContent='ERROR'}
run.onclick=async()=>{let payload;try{payload=JSON.parse(editor.value)}catch(e){showError('詳細な市場データの形式が正しくありません。');return}run.disabled=true;run.textContent=`${selectedTitle}を実行中...`;resultView.className='result-view empty';resultView.textContent='Gemmaが市場情報を分析しています。';rawResult.hidden=true;const start=performance.now();try{const response=await fetch(`kfxbrain.php?proxy=run&endpoint=${encodeURIComponent(endpoint)}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)});const data=await response.json();document.querySelector('#statusMetric').textContent=String(response.status);document.querySelector('#latencyMetric').textContent=`${data.latency_ms??Math.round(performance.now()-start)} ms`;document.querySelector('#modelMetric').textContent=data.model||'Gemma';result.textContent=JSON.stringify(data,null,2);rawResult.hidden=false;if(response.ok)renderReadable(data);else showError(errorText(data),data)}catch(e){showError(e.message)}finally{run.disabled=false;run.textContent=`${selectedTitle}を実行`}};
fetch('kfxbrain.php?proxy=health',{cache:'no-store'}).then(r=>r.json()).then(d=>{const ok=Boolean(d.ok);document.querySelector('#healthDot').className='dot '+(ok?'ok':'bad');document.querySelector('#healthText').textContent=ok?`${d.model} READY`:'API OFFLINE'}).catch(()=>{document.querySelector('#healthDot').className='dot bad';document.querySelector('#healthText').textContent='API OFFLINE'});
</script>
<?php endif; ?>
</body>
</html>
