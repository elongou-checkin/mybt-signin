#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mybt auto signin + casdoor renew"""
from __future__ import annotations
import base64, hashlib, hmac, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request, http.cookiejar
from typing import Any, Dict, Optional, Tuple

def env(name, default=None):
    v = os.environ.get(name)
    if v is None: return default
    v = v.strip(); return v if v != "" else default

def log(msg):
    print(msg, flush=True)

def wx_test_notify(ok, content):
    """Send signin result via WeChat sandbox test account (mp.weixin.qq.com). Returns True when sent."""
    appid, secret = env("WX_TEST_APPID", ""), env("WX_TEST_APP_SECRET", "")
    template_id, openid = env("WX_TEST_TEMPLATE_ID", ""), env("WX_TEST_OPENID", "")
    if not (appid and secret and template_id and openid): return False
    try:
        q = urllib.parse.urlencode({"grant_type": "client_credential", "appid": appid, "secret": secret})
        with urllib.request.urlopen(f"https://api.weixin.qq.com/cgi-bin/token?{q}", timeout=15) as resp:
            tok = json.loads(resp.read().decode("utf-8"))
        access_token = tok.get("access_token")
        if not access_token:
            log(f"❌ 微信测试号获取 access_token 失败: {tok}"); return False
        body = json.dumps({"touser": openid, "template_id": template_id,
                           "data": {"result": {"value": "mybt 签到成功" if ok else "mybt 签到失败"},
                                    "detail": {"value": content[:200]}}}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}",
                                     data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if isinstance(result, dict) and result.get("errcode") == 0:
            log("✅ 微信测试号通知已发送"); return True
        log(f"❌ 微信测试号推送失败: {result}"); return False
    except Exception as e:
        log(f"❌ 微信测试号推送异常: {e}"); return False

def notify(ok, content):
    """Notification chain: WeChat test account -> WxPusher -> PushPlus."""
    if wx_test_notify(ok, content): return
    pushplus_notify(ok, content)

def pushplus_notify(ok, content):
    """Send signin result to WeChat via WxPusher (preferred) or PushPlus (fallback). Skipped when neither is configured."""
    title = "mybt 签到成功" if ok else "mybt 签到失败"
    sent = False
    app_token = env("WXPUSHER_APP_TOKEN", "")
    uids = [u.strip() for u in (env("WXPUSHER_UIDS", "") or "").split(",") if u.strip()]
    if app_token and uids:
        try:
            body = json.dumps({"appToken": app_token, "content": title + "\n" + content, "summary": title, "contentType": 1, "uids": uids}).encode("utf-8")
            req = urllib.request.Request("https://wxpusher.zjiecode.com/api/send/message", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            if isinstance(result, dict) and result.get("code") == 1000:
                log("✅ WxPusher 通知已发送"); sent = True
            else:
                log(f"❌ WxPusher 推送失败: {result}")
        except Exception as e:
            log(f"❌ WxPusher 推送异常: {e}")
    token = env("PUSHPLUS_TOKEN", "")
    if not token:
        if not sent:
            # 必须显式告警：静默跳过会让「通知配置失效」伪装成正常，
            # 工作流仍显示绿色但实际一条消息都没发出。
            log("⚠️ 未配置任何可用通知渠道（WxPusher / PushPlus / 微信测试号），本次未发送通知。")
            log("   若非预期，请检查仓库 Secrets：WXPUSHER_APP_TOKEN 与 WXPUSHER_UIDS。")
        return
    try:
        body = json.dumps({"token": token, "title": title, "content": content, "template": "txt"}).encode("utf-8")
        req = urllib.request.Request("https://www.pushplus.plus/send", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if isinstance(result, dict) and result.get("code") == 200:
            log("✅ PushPlus 通知已发送")
        else:
            log(f"❌ PushPlus 推送失败: {result}")
    except Exception as e:
        log(f"❌ PushPlus 推送异常: {e}")

def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sort_query(query: str) -> str:
    """Sort query params by key, mirroring the frontend signing helper."""
    if not query: return ""
    keys, values = [], {}
    for kv in query.split("&"):
        if "=" in kv:
            k, v = kv.split("=", 1)
        else:
            k, v = kv, None
        if k not in values: keys.append(k)
        values[k] = v
    keys.sort()
    return "&".join(k if values[k] is None else f"{k}={values[k]}" for k in keys)

def build_sign_headers(method, api_path, body, secret):
    path, query = api_path, ""
    if "?" in api_path: path, query = api_path.split("?", 1)
    query = sort_query(query)
    ts = str(int(time.time())); body = body or ""
    canonical = f"{method.upper()}\n{path}\n{query}\n{sha256_hex(body)}\n{ts}"
    sign = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"X-Sign": sign, "X-Timestamp": ts}

class HttpSession:
    def __init__(self, ua):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj), urllib.request.HTTPSHandler())
        self.ua = ua
    def request(self, url, method="GET", data=None, headers=None, form=False, timeout=30):
        h = {"User-Agent": self.ua, "Accept": "application/json, text/html;q=0.9,*/*;q=0.8", "Accept-Language": "zh-CN,zh;q=0.9"}
        if headers: h.update(headers)
        body=None
        if data is not None:
            if form:
                body = urllib.parse.urlencode(data).encode("utf-8"); h["Content-Type"]="application/x-www-form-urlencoded"
            elif isinstance(data, (dict, list)):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8"); h["Content-Type"]="application/json"
            elif isinstance(data, (bytes, bytearray)): body=bytes(data)
            else: body=str(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=h, method=method.upper())
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return resp.geturl(), resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return getattr(e, "url", url), e.code, dict(e.headers or {}), e.read()
        except Exception as e:
            return url, 0, {}, str(e).encode("utf-8", "replace")

class CasdoorLogin:
    def __init__(self, base_url, auth_url, username, password, turnstile_token=""):
        self.base_url=base_url.rstrip("/"); self.auth_url=auth_url.rstrip("/")
        self.username=username; self.password=password; self.turnstile_token=turnstile_token
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        self.http=HttpSession(self.ua)
    def login(self):
        url, status, headers, body = self.http.request(f"{self.base_url}/api/auth/casdoor/login")
        if status and status >= 400: raise RuntimeError(f"start oauth failed HTTP {status}: {body[:200]!r}")
        authorize_url = url
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(authorize_url).query)
        client_id=(qs.get("client_id") or [""])[0]
        redirect_uri=(qs.get("redirect_uri") or [""])[0]
        scope=(qs.get("scope") or ["openid profile email"])[0]
        state=(qs.get("state") or [""])[0]
        if not client_id or not redirect_uri: raise RuntimeError(f"oauth params incomplete: {authorize_url}")
        app_q={"clientId":client_id,"responseType":"code","redirectUri":redirect_uri,"type":"code","scope":scope,"state":state}
        app_url=f"{self.auth_url}/api/get-app-login?{urllib.parse.urlencode(app_q)}"
        _, status, _, body = self.http.request(app_url)
        app_json=json.loads(body.decode("utf-8","replace") or "{}")
        app=app_json.get("data") or {}
        org=app.get("organization") or "KiteYuan Users Organization"
        app_name=app.get("name") or "KiteYuan KiteMagnet"
        log(f"Casdoor app={app_name} org={org} enablePassword={app.get('enablePassword')}")
        login_payload={"application":app_name,"organization":org,"username":self.username,"password":self.password,"autoSignin":True,"type":"code","signinMethod":"Password"}
        if self.turnstile_token:
            login_payload["captchaType"]="Cloudflare Turnstile"
            login_payload["captchaToken"]=self.turnstile_token
            login_payload["captchaCode"]=self.turnstile_token
        login_query={"clientId":client_id,"responseType":"code","redirectUri":redirect_uri,"type":"code","scope":scope,"state":state}
        login_url=f"{self.auth_url}/api/login?{urllib.parse.urlencode(login_query)}"
        _, status, headers, body = self.http.request(login_url, method="POST", data=login_payload, headers={"Origin":self.auth_url,"Referer":authorize_url})
        text=body.decode("utf-8","replace")
        try: login_json=json.loads(text or "{}")
        except json.JSONDecodeError: raise RuntimeError(f"login non-json HTTP {status}: {text[:300]}")
        if login_json.get("status") != "ok":
            msg=login_json.get("msg") or login_json.get("message") or text[:300]
            low=str(msg).lower()
            if "captcha" in low or "turnstile" in low or "人机" in str(msg):
                raise RuntimeError(f"login requires captcha/turnstile: {msg}")
            raise RuntimeError(f"login failed: {msg}")
        data=login_json.get("data"); data2=login_json.get("data2"); code=None; redirect=None
        if isinstance(data, str) and data: code=data
        if isinstance(data, dict): code=data.get("code") or data.get("authCode")
        if not code and isinstance(data2, str) and len(data2) < 200 and not data2.startswith("http"): code=data2
        if isinstance(data2, str) and data2.startswith("http"): redirect=data2
        if isinstance(data, str) and data.startswith("http"): redirect=data
        if redirect and not code:
            q=urllib.parse.parse_qs(urllib.parse.urlparse(redirect).query); code=(q.get("code") or [""])[0]
        if not code:
            log(f"login ok but no code in response, raw={login_json}")
            url2, status2, headers2, body2 = self.http.request(authorize_url)
            if "token=" in url2:
                token=urllib.parse.parse_qs(urllib.parse.urlparse(url2).query).get("token",[""])[0]
                if token: return token, self._user_id_from_token(token)
            text2=body2.decode("utf-8","replace")
            m=re.search(r"code=([A-Za-z0-9_\-\.]+)", url2 + "\n" + text2)
            if m: code=m.group(1)
            else: raise RuntimeError(f"cannot extract oauth code after login: final={url2} body={text2[:200]!r}")
        callback=f"{self.base_url}/api/auth/casdoor/callback?" + urllib.parse.urlencode({"code":code,"state":state})
        url3, status3, headers3, body3 = self.http.request(callback)
        final_url=url3
        token=self._extract_token(url3, body3)
        if not token:
            loc=headers3.get("Location") or headers3.get("location")
            if loc:
                final_url=urllib.parse.urljoin(self.base_url+"/", loc)
                token=self._extract_token(final_url, b"")
        if not token:
            login_code=self._extract_param(final_url, "login_code") or self._extract_param(url3, "login_code")
            if login_code:
                log("检测到 login_code 回调，改用 POST /auth/session 换取 token")
                token=self._exchange_login_code(login_code)
        if not token: raise RuntimeError(f"callback did not return token. final={url3} status={status3} body={body3[:200]!r}")
        return token, self._user_id_from_token(token)
    def _exchange_login_code(self, login_code):
        """站点回调已改为下发 login_code，需再调 /auth/session 换取 token。"""
        _, status, _, body = self.http.request(f"{self.base_url}/api/auth/session", method="POST",
            data={"login_code":login_code}, headers={"Origin":self.base_url,"Referer":self.base_url+"/login"})
        text=body.decode("utf-8","replace")
        try: payload=json.loads(text or "{}")
        except json.JSONDecodeError: raise RuntimeError(f"session exchange non-json HTTP {status}: {text[:300]}")
        if status and status >= 400: raise RuntimeError(f"session exchange failed HTTP {status}: {text[:300]}")
        token=payload.get("token") if isinstance(payload, dict) else None
        if not token and isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            token=payload["data"].get("token")
        if not token: raise RuntimeError(f"session exchange returned no token: {text[:300]}")
        return str(token).removeprefix("Bearer ").strip()
    @staticmethod
    def _extract_param(url, key):
        q=urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return (q.get(key) or [""])[0].strip()
    @staticmethod
    def _extract_token(url, body):
        q=urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        token=(q.get("token") or [""])[0].strip()
        if token: return token
        text=body.decode("utf-8","replace") if body else ""
        m=re.search(r"[?&#]token=([A-Za-z0-9_\-\.]+)", url + "\n" + text)
        return m.group(1) if m else ""
    @staticmethod
    def _user_id_from_token(token):
        try:
            payload=token.split(".")[1]; pad="=" * (-len(payload) % 4)
            data=json.loads(base64.urlsafe_b64decode(payload+pad).decode("utf-8"))
            return str(data.get("uid") or data.get("id") or "")
        except Exception:
            return ""

class MybtClient:
    def __init__(self, base_url, token, user_id, secret="change-this-secret", cookie=""):
        self.base_url=base_url.rstrip("/"); self.token=token.removeprefix("Bearer ").strip()
        self.user_id=user_id; self.secret=secret or "change-this-secret"; self.cookie=cookie
        self.ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    def set_sign_secret(self, secret):
        if secret: self.secret=secret
    def request(self, method, path, body_obj=None):
        rel=path if path.startswith("/") else f"/{path}"
        if not rel.startswith("/api/"): rel="/api"+rel
        body=None if body_obj is None else json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))
        headers={"User-Agent":self.ua,"Accept":"application/json, */*","Content-Type":"application/json","Authorization":f"Bearer {self.token}","Origin":self.base_url,"Referer":self.base_url+"/"}
        if self.cookie: headers["Cookie"]=self.cookie
        headers.update(build_sign_headers(method, rel, body or "", self.secret))
        data=None if body is None else body.encode("utf-8")
        req=urllib.request.Request(self.base_url+rel, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw=resp.read().decode("utf-8","replace"); status=resp.getcode() or 200
        except urllib.error.HTTPError as e:
            raw=e.read().decode("utf-8","replace"); status=e.code
        except Exception as e:
            return 0, None, f"network error: {type(e).__name__}: {e}"
        try: parsed=json.loads(raw) if raw else {}
        except json.JSONDecodeError: parsed=raw
        return status, parsed, raw
    def me(self): return self.request("GET", "/auth/me")
    def signin(self): return self.request("POST", "/auth/points/tasks/signin", {})
    def visit(self): return self.request("POST", "/auth/points/tasks/visit", {})

def summarize(action, status, data, raw):
    if status == 0: return False, f"{action}: {raw}"
    if isinstance(data, dict):
        err=str(data.get("error") or data.get("message") or data.get("msg") or "")
        if status >= 400:
            if any(k in err for k in ("已签到","已完成","已领取","already","Already")): return True, f"{action}: {err}"
            return False, f"{action}: HTTP {status} - {err or raw[:200]}"
        added=data.get("added")
        if added is not None: return True, f"{action}: 成功，获得 {added} 积分"
        return True, f"{action}: 成功 - {json.dumps(data, ensure_ascii=False)[:300]}"
    if 200 <= status < 300: return True, f"{action}: HTTP {status}"
    return False, f"{action}: HTTP {status} - {raw[:200]}"

def main():
    base_url=env("MYBT_BASE_URL","https://mybt.kiteyuan.info") or "https://mybt.kiteyuan.info"
    auth_url=env("MYBT_AUTH_URL","https://auth.kiteyuan.info") or "https://auth.kiteyuan.info"
    secret=env("MYBT_SECRET","change-this-secret") or "change-this-secret"
    cookie=env("MYBT_COOKIE","") or ""
    do_visit=(env("MYBT_DO_VISIT","1") or "1").lower() in ("1","true","yes","y")
    username=env("MYBT_USERNAME") or env("CASDOOR_USERNAME")
    password=env("MYBT_PASSWORD") or env("CASDOOR_PASSWORD")
    turnstile=env("MYBT_TURNSTILE_TOKEN","") or ""
    token=env("MYBT_TOKEN"); user_id=env("MYBT_USER_ID") or ""
    log("== mybt signin =="); log(f"time: {time.strftime('%Y-%m-%d %H:%M:%S')}"); log(f"base: {base_url}")
    if username and password:
        log("==> 尝试 Casdoor 自动登录续期")
        try:
            token, uid = CasdoorLogin(base_url, auth_url, username, password, turnstile).login()
            if uid: user_id=uid
            log("✅ 自动登录成功，已获取新 token")
        except Exception as e:
            log(f"❌ 自动登录失败: {e}")
            if not token:
                log("无可用 MYBT_TOKEN 兜底，退出"); notify(False, "自动登录失败且无 MYBT_TOKEN 兜底: " + str(e)); return 2
            log("回退到已有 MYBT_TOKEN")
    elif not token:
        log("缺少 MYBT_USERNAME/MYBT_PASSWORD 或 MYBT_TOKEN"); notify(False, "缺少 MYBT_USERNAME/MYBT_PASSWORD 或 MYBT_TOKEN"); return 2
    if not user_id:
        try:
            payload=token.split(".")[1]; pad="=" * (-len(payload)%4)
            data=json.loads(base64.urlsafe_b64decode(payload+pad).decode("utf-8"))
            user_id=str(data.get("uid") or data.get("id") or "")
        except Exception: pass
    if not user_id:
        log("缺少 MYBT_USER_ID，且无法从 token 解析"); notify(False, "缺少 MYBT_USER_ID，且无法从 token 解析"); return 2
    client=MybtClient(base_url, token, user_id, secret=secret, cookie=cookie)
    ok_all=True; msgs=[]
    status, data, raw = client.me(); ok, msg = summarize("me", status, data, raw); log(msg); msgs.append(msg)
    if not ok:
        log("登录态失效。请检查自动登录账号密码/验证码，或更新 MYBT_TOKEN"); notify(False, "\n".join(msgs)); return 1
    if isinstance(data, dict):
        if data.get("sign_secret"):
            client.set_sign_secret(data["sign_secret"])
        if isinstance(data.get("user"), dict):
            user=data["user"]; log(f"user: {user.get('username')} points={user.get('points')}"); msgs.append(f"用户: {user.get('username')} 当前积分: {user.get('points')}")
            if user.get("id"): client.user_id=str(user.get("id"))
    status, data, raw = client.signin(); ok, msg = summarize("signin", status, data, raw); log(msg); ok_all = ok_all and ok; msgs.append(msg)
    if do_visit:
        status, data, raw = client.visit(); ok, msg = summarize("visit", status, data, raw); log(msg); ok_all = ok_all and ok; msgs.append(msg)
    status, data, raw = client.me()
    if status==200 and isinstance(data, dict) and isinstance(data.get("user"), dict):
        log(f"points_after: {data['user'].get('points')}"); msgs.append(f"签到后积分: {data['user'].get('points')}")
    if ok_all: log("DONE: success"); notify(True, "\n".join(msgs)); return 0
    log("DONE: failed"); notify(False, "\n".join(msgs)); return 1

if __name__ == "__main__":
    try: raise SystemExit(main())
    except KeyboardInterrupt: raise SystemExit(130)
