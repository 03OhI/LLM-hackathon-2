#!/usr/bin/env python3
"""대표 팀 fixture 전체에 대한 배정 분포 리포트.

usage:
  python simulate_assignment.py quests.json patterns.enum.json [topics.json]
  python simulate_assignment.py quests.json patterns.enum.json topics.json --fixtures fixtures.json

fixture 정본은 실제 엔진이다. 저장소에서 돌릴 때는 team_rules.yaml과 match_team_rules()로
fixture를 뽑아 JSON 배열로 넘긴다. 각 항목은 QuestMatchContext와 같은 모양이면 된다.

    [{"team_size": 4,
      "matched_rule_ids": ["TEAM_BALANCED_AGENCY", "TEAM_ADAPTABILITY"],
      "context_tags": ["FIRST_MEETING", "HACKATHON"]}, ...]

--fixtures 없이 돌리면 아래 MUTUALLY_EXCLUSIVE 표로 조합을 합성한다. 이 표는 실제
team_rules.yaml을 확인하지 못한 상태의 [가정]이며 정본이 아니다. 합성 모드로 돌리면
리포트 상단에 경고를 찍는다.

검증기(validate_quests.py)가 카탈로그의 정합성을 본다면, 이 스크립트는 카탈로그가
실제 배정에서 어떻게 분포하는지를 본다. 점수식·필터는 확정된 배정 계약과 같다.

  best_for 일치 rule_id 1건당 +3
  also_for 일치 rule_id 1건당 +1
  context_tags 일치 태그 1건당 +1
  같은 category 반복 -2   (단일 배정 시뮬레이션에서는 미적용)
  avoid_for 일치 / 인원 불일치 / HIGH / MANUAL / 비활성 / is_universal -> 후보 제외

정상 경로는 상위 3개를 Bedrock에 넘기므로 1위와 상위 3개 포함을 함께 집계한다.
"""
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

SCORE_BEST, SCORE_ALSO, SCORE_CONTEXT = 3, 1, 1
TOP_N = 3                      # Bedrock에 넘기는 후보 수
CONCENTRATION_LIMIT = 0.40     # 한 퀘스트가 전체 1위에서 차지해도 되는 상한

TEAM_SIZES = [3, 4, 5, 6, 7, 8, 9, 10]
TAG_SETS = [
    ("P0 기본", {"FIRST_MEETING", "HACKATHON"}),
    ("장기·원격", {"FIRST_MEETING", "REMOTE_TEAM", "LONG_TERM_PROJECT"}),
    ("역할 분담 전·툴 미비", {"FIRST_MEETING", "BEFORE_ROLE_ASSIGNMENT", "WORKSPACE_NOT_READY"}),
]

# [가정] team_rules.yaml을 확인하지 못해 같은 축의 반대편끼리만 배타로 뒀다.
# 실제 규칙이 다르면 이 표만 고치면 된다.
MUTUALLY_EXCLUSIVE = [
    {"TEAM_DRIVER_ENERGY", "TEAM_LOW_DRIVER"},
    {"TEAM_DRIVER_ENERGY", "TEAM_SUPPORTER_MAJORITY"},
    {"TEAM_BALANCED_AGENCY", "TEAM_DRIVER_ENERGY"},
    {"TEAM_BALANCED_AGENCY", "TEAM_LOW_DRIVER"},
    {"TEAM_BALANCED_AGENCY", "TEAM_SUPPORTER_MAJORITY"},
    {"TEAM_PLANNING_STABILITY", "TEAM_PLANNING_OVERLOAD"},
    {"TEAM_PLANNING_STABILITY", "TEAM_ADAPTER_MAJORITY"},
    {"TEAM_ADAPTABILITY", "TEAM_PLANNING_OVERLOAD"},
    {"TEAM_BALANCED_CONFLICT", "TEAM_CONFRONTER_MAJORITY"},
    {"TEAM_CONFRONTER_MAJORITY", "TEAM_HARMONIZER_PRESENCE"},
    {"TEAM_DIRECT_CONCENTRATION", "TEAM_TACTFUL_COMMUNICATION"},
    {"TEAM_DIVERSE_COMMUNICATION", "TEAM_DIRECT_CONCENTRATION"},
    {"TEAM_DIVERSE_COMMUNICATION", "TEAM_TACTFUL_COMMUNICATION"},
]


def is_auto_candidate(q):
    return (q.get("is_active") is True
            and q.get("assignment") == "AUTO"
            and q.get("disclosure_level") in ("LOW", "MEDIUM"))


def fits(q, n):
    ts = q.get("team_size", {})
    return ts.get("min", 99) <= n <= ts.get("max", 0)


def rule_matched(q, rules):
    return bool((set(q.get("best_for", [])) | set(q.get("also_for", []))) & rules)


def score(q, rules, tags):
    if not is_auto_candidate(q) or q.get("is_universal"):
        return None
    if set(q.get("avoid_for", [])) & rules:
        return None
    return (SCORE_BEST * len(set(q.get("best_for", [])) & rules)
            + SCORE_ALSO * len(set(q.get("also_for", [])) & rules)
            + SCORE_CONTEXT * len(set(q.get("context_tags", [])) & tags))


def viable(combo):
    s = set(combo)
    return not any(pair <= s for pair in MUTUALLY_EXCLUSIVE)


def load_fixtures(path, rules):
    """실제 엔진이 뽑아준 fixture. 정본."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out, unknown = [], set()
    for i, f in enumerate(raw):
        rs = set(f.get("matched_rule_ids", []))
        unknown |= rs - set(rules)
        out.append((rs, int(f["team_size"]), set(f.get("context_tags", []))))
    if unknown:
        print(f"[경고] fixture에 어휘 밖 rule_id: {', '.join(sorted(unknown))}\n")
    return out


def synth_fixtures(rules):
    """[가정] 합성 fixture. 실제 엔진을 못 쓸 때만."""
    out = []
    for k in (1, 2, 3, 4):
        for combo in combinations(rules, k):
            if not viable(combo):
                continue
            for size in TEAM_SIZES:
                for _, tags in TAG_SETS:
                    out.append((set(combo), size, tags))
    return out


def main(quests_path, enum_path, topics_path=None, *argv):
    data = json.loads(Path(quests_path).read_text(encoding="utf-8"))
    rules = json.loads(Path(enum_path).read_text(encoding="utf-8"))["rule_ids"]
    fx_path = None
    if "--fixtures" in argv:
        fx_path = argv[argv.index("--fixtures") + 1]
    by_id = {q["quest_id"]: q for q in data}
    card = set()
    if topics_path and Path(topics_path).exists():
        tj = json.loads(Path(topics_path).read_text(encoding="utf-8"))
        card = {t["quest_id"] for t in tj.get("types", {}).values() if "quest_id" in t}

    fallback = sorted(
        (q for q in data if q.get("is_universal") and is_auto_candidate(q)),
        key=lambda q: (q["disclosure_level"], q["duration_minutes"], q["quest_id"]))
    fallback_id = fallback[0]["quest_id"] if fallback else None

    excluded = [q["quest_id"] for q in data if not is_auto_candidate(q)]

    fixtures = load_fixtures(fx_path, rules) if fx_path else synth_fixtures(rules)

    first, top3 = Counter(), Counter()
    starved = []
    n_fixture = n_fallback = 0

    for rs, size, tags in fixtures:
        n_fixture += 1
        cand = []
        for q in data:
            if not fits(q, size) or not rule_matched(q, rs):
                continue
            s = score(q, rs, tags)
            if s is not None:
                cand.append((s, q))
        if not cand:
            starved.append((sorted(rs), size, sorted(tags)))
            n_fallback += 1
            if fallback_id:
                first[fallback_id] += 1
                top3[fallback_id] += 1
            continue
        cand.sort(key=lambda p: (-p[0], p[1]["disclosure_level"],
                                 p[1]["duration_minutes"], p[1]["quest_id"]))
        first[cand[0][1]["quest_id"]] += 1
        for _, q in cand[:TOP_N]:
            top3[q["quest_id"]] += 1

    # ---- 리포트 ----
    if fx_path:
        print(f"fixture: {fx_path} (실제 엔진 산출) {n_fixture}건")
    else:
        print(f"fixture: 합성 {n_fixture}건 "
              f"(rule 조합 1~4개 × 인원 {len(TEAM_SIZES)}종 × 상황 태그 {len(TAG_SETS)}종)")
        print("  [경고] MUTUALLY_EXCLUSIVE 수동 표로 만든 [가정] fixture다. 정본이 아니다.")
        print("         저장소에서는 team_rules.yaml + match_team_rules()로 fixture를 뽑아")
        print("         --fixtures 로 넘길 것.")
    print(f"  자동 후보 제외 퀘스트: {', '.join(excluded) if excluded else '없음'}")
    print(f"  범용 폴백: {fallback_id}\n")

    hdr = f"{'quest_id':<12} {'유형':<5} {'1위':>6} {'1위%':>6} {'상위3':>7} {'상위3%':>7}"
    print(hdr)
    print("-" * len(hdr))
    for q in data:
        qid = q["quest_id"]
        if not is_auto_candidate(qid and by_id[qid]):
            continue
        f, t3 = first[qid], top3[qid]
        kind = "카드" if qid in card else ("폴백" if qid == fallback_id else "일반")
        print(f"{qid:<12} {kind:<5} {f:>6} {f/n_fixture:>5.1%} {t3:>7} {t3/n_fixture:>6.1%}")

    agg = Counter()
    for q in data:
        qid = q["quest_id"]
        if not is_auto_candidate(q):
            continue
        agg["카드" if qid in card else ("폴백" if qid == fallback_id else "일반")] += first[qid]
    print("-" * len(hdr))
    for kind in ("카드", "일반", "폴백"):
        print(f"{kind + ' 합계':<18} {agg[kind]:>6} {agg[kind]/n_fixture:>5.1%}")

    never = [q["quest_id"] for q in data
             if is_auto_candidate(q) and top3[q["quest_id"]] == 0]
    print(f"\n맞춤 후보 0개 (폴백행): {len(starved)}건 ({len(starved)/n_fixture:.1%})")
    print(f"범용 폴백 배정:        {n_fallback}건 ({n_fallback/n_fixture:.1%})")
    for rs, size, tags in starved[:10]:
        print(f"   - {size}명 / {'+'.join(rs) or '(rule 없음)'} / {'+'.join(tags)}")
    if len(starved) > 10:
        print(f"   ... 외 {len(starved) - 10}건")
    if never:
        print(f"상위 3개에 한 번도 못 든 퀘스트: {', '.join(never)}")

    print()
    over = [(qid, c) for qid, c in first.most_common()
            if c / n_fixture >= CONCENTRATION_LIMIT]
    if over:
        for qid, c in over:
            print(f"[집중] {qid}가 전체 1위의 {c/n_fixture:.1%} 차지 "
                  f"(상한 {CONCENTRATION_LIMIT:.0%} 초과)")
        return 1
    top_qid, top_c = first.most_common(1)[0]
    print(f"[집중] 상한 {CONCENTRATION_LIMIT:.0%} 이내. "
          f"최다 1위는 {top_qid} {top_c/n_fixture:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
