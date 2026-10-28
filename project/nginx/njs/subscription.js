// /etc/nginx/njs/subscription.js
// njs module for subscription headers and short import links.

var fs = require("fs");

var CACHE_MS = 5000;
var cache = { ts: 0, data: [] };
var HAPP_LINKS_FILE = "/var/lib/vless-sub/happ-links.json";
var happCache = { ts: 0, data: {} };

var SERG_SUPPORT_CHAT_URL = "https://t.me/serg_hexen";

function loadClients() {
    var now = Date.now();
    if (cache.data && (now - cache.ts) < CACHE_MS) {
        return cache.data;
    }
    try {
        var txt = fs.readFileSync("/var/lib/vless-sub/clients.json");
        cache.data = JSON.parse(txt);
        cache.ts = now;
    } catch (e) {
        cache.data = [];
        cache.ts = now;
    }
    return cache.data;
}

function tokenFromURI(uri) {
    var m = uri.match(/^\/sub\/([A-Za-z0-9._-]+)$/);
    return m ? m[1] : null;
}

function importPartsFromURI(uri) {
    var m = uri.match(/^\/i\/([A-Za-z0-9._-]+)(?:\/(ios|android|happ|mac|sub))?$/);
    if (!m) {
        return null;
    }
    return { key: m[1], platform: (m[2] || "menu") };
}

function findClientByKey(key) {
    var clients = loadClients();
    for (var i = 0; i < clients.length; i++) {
        if (clients[i].token === key || clients[i].name === key) {
            return clients[i];
        }
    }
    return null;
}

function readSubBodyByKey(key) {
    try {
        return fs.readFileSync("/var/www/sub/" + key).toString().trim();
    } catch (e1) {
        var found = findClientByKey(key);
        if (found && found.token) {
            try {
                return fs.readFileSync("/var/www/sub/" + found.token).toString().trim();
            } catch (e2) {
                return "";
            }
        }
        return "";
    }
}

function isLikelyBase64(s) {
    if (!s || s.length < 16) {
        return false;
    }
    return /^[A-Za-z0-9+/=\r\n]+$/.test(s);
}

function decodeBase64ToUtf8(s) {
    try {
        return Buffer.from(s, "base64").toString("utf-8");
    } catch (e) {
        return "";
    }
}

function looksLikeLinkList(s) {
    return !!(s && (s.indexOf("vless://") >= 0 || s.indexOf("vmess://") >= 0 || s.indexOf("trojan://") >= 0));
}

function sub_response(r) {
    var key = tokenFromURI(r.uri);
    if (!key) {
        r.return(404, "Not found");
        return;
    }

    var body = readSubBodyByKey(key);
    if (!body) {
        r.return(404, "Not found");
        return;
    }

    var ua = ((r.headersIn["User-Agent"] || r.headersIn["user-agent"] || "") + "").toLowerCase();
    var isV2RayTun = ua.indexOf("v2raytun") >= 0 || ua.indexOf("v2ray") >= 0;
    if (isV2RayTun && isLikelyBase64(body)) {
        var decoded = decodeBase64ToUtf8(body);
        if (looksLikeLinkList(decoded)) {
            body = decoded;
        }
    }

    r.headersOut["Content-Type"] = "text/plain; charset=utf-8";
    r.return(200, body);
}

function loadHappLinks() {
    var now = Date.now();
    if (happCache.data && (now - happCache.ts) < CACHE_MS) {
        return happCache.data;
    }
    try {
        var txt = fs.readFileSync(HAPP_LINKS_FILE);
        happCache.data = JSON.parse(txt);
        happCache.ts = now;
    } catch (e) {
        happCache.data = {};
        happCache.ts = now;
    }
    return happCache.data;
}

function add_headers(r) {
    var key = tokenFromURI(r.uri);
    if (!key) {
        return;
    }

    var found = findClientByKey(key);
    var expire = 0;
    if (found) {
        expire = Number(found.expire) || 0;
    }

    r.headersOut["Profile-Update-Interval"] = "24";
    r.headersOut["Profile-Title"] = "HexenKVN";
    r.headersOut["Support-Url"] = "https://serghexen.ru:8443/support";
    r.headersOut["Profile-Web-Page-Url"] = "https://serghexen.ru:8443/support";

    r.headersOut["Subscription-Userinfo"] =
        "upload=0; download=0; total=0; expire=" + expire;
}

function renderMenuPage(r, subUrl, host, alias) {
    var deepLinkV2Android = "v2raytun://import/" + subUrl;
    var deepLinkV2Ios = "v2raytun://import/" + subUrl;
    var deepLinkV2Mac = "v2raytun://import/" + subUrl;
    var happLaunchUrl = "https://" + host + "/i/" + alias + "/happ";

    var v2StoreAndroid = "https://play.google.com/store/apps/details?id=com.v2raytun.android&hl=ru";
    var happStoreAndroid = "https://play.google.com/store/apps/details?id=com.happproxy&pli=1";
    var v2StoreIos = "https://apps.apple.com/ru/app/v2raytun/id6476628951";
    var happStoreIos = "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973";
    var v2StoreMac = "https://apps.apple.com/ru/app/v2raytun/id6476628951";
    var happStoreMac = "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973";
    var v2SetupWindows = "https://storage.v2raytun.com/v2RayTun_Setup.exe";
    var happSetupWindows = "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe";

    var html = "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        + "<title>HexenKVN Setup</title>"
        + "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\"><link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>"
        + "<link href=\"https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Unbounded:wght@600;700&display=swap\" rel=\"stylesheet\">"
        + "<style>"
        + ":root{--bg:#070c16;--card:#0f1728;--line:#24324a;--txt:#e8f0ff;--muted:#9ab0d5;--accent:#2dd4bf;--accent2:#3b82f6;--ink:#e8f0ff}"
        + "*{box-sizing:border-box}body{margin:0;font-family:'Manrope',sans-serif;color:var(--txt);background:radial-gradient(1200px 520px at 8% -10%,#1b2c4a 0%,#0a1120 48%,#070c16 100%)}"
        + ".wrap{max-width:940px;margin:0 auto;padding:18px}.card{background:linear-gradient(180deg,rgba(15,23,40,.98),rgba(10,17,31,.98));border:1px solid var(--line);border-radius:22px;padding:18px;box-shadow:0 22px 60px rgba(0,0,0,.45)}"
        + ".brand{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:6px}.logo{font-family:'Unbounded',sans-serif;font-size:24px;letter-spacing:.4px;color:#f6fbff}.chip{display:inline-flex;align-items:center;justify-content:center;min-height:26px;padding:0 9px;border-radius:999px;font-size:9px;line-height:1;letter-spacing:.28px;text-transform:uppercase;font-weight:800;color:#d8fffb;background:linear-gradient(90deg,rgba(45,212,191,.18),rgba(59,130,246,.18));border:1px solid rgba(104,219,255,.45);white-space:nowrap}"
        + ".muted{color:var(--muted)}.tabs{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.tab{padding:10px 14px;border-radius:12px;border:1px solid var(--line);background:#121d32;color:var(--ink);cursor:pointer;font-weight:700}"
        + ".tab.active{color:#071620;border-color:transparent;background:linear-gradient(90deg,var(--accent),var(--accent2));box-shadow:0 10px 24px rgba(43,183,255,.24)}"
        + ".apps{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0}.app{padding:12px;border-radius:14px;border:1px solid var(--line);background:#121d32;cursor:pointer;text-align:left}.app.active{border-color:#7dd9ff;box-shadow:inset 0 0 0 1px rgba(125,217,255,.55),0 8px 24px rgba(59,130,246,.16)}"
        + ".app-line{display:flex;align-items:center;gap:10px}.ico{width:36px;height:36px;display:inline-flex;align-items:center;justify-content:center;border-radius:10px;background:#1a2740;border:1px solid #32527f;font-weight:800;color:#d7e9ff;font-size:14px}.name{font-weight:800;color:#eef6ff}"
        + ".btns{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.btn{display:inline-block;border:1px solid transparent;cursor:pointer;text-decoration:none;padding:12px 15px;border-radius:12px;font-weight:800;font-size:14px}"
        + ".btn.main{color:#071620;background:linear-gradient(90deg,var(--accent),var(--accent2));box-shadow:0 10px 28px rgba(39,177,244,.3)}.btn.alt{color:#e8f0ff;background:#121d32;border-color:var(--line)}"
        + ".hint{margin:6px 0 10px;padding:9px 11px;border-radius:10px;background:#101f36;border:1px solid #2c4b73;color:#b7d6ff;font-weight:600}"
        + ".guide{margin-top:12px;padding:13px 14px;border:1px solid var(--line);border-radius:14px;background:#0f1a2e}.guide h3{margin:0 0 8px;font-family:'Unbounded',sans-serif;font-size:14px;letter-spacing:.3px;color:#f2f7ff}.guide ol{margin:0 0 0 18px;padding:0}.guide li{margin:6px 0;color:var(--muted)}"
        + "@media (max-width:640px){.apps{grid-template-columns:1fr}.btn{width:100%;text-align:center}}"
        + "</style></head><body><div class=\"wrap\"><div class=\"card\">"
        + "<div class=\"brand\"><div class=\"logo\">HexenKVN</div><div class=\"chip\">Быстрое подключение</div></div>"
        + "<p class=\"muted\" style=\"margin:0\">Выберите платформу и приложение.</p>"
        + "<div class=\"tabs\"><button id=\"tab-android\" class=\"tab\" type=\"button\">Android</button><button id=\"tab-ios\" class=\"tab\" type=\"button\">iOS</button><button id=\"tab-macos\" class=\"tab\" type=\"button\">macOS</button><button id=\"tab-windows\" class=\"tab\" type=\"button\">Windows</button></div>"
        + "<div id=\"apps\" class=\"apps\"></div>"
        + "<div class=\"btns\"><a id=\"install\" class=\"btn alt\" href=\"#\">Установить приложение</a><button id=\"import\" class=\"btn main\" type=\"button\">Добавить подписку</button><a class=\"btn alt\" href=\"" + SERG_SUPPORT_CHAT_URL + "\" target=\"_blank\" rel=\"noopener\">Поддержка</a></div>"
        + "<div class=\"hint\" id=\"hint\"></div>"
        + "<div class=\"guide\"><h3>Как подключиться</h3><ol>"
        + "<li>Выберите вашу платформу (Android, iOS, macOS, Windows).</li>"
        + "<li>Установите рекомендованное приложение.</li>"
        + "<li>Нажмите «Добавить подписку» и подтвердите открытие приложения.</li>"
        + "<li>В приложении: откройте список профилей, обновите подписку и включите профиль VPN.</li>"
        + "<li>Готово. Проверка: откройте любой сайт без VPN-блокировок. Если есть проблема, нажмите «Поддержка».</li>"
        + "</ol></div>"
        + "</div></div>"
        + "<script>"
        + "(function(){"
        + "var cfg={subUrl:" + JSON.stringify(subUrl) + ",apps:{android:[{id:\"v2\",name:\"v2RayTun\",icon:\"V2\",store:" + JSON.stringify(v2StoreAndroid) + ",mode:\"deeplink\",link:" + JSON.stringify(deepLinkV2Android) + "},{id:\"happ\",name:\"Happ\",icon:\"H\",store:" + JSON.stringify(happStoreAndroid) + ",mode:\"deeplink\",link:" + JSON.stringify(happLaunchUrl) + "}],ios:[{id:\"v2\",name:\"v2RayTun\",icon:\"V2\",store:" + JSON.stringify(v2StoreIos) + ",mode:\"deeplink\",link:" + JSON.stringify(deepLinkV2Ios) + "},{id:\"happ\",name:\"Happ\",icon:\"H\",store:" + JSON.stringify(happStoreIos) + ",mode:\"deeplink\",link:" + JSON.stringify(happLaunchUrl) + "}],macos:[{id:\"v2\",name:\"v2RayTun\",icon:\"V2\",store:" + JSON.stringify(v2StoreMac) + ",mode:\"deeplink\",link:" + JSON.stringify(deepLinkV2Mac) + "},{id:\"happ\",name:\"Happ\",icon:\"H\",store:" + JSON.stringify(happStoreMac) + ",mode:\"deeplink\",link:" + JSON.stringify(happLaunchUrl) + "}],windows:[{id:\"v2\",name:\"v2RayTun\",icon:\"V2\",store:" + JSON.stringify(v2SetupWindows) + ",mode:\"open\",link:" + JSON.stringify(subUrl) + "},{id:\"happ\",name:\"Happ\",icon:\"H\",store:" + JSON.stringify(happSetupWindows) + ",mode:\"deeplink\",link:" + JSON.stringify(happLaunchUrl) + "}]}};"
        + "var state={platform:\"android\",app:\"v2\"};"
        + "if(/iPhone|iPad|iPod/i.test(navigator.userAgent)){state.platform=\"ios\";state.app=\"v2\";}"
        + "else if(/Macintosh|Mac OS X/i.test(navigator.userAgent)){state.platform=\"macos\";state.app=\"v2\";}"
        + "else if(/Windows NT/i.test(navigator.userAgent)){state.platform=\"windows\";state.app=\"v2\";}"
        + "var q=new URLSearchParams(location.search);var qp=q.get(\"platform\");if(qp===\"android\"||qp===\"ios\"||qp===\"macos\"||qp===\"windows\"){state.platform=qp;state.app=\"v2\";}"
        + "var appsEl=document.getElementById(\"apps\"),installEl=document.getElementById(\"install\"),importEl=document.getElementById(\"import\"),hintEl=document.getElementById(\"hint\");"
        + "var tabA=document.getElementById(\"tab-android\"),tabI=document.getElementById(\"tab-ios\"),tabM=document.getElementById(\"tab-macos\"),tabW=document.getElementById(\"tab-windows\");"
        + "function currentApps(){return cfg.apps[state.platform];}"
        + "function selected(){var list=currentApps();for(var i=0;i<list.length;i++){if(list[i].id===state.app){return list[i];}}return list[0];}"
        + "function renderApps(){var list=currentApps();if(!list.length){appsEl.innerHTML=\"\";return;}var found=false;for(var i=0;i<list.length;i++){if(list[i].id===state.app){found=true;}}if(!found){state.app=list[0].id;}var html=\"\";for(var j=0;j<list.length;j++){var a=list[j];var cls=\"app\"+(a.id===state.app?\" active\":\"\");html+=\"<button type=\\\"button\\\" class=\\\"\"+cls+\"\\\" data-app=\\\"\"+a.id+\"\\\"><div class=\\\"app-line\\\"><span class=\\\"ico\\\">\"+a.icon+\"</span><span class=\\\"name\\\">\"+a.name+\"</span></div></button>\";}appsEl.innerHTML=html;var nodes=appsEl.querySelectorAll(\"button[data-app]\");for(var k=0;k<nodes.length;k++){nodes[k].addEventListener(\"click\",function(){state.app=this.getAttribute(\"data-app\");refresh();});}}"
        + "function hintText(){if(state.platform===\"ios\"){return \"Для iOS по умолчанию выбран v2RayTun. После импорта откройте приложение и включите профиль.\";}if(state.platform===\"macos\"){return \"Для macOS доступны v2RayTun и Happ. Установите приложение и нажмите «Добавить подписку».\";}if(state.platform===\"windows\"){return \"Для Windows доступны v2RayTun и Happ. Установите приложение и нажмите «Добавить подписку».\";}return \"Для Android по умолчанию выбран v2RayTun. После импорта обновите подписку и включите профиль.\";}"
        + "function refresh(){tabA.classList.toggle(\"active\",state.platform===\"android\");tabI.classList.toggle(\"active\",state.platform===\"ios\");tabM.classList.toggle(\"active\",state.platform===\"macos\");tabW.classList.toggle(\"active\",state.platform===\"windows\");renderApps();var a=selected();installEl.href=a.store;importEl.textContent=\"Добавить подписку\";hintEl.textContent=hintText();}"
        + "tabA.addEventListener(\"click\",function(){state.platform=\"android\";state.app=\"v2\";refresh();});tabI.addEventListener(\"click\",function(){state.platform=\"ios\";state.app=\"v2\";refresh();});tabM.addEventListener(\"click\",function(){state.platform=\"macos\";state.app=\"v2\";refresh();});tabW.addEventListener(\"click\",function(){state.platform=\"windows\";state.app=\"v2\";refresh();});"
        + "importEl.addEventListener(\"click\",function(){var a=selected();if(a.mode===\"deeplink\"){window.location.href=a.link;return;}if(a.mode===\"open\"){window.location.href=a.link;}});"
        + "refresh();"
        + "})();"
        + "</script></body></html>";

    r.headersOut["Content-Type"] = "text/html; charset=utf-8";
    r.return(200, html);
}

function renderIosPage(r, subUrl, host, alias) {
    var deepLinkV2 = "v2raytun://import/" + subUrl;
    var deepLinkHapp = "https://" + host + "/i/" + alias + "/happ";
    var v2Store = "https://apps.apple.com/ru/app/v2raytun/id6476628951";
    var happStore = "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973";

    var html = "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        + "<title>HexenKVN - iOS</title>"
        + "<style>"
        + ":root{--bg:#0b1220;--bg2:#111b31;--card:#121c30;--line:#25324e;--text:#e9eefc;--muted:#9fb1d3;--acc:#2dd4bf;--acc2:#38bdf8}"
        + "*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,sans-serif;background:radial-gradient(1200px 700px at 10% -10%,#1e293b 0%,#0b1220 45%,#090f1b 100%);color:var(--text)}"
        + ".wrap{max-width:760px;margin:0 auto;padding:20px}.panel{background:linear-gradient(180deg,rgba(18,28,48,.92),rgba(12,19,33,.92));border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 20px 60px rgba(0,0,0,.35)}"
        + "h1{margin:0 0 6px;font-size:26px}p{margin:8px 0;color:var(--muted)}.apps{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0 8px}.app{border:1px solid var(--line);border-radius:12px;padding:12px;background:#0f1729;cursor:pointer}"
        + ".app.active{border-color:var(--acc2);box-shadow:inset 0 0 0 1px rgba(56,189,248,.45)}.name{font-weight:700}.btns{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.btn{display:inline-block;text-decoration:none;color:#07131f;background:linear-gradient(90deg,var(--acc),var(--acc2));padding:12px 14px;border-radius:10px;font-weight:700}"
        + ".btn.alt{background:#18243b;color:var(--text);border:1px solid var(--line)}.meta{font-size:13px;word-break:break-all;background:#0a1222;border:1px solid var(--line);border-radius:10px;padding:10px}"
        + "@media (max-width:560px){.apps{grid-template-columns:1fr}}"
        + "</style></head><body><div class=\"wrap\"><div class=\"panel\">"
        + "<h1>HexenKVN</h1><p>iOS setup and subscription import.</p>"
        + "<div class=\"apps\">"
        + "<button class=\"app active\" id=\"v2\" type=\"button\"><div class=\"name\">v2RayTun</div><p>Recommended for iOS</p></button>"
        + "<button class=\"app\" id=\"happ\" type=\"button\"><div class=\"name\">Happ</div><p>Alternative client for iOS</p></button>"
        + "</div>"
        + "<div class=\"btns\">"
        + "<a class=\"btn alt\" id=\"install\" href=\"" + v2Store + "\">Install app</a>"
        + "<a class=\"btn\" id=\"import\" href=\"" + deepLinkV2 + "\">Add subscription</a>"
        + "</div>"
        + "<p>Manual URL (copy if app did not open):</p>"
        + "<div class=\"meta\">" + subUrl + "</div>"
        + "</div></div>"
        + "<script>"
        + "(function(){var selected=\"v2\";var apps={v2:{store:" + JSON.stringify(v2Store) + ",link:" + JSON.stringify(deepLinkV2) + "},happ:{store:" + JSON.stringify(happStore) + ",link:" + JSON.stringify(deepLinkHapp) + "}};"
        + "var v2=document.getElementById(\"v2\"),h=document.getElementById(\"happ\"),i=document.getElementById(\"import\"),s=document.getElementById(\"install\");"
        + "function apply(k){selected=k;v2.classList.toggle(\"active\",k===\"v2\");h.classList.toggle(\"active\",k===\"happ\");i.href=apps[k].link;s.href=apps[k].store;}"
        + "v2.addEventListener(\"click\",function(){apply(\"v2\")});h.addEventListener(\"click\",function(){apply(\"happ\")});"
        + "setTimeout(function(){window.location.href=apps[selected].link;},140);})();"
        + "</script></body></html>";

    r.headersOut["Content-Type"] = "text/html; charset=utf-8";
    r.return(200, html);
}

function happ_redirect(r, found, subUrl) {
    var links = loadHappLinks();
    var link = null;

    if (found) {
        if (found.name && links[found.name]) {
            link = links[found.name];
        } else if (found.token && links[found.token]) {
            link = links[found.token];
        }
    }

    if (link) {
        r.return(302, link);
        return;
    }

    var fallback = "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head><body style=\"font-family:system-ui;padding:16px\">"
        + "<p>Открываем импорт Happ.</p>"
        + "<form id=\"happgen\" method=\"POST\" action=\"https://crypto.happ.su/\"><input type=\"hidden\" name=\"url\" value=\"" + subUrl + "\"><button type=\"submit\">Открыть генератор Happ</button></form>"
        + "<script>(function(){setTimeout(function(){var f=document.getElementById('happgen');if(f){f.submit();}},120);})();</script>"
        + "</body></html>";
    r.headersOut["Content-Type"] = "text/html; charset=utf-8";
    r.return(200, fallback);
}

function renderAndroidPage(r, subUrl, host, alias) {
    var deepLinkV2 = "v2raytun://import/" + subUrl;
    var deepLinkHapp = "https://" + host + "/i/" + alias + "/happ";
    var v2Store = "https://play.google.com/store/apps/details?id=com.v2raytun.android&hl=ru";
    var happStore = "https://play.google.com/store/apps/details?id=com.happproxy&pli=1";

    var html = "<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        + "<title>HexenKVN - Android</title>"
        + "<style>"
        + ":root{--bg:#0b1220;--bg2:#111b31;--card:#121c30;--line:#25324e;--text:#e9eefc;--muted:#9fb1d3;--acc:#2dd4bf;--acc2:#38bdf8}"
        + "*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,sans-serif;background:radial-gradient(1200px 700px at 10% -10%,#1e293b 0%,#0b1220 45%,#090f1b 100%);color:var(--text)}"
        + ".wrap{max-width:760px;margin:0 auto;padding:20px}.panel{background:linear-gradient(180deg,rgba(18,28,48,.92),rgba(12,19,33,.92));border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 20px 60px rgba(0,0,0,.35)}"
        + "h1{margin:0 0 6px;font-size:26px}p{margin:8px 0;color:var(--muted)}.apps{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0 8px}.app{border:1px solid var(--line);border-radius:12px;padding:12px;background:#0f1729;cursor:pointer}"
        + ".app.active{border-color:var(--acc2);box-shadow:inset 0 0 0 1px rgba(56,189,248,.45)}.name{font-weight:700}.btns{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.btn{display:inline-block;text-decoration:none;color:#07131f;background:linear-gradient(90deg,var(--acc),var(--acc2));padding:12px 14px;border-radius:10px;font-weight:700}"
        + ".btn.alt{background:#18243b;color:var(--text);border:1px solid var(--line)}.meta{font-size:13px;word-break:break-all;background:#0a1222;border:1px solid var(--line);border-radius:10px;padding:10px}"
        + "@media (max-width:560px){.apps{grid-template-columns:1fr}}"
        + "</style></head><body><div class=\"wrap\"><div class=\"panel\">"
        + "<h1>HexenKVN</h1><p>Android setup and subscription import.</p>"
        + "<div class=\"apps\">"
        + "<button class=\"app active\" id=\"v2\" type=\"button\"><div class=\"name\">v2RayTun</div><p>Recommended for this config format</p></button>"
        + "<button class=\"app\" id=\"happ\" type=\"button\"><div class=\"name\">Happ</div><p>Alternative client for Android</p></button>"
        + "</div>"
        + "<div class=\"btns\">"
        + "<a class=\"btn alt\" id=\"install\" href=\"" + v2Store + "\">Install app</a>"
        + "<a class=\"btn\" id=\"import\" href=\"" + deepLinkV2 + "\">Add subscription</a>"
        + "</div>"
        + "<p>Manual URL (copy if app did not open):</p>"
        + "<div class=\"meta\">" + subUrl + "</div>"
        + "</div></div>"
        + "<script>"
        + "(function(){var selected=\"v2\";var apps={v2:{store:" + JSON.stringify(v2Store) + ",link:" + JSON.stringify(deepLinkV2) + "},happ:{store:" + JSON.stringify(happStore) + ",link:" + JSON.stringify(deepLinkHapp) + "}};"
        + "var v2=document.getElementById(\"v2\"),h=document.getElementById(\"happ\"),i=document.getElementById(\"import\"),s=document.getElementById(\"install\");"
        + "function apply(k){selected=k;v2.classList.toggle(\"active\",k===\"v2\");h.classList.toggle(\"active\",k===\"happ\");i.href=apps[k].link;s.href=apps[k].store;}"
        + "v2.addEventListener(\"click\",function(){apply(\"v2\")});h.addEventListener(\"click\",function(){apply(\"happ\")});"
        + "setTimeout(function(){window.location.href=apps[selected].link;},140);})();"
        + "</script></body></html>";

    r.headersOut["Content-Type"] = "text/html; charset=utf-8";
    r.return(200, html);
}

function import_redirect(r) {
    var parts = importPartsFromURI(r.uri);
    if (!parts) {
        r.return(404, "Not found");
        return;
    }

    var found = findClientByKey(parts.key);
    if (!found) {
        r.return(404, "Unknown alias");
        return;
    }

    var host = r.headersIn.host || "example.com:8443";
    var subUrl = "https://" + host + "/sub/" + found.name;

    if (parts.platform === "menu") {
        renderMenuPage(r, subUrl, host, found.name);
        return;
    }
    if (parts.platform === "ios") {
        renderIosPage(r, subUrl, host, found.name);
        return;
    }
    if (parts.platform === "android") {
        renderAndroidPage(r, subUrl, host, found.name);
        return;
    }
    if (parts.platform === "happ") {
        happ_redirect(r, found, subUrl);
        return;
    }
    if (parts.platform === "mac") {
        r.return(302, "v2raytun://import/" + subUrl);
        return;
    }
    if (parts.platform === "sub") {
        r.return(302, subUrl);
        return;
    }
    r.return(404, "Unknown platform");
}

export default { add_headers, import_redirect, sub_response };
