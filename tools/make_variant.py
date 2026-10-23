#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""뉴스레이다 고용노동부판(김동빈 기자용) 생성기.

원본(tolibre/news-monitor — 김광일 기자 출입처판)의 파일을 그대로 가져와
'출입처·바이라인·브라우저 저장키·보관 기간' 같은 설정만 바꿔 이 저장소에 쓴다.
(기후·문체판 tolibre/newsradar-climate-culture 생성기와 같은 구조 — 설정 블록만 다르다.)

  python tools/make_variant.py <원본 저장소 경로> [<출력 경로, 기본=이 저장소>]

- 치환마다 '원본에서 정확히 몇 번 나와야 하는지'를 적어 두고, 다르면 아무 파일도
  쓰지 않고 멈춘다.
- 원본 쪽 파일은 읽기만 한다. 함수는 바꾸지 않는다(설정·문구만).
- 원본의 주체 출입처 배정·'전체' 탭 주체 가점(+2)·주요 매체 가점(+1)·사진 설명형 제목 거르기는
  원본 값 그대로 쓴다(김광일판과 같음).
"""
import hashlib, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import social_team as ST   # 사회정책팀 휴일 특근 묶음(세 저장소 공용 사본)

# ---------------------------------------------------------------- 설정값 ---
REPORTER = "김동빈"                       # 노컷 원문 author 메타 'CBS노컷뉴스 김동빈 기자'로 가정 — 첫 실행 로그로 확인할 것
BEATS_TITLE = "고용노동부·노동"
STORE_PREFIX = "nm-lab-"                  # 브라우저 저장키 — 원본('nm-live-')·재경부('nm-moef-')·국회('nm-asm-')·산업부('nm-ind-')·
                                          # 기후문체('nm-cc-')·복지보건('nm-wel-')과 같은 출처(tolibre.github.io)라 반드시 달라야 한다
# 섹션 순서: 부처(노동부) → 사안어 '노동'. 그룹명 '노동부' = 제목에서 가장 흔한 이름(원본 DB 제목 실측 10/22:
# 노동부 57 · 고용노동부 24 · 고용부 11).
GROUPS = ["노동부", "노동"]
REPORT_ORDER_JS = "[" + ",".join(f"'{g}'" for g in GROUPS) + "]"

NEW_BASE_KEYWORDS = '''BASE_KEYWORDS = [
    # 뉴스레이다 고용노동부판(tools/make_variant.py가 생성 — 직접 고치지 말 것).
    # 김동빈 기자가 평소 검색하는 '고용노동부'·'노동'(사용자 10/22) + 제목 약칭 노동부·고용부.
    # 부처 이름이 '노동'보다 앞이어야 '고용노동부' 제목 기사가 노동부 섹션으로 간다(KEYWORDS 순서 = 섹션 판정 순서).
    "고용노동부", "노동부", "고용부",
    # 제목 약칭 '노동장관·노동차관'(예: '김영훈 노동장관 "정년연장 연내 처리"')은 검색하지 않고(KEYWORD_MAX_PAGES 0)
    # 제목 판정에만 쓴다 — 없으면 이런 기사가 '노동' 섹션으로 간다(국회판 정당 약칭과 같은 방식).
    "노동장관", "노동차관",
    # '노동'은 사안어(원본 누리호·산업부판 대미투자와 같은 자리) — KEYWORD_GROUPS에 매핑하지 않는다(0-28 교훈:
    # 출입처명 토큰·주체 판정 단서에 들어가면 그 한 단어로 다른 사안이 묶인다).
    "노동",
]
'''
NEW_GROUPS_LINE = ("KEYWORD_GROUPS.update(DUTY_KEYWORD_GROUPS)\n"
                   "KEYWORD_GROUPS.update({'고용노동부': '노동부', '노동부': '노동부', '고용부': '노동부',\n"
                   "                       '노동장관': '노동부', '노동차관': '노동부'})   # 노동판(생성기)\n")
# 단어 일부 오매칭 예방: '고용부진·고용부담·고용부문·고용부족·고용부채'(경제 기사에 흔함),
# '노동신문'·'조선노동당'(북한), '노동당'(단, '노동당국'은 노동 사안이라 남긴다), 매체명 '매일노동뉴스'.
# (0-67부터 안 씀 — 오탐 규칙은 tools/social_team.py의 ANTI가 팀 전체 몫으로 넣는다)
NEW_ANTI = ('    "개인정보위": [],\n'
            '    "고용부":   [r"고용부진", r"고용부담", r"고용부문", r"고용부족", r"고용부채"],   # 노동판(생성기)\n'
            '    "노동":     [r"노동신문", r"조선노동당", r"노동당(?!국)", r"매일노동뉴스"],   # 노동판(생성기)\n')

# '노동' 섹션 '관련 약함' 접기(원본 0-69 LIVE_FOLD_KEEP 자리) — 0-76(10/23 판별 점검, 사용자 "그러자").
# '노동' 섹션은 하루 1,881건(본문 매칭 79%), 10/23 14:00 보고 117묶음으로 열한 판 중 가장 컸다. 제목에 아래 노동 관련 말이
# 하나도 없는 묶음(본문에만 '노동'이 스친 연예·지역행사·외신 기사)을 섹션 끝에 접는다 — 24시간 재생 1,881건 중 997건(53%).
# 접힌 쪽 표본에서 소관 기사였던 '업무상 질병 5년새 2배…조사인력 제자리'·'장애인 표준사업장 점검 구멍' 때문에 '업무상'·'사업장'을 넣었다. [단독]은 접지 않는다(원본 규칙).
# 당직 섹션 '노동' 접기(social_team.py DUTY_FOLD_GROUPS — 다른 판에서만)와 별개로 이 판 본 섹션에만 건다.
_LABOR_WORDS = ["노동", "노조", "노사", "근로", "임금", "파업", "고용", "일자리", "실업", "산재", "중대재해", "산업안전", "업무상",
                "52시간", "4.5일", "비정규", "하청", "해고", "채용", "취업", "노란봉투", "교섭", "쟁의", "노총", "근무", "퇴직",
                "정년", "육아휴직", "직장", "갑질", "체불", "외국인력", "일하", "사업장"]
FOLD_KEEP = {"노동": {"keep": [], "fold": [], "need": [re.escape(w) for w in _LABOR_WORDS],
                     "label": "관련 약함",
                     "desc": "노동 섹션에서 제목에 노동·노조·임금·파업·고용·일자리·산재 같은 말이 하나도 없는 묶음 — 본문에만 ‘노동’이 스친 기사 — 을 섹션 끝에 접어 둡니다. [단독]은 접지 않고, 건수에는 포함합니다."}}

# 기관장 이름 씨앗 — 김영훈 장관(10/13 국감 기사로 확인). 차관은 확인 못 해 DB 학습에 맡김. 인사가 바뀌면 고칠 것.
SEED = {"김영훈": "노동부"}

# (파일, 찾을 문자열 또는 정규식, 바꿀 문자열, 원본에서 나와야 하는 횟수, 정규식 여부)
NM = "news_monitor.py"
RP = "render_page.py"

REPLACEMENTS = [
    # ---- news_monitor.py: 출입처 ----
    # 0-44·0-67: 휴일 특근 — 원본은 경제정책팀 8곳을 당직으로 모은다. 사회정책팀 판은 그 묶음을 팀 묶음(social_team.py)으로
    # 바꾸고 DUTY_COLLECT는 원본 값(True) 그대로 둔다(사용자 10/22 "세 명을 그룹화해서 휴일 당직 기능을 만들자").
    *ST.replacements(NM, RP, GROUPS, FOLD_KEEP),   # 0-72 당직 섹션 접기 + 0-76 노동 섹션 관련 약함
    # 0-46: 원본의 EXCLUDE_TERMS(대한체육회·스포츠공정위·모의공정위)는 '공정위' 검색어 오탐용이다. 이 판은 '공정위'를
    # 검색하지 않으니 끈다(기후·문체판 0-46과 같음).
    (NM, r"EXCLUDE_TERMS = \[\n(?:.*\n)*?\]\n",
         "EXCLUDE_TERMS = []   # 이 판은 '공정위'를 검색하지 않아 공정위 오탐용 제외어가 필요 없다(생성기, 0-46)\n", 1, True),
    (NM, r"BASE_KEYWORDS = \[\n(?:.*\n)*?\]\n", NEW_BASE_KEYWORDS, 1, True),
    (NM, 'TEMP_KEYWORDS = {\n    "대미투자": "2026-09-23",\n}\n', "TEMP_KEYWORDS = {}\n", 1, False),
    (NM, "KEYWORD_GROUPS.update(DUTY_KEYWORD_GROUPS)\n", NEW_GROUPS_LINE, 1, False),
    # ---- news_monitor.py: 보관 기간 ----
    # 첫 실행 실측(10/22 15:06, 1,865건): 네이버 '노동' 500건이 약 27시간·'고용노동부'·'노동부' 500건이 약 24시간을 덮음 →
    # 하루 1,000~1,500건, 다른 판과 비슷 → 같은 45일. 처음엔 '노동'이 흔한 말이라 30일로 시작했다.
    (NM, "RETENTION_DAYS = 90 ", "RETENTION_DAYS = 45 ", 1, False),
    # ---- news_monitor.py: 기관장 이름 씨앗(원본 0-38 자리) ----
    (NM, "ACTOR_PEOPLE_SEED = {}\n", f"ACTOR_PEOPLE_SEED = {SEED!r}   # 노동판(생성기)\n", 1, False),
    # ---- news_monitor.py: 바이라인(본인 기사 섹션) ----
    (NM, 'BYLINE_NAME = "김광일"', f'BYLINE_NAME = "{REPORTER}"', 1, False),
    (NM, 'BYLINE_SECTION = "김광일 기자"', f'BYLINE_SECTION = "{REPORTER} 기자"', 1, False),

    # ---- render_page.py: 보고 양식 순서 ----
    (RP, "var REPORT_ORDER = ['방미통위','공정위','과기정통부','우주항공청'];",
         f"var REPORT_ORDER = {REPORT_ORDER_JS};", 2, False),
    (RP, "출입처 순서(방미통위 → 공정위 → 과기정통부 → 우주청 → 2진)",
         "출입처 순서(" + " → ".join(GROUPS) + ")", 2, False),
    # ---- render_page.py: 브라우저 저장키(같은 출처의 다른 페이지와 섞이지 않게) ----
    (RP, "'nm-live-", f"'{STORE_PREFIX}", 6, False),
    # ---- render_page.py: 출입처 식별색(원본 앞 두 출입처 색) ----
    (RP, '[data-g="공정위"], [data-b="공정위"]', '[data-g="노동부"], [data-b="노동부"]', 1, False),
    (RP, '[data-g="과기정통부"], [data-b="과기정통부"]', '[data-g="노동"], [data-b="노동"]', 1, False),
    (RP, '[data-g="김광일 기자"], [data-b="김광일 기자"]',
         f'[data-g="{REPORTER} 기자"], [data-b="{REPORTER} 기자"]', 1, False),
    # ---- render_page.py: 기기 연동 숨김(GitHub 계정이 없는 기자는 못 쓴다 — 버튼만 숨김) ----
    (RP, '<button type="button" id="sync" class="sync off"',
         '<button type="button" id="sync" class="sync off" style="display:none"', 1, False),
    # ---- render_page.py: 화면 문구 ----
    (RP, "<title>뉴스레이다</title>", f"<title>뉴스레이다 · {BEATS_TITLE}</title>", 1, False),
    # 0-75: 머리줄 판 주인(사용자 10/23 "이 페이지가 누구의 판인지 각자의 이름을 써주면 좋겠어. 출입처명도 간략히")
    (RP, '<span class="who">김광일<span class="whob"> (과학·방송·경쟁 담당)</span></span>', '<span class="who">김동빈<span class="whob"> (노동부)</span></span>', 1, False),
    (RP, "document.title = '뉴스레이다 · ' + r.title;",
         "document.title = '뉴스레이다(노동) · ' + r.title;", 1, False),
    (RP, "맨 끝 ‘김광일 기자’는", f"맨 끝 ‘{REPORTER} 기자’는", 1, False),
    (RP, "체크한 기사와 ‘여기까지 확인’은 이 기기에 저장되고, 머리줄 <b>기기 연동</b>을 켜면 다른 기기와 맞춰집니다(내 GitHub 비공개 gist). · <a href=\"../\">최신 다이제스트</a> · <a href=\"../archive/\">지난 다이제스트</a></p>",
         "체크한 기사와 ‘여기까지 확인’은 이 기기(브라우저)에만 저장됩니다 — PC와 폰은 따로 기억합니다.</p>", 1, False),
]

# 원본에서 그대로 가져오는 파일(치환 없음)
COPY_AS_IS = ["merge_db.py", "retitle.py"]

# 페이지에 남아 있으면 안 되는 문자열 — 주석(# / //)이 아닌 줄에서만 검사한다.
# (news_monitor.py는 문자열 대신 아래 EXPECT로 '실제로 import했을 때의 값'을 검사한다.
#  원본의 우주항공청·CBS 매핑·소관 어휘는 남아 있어도 검색어가 아니면 무해하다.)
FORBIDDEN = {
    RP: ["nm-live-", "김광일 기자\"", "기기 연동</b>", "방미통위 → 공정위"],
}
# 생성한 news_monitor.py를 별도 프로세스로 import해 확인할 값(당직·임시 키워드가 꺼진 날짜 기준).
EXPECT = {
    "DUTY_ONLY_GROUPS": ST.duty_only(GROUPS),   # 0-67 — 사회정책팀 묶음 중 이 판 섹션이 아닌 것
    "DUTY_COLLECT": True,
    "LIVE_FOLD_KEEP": ST.fold_keep(GROUPS, FOLD_KEEP),   # 0-72·0-76
    "LIVE_WEAK_FOLD_GROUPS": list(ST.WEAK_GROUPS),   # 0-68
    "EXCLUDE_TERMS": [],      # 0-46 — 공정위 오탐용 제외어 꺼짐
    "KEYWORDS": ["고용노동부", "노동부", "고용부", "노동장관", "노동차관", "노동"],
    "GROUP_ORDER": GROUPS,
    "RETENTION_DAYS": 45,
    "BYLINE_NAME": REPORTER,
    "BYLINE_SECTION": f"{REPORTER} 기자",
    "ACTOR_ASSIGN": True,
    "LIVE_ACTOR_BONUS": 2.0,
    "ACTOR_PEOPLE_SEED": SEED,
}


def md5(b):
    return hashlib.md5(b).hexdigest()


def apply(src_dir):
    out = {}
    for fname in {r[0] for r in REPLACEMENTS}:
        with open(os.path.join(src_dir, fname), encoding="utf-8") as f:
            out[fname] = f.read()
    errors = []
    for fname, old, new, count, is_re in REPLACEMENTS:
        text = out[fname]
        found = len(re.findall(old, text)) if is_re else text.count(old)
        if found != count:
            errors.append(f"{fname}: {old[:60]!r} — {count}번이어야 하는데 {found}번")
            continue
        out[fname] = re.sub(old, lambda m: new, text) if is_re else text.replace(old, new)
    if errors:
        raise SystemExit("원본이 예상과 달라 생성을 멈춥니다(아무 파일도 쓰지 않음):\n  "
                         + "\n  ".join(errors))
    leftovers = []
    for fname, pats in FORBIDDEN.items():
        for i, line in enumerate(out[fname].splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or s.startswith("//"):
                continue
            for p in pats:
                if p in line:
                    leftovers.append(f"{fname}:{i}: {p!r} — {s[:80]}")
    if leftovers:
        raise SystemExit("원본 고유 문자열이 남았습니다:\n  " + "\n  ".join(leftovers))
    return out


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = os.path.abspath(sys.argv[1])
    dst = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else
                          os.path.join(os.path.dirname(__file__), ".."))
    out = apply(src)
    # 먼저 임시 폴더에 써서 import 검사를 통과한 뒤에만 실제 위치로 옮긴다.
    import json, subprocess, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for fname, text in out.items():
            with open(os.path.join(tmp, fname), "w", encoding="utf-8") as f:
                f.write(text)
        probe = ("import json, news_monitor as m; print(json.dumps({k: getattr(m, k) for k in %r}, "
                 "ensure_ascii=False))" % list(EXPECT))
        env = dict(os.environ, DUTY_MODE="")
        r = subprocess.run([sys.executable, "-c", probe], cwd=tmp, env=env,
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("생성본 import 실패:\n" + r.stderr[-2000:])
        got = json.loads(r.stdout.strip().splitlines()[-1])
        bad = {k: (got.get(k), v) for k, v in EXPECT.items() if got.get(k) != v}
        if bad:
            raise SystemExit(f"생성본 설정값이 예상과 다릅니다: {bad}")
    for fname, text in sorted(out.items()):
        with open(os.path.join(dst, fname), "w", encoding="utf-8") as f:
            f.write(text)
    for fname in COPY_AS_IS:
        shutil.copyfile(os.path.join(src, fname), os.path.join(dst, fname))
    for fname in sorted(list(out) + COPY_AS_IS):
        with open(os.path.join(src, fname), "rb") as a, open(os.path.join(dst, fname), "rb") as b:
            print(f"{fname:18s} 원본 {md5(a.read())} → 생성 {md5(b.read())}")


if __name__ == "__main__":
    main()
