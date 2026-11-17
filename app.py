# 웹 요청, 회원 인증, 화면과 데이터베이스를 연결합니다.
import json  # 공부 데이터를 JSON으로 변환하거나 읽습니다.
import calendar  # 월간 달력의 날짜를 계산합니다.
from hashlib import sha256  # 추천 결과의 비교용 해시를 계산합니다.
from datetime import date, datetime, timedelta  # 날짜·시각과 시간 차이를 계산합니다.
from pathlib import Path  # 프로젝트 파일의 경로를 다룹니다.
from io import BytesIO  # PDF를 메모리에 보관합니다.

import os  # 배포 환경 변수와 실행 설정을 읽습니다.
import planner as P  # 계획 배분과 진도 계산 함수를 불러옵니다.
from uuid import uuid4  # 일정에 쓸 고유 ID를 생성합니다.
from datetime import timezone  # 날짜·시각과 시간 차이를 계산합니다.
from functools import wraps  # 로그인 검사로 감싼 함수의 정보를 보존합니다.
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session  # 웹 요청, 응답, 화면과 세션을 처리합니다.
from flask_sqlalchemy import SQLAlchemy  # Flask에서 데이터베이스 모델을 사용합니다.
from sqlalchemy import text  # 데이터베이스 명령을 실행합니다.
from sqlalchemy.exc import IntegrityError  # 데이터베이스 명령을 실행합니다.
from flask_wtf.csrf import CSRFProtect  # 폼 요청의 CSRF 토큰을 검증합니다.
from werkzeug.security import generate_password_hash, check_password_hash  # 비밀번호 해시 생성과 검증을 맡습니다.

# Flask 앱을 만들고 환경 변수에 따라 로컬 DB 또는 배포 DB를 연결합니다.
app = Flask(__name__)  # app 변수에 이 줄의 계산 결과를 저장합니다.
if os.environ.get('RENDER') and (not os.environ.get('DATABASE_URL') or not os.environ.get('SECRET_KEY')):
    raise RuntimeError('배포 환경에는 DATABASE_URL과 SECRET_KEY가 필요합니다.')
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "local-dev-key-change-before-deploy")
database_url = os.environ.get("DATABASE_URL", "sqlite:///study_planner.db")  # database_url 변수에 이 줄의 계산 결과를 저장합니다.
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)  # database_url 변수에 이 줄의 계산 결과를 저장합니다.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)  # database_url 변수에 이 줄의 계산 결과를 저장합니다.
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"
# SQLAlchemy가 계정과 학습 데이터를 저장하고 CSRFProtect가 폼 요청을 검증합니다.
db = SQLAlchemy(app)  # db 변수에 이 줄의 계산 결과를 저장합니다.
csrf = CSRFProtect(app)  # csrf 변수에 이 줄의 계산 결과를 저장합니다.

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # 행을 구별하는 기본 키입니다.
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)  # 입력한 사용자 이름 값을 준비합니다.
    password_hash = db.Column(db.String(255), nullable=False)  # 검증에 쓰는 비밀번호 해시입니다.
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)  # 계정 생성 시각입니다.

class PlannerData(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # 행을 구별하는 기본 키입니다.
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)  # 이 자료가 속한 계정 ID입니다.
    payload = db.Column(db.Text, nullable=False)  # JSON으로 변환한 공부 자료 값을 준비합니다.

with app.app_context():
    db.create_all()

BASE_DIR = Path(__file__).resolve().parent  # BASE_DIR 변수에 이 줄의 계산 결과를 저장합니다.
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]  # WEEKDAYS 변수에 이 줄의 계산 결과를 저장합니다.
MODES = ["시간 기반 자동", "쪽수", "문제 수", "단어 수"]  # MODES 변수에 이 줄의 계산 결과를 저장합니다.

DEFAULT_DATA = {  # DEFAULT_DATA 변수에 이 줄의 계산 결과를 저장합니다.
    "settings": {
        "exam_date": (P.today() + timedelta(days=21)).isoformat(),
        "daily_minutes": 240,
        "start_time": "18:00",
        "session_minutes": 50,
        "break_minutes": 10,
        "study_days": WEEKDAYS[:],
        "revision_days": [1, 3, 7],
    },
    "subjects": [],
    "schedule": [],
    "completed": []
}



def load_data():  # 계정의 저장 데이터를 읽고 이전 버전의 누락 항목을 보완합니다.
    # 같은 계정의 타이머/계획 요청이 동시에 오면 순서대로 저장합니다.
    if request.method == 'POST':
        if db.engine.dialect.name == 'sqlite':
            db.session.execute(text('BEGIN IMMEDIATE'))
        else:
            User.query.filter_by(id=session['user_id']).with_for_update().first()
    record = PlannerData.query.filter_by(user_id=session["user_id"]).first()  # 현재 계정의 DB 행 값을 준비합니다.
    if record:
        try:
            data = json.loads(record.payload)  # 현재 계정의 공부 자료 값을 준비합니다.
        except (json.JSONDecodeError, TypeError):
            data = json.loads(json.dumps(DEFAULT_DATA))  # 현재 계정의 공부 자료 값을 준비합니다.
    else:
        data = json.loads(json.dumps(DEFAULT_DATA))  # 현재 계정의 공부 자료 값을 준비합니다.
    for key, value in DEFAULT_DATA.items():
        if key not in data:
            data[key] = json.loads(json.dumps(value))
    for subject in data.get("subjects", []):
        subject.setdefault("book", "")
        subject.setdefault("start_page", 1)
        subject.setdefault("end_page", 1)
        subject.setdefault("current_page", subject.get("start_page", 1))
        subject.setdefault("pages_per_day", 5)
        subject.setdefault("tracking_mode", "시간 기반 자동")
        subject.setdefault("unit_total", 0)
        subject.setdefault("unit_done", 0)
        subject.setdefault("task", "핵심 개념 학습")
        subject.setdefault("importance", 3)
        subject.setdefault("difficulty", 3)
        subject.setdefault("progress", 0)
    return P.normalize(data)  # 호출한 곳에 결과를 돌려줍니다.



def save_data(data):  # 현재 계정의 변경 내용을 데이터베이스에 저장합니다.
    record = PlannerData.query.filter_by(user_id=session["user_id"]).first()  # 현재 계정의 DB 행 값을 준비합니다.
    payload = json.dumps(data, ensure_ascii=False)  # JSON으로 변환한 공부 자료 값을 준비합니다.
    if record:
        record.payload = payload
    else:
        db.session.add(PlannerData(user_id=session["user_id"], payload=payload))
    db.session.commit()



def login_required(view):  # 로그인 세션을 검사하고 필요하면 로그인 화면으로 보냅니다.
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))  # 처리 후 지정한 화면으로 이동합니다.
        return view(*args, **kwargs)  # 호출한 곳에 결과를 돌려줍니다.
    return wrapped  # 호출한 곳에 결과를 돌려줍니다.



def get_context():  # 현재 사용자에게 필요한 학습 데이터를 준비합니다.
    data = load_data()  # 현재 계정의 공부 자료 값을 준비합니다.
    return data  # 호출한 곳에 결과를 돌려줍니다.


@app.route("/register", methods=["GET", "POST"])

def register():  # 회원가입 입력을 검사하고 비밀번호 해시와 계정을 저장합니다.
    if "user_id" in session:
        return redirect(url_for("dashboard"))  # 처리 후 지정한 화면으로 이동합니다.
    if request.method == "POST":
        username = request.form.get("username", "").strip()  # 입력한 사용자 이름 값을 준비합니다.
        password = request.form.get("password", "")  # 입력한 비밀번호 값을 준비합니다.
        confirm = request.form.get("confirm_password", "")  # 비밀번호 확인 값 값을 준비합니다.
        if not (3 <= len(username) <= 40) or not username.replace("_", "").isalnum():
            flash("아이디는 영문·숫자·밑줄을 사용해 3~40자로 입력해 주세요.", "error")
        elif len(password) < 10:
            flash("비밀번호는 10자 이상으로 설정해 주세요.", "error")
        elif password != confirm:
            flash("비밀번호 확인이 일치하지 않습니다.", "error")
        elif User.query.filter_by(username=username).first():
            flash("이미 사용 중인 아이디입니다.", "error")
        else:
            user = User(username=username, password_hash=generate_password_hash(password))  # 계정 정보 값을 준비합니다.
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('이미 등록된 아이디입니다.', 'error')
                return redirect(url_for('register'))  # 처리 후 지정한 화면으로 이동합니다.
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            flash("회원가입이 완료되었습니다.", "success")
            return redirect(url_for("dashboard"))  # 처리 후 지정한 화면으로 이동합니다.
    return render_template("register.html")  # 템플릿에 값을 전달해 화면을 만듭니다.


@app.route("/login", methods=["GET", "POST"])

def login():  # 사용자 정보와 비밀번호를 확인하고 로그인 세션을 설정합니다.
    if "user_id" in session:
        return redirect(url_for("dashboard"))  # 처리 후 지정한 화면으로 이동합니다.
    if request.method == "POST":
        username = request.form.get("username", "").strip()  # 입력한 사용자 이름 값을 준비합니다.
        password = request.form.get("password", "")  # 입력한 비밀번호 값을 준비합니다.
        user = User.query.filter_by(username=username).first()  # 계정 정보 값을 준비합니다.
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("dashboard"))  # 처리 후 지정한 화면으로 이동합니다.
        flash("아이디 또는 비밀번호를 확인해 주세요.", "error")
    return render_template("login.html")  # 템플릿에 값을 전달해 화면을 만듭니다.


@app.route("/logout", methods=["POST"])
@login_required

def logout():  # 세션을 지워 로그아웃합니다.
    session.clear()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("login"))  # 처리 후 지정한 화면으로 이동합니다.


@app.route("/")
@login_required

def dashboard():  # 오늘 할 일과 공부 시간, 목표 대비 진도를 모아 홈에 표시합니다.
    data = get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    settings = data["settings"]  # 자습 시간과 마감일 설정 값을 준비합니다.
    exam = date.fromisoformat(settings["exam_date"])  # 전체 학습 마감일 값을 준비합니다.
    days_left = max(0, (exam - P.today()).days)  # 마감일까지 남은 일수 값을 준비합니다.
    progress = sum(P.progress(s, data) for s in data["subjects"]) / len(data["subjects"]) if data["subjects"] else 0  # progress 변수에 이 줄의 계산 결과를 저장합니다.
    upcoming = [x for x in data["schedule"] if x["date"] >= P.today().isoformat()][:12]  # upcoming 변수에 이 줄의 계산 결과를 저장합니다.
    today_items=sorted([x for x in data['schedule'] if x['date']==P.today().isoformat()],key=lambda x:x.get('start',''))  # today_items 변수에 이 줄의 계산 결과를 저장합니다.
    done_minutes=P.actual_seconds(data,day=P.today().isoformat())//60  # done_minutes 변수에 이 줄의 계산 결과를 저장합니다.
    subject_minutes={sub['name']:P.actual_seconds(data,sub['name'],P.today().isoformat())//60 for sub in data['subjects']}  # subject_minutes 변수에 이 줄의 계산 결과를 저장합니다.
    day_goal=P.capacity(data,P.today())  # day_goal 변수에 이 줄의 계산 결과를 저장합니다.
    goal_percent=min(100,round(done_minutes/max(1,day_goal)*100)) if day_goal else 0  # 오늘 시간 목표의 달성률 값을 준비합니다.
    return render_template('dashboard.html',data=data,days_left=days_left,progress=progress,today_items=today_items,done_minutes=done_minutes,subject_minutes=subject_minutes,
                           goal_percent=goal_percent,day_goal=day_goal,subject_progress=lambda sub,_:P.progress(sub,data),now_iso=datetime.now(timezone.utc).isoformat())




def subject_values(f, data, existing=None):  # 과목 폼의 값과 진도 범위, 우선순위를 검증합니다.
    name = (existing or {}).get('name') or f.get('name','').strip()  # 과목 또는 사용자 이름 값을 준비합니다.
    if not name or len(name)>60: raise ValueError('과목명은 1~60자로 입력해 주세요.')
    if existing is None and any(x['name'].casefold()==name.casefold() for x in data['subjects']): raise ValueError('이미 등록된 과목입니다.')
    mode=f.get('tracking_mode','시간 기반 자동')  # 진도 계산 방식 값을 준비합니다.
    if mode not in MODES: raise ValueError('진도 방식을 확인해 주세요.')
    first=P.integer(f.get('start_page') or 1,1,100000,'시작 쪽수')  # 범위의 첫 번호 값을 준비합니다.
    last=P.integer(f.get('end_page') or first,first,100000,'끝 쪽수')  # 범위의 마지막 번호 값을 준비합니다.
    total=last-first+1 if mode=='쪽수' else P.integer(f.get('unit_total') or 0,0,100000,'전체 수량')  # total 변수에 이 줄의 계산 결과를 저장합니다.
    if mode!='시간 기반 자동' and total<1: raise ValueError('수량 방식은 전체 수량 또는 쪽수 범위가 필요합니다.')
    deadline=P.day_value(f.get('deadline') or data['settings']['exam_date'])  # 과목 마감일 값을 준비합니다.
    if deadline>P.day_value(data['settings']['exam_date']):raise ValueError('과목 마감일은 전체 마감일 이내여야 합니다.')
    if existing and any(l['subject']==name for l in data['logs']):
        if mode!=existing['tracking_mode'] or (mode=='쪽수' and first!=existing['start_page']):raise ValueError('기록이 있는 과목은 진도 방식/시작 쪽수를 바꿀 수 없습니다. 새 과목으로 등록해 주세요.')
    rank = P.integer(f.get('priority_rank', P.priority_rank(existing or {})), 1, 3, '우선순위')  # 과목의 우선순위 값을 준비합니다.
    task = f.get('task', '').strip()  # 세부 학습 목표 값을 준비합니다.
    if len(task) > 300:
        raise ValueError('세부 학습 목표는 300자 이내로 입력해 주세요.')
    result=dict(name=name,task=task or '핵심 개념 학습',priority_rank=rank,book=f.get('book','').strip()[:150],tracking_mode=mode,start_page=first,end_page=last,  # 이 함수에서 계산한 결과 값을 준비합니다.
                unit_total=total,unit_done=P.integer(f.get('unit_done') or 0,0,max(0,total),'기존 완료량'),current_page=first,pages_per_day=5,
                importance={1: 5, 2: 3, 3: 1}[rank],difficulty=P.integer(f.get('difficulty',3),1,5,'난이도'),progress=0,
                target_minutes=P.integer(f.get('target_minutes') or 600,1,100000,'총 목표 시간'),minutes_per_unit=P.integer(f.get('minutes_per_unit') or 5,1,120,'단위당 예상 시간'),
                deadline=deadline.isoformat(),note=f.get('note','')[:2000])
    if mode!='시간 기반 자동':
        lo,hi=P.bounds(result)
        if any(x.get('range_end') is not None and (x['range_end']>hi or x['range_start']<lo) for x in data['schedule']+data['logs'] if x['subject']==name):raise ValueError('기존 계획/기록 범위보다 목표 범위를 줄일 수 없습니다.')
    return result  # 호출한 곳에 결과를 돌려줍니다.

@app.route('/subjects',methods=['GET','POST'])
@login_required

def subjects():  # 과목 목록을 표시하고 새 과목 등록을 처리합니다.
    data=get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    if request.method=='POST':
        try:
            data['subjects'].append(subject_values(request.form,data));save_data(data);flash('과목을 추가했습니다.','success')
        except ValueError as e:flash(str(e),'error')
        return redirect(url_for('subjects'))  # 처리 후 지정한 화면으로 이동합니다.
    return render_template('subjects.html',data=data,modes=MODES,priority_rank=P.priority_rank,subject_progress=lambda s,_:P.progress(s,data))  # 템플릿에 값을 전달해 화면을 만듭니다.

@app.route('/subjects/<path:name>/update',methods=['POST'])
@login_required

def update_subject(name):  # 선택한 과목의 설정을 수정합니다.
    data=get_context();subject=next((x for x in data['subjects'] if x['name']==name),None)  # 현재 계정의 공부 자료 값을 준비합니다.
    try:
        if subject is None:raise ValueError('과목을 찾을 수 없습니다.')
        subject.update(subject_values(request.form,data,subject));save_data(data);flash('과목을 수정했습니다. 기존 계획은 자동 변경되지 않습니다.','success')
    except ValueError as e:flash(str(e),'error')
    return redirect(url_for('subjects'))  # 처리 후 지정한 화면으로 이동합니다.

@app.route('/subjects/<path:name>/delete',methods=['POST'])
@login_required

def delete_subject(name):  # 선택한 과목과 연결된 학습 데이터를 제거합니다.
    data=get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    if data['active_timer'] and data['active_timer']['subject']==name:
        flash('진행 중인 타이머를 먼저 종료해 주세요.','error')
    else:
        data['subjects']=[x for x in data['subjects'] if x['name']!=name]
        data['schedule']=[x for x in data['schedule'] if x['subject']!=name]
        data['logs']=[x for x in data['logs'] if x['subject']!=name]
        save_data(data);flash('과목과 관련 계획/기록을 삭제했습니다.','success')
    return redirect(url_for('subjects'))  # 처리 후 지정한 화면으로 이동합니다.

@app.route('/settings',methods=['GET','POST'])
@login_required

def settings():  # 요일별 자습 시간, 전체 마감일과 복습 간격을 표시하고 저장합니다.
    data=get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    if request.method=='POST':
        f=request.form  # f 변수에 이 줄의 계산 결과를 저장합니다.
        try:
            end=P.day_value(f.get('exam_date'));P.clock(f.get('start_time',''))  # 끝 위치 또는 종료 시각 값을 준비합니다.
            if not 0<=(end-P.today()).days<=365:raise ValueError('전체 마감일은 오늘부터 1년 이내로 설정해 주세요.')
            weekly={d:P.integer(f.get('weekday_'+str(i)),0,900,d+'요일 공부 시간') for i,d in enumerate(WEEKDAYS)}  # 요일별 자습 시간 값을 준비합니다.
            if not any(weekly.values()):raise ValueError('공부할 요일을 적어도 하나 설정해 주세요.')
            revisions=[P.integer(x,1,30,'복습 간격') for x in f.getlist('revision_days')]  # 설정한 복습 간격 값을 준비합니다.
            updated=dict(goal=f.get('goal','').strip()[:150] or '학습 목표',exam_date=end.isoformat(),weekday_minutes=weekly,  # updated 변수에 이 줄의 계산 결과를 저장합니다.
                         daily_minutes=weekly[WEEKDAYS[P.today().weekday()]],start_time=f['start_time'],study_days=[d for d in WEEKDAYS if weekly[d]>0],
                         session_minutes=P.integer(f.get('session_minutes'),15,120,'한 번의 집중 시간'),break_minutes=P.integer(f.get('break_minutes'),0,60,'휴식 시간'),revision_days=revisions)
            old_end=data['settings']['exam_date']  # old_end 변수에 이 줄의 계산 결과를 저장합니다.
            for sub in data['subjects']:
                if sub['deadline']==old_end:sub['deadline']=end.isoformat()
                elif sub['deadline']>end.isoformat():raise ValueError('전체 마감일보다 늦은 과목 마감일을 먼저 수정해 주세요.')
            data['settings'].update(updated);save_data(data);flash('공부 환경을 저장했습니다. 기존 계획은 유지됩니다.','success')
        except (ValueError,KeyError) as e:flash(str(e),'error')
        return redirect(url_for('settings'))  # 처리 후 지정한 화면으로 이동합니다.
    return render_template('settings.html',data=data,weekdays=WEEKDAYS)  # 템플릿에 값을 전달해 화면을 만듭니다.


def plan_values(f,data):  # 계획 입력값을 검사하고 저장할 일정 형태로 변환합니다.
    subject=next((x for x in data['subjects'] if x['name']==f.get('subject')),None)  # subject 변수에 이 줄의 계산 결과를 저장합니다.
    if not subject:raise ValueError('등록된 과목을 선택해 주세요.')
    day=P.day_value(f.get('date'));minutes=P.integer(f.get('minutes'),1,900,'예상 시간')  # 일정 또는 기록의 날짜 값을 준비합니다.
    task=f.get('task','').strip()  # 세부 학습 목표 값을 준비합니다.
    if not task or len(task)>500:raise ValueError('할 일은 1~500자로 입력해 주세요.')
    start=f.get('start','').strip() or '자율';end='자율'  # 시작 위치 또는 시작 시각 값을 준비합니다.
    if start!='자율':
        t=P.clock(start)  # t 변수에 이 줄의 계산 결과를 저장합니다.
        if t+minutes>1440:raise ValueError('자정을 넘는 계획은 날짜별로 나누어 주세요.')
        end=P.hhmm(t+minutes)  # 끝 위치 또는 종료 시각 값을 준비합니다.
    kind=f.get('kind','학습')  # kind 변수에 이 줄의 계산 결과를 저장합니다.
    if kind not in ['학습','복습']:raise ValueError('계획 구분을 확인해 주세요.')
    first=last=None  # 범위의 첫 번호 값을 준비합니다.
    if f.get('range_start') or f.get('range_end'):
        if subject['tracking_mode']=='시간 기반 자동':raise ValueError('쪽수/문제 범위는 과목에서 수량 진도 방식을 선택한 뒤 입력해 주세요.')
        lo,hi=P.bounds(subject);first=P.integer(f.get('range_start'),lo,hi,'시작 번호');last=P.integer(f.get('range_end'),first,hi,'끝 번호')  # 범위의 첫 번호 값을 준비합니다.
    return dict(subject=subject['name'],date=day.isoformat(),minutes=minutes,remaining_minutes=P.integer(f.get('remaining_minutes') or minutes,1,minutes,'남은 예상 시간'),task=task,start=start,end=end,
                kind=kind,range_start=first,range_end=last,book=f.get('book','').strip()[:150] or subject['book'],note=f.get('note','')[:2000])


def warnings(data):  # 일정의 시간 초과와 겹침을 안내합니다.
    result=[]  # 이 함수에서 계산한 결과 값을 준비합니다.
    for d in sorted(set(x['date'] for x in data['schedule'])):
        items=[x for x in data['schedule'] if x['date']==d]  # 해당 조건에 맞는 일정 값을 준비합니다.
        total=sum(x['minutes'] for x in items);cap=P.capacity(data,P.day_value(d))  # total 변수에 이 줄의 계산 결과를 저장합니다.
        if total>cap:result.append(f'{d}: 계획 {total}분 / 가능 {cap}분 (초과 {total-cap}분)')
        fixed=sorted((P.clock(x['start']),P.clock(x['start'])+x['minutes']) for x in items if x['start']!='자율')  # fixed 변수에 이 줄의 계산 결과를 저장합니다.
        if any(b>c for (_,b),(c,_) in zip(fixed,fixed[1:])):result.append(f'{d}: 시작 시간이 겹치는 계획이 있습니다.')
    return result  # 호출한 곳에 결과를 돌려줍니다.


def recommendation_signature(items, shortages):  # 추천 내용의 요약값으로 미리보기 이후 변경을 확인합니다.
    # 생성할 때마다 달라지는 내부 ID를 빼고 화면에 제시할 내용을 비교합니다.
    content = [{key: value for key, value in item.items() if key != 'id'} for item in items]  # content 변수에 이 줄의 계산 결과를 저장합니다.
    encoded = json.dumps([content, shortages], ensure_ascii=False, sort_keys=True)  # encoded 변수에 이 줄의 계산 결과를 저장합니다.
    return sha256(encoded.encode('utf-8')).hexdigest()  # 호출한 곳에 결과를 돌려줍니다.


@app.get('/schedule/recommendation')
@login_required

def schedule_recommendation():  # 추천 일정을 계산해 저장 전 화면에 표시합니다.
    data = get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    if not data['subjects']:
        flash('과목과 세부 학습 목표를 먼저 등록해 주세요.', 'error')
        return redirect(url_for('subjects'))  # 처리 후 지정한 화면으로 이동합니다.
    existing_count = len(data['schedule'])  # existing_count 변수에 이 줄의 계산 결과를 저장합니다.
    try:
        _, _, shortages = P.generate(data)
    except ValueError as error:
        flash(str(error), 'error')
        return redirect(url_for('schedule'))  # 처리 후 지정한 화면으로 이동합니다.
    items = data['schedule'][existing_count:]  # 해당 조건에 맞는 일정 값을 준비합니다.
    return render_template(
        'recommendation.html',
        items=sorted(items, key=lambda item: (item['date'], item['start'])),
        shortages=shortages,
        ranks={subject['name']: P.priority_rank(subject) for subject in data['subjects']},
        signature=recommendation_signature(items, shortages),
    )


@app.route('/schedule',methods=['GET','POST'])
@login_required

def schedule():  # 날짜별 계획을 조회하고 추가, 추천 저장, 재배분 요청을 처리합니다.
    data=get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    if request.method=='POST':
        try:
            action=request.form.get('action')  # 폼에서 요청한 동작 값을 준비합니다.
            if action=='generate':
                if not data['subjects']:raise ValueError('먼저 과목을 등록해 주세요.')
                existing_count = len(data['schedule'])  # existing_count 변수에 이 줄의 계산 결과를 저장합니다.
                n, r, shortages = P.generate(data)
                signature = request.form.get('recommendation_signature')  # 미리 본 추천 결과를 확인하는 값 값을 준비합니다.
                if signature and signature != recommendation_signature(data['schedule'][existing_count:], shortages):
                    flash('계획이나 설정이 바뀌었습니다. 새 추천 계획을 확인해 주세요.', 'error')
                    return redirect(url_for('schedule_recommendation'))  # 처리 후 지정한 화면으로 이동합니다.
                data['planning_report'] = shortages
                flash(f'학습 {n}개, 복습 {r}개를 추가했습니다. 기존 계획과 기록은 유지됩니다.','success')
            elif action=='redistribute':
                n,left=P.redistribute(data,P.day_value(request.form.get('cutoff')),P.day_value(request.form.get('start_date')))
                data['planning_report']=[f'미완료 {left}분을 배치하지 못했습니다. 원래 날짜에 남겨 두었습니다.'] if left else []
                flash(f'남은 공부를 {n}개 계획으로 나누어 배치했습니다.','success')
            elif action=='add':
                item=plan_values(request.form,data);item.update(id=uuid4().hex,done=False,source='manual');data['schedule'].append(item);flash('계획을 추가했습니다.','success')  # 학습 일정 한 건 값을 준비합니다.
            else:raise ValueError('요청을 확인해 주세요.')
            save_data(data)
        except (ValueError,KeyError) as e:flash(str(e),'error')
        return redirect(url_for('schedule',date=request.form.get('date') or P.today().isoformat()))  # 처리 후 지정한 화면으로 이동합니다.
    try:selected=P.day_value(request.args.get('date',P.today().isoformat())).isoformat()  # selected 변수에 이 줄의 계산 결과를 저장합니다.
    except ValueError:selected=P.today().isoformat()  # selected 변수에 이 줄의 계산 결과를 저장합니다.
    items=sorted([x for x in data['schedule'] if x['date']==selected],key=lambda x:(x['start']=='자율',x['start']))  # 해당 조건에 맞는 일정 값을 준비합니다.
    return render_template('schedule.html',data=data,selected=selected,items=items,warnings=warnings(data),tomorrow=(P.today()+timedelta(days=1)).isoformat())  # 템플릿에 값을 전달해 화면을 만듭니다.

@app.route('/schedule/<path:item_id>/update',methods=['POST'])
@login_required

def update_schedule(item_id):  # 기존 일정의 시간, 내용 및 완료 여부를 수정합니다.
    data=get_context();item=next((x for x in data['schedule'] if x['id']==item_id),None)  # 현재 계정의 공부 자료 값을 준비합니다.
    try:
        if not item:raise ValueError('계획을 찾을 수 없습니다.')
        values=plan_values(request.form,data)  # values 변수에 이 줄의 계산 결과를 저장합니다.
        if values['subject']!=item['subject'] and any(l.get('item_id')==item_id for l in data['logs']):raise ValueError('기록이 있는 계획의 과목은 변경할 수 없습니다.')
        item.update(values,done=request.form.get('done')=='on',source='manual');save_data(data);flash('계획을 수정했습니다.','success')
    except (ValueError,KeyError) as e:flash(str(e),'error')
    return redirect(url_for('schedule',date=item['date'] if item else P.today().isoformat()))  # 처리 후 지정한 화면으로 이동합니다.

@app.route('/schedule/<path:item_id>/delete',methods=['POST'])
@login_required

def delete_schedule(item_id):  # 선택한 일정을 삭제합니다.
    data=get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    if data['active_timer'] and data['active_timer'].get('item_id')==item_id:flash('타이머를 먼저 종료해 주세요.','error')
    else:
        data['schedule']=[x for x in data['schedule'] if x['id']!=item_id];save_data(data);flash('계획을 삭제했습니다. 실제 공부 기록은 보존됩니다.','success')
    return redirect(url_for('schedule'))  # 처리 후 지정한 화면으로 이동합니다.

@app.route('/progress',methods=['GET','POST'])
@login_required

def progress():  # 실제 학습 기록의 입력, 수정, 삭제 및 진도 조회를 처리합니다.
    data=get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    if request.method=='POST':
        try:
            f=request.form;action=f.get('action')  # f 변수에 이 줄의 계산 결과를 저장합니다.
            if action=='done':
                selected=P.day_value(f.get('date')).isoformat()  # selected 변수에 이 줄의 계산 결과를 저장합니다.
                for x in data['schedule']:
                    if x['date']==selected:x['done']=f.get(x['id'])=='on'
                flash('완료 상태를 저장했습니다. 실제 시간/수량은 별도로 기록해 주세요.','success')
            elif action in ['log','edit_log']:
                subject=next((s for s in data['subjects'] if s['name']==f.get('subject')),None)  # subject 변수에 이 줄의 계산 결과를 저장합니다.
                if not subject:raise ValueError('등록된 과목을 선택해 주세요.')
                day=P.day_value(f.get('date'))  # 일정 또는 기록의 날짜 값을 준비합니다.
                if day>P.today():raise ValueError('실제 기록은 오늘 또는 지난 날짜로 입력해 주세요.')
                seconds=P.integer(f.get('actual_minutes') or 0,0,1440,'실제 공부 시간')*60+P.integer(f.get('actual_seconds') or 0,0,59,'초')  # 실제 공부 시간(초) 값을 준비합니다.
                first=last=None;kind=f.get('kind','학습')  # 범위의 첫 번호 값을 준비합니다.
                if kind not in ['학습','복습']:raise ValueError('기록 구분을 확인해 주세요.')
                if f.get('range_start') or f.get('range_end'):
                    if subject['tracking_mode']=='시간 기반 자동':raise ValueError('수량 기록은 과목의 진도 방식을 먼저 변경해 주세요.')
                    lo,hi=P.bounds(subject);first=P.integer(f.get('range_start'),lo,hi,'실제 시작 번호');last=P.integer(f.get('range_end'),first,hi,'실제 끝 번호')  # 범위의 첫 번호 값을 준비합니다.
                if not seconds and first is None:raise ValueError('실제 시간 또는 완료한 범위를 입력해 주세요.')
                item_id=f.get('item_id') or None  # item_id 변수에 이 줄의 계산 결과를 저장합니다.
                if item_id and not any(x['id']==item_id and x['subject']==subject['name'] for x in data['schedule']):raise ValueError('같은 과목의 계획을 선택해 주세요.')
                values=dict(subject=subject['name'],date=day.isoformat(),seconds=seconds,range_start=first,range_end=last,note=f.get('note','')[:2000],kind=kind,item_id=item_id,source='manual')  # values 변수에 이 줄의 계산 결과를 저장합니다.
                if action=='edit_log':
                    log=next((l for l in data['logs'] if l['id']==f.get('log_id')),None)  # log 변수에 이 줄의 계산 결과를 저장합니다.
                    if not log:raise ValueError('기록을 찾을 수 없습니다.')
                    log.update(values)
                else:data['logs'].append(dict(values,id=uuid4().hex))
                flash('실제 기록을 저장했습니다. 번호가 겹치는 학습량은 한 번만 계산됩니다.','success')
            elif action=='delete_log':
                data['logs']=[l for l in data['logs'] if l['id']!=f.get('log_id')];flash('기록을 삭제했습니다.','success')
            else:raise ValueError('요청을 확인해 주세요.')
            save_data(data)
        except (ValueError,KeyError) as e:flash(str(e),'error')
        return redirect(url_for('progress',date=request.form.get('date') or P.today().isoformat()))  # 처리 후 지정한 화면으로 이동합니다.
    try:selected=P.day_value(request.args.get('date',P.today().isoformat())).isoformat()  # selected 변수에 이 줄의 계산 결과를 저장합니다.
    except ValueError:selected=P.today().isoformat()  # selected 변수에 이 줄의 계산 결과를 저장합니다.
    items=[x for x in data['schedule'] if x['date']==selected]  # 해당 조건에 맞는 일정 값을 준비합니다.
    logs=[x for x in data['logs'] if x['date']==selected]  # 실제 학습 기록 값을 준비합니다.
    return render_template('progress.html',data=data,selected=selected,items=items,logs=logs,subject_progress=lambda s,_:P.progress(s,data),actual_minutes=round(P.actual_seconds(data,day=selected)/60,1),planned_minutes=sum(x['minutes'] for x in items))  # 템플릿에 값을 전달해 화면을 만듭니다.

@app.route('/timer',methods=['POST'])
@login_required

def timer():  # 타이머 시작과 종료를 처리하고 실제 공부 시간을 날짜별로 기록합니다.
    data=get_context();f=request.form  # 현재 계정의 공부 자료 값을 준비합니다.
    try:
        if f.get('action')=='start':
            if data['active_timer']:raise ValueError('이미 실행 중인 타이머가 있습니다.')
            if not any(s['name']==f.get('subject') for s in data['subjects']):raise ValueError('과목을 선택해 주세요.')
            data['active_timer']=dict(subject=f['subject'],started=datetime.now(timezone.utc).isoformat())
            flash('타이머를 시작했습니다. 화면을 새로 열어도 이어집니다.','success')
        elif f.get('action')=='stop':
            active=data['active_timer']  # 실행 중인 타이머 값을 준비합니다.
            if not active:raise ValueError('실행 중인 타이머가 없습니다.')
            begin=datetime.fromisoformat(active['started']);end=datetime.now(timezone.utc)  # begin 변수에 이 줄의 계산 결과를 저장합니다.
            # 자정을 지났다면 한국 시간 날짜별로 기록을 나눕니다.
            cursor=begin  # 다음으로 계산할 위치 값을 준비합니다.
            while cursor<end:
                local=cursor.astimezone(P.KST)  # local 변수에 이 줄의 계산 결과를 저장합니다.
                boundary=datetime.combine(local.date()+timedelta(days=1),datetime.min.time(),tzinfo=P.KST)  # 한국 시간 기준 다음 자정 값을 준비합니다.
                finish=min(end,boundary);seconds=int((finish-cursor).total_seconds())  # finish 변수에 이 줄의 계산 결과를 저장합니다.
                if seconds>0:data['logs'].append(dict(id=uuid4().hex,subject=active['subject'],date=local.date().isoformat(),seconds=seconds,range_start=None,range_end=None,note='타이머 기록',kind='학습',item_id=None,source='timer'))
                cursor=finish  # 다음으로 계산할 위치 값을 준비합니다.
            data['active_timer']=None;flash('타이머 시간을 저장했습니다. 완료 범위는 진도 화면에서 추가할 수 있습니다.','success')
        elif f.get('action')=='cancel':data['active_timer']=None;flash('실행 중인 타이머를 기록 없이 취소했습니다.','success')
        else:raise ValueError('요청을 확인해 주세요.')
        save_data(data)
    except ValueError as e:flash(str(e),'error')
    return redirect(url_for('dashboard'))  # 처리 후 지정한 화면으로 이동합니다.

@app.route("/calendar")
@login_required

def calendar_view():  # 선택한 달의 날짜와 일정 개수를 계산합니다.
    data = get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    today = P.today()  # today 변수에 이 줄의 계산 결과를 저장합니다.
    try:
        year = P.integer(request.args.get("year", today.year),1901,9998,"연도")  # year 변수에 이 줄의 계산 결과를 저장합니다.
        month = P.integer(request.args.get("month", today.month),1,12,"월")  # month 변수에 이 줄의 계산 결과를 저장합니다.
    except ValueError:
        year,month=today.year,today.month
    cal = calendar.Calendar(firstweekday=0)  # 월간 달력 계산기 값을 준비합니다.
    weeks = cal.monthdatescalendar(year, month)  # 달력을 구성할 주별 날짜 목록 값을 준비합니다.
    counts = {}  # 날짜별 일정 개수 값을 준비합니다.
    for item in data["schedule"]:
        counts[item["date"]] = counts.get(item["date"], 0) + 1
    prev_month = (date(year, month, 1) - timedelta(days=1))  # prev_month 변수에 이 줄의 계산 결과를 저장합니다.
    next_month = (date(year, month, calendar.monthrange(year, month)[1]) + timedelta(days=1))  # next_month 변수에 이 줄의 계산 결과를 저장합니다.
    return render_template("calendar.html", data=data, weeks=weeks, counts=counts, year=year, month=month,
                           prev_year=prev_month.year, prev_month=prev_month.month,
                           next_year=next_month.year, next_month=next_month.month)


@app.route("/export/day/<selected>")
@login_required

def export_day(selected):  # 선택한 날짜의 계획을 PDF로 생성해 내려보냅니다.
    from reportlab.lib.pagesizes import A4  # 이 코드에서 쓰는 reportlab.lib.pagesizes 모듈 또는 도구를 불러옵니다.
    from reportlab.pdfgen import canvas  # 이 코드에서 쓰는 reportlab.pdfgen 모듈 또는 도구를 불러옵니다.
    from reportlab.pdfbase import pdfmetrics  # 이 코드에서 쓰는 reportlab.pdfbase 모듈 또는 도구를 불러옵니다.
    from reportlab.pdfbase.ttfonts import TTFont  # 이 코드에서 쓰는 reportlab.pdfbase.ttfonts 모듈 또는 도구를 불러옵니다.
    data = get_context()  # 현재 계정의 공부 자료 값을 준비합니다.
    items = [x for x in data["schedule"] if x["date"] == selected]  # 해당 조건에 맞는 일정 값을 준비합니다.
    buffer = BytesIO()  # PDF를 임시 보관할 메모리 공간 값을 준비합니다.
    c = canvas.Canvas(buffer, pagesize=A4)  # c 변수에 이 줄의 계산 결과를 저장합니다.
    width, height = A4
    font_name = "Helvetica"  # PDF에 사용할 글꼴 값을 준비합니다.
    candidates = [  # 현재 배치할 수 있는 후보 값을 준비합니다.
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.suffix.lower() == ".ttf":
            try:
                pdfmetrics.registerFont(TTFont("Korean", str(candidate)))
                font_name = "Korean"  # PDF에 사용할 글꼴 값을 준비합니다.
                break
            except Exception:
                pass
    c.setFont(font_name, 16)
    c.drawString(48, height - 55, f"STUDY PLANNER - {selected}")
    c.setFont(font_name, 10)
    y = height - 90  # y 변수에 이 줄의 계산 결과를 저장합니다.
    if not items:
        c.drawString(48, y, "No study plan.")
    for item in items:
        line = f'{item.get("start","")}  {item["subject"]}  {item["task"]}  ({item["minutes"]} min)  {"DONE" if item.get("done") else ""}'  # line 변수에 이 줄의 계산 결과를 저장합니다.
        c.drawString(48, y, line[:100])
        y -= 22  # y 변수에 이 줄의 계산 결과를 저장합니다.
        if y < 55:
            c.showPage()
            c.setFont(font_name, 10)
            y = height - 55  # y 변수에 이 줄의 계산 결과를 저장합니다.
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"study_plan_{selected}.pdf", mimetype="application/pdf")  # 생성한 파일을 다운로드 응답으로 보냅니다.


@app.get('/sw.js')
def service_worker():
    # 사이트 최상위 주소에서 스크립트를 제공해 전체 앱 경로에 적용합니다.
    response = app.send_static_file('sw.js')  # 브라우저로 돌려줄 응답 값을 준비합니다.
    response.headers['Cache-Control'] = 'no-cache'
    return response  # 호출한 곳에 결과를 돌려줍니다.


@app.context_processor

def inject_today():  # 화면에서 공통으로 사용할 오늘 날짜를 제공합니다.
    return {"today": P.today()}  # 호출한 곳에 결과를 돌려줍니다.


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
