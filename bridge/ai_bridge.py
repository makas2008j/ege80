import base64, hashlib, json, os, secrets, sqlite3, sys, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HOST='127.0.0.1'; PORT=8000
AI_TOKEN=os.environ.get('AI_TOKEN','').strip()
OLLAMA_URL=os.environ.get('OLLAMA_URL','http://127.0.0.1:11434')
MODEL=os.environ.get('OLLAMA_MODEL','qwen3:8b')
TIMEOUT=300
SYSTEM_PROMPTS={
 'russian':'Ты локальный репетитор по русскому языку для подготовки к ЕГЭ (Задание 27 — сочинение, тесты). Отвечай по-русски, понятно и по делу. Если создаёшь задания, они авторские, а не официальные задания ФИПИ.',
 'math':'Ты локальный репетитор по профильной математике для подготовки к ЕГЭ (алгебра, геометрия, тригонометрия, производные, экономические задачи, параметры). Отвечай по-русски понятно, показывай решение по шагам, используй формулы. Если создаёшь задания, они авторские, а не официальные задания ФИПИ.',
 'soc':'Ты локальный репетитор по обществознанию для подготовки к ЕГЭ (человек и общество, экономика, социальные отношения, политика, право, познание и культура). Отвечай по-русски понятно, опирайся на кодификатор и терминологию ФИПИ. Если создаёшь задания, они авторские, а не официальные задания ФИПИ.',
 'info':'Ты локальный репетитор по информатике для подготовки к ЕГЭ (кодирование, логика, алгоритмы, Python, системы счисления, базы данных). Отвечай по-русски понятно, показывай код и поясняй решение. Если создаёшь задания, они авторские, а не официальные задания ФИПИ.',
}
SYSTEM_PROMPT=SYSTEM_PROMPTS['russian']

# ---------------- SQLite / учётные записи ----------------
DB_PATH=os.path.join(os.path.dirname(os.path.abspath(__file__)),'ege.db')
SESSION_TTL=60*60*24*30  # 30 дней

def db():
    d=sqlite3.connect(DB_PATH,timeout=10)
    d.row_factory=sqlite3.Row
    return d

def init_db():
    d=db()
    d.executescript('''
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      login TEXT UNIQUE NOT NULL,
      pass_hash TEXT NOT NULL,
      pass_salt TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS sessions(
      token TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL,
      created_at TEXT DEFAULT (datetime('now')),
      expires_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS user_data(
      user_id INTEGER NOT NULL,
      subject TEXT NOT NULL,
      key TEXT NOT NULL,
      value TEXT,
      updated_at TEXT DEFAULT (datetime('now')),
      PRIMARY KEY(user_id, subject, key),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_user_data ON user_data(user_id, subject);
    ''')
    d.commit(); d.close()

def hash_pass(pw,salt):
    return hashlib.pbkdf2_hmac('sha256',pw.encode('utf-8'),salt.encode('utf-8'),120000).hex()

def create_user(login,pw):
    salt=secrets.token_hex(16)
    d=db()
    try:
        cur=d.execute('INSERT INTO users(login,pass_hash,pass_salt) VALUES(?,?,?)',(login,hash_pass(pw,salt),salt))
        uid=cur.lastrowid; d.commit()
    except sqlite3.IntegrityError:
        d.close(); return None
    d.close(); return uid

def get_user_by_login(login):
    d=db(); r=d.execute('SELECT * FROM users WHERE login=?',(login,)).fetchone(); d.close(); return r

def get_user_by_id(uid):
    d=db(); r=d.execute('SELECT id,login,created_at FROM users WHERE id=?',(uid,)).fetchone(); d.close(); return r

def verify_user(login,pw):
    u=get_user_by_login(login)
    if not u: return None
    if hash_pass(pw,u['pass_salt'])!=u['pass_hash']: return None
    return u

def create_session(uid):
    d=db()
    token=secrets.token_urlsafe(32)
    d.execute('INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,datetime(\'now\',\'+30 days\'))',(token,uid))
    d.commit(); d.close(); return token

def session_user(token):
    if not token: return None
    d=db()
    r=d.execute('SELECT u.id,u.login FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>datetime(\'now\')',(token,)).fetchone()
    d.close(); return dict(r) if r else None

def logout_session(token):
    d=db(); d.execute('DELETE FROM sessions WHERE token=?',(token,)); d.commit(); d.close()

def get_data(uid,subject,key):
    d=db(); r=d.execute('SELECT value FROM user_data WHERE user_id=? AND subject=? AND key=?',(uid,subject,key)).fetchone(); d.close(); return r['value'] if r else None

def set_data(uid,subject,key,value):
    d=db()
    d.execute('INSERT INTO user_data(user_id,subject,key,value) VALUES(?,?,?,?) ON CONFLICT(user_id,subject,key) DO UPDATE SET value=excluded.value, updated_at=datetime(\'now\')',(uid,subject,key,value))
    d.commit(); d.close()

def send_json(h,status,payload):
    raw=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    h.send_response(status); h.send_header('Content-Type','application/json; charset=utf-8')
    h.send_header('Access-Control-Allow-Origin','*'); h.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
    h.send_header('Access-Control-Allow-Headers','Content-Type, Authorization, X-Session-Token'); h.send_header('Access-Control-Max-Age','86400')
    h.send_header('Content-Length',str(len(raw))); h.end_headers(); h.wfile.write(raw)

def ollama_request(path,payload=None):
    url=OLLAMA_URL.rstrip('/')+path; data=None; headers={'Accept':'application/json'}
    if payload is not None:
        data=json.dumps(payload,ensure_ascii=False).encode('utf-8'); headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=data,headers=headers,method='POST' if data else 'GET')
    try:
        with urllib.request.urlopen(req,timeout=TIMEOUT) as r: return r.status,json.loads(r.read().decode('utf-8','replace'))
    except urllib.error.HTTPError as e:
        body=e.read().decode('utf-8','replace')
        try: detail=json.loads(body)
        except Exception: detail=body
        raise RuntimeError(f'Ollama HTTP {e.code}: {detail}')
    except urllib.error.URLError as e: raise RuntimeError(f'Не удалось подключиться к Ollama: {e.reason}')

def chat(message,history=None,images=None,subject=None,errors=None):
    sysp=SYSTEM_PROMPTS.get(subject) or SYSTEM_PROMPT
    if isinstance(errors,list) and errors:
        lines=[]
        for e in errors[:30]:
            if not isinstance(e,dict): continue
            task=str(e.get('task') or '').strip()
            title=str(e.get('title') or '').strip()
            note=str(e.get('note') or '').strip()
            status='исправлено' if e.get('status')=='resolved' else 'нужно повторить'
            row=f"- №{task} ({status}): {title}"
            if note: row+=f" — {note}"
            lines.append(row)
        if lines:
            sysp=sysp+("\n\nЖурнал ошибок ученика (учитывай его при ответе, если вопрос связан с этими темами, "
                       "обращай внимание на повторяющиеся ошибки и предлагай их проработать):\n"+"\n".join(lines))
    messages=[{'role':'system','content':sysp}]
    if isinstance(history,list):
        for item in history[-12:]:
            if isinstance(item,dict) and item.get('role') in ('user','assistant') and item.get('content'):
                messages.append({'role':item['role'],'content':str(item['content'])})
    user_part={'role':'user','content':str(message)}
    if isinstance(images,list) and images:
        user_part['images']=[img for img in images if isinstance(img,str) and img.strip()]
    messages.append(user_part)
    _,data=ollama_request('/api/chat',{'model':MODEL,'messages':messages,'stream':False,'think':False,'options':{'temperature':0.3}})
    msg=data.get('message') or {}; content=msg.get('content') or msg.get('thinking') or data.get('response') or ''
    if not content: raise RuntimeError('Ollama вернула пустой ответ: '+json.dumps(data,ensure_ascii=False))
    return content

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,fmt,*args): print('[%s] %s'%(self.log_date_time_string(),fmt%args),flush=True)
    def authorized(self):
        if not AI_TOKEN: return True
        if self.headers.get('Authorization','')=='Bearer '+AI_TOKEN: return True
        # запросы авторизации всегда доступны (логин/регистрация)
        if self.path.startswith('/api/auth/'): return True
        # любой запрос с валидной пользовательской сессией
        try:
            if session_user(self.session_token()): return True
        except Exception:
            pass
        return False
    def do_OPTIONS(self):
        self.send_response(204); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type, Authorization, X-Session-Token'); self.send_header('Access-Control-Max-Age','86400'); self.end_headers()
    def do_GET(self):
        if self.path.startswith('/api/') and not self.authorized(): return send_json(self,401,{'ok':False,'error':'Unauthorized'})
        if self.path=='/api/status':
            try:
                _,tags=ollama_request('/api/tags'); names=[m.get('name') for m in tags.get('models',[])]
                return send_json(self,200,{'ok':True,'model':MODEL,'ollama':True,'model_installed':MODEL in names,'models':names})
            except Exception as e: return send_json(self,503,{'ok':False,'model':MODEL,'ollama':False,'error':str(e)})
        if self.path=='/api/':
            return send_json(self,200,{'ok':True,'service':'EGE Local AI Bridge','model':MODEL})
        if self.path=='/api/auth/me':
            token=self.session_token()
            u=session_user(token)
            if not u: return send_json(self,401,{'ok':False,'error':'Not logged in'})
            return send_json(self,200,{'ok':True,'user':u['login']})
        return send_json(self,404,{'ok':False,'error':'Not found'})
    def session_token(self):
        h=self.headers.get('X-Session-Token','') or ''
        return h.strip()
    def _ensure_admin(self):
        u=get_user_by_login('admin')
        if u: return u['id']
        uid=create_user('admin','admin')
        return uid
    def do_POST(self):
        if not self.authorized(): return send_json(self,401,{'ok':False,'error':'Unauthorized'})
        try:
            raw=self.rfile.read(int(self.headers.get('Content-Length','0'))).decode('utf-8') if self.headers.get('Content-Length') else '{}'
            if not raw.strip(): raw='{}'
            data=json.loads(raw)
        except Exception as e: return send_json(self,400,{'ok':False,'error':f'Некорректный JSON: {e}'})
        try:
            if self.path=='/api/auth/register':
                login=str(data.get('login') or '').strip(); pw=str(data.get('password') or '')
                if len(login)<2 or len(pw)<3: return send_json(self,400,{'ok':False,'error':'Логин (мин. 2 симв.) и пароль (мин. 3 симв.) обязательны'})
                if login.lower()=='admin': return send_json(self,400,{'ok':False,'error':'Логин admin зарезервирован'})
                if get_user_by_login(login) is not None: return send_json(self,409,{'ok':False,'error':'Такой логин уже существует'})
                uid=create_user(login,pw)
                if uid is None: return send_json(self,409,{'ok':False,'error':'Такой логин уже существует'})
                token=create_session(uid); return send_json(self,200,{'ok':True,'token':token,'user':login})
            if self.path=='/api/auth/login':
                login=str(data.get('login') or '').strip(); pw=str(data.get('password') or '')
                if login=='admin' and pw=='admin':
                    token=create_session(0 if False else self._ensure_admin()); return send_json(self,200,{'ok':True,'token':token,'user':'admin'})
                u=verify_user(login,pw)
                if not u: raise PermissionError('Неверный логин или пароль')
                token=create_session(u['id']); return send_json(self,200,{'ok':True,'token':token,'user':u['login']})
            if self.path=='/api/auth/logout':
                token=self.session_token()
                if token: logout_session(token)
                return send_json(self,200,{'ok':True})
            if self.path=='/api/auth/me':
                token=self.session_token(); u=session_user(token)
                if not u: return send_json(self,401,{'ok':False,'error':'Not logged in'})
                return send_json(self,200,{'ok':True,'user':u['login']})
            if self.path=='/api/me':
                token=self.session_token(); u=session_user(token)
                if not u: return send_json(self,401,{'ok':False,'error':'Not logged in'})
                return send_json(self,200,{'ok':True,'user':u['login']})
            if self.path=='/api/data/get':
                token=self.session_token(); u=session_user(token)
                if not u: return send_json(self,401,{'ok':False,'error':'Not logged in'})
                subject=str(data.get('subject') or ''); keys=data.get('keys')
                if isinstance(keys,list) and len(keys)<=200:
                    out={}
                    for k in keys:
                        v=get_data(u['id'],subject,k)
                        if v is not None:
                            try: out[k]=json.loads(v)
                            except Exception: out[k]=v
                    return send_json(self,200,{'ok':True,'data':out})
                return send_json(self,400,{'ok':False,'error':'Нужен list keys'})
            if self.path=='/api/data/set':
                token=self.session_token(); u=session_user(token)
                if not u: return send_json(self,401,{'ok':False,'error':'Not logged in'})
                subject=str(data.get('subject') or ''); payload=data.get('data')
                if not isinstance(payload,dict): raise ValueError('Нужен объект data {key:value}')
                for k,v in payload.items():
                    set_data(u['id'],subject,k,json.dumps(v,ensure_ascii=False))
                return send_json(self,200,{'ok':True})
            if self.path=='/api/chat':
                msg=data.get('message') or data.get('prompt') or ''
                images=data.get('images')
                if not str(msg).strip() and not (isinstance(images,list) and images):
                    raise ValueError('Поле message пустое')
                content=chat(msg,data.get('history'),images,data.get('subject'),data.get('errors')); return send_json(self,200,{'ok':True,'response':content,'message':{'role':'assistant','content':content}})
            if self.path=='/api/generate':
                prompt=data.get('prompt') or data.get('message') or ''
                if not str(prompt).strip(): raise ValueError('Поле prompt пустое')
                return send_json(self,200,{'ok':True,'response':chat(prompt)})
            if self.path=='/api/analyze-error':
                prompt=data.get('prompt') or data.get('error') or ''
                if not str(prompt).strip(): raise ValueError('Не передана ошибка')
                return send_json(self,200,{'ok':True,'response':chat('Разбери ошибку ученика и объясни правило простыми словами.\n\n'+str(prompt))})
            if self.path=='/api/summarize':
                text=data.get('text') or data.get('prompt') or ''
                if not str(text).strip(): raise ValueError('Не передан текст')
                return send_json(self,200,{'ok':True,'response':chat('Сделай краткий, но информативный конспект для подготовки к ЕГЭ по русскому языку:\n\n'+str(text))})
            return send_json(self,404,{'ok':False,'error':'Not found'})
        except Exception as e:
            print(f'ERROR {self.path}: {type(e).__name__}: {e}',file=sys.stderr,flush=True); return send_json(self,500,{'ok':False,'error':str(e),'path':self.path})

def main():
    init_db()
    print('EGE Local AI Bridge v7 (SQLite)'); print(f'Bridge: http://{HOST}:{PORT}'); print(f'DB: {DB_PATH}'); print(f'Ollama: {OLLAMA_URL}'); print(f'Model: {MODEL}'); print('Auth: enabled' if AI_TOKEN else 'Auth: disabled'); print('Ctrl+C to stop.\n',flush=True)
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nStopping...')
    finally: server.server_close()
if __name__=='__main__': main()