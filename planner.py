# 시간표 배분과 학습 진도 계산을 담당합니다.
"""계획 계산: 화면/DB와 분리하여 수행평가에서 알고리즘을 설명하고 검사할 수 있습니다."""
import math  # 이 코드에서 쓰는 math 모듈 또는 도구를 불러옵니다.
from datetime import date, datetime, timedelta, timezone  # 날짜·시각과 시간 차이를 계산합니다.
from uuid import uuid4  # 일정에 쓸 고유 ID를 생성합니다.

KST = timezone(timedelta(hours=9))  # KST 변수에 이 줄의 계산 결과를 저장합니다.
WEEKDAYS = ['월','화','수','목','금','토','일']  # WEEKDAYS 변수에 이 줄의 계산 결과를 저장합니다.
MODES = ['시간 기반 자동','쪽수','문제 수','단어 수']  # MODES 변수에 이 줄의 계산 결과를 저장합니다.


def today():  # 한국 시간 기준 오늘 날짜를 반환합니다.
    return datetime.now(KST).date()  # 호출한 곳에 결과를 돌려줍니다.


def integer(value, low, high, label):  # 입력을 정수로 바꾸고 허용 범위를 확인합니다.
    try:
        number = int(value)  # number 변수에 이 줄의 계산 결과를 저장합니다.
    except (ValueError, TypeError):
        raise ValueError(f'{label}: 정수를 입력해 주세요.')
    if not low <= number <= high:
        raise ValueError(f'{label}: {low}~{high} 범위로 입력해 주세요.')
    return number  # 호출한 곳에 결과를 돌려줍니다.


def day_value(value):  # 문자열을 날짜로 바꿉니다.
    try:
        return date.fromisoformat(value)  # 호출한 곳에 결과를 돌려줍니다.
    except (ValueError, TypeError):
        raise ValueError('날짜를 확인해 주세요.')


def clock(value):  # 시각을 자정 이후 몇 분인지로 바꿉니다.
    try:
        h,m = map(int,value.split(':'))
        if not (0 <= h < 24 and 0 <= m < 60): raise ValueError()
        return h*60+m  # 호출한 곳에 결과를 돌려줍니다.
    except (ValueError, AttributeError):
        raise ValueError('시작 시간은 시:분 형식으로 입력해 주세요.')


def hhmm(minutes):  # 자정 이후 분을 화면에 표시할 시각으로 바꿉니다.
    return f'{minutes//60:02d}:{minutes%60:02d}'  # 호출한 곳에 결과를 돌려줍니다.


def normalize(data):  # 이전 저장 데이터에 필요한 기본값을 채웁니다.
    settings = data['settings']  # 자습 시간과 마감일 설정 값을 준비합니다.
    for k,v in dict(goal='시험 준비',session_minutes=50,break_minutes=10,start_time='18:00',revision_days=[]).items():settings.setdefault(k,v)
    settings.setdefault('weekday_minutes',{d:settings.get('daily_minutes',240) if d in settings.get('study_days',WEEKDAYS) else 0 for d in WEEKDAYS})
    data.setdefault('logs',[])
    data.setdefault('active_timer',None)
    for s in data['subjects']:
        s.setdefault('deadline',settings['exam_date'])
        s.setdefault('note','')
        s.setdefault('minutes_per_unit',5)
        s.setdefault('target_minutes',600)
        if s['tracking_mode']=='쪽수':
            s['unit_total']=s['end_page']-s['start_page']+1
            s['unit_done']=min(s['unit_total'],max(s.get('unit_done',0),s.get('current_page',s['start_page'])-s['start_page']))
    for item in data['schedule']:
        for k,v in dict(id=uuid4().hex,note='',book='',range_start=None,range_end=None,source='manual',remaining_minutes=item['minutes']).items():item.setdefault(k,v)
    return data  # 호출한 곳에 결과를 돌려줍니다.


def bounds(s):  # 과목의 전체 학습 번호 범위를 구합니다.
    first=s['start_page'] if s['tracking_mode']=='쪽수' else 1  # 범위의 첫 번호 값을 준비합니다.
    return first, first+s['unit_total']-1  # 호출한 곳에 결과를 돌려줍니다.


def merge_ranges(ranges):  # 겹치거나 이어지는 번호 범위를 합칩니다.
    merged=[]  # merged 변수에 이 줄의 계산 결과를 저장합니다.
    for a,b in sorted(ranges):
        if merged and a<=merged[-1][1]+1:merged[-1]=(merged[-1][0],max(merged[-1][1],b))
        else:merged.append((a,b))
    return merged  # 호출한 곳에 결과를 돌려줍니다.


def subtract_ranges(first,last,ranges):  # 전체 범위에서 이미 처리한 번호를 빼고 남은 범위를 구합니다.
    result=[]; cursor=first  # 이 함수에서 계산한 결과 값을 준비합니다.
    for a,b in merge_ranges(ranges):
        if b<cursor:continue
        if a>last:break
        if a>cursor:result.append((cursor,min(last,a-1)))
        cursor=max(cursor,b+1)  # 다음으로 계산할 위치 값을 준비합니다.
    if cursor<=last:result.append((cursor,last))
    return result  # 호출한 곳에 결과를 돌려줍니다.


def completed_ranges(s, data):  # 과목에서 실제 완료한 번호 범위를 모읍니다.
    first,last=bounds(s)
    ranges=[(first,first+s.get('unit_done',0)-1)] if s.get('unit_done',0) else []  # 번호의 시작과 끝 범위 값을 준비합니다.
    ranges += [(max(first,l['range_start']),min(last,l['range_end'])) for l in data['logs'] if l['subject']==s['name'] and l.get('range_start') is not None and l.get('kind')!='복습']  # 번호의 시작과 끝 범위을 갱신합니다.
    return merge_ranges([(a,b) for a,b in ranges if a<=b])  # 호출한 곳에 결과를 돌려줍니다.


def actual_seconds(data, subject=None, day=None):  # 조건에 해당하는 실제 공부 시간을 초 단위로 합산합니다.
    return sum(l['seconds'] for l in data['logs'] if (subject is None or l['subject']==subject) and (day is None or l['date']==day))  # 호출한 곳에 결과를 돌려줍니다.


def progress(s,data):  # 목표 시간이나 목표 수량에 대한 실제 진도를 계산합니다.
    if s['tracking_mode']=='시간 기반 자동':
        return round(min(100,actual_seconds(data,s['name'])/max(1,s['target_minutes']*60)*100),1)  # 호출한 곳에 결과를 돌려줍니다.
    done=sum(b-a+1 for a,b in completed_ranges(s,data))  # done 변수에 이 줄의 계산 결과를 저장합니다.
    return round(min(100,done/max(1,s['unit_total'])*100),1)  # 호출한 곳에 결과를 돌려줍니다.


def capacity(data,day):  # 해당 요일의 자습 가능 시간을 확인합니다.
    return int(data['settings']['weekday_minutes'][WEEKDAYS[day.weekday()]])  # 호출한 곳에 결과를 돌려줍니다.


def free_slots(data,day):  # 기존 일정과 휴식 시간을 고려해 빈 시간을 찾습니다.
    """기존 계획과 휴식 사이의 빈 구간만 반환. 순공 가능량과 자정 경계를 모두 지킵니다."""
    st=data['settings']; start=clock(st['start_time']); rest=st['break_minutes']  # st 변수에 이 줄의 계산 결과를 저장합니다.
    items=[x for x in data['schedule'] if x['date']==day.isoformat()]  # 해당 조건에 맞는 일정 값을 준비합니다.
    budget=max(0,capacity(data,day)-sum(x['minutes'] for x in items))  # 해당 날짜에 남은 자습 시간 값을 준비합니다.
    busy=[]; floating=0  # busy 변수에 이 줄의 계산 결과를 저장합니다.
    for x in items:
        if x['start']=='자율':floating+=x['minutes']+rest  # floating 변수에 이 줄의 계산 결과를 저장합니다.
        else:
            t=clock(x['start']);busy.append((max(start,t-rest),min(1440,t+x['minutes']+rest)))  # t 변수에 이 줄의 계산 결과를 저장합니다.
    start=min(1440,start+floating)  # 시작 위치 또는 시작 시각 값을 준비합니다.
    gaps=[];cur=start  # gaps 변수에 이 줄의 계산 결과를 저장합니다.
    for a,b in merge_ranges(busy):
        if a>cur:gaps.append((cur,a))
        cur=max(cur,b)  # cur 변수에 이 줄의 계산 결과를 저장합니다.
    if cur<1440:gaps.append((cur,1440))
    return [(a,min(b,a+budget)) for a,b in gaps if b>a and budget>0],budget  # 호출한 곳에 결과를 돌려줍니다.


def make_item(s, day, start, minutes, task, **extra):  # 저장 가능한 새 계획 항목을 만듭니다.
    return dict(id=uuid4().hex,subject=s['name'],date=day.isoformat(),start=hhmm(start),end=hhmm(start+minutes),minutes=minutes,remaining_minutes=minutes,task=task,kind='학습',done=False,range_start=None,range_end=None,book=s.get('book',''),note='',source='auto',**extra)  # 호출한 곳에 결과를 돌려줍니다.


def unplanned(s,data):  # 기존 기록과 계획을 제외한 학습량을 계산합니다.
    if s['tracking_mode']=='시간 기반 자동':
        committed=sum(x.get('remaining_minutes',x['minutes']) for x in data['schedule'] if x['subject']==s['name'] and not x['done'] and x['kind']=='학습')  # committed 변수에 이 줄의 계산 결과를 저장합니다.
        return max(0,s['target_minutes']-math.ceil(actual_seconds(data,s['name'])/60)-committed)  # 호출한 곳에 결과를 돌려줍니다.
    first,last=bounds(s)
    reserved=completed_ranges(s,data)+[(x['range_start'],x['range_end']) for x in data['schedule'] if x['subject']==s['name'] and x.get('range_start') is not None and x['kind']=='학습']  # reserved 변수에 이 줄의 계산 결과를 저장합니다.
    return subtract_ranges(first,last,reserved)  # 호출한 곳에 결과를 돌려줍니다.


def priority_rank(subject):  # 이전 중요도 설정도 사용할 수 있도록 1~3순위로 해석합니다.
    if 'priority_rank' in subject:
        return subject['priority_rank']  # 호출한 곳에 결과를 돌려줍니다.
    # 기존 1~5 중요도는 높음 / 보통 / 낮음의 세 단계로 옮깁니다.
    importance = subject.get('importance', 3)  # importance 변수에 이 줄의 계산 결과를 저장합니다.
    if importance >= 4:
        return 1  # 호출한 곳에 결과를 돌려줍니다.
    return 2 if importance == 3 else 3  # 호출한 곳에 결과를 돌려줍니다.



def generate(data):  # 마감일, 순위와 빈 시간에 맞춰 학습 및 복습 계획을 만듭니다.
    """기존 계획은 보존하고 남은 목표만 배분. 빠른 마감일 우선, 같은 마감일은 1~3순위를 반영합니다."""
    start=today(); horizon=day_value(data['settings']['exam_date'])  # 시작 위치 또는 시작 시각 값을 준비합니다.
    if horizon<start:raise ValueError('설정에서 앞으로의 마감일을 지정해 주세요.')
    if (horizon-start).days>365:raise ValueError('자동 계획은 최대 1년 범위에서 생성할 수 있습니다.')
    pending={s['name']:unplanned(s,data) for s in data['subjects']}  # 과목별 미배정 학습량 값을 준비합니다.
    assigned={s['name']:0 for s in data['subjects']}; added=[]  # 과목별로 이미 배정한 분량 값을 준비합니다.
    ranks = {s['name']: priority_rank(s) for s in data['subjects']}  # 과목별 우선순위 값을 준비합니다.
    def allocation_order(subject):
        name = subject['name']  # 과목 또는 사용자 이름 값을 준비합니다.
        rank = ranks[name]  # 과목의 우선순위 값을 준비합니다.
        return subject['deadline'], assigned[name] / (4 - rank), rank, -subject['difficulty'], name  # 호출한 곳에 결과를 돌려줍니다.

    st=data['settings']  # st 변수에 이 줄의 계산 결과를 저장합니다.
    for offset in range((horizon-start).days+1):
        day=start+timedelta(days=offset)  # 일정 또는 기록의 날짜 값을 준비합니다.
        while True:
            slots,budget=free_slots(data,day)
            candidates=[]  # 현재 배치할 수 있는 후보 값을 준비합니다.
            for s in data['subjects']:
                rate=1 if s['tracking_mode']=='시간 기반 자동' else s['minutes_per_unit']  # 단위당 소요 시간 값을 준비합니다.
                if pending[s['name']] and day<=day_value(s['deadline']) and any(min(b-a,budget,st['session_minutes'])>=rate for a,b in slots):candidates.append(s)
            if not candidates:break
            s = min(candidates, key=allocation_order)  # s 변수에 이 줄의 계산 결과를 저장합니다.
            rate=1 if s['tracking_mode']=='시간 기반 자동' else s['minutes_per_unit']  # 단위당 소요 시간 값을 준비합니다.
            a,b=next((a,b) for a,b in slots if min(b-a,budget,st['session_minutes'])>=rate)
            limit=min(b-a,budget,st['session_minutes']); work=pending[s['name']]  # limit 변수에 이 줄의 계산 결과를 저장합니다.
            if isinstance(work,int):
                minutes=min(limit,work);pending[s['name']]-=minutes  # 공부 시간(분) 값을 준비합니다.
                item=make_item(s,day,a,minutes,s['task'])  # 학습 일정 한 건 값을 준비합니다.
            else:
                first,last=work[0];count=min(last-first+1,limit//rate);end=first+count-1  # count 변수에 이 줄의 계산 결과를 저장합니다.
                minutes=count*rate  # 공부 시간(분) 값을 준비합니다.
                item=make_item(s,day,a,minutes,f"{s['task']} · {first}~{end} ({s['tracking_mode']})")  # 학습 일정 한 건 값을 준비합니다.
                item.update(range_start=first,range_end=end)
                if end==last:work.pop(0)
                else:work[0]=(end+1,last)
            data['schedule'].append(item);added.append(item);assigned[s['name']]+=minutes
    # 과목/학습일마다 복습을 한 번씩 배치하며, 복습도 하루 가능 시간을 소비합니다.
    reviews=0;missing_reviews=0  # reviews 변수에 이 줄의 계산 결과를 저장합니다.
    sources={(x['subject'],x['date']) for x in data['schedule'] if x['kind']=='학습'}  # sources 변수에 이 줄의 계산 결과를 저장합니다.
    for name,source_day in sorted(sources):
        for gap in st['revision_days']:
            rd=day_value(source_day)+timedelta(days=gap)  # rd 변수에 이 줄의 계산 결과를 저장합니다.
            if rd<start:continue
            key=f'{name}|{source_day}|{gap}'  # key 변수에 이 줄의 계산 결과를 저장합니다.
            if any(x.get('review_key')==key for x in data['schedule']):continue
            s=next((s for s in data['subjects'] if s['name']==name),None)  # s 변수에 이 줄의 계산 결과를 저장합니다.
            if s is None:continue
            if rd>min(horizon,day_value(s['deadline'])):missing_reviews+=1;continue  # missing_reviews 변수에 이 줄의 계산 결과를 저장합니다.
            slots,budget=free_slots(data,rd)
            slot=next(((a,b) for a,b in slots if min(b-a,budget)>=15),None)  # 사용 가능한 시간 구간 값을 준비합니다.
            if not slot:missing_reviews+=1;continue  # missing_reviews 변수에 이 줄의 계산 결과를 저장합니다.
            item=make_item(s,rd,slot[0],15,f'{source_day} 학습 내용 복습')  # 학습 일정 한 건 값을 준비합니다.
            item.update(kind='복습',review_key=key);data['schedule'].append(item);reviews+=1  # reviews 변수에 이 줄의 계산 결과를 저장합니다.
    shortages=[]  # 배정하지 못한 학습량 안내 값을 준비합니다.
    for s in data['subjects']:
        work=pending[s['name']]  # work 변수에 이 줄의 계산 결과를 저장합니다.
        minutes=work if isinstance(work,int) else sum(b-a+1 for a,b in work)*s['minutes_per_unit']  # 공부 시간(분) 값을 준비합니다.
        if minutes:shortages.append(f"{s['name']}: 학습 {minutes}분 미배정")
    if missing_reviews:shortages.append(f'복습 {missing_reviews}회({missing_reviews*15}분) 미배정: 마감일 또는 여유 시간 확인')
    return len(added),reviews,shortages  # 호출한 곳에 결과를 돌려줍니다.


def redistribute(data, cutoff, start):  # 미완료 계획을 이후의 빈 시간에 나누어 배치합니다.
    """미완료 계획만 이동/분할. 기록은 원본 ID에 남기고 빈 시간에 남은 분량을 배치합니다."""
    if start<today():raise ValueError('옮길 시작 날짜는 오늘 이후여야 합니다.')
    horizon=day_value(data['settings']['exam_date'])  # 계획을 배치할 마지막 날짜 값을 준비합니다.
    if start>horizon or (horizon-start).days>365:raise ValueError('시작일과 마감일을 확인해 주세요.')
    targets=[x for x in data['schedule'] if not x['done'] and x['date']<=cutoff.isoformat()]  # targets 변수에 이 줄의 계산 결과를 저장합니다.
    moved=0;unallocated=0  # moved 변수에 이 줄의 계산 결과를 저장합니다.
    for item in targets:
        s=next(s for s in data['subjects'] if s['name']==item['subject'])  # s 변수에 이 줄의 계산 결과를 저장합니다.
        data['schedule'].remove(item)
        ranges=None  # 번호의 시작과 끝 범위 값을 준비합니다.
        if item.get('range_start') is not None:
            ranges=subtract_ranges(item['range_start'],item['range_end'],completed_ranges(s,data) if item['kind']=='학습' else [])  # 번호의 시작과 끝 범위 값을 준비합니다.
        remaining=item.get('remaining_minutes',item['minutes']) if ranges is None else sum(b-a+1 for a,b in ranges)*s['minutes_per_unit']  # 아직 배치하지 못한 분량 값을 준비합니다.
        original_remaining=remaining  # original_remaining 변수에 이 줄의 계산 결과를 저장합니다.
        for off in range((horizon-start).days+1):
            day=start+timedelta(days=off)  # 일정 또는 기록의 날짜 값을 준비합니다.
            if day>day_value(s['deadline']):break
            while remaining>0:
                slots,budget=free_slots(data,day);rate=s['minutes_per_unit'] if ranges is not None else 1  # 단위당 소요 시간 값을 준비합니다.
                slot=next(((a,b) for a,b in slots if min(b-a,budget,data['settings']['session_minutes'])>=rate),None)  # 사용 가능한 시간 구간 값을 준비합니다.
                if not slot:break
                a,b=slot;limit=min(b-a,budget,data['settings']['session_minutes'])  # limit 변수에 이 줄의 계산 결과를 저장합니다.
                clone=dict(item,id=uuid4().hex,date=day.isoformat(),start=hhmm(a),done=False,source='rescheduled',origin_id=item.get('origin_id',item['id']))  # clone 변수에 이 줄의 계산 결과를 저장합니다.
                if ranges is not None:
                    first,last=ranges[0];count=min(last-first+1,limit//rate);end=first+count-1;minutes=count*rate  # count 변수에 이 줄의 계산 결과를 저장합니다.
                    clone.update(range_start=first,range_end=end,task=f"{s['task']} · {first}~{end} ({s['tracking_mode']})")
                    if end==last:ranges.pop(0)
                    else:ranges[0]=(end+1,last)
                else:minutes=min(limit,remaining)  # 공부 시간(분) 값을 준비합니다.
                clone.update(minutes=minutes,remaining_minutes=minutes,end=hhmm(a+minutes))
                data['schedule'].append(clone);remaining-=minutes;moved+=1  # 아직 배치하지 못한 분량을 갱신합니다.
        if remaining:
            if ranges is None:
                item.update(minutes=remaining,remaining_minutes=remaining,start='자율',end='자율');data['schedule'].append(item)
            else:
                for i,(a,b) in enumerate(ranges):
                    clone=dict(item,id=item['id'] if i==0 else uuid4().hex,range_start=a,range_end=b,minutes=(b-a+1)*s['minutes_per_unit'],remaining_minutes=(b-a+1)*s['minutes_per_unit'],start='자율',end='자율',task=f"{s['task']} · {a}~{b} ({s['tracking_mode']})")  # clone 변수에 이 줄의 계산 결과를 저장합니다.
                    data['schedule'].append(clone)
            unallocated+=remaining  # unallocated 변수에 이 줄의 계산 결과를 저장합니다.
        # 이미 수행한 원본 계획 부분을 보존해 기록과 완료 내역을 잃지 않습니다.
        spent=item['minutes']-original_remaining  # spent 변수에 이 줄의 계산 결과를 저장합니다.
        if any(l.get('item_id')==item['id'] for l in data['logs']) and not any(x['id']==item['id'] for x in data['schedule']):
            history=dict(item,done=True,minutes=max(0,spent),remaining_minutes=0,range_start=None,range_end=None,task=item['task']+' (진행 기록)',source='history',start='자율',end='자율')  # history 변수에 이 줄의 계산 결과를 저장합니다.
            data['schedule'].append(history)
    return moved,unallocated  # 호출한 곳에 결과를 돌려줍니다.
