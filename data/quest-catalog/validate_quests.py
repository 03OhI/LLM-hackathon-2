#!/usr/bin/env python3
"""퀘스트 카탈로그 검증기 v3 (SPEC V5.2 기준).

usage: python validate_quests.py quest.schema.json quests.json patterns.enum.json

검사 범위
  1. JSON Schema (SPEC §4.1 QuestTemplate과 필드 단위 일치)
  2. 어휘 대조   - best/also/avoid_for는 team_rules.yaml rule_id, context_tags는 SPEC §3 허용 태그
  3. 품질 조건  - SPEC §4.4
  4. 인수 기준  - SPEC §10 카탈로그 항목
  5. 배정 시뮬레이션 - SPEC §5.1 점수식으로 rule_id별 후보 존재 여부 확인
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator

PREFIX_BY_CATEGORY = {
    "CASUAL_BONDING": "CSB", "WORK_STYLE_DISCOVERY": "WSD", "COMMUNICATION": "COM",
    "TEAM_SAFETY": "TSF", "TEAM_IDENTITY": "TID", "SHARED_ARTIFACT": "SAR",
}
ALL_CATEGORIES = set(PREFIX_BY_CATEGORY)
PRODUCT_TEAM_MIN, PRODUCT_TEAM_MAX = 3, 10
BIG_TEAM_THRESHOLD = 9          # SPEC §4.4 "9~10명 자동 퀘스트 최소 4개"
BIG_TEAM_MIN_COUNT = 4

# 1인당 체크 1건을 처리하는 데 드는 대략 시간(분). 페이스 경고에만 사용한다.
COST_MINUTES = {"VOTE": 0.3, "REACTION": 0.2, "APPROVE": 0.3, "TEXT_SUBMIT": 2.0}

# 배정 점수식 (확정). 일치 1건당 가산(per-match).
#   best_for +3 / also_for +1 / context_tags +1 / 같은 category 반복 -2
# is_universal 가산점은 제거했다. 범용 퀘스트는 일반 AUTO 후보와 점수 경쟁을 하지 않고,
# 적합한 rule_id 후보가 없거나 Bedrock이 실패했을 때의 폴백으로만 쓴다.
SCORE_BEST, SCORE_ALSO, SCORE_CONTEXT, SCORE_SAME_CATEGORY = 3, 1, 1, -2

NOISE_PATTERNS = [
    (re.compile(r"\[cite[:_]"), "참조 마커 [cite:] 오염"),
    (re.compile(r"\[\d+\]"), "각주 번호 오염"),
    (re.compile(r"```"), "코드펜스 잔여"),
]


def walk_strings(node, path="$"):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, f"{path}[{i}]")


def is_auto_candidate(q):
    """SPEC §4.4: 자동 후보는 활성 + AUTO + 공개 수준 LOW|MEDIUM."""
    return (q.get("is_active") is True
            and q.get("assignment") == "AUTO"
            and q.get("disclosure_level") in ("LOW", "MEDIUM"))


def score(q, rule_ids, context_tags, used_categories):
    """일치 1건당 가산(per-match) 점수. 후보에서 제외되면 None.

    범용 퀘스트(is_universal)는 점수 경쟁에 참여하지 않는다. 폴백 전용이다.
    """
    if not is_auto_candidate(q) or q.get("is_universal"):
        return None
    if set(q.get("avoid_for", [])) & rule_ids:
        return None
    s = SCORE_BEST * len(set(q.get("best_for", [])) & rule_ids)
    s += SCORE_ALSO * len(set(q.get("also_for", [])) & rule_ids)
    s += SCORE_CONTEXT * len(set(q.get("context_tags", [])) & context_tags)
    s += SCORE_SAME_CATEGORY if q.get("category") in used_categories else 0
    return s


def fits(q, team_size):
    ts = q.get("team_size", {})
    return ts.get("min", 99) <= team_size <= ts.get("max", 0)


def main(schema_path, data_path, enum_path):
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    vocab = json.loads(Path(enum_path).read_text(encoding="utf-8"))

    known_rules = set(vocab["rule_ids"])
    known_tags = set(vocab["context_tags"])
    default_tags = set(vocab.get("p0_default_context_tags", []))

    errors, warnings = [], []

    for e in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda x: list(x.path)):
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        errors.append(f"[SCHEMA] {loc}: {e.message}")

    for path, s in walk_strings(data):
        for pat, label in NOISE_PATTERNS:
            if pat.search(s):
                errors.append(f"[NOISE] {path}: {label} -> {s[:40]!r}")

    ids, big_team_auto = [], 0

    for i, q in enumerate(data):
        qid = q.get("quest_id", f"<index {i}>")
        ids.append(qid)

        cat = q.get("category")
        if cat in PREFIX_BY_CATEGORY and isinstance(q.get("quest_id"), str):
            want = PREFIX_BY_CATEGORY[cat]
            got = q["quest_id"].split("_")[1] if q["quest_id"].count("_") >= 2 else "?"
            if got != want:
                errors.append(f"[ID] {qid}: category={cat}이면 접두사는 {want} (현재 {got})")

        # SPEC §4.2 / §10 - 적합 필드는 실제 rule_id 또는 빈 배열
        for field in ("best_for", "also_for", "avoid_for"):
            for code in q.get(field, []):
                if code not in known_rules:
                    errors.append(f"[VOCAB] {qid}.{field}: team_rules.yaml에 없는 rule_id {code}")
        for tag in q.get("context_tags", []):
            if tag not in known_tags:
                errors.append(f"[VOCAB] {qid}.context_tags: 미허용 상황 태그 {tag}")

        overlap = set(q.get("best_for", []) + q.get("also_for", [])) & set(q.get("avoid_for", []))
        if overlap:
            errors.append(f"[CONFLICT] {qid}: 적합/비적합 중복 {sorted(overlap)}")

        # SPEC §4.3 - is_universal이면 avoid_for는 빈 배열 (단방향)
        if q.get("is_universal") and q.get("avoid_for"):
            errors.append(f"[UNIVERSAL] {qid}: is_universal=true인데 avoid_for={q['avoid_for']}")

        # reveals_axes 내부 정합성
        seen_dims = set()
        for j, d in enumerate(q.get("reveals_axes", [])):
            if not isinstance(d, dict):
                continue
            if d.get("pole_a") == d.get("pole_b"):
                errors.append(f"[AXIS] {qid}.reveals_axes[{j}]: 두 극이 동일")
            key = (d.get("axis"), d.get("dimension"))
            if key in seen_dims:
                errors.append(f"[AXIS] {qid}.reveals_axes[{j}]: 축·차원 중복 {key}")
            seen_dims.add(key)

        ts = q.get("team_size", {})
        lo, hi = ts.get("min"), ts.get("max")
        if lo and hi:
            if lo > hi:
                errors.append(f"[SIZE] {qid}: min({lo}) > max({hi})")
            if lo < PRODUCT_TEAM_MIN or hi > PRODUCT_TEAM_MAX:
                errors.append(f"[SIZE] {qid}: 제품 범위 {PRODUCT_TEAM_MIN}~{PRODUCT_TEAM_MAX} 이탈")
            if hi >= BIG_TEAM_THRESHOLD and is_auto_candidate(q):
                big_team_auto += 1

        # SPEC §4.4 - 모든 퀘스트에 PER_MEMBER 체크
        checks = q.get("completion_condition", {}).get("checks", [])
        pm = [c for c in checks if c.get("scope") == "PER_MEMBER"]
        if not pm:
            errors.append(f"[PARTICIPATION] {qid}: PER_MEMBER 체크 없음")
        dur = q.get("duration_minutes", 0)
        cost = sum(COST_MINUTES.get(c["type"], 1.0) * c["min_count"] for c in pm)
        if dur and cost > dur * 0.6:
            warnings.append(f"[PACE] {qid}: 1인당 체크 비용 {cost:.1f}분 / 배정 {dur}분")

        # SPEC §4.4 - HIGH는 반드시 MANUAL (스키마 allOf 보조 확인)
        if q.get("disclosure_level") == "HIGH" and q.get("assignment") == "AUTO":
            errors.append(f"[DISCLOSURE] {qid}: disclosure=HIGH인데 assignment=AUTO")

    for qid, n in Counter(ids).items():
        if n > 1:
            errors.append(f"[DUP] quest_id 중복: {qid} ({n}회)")

    # ---- topics.json (있을 때만) ---------------------------------------
    topics_path = Path(data_path).with_name("topics.json")
    topics = None
    if topics_path.exists():
        topics = json.loads(topics_path.read_text(encoding="utf-8"))
        groups, types = topics.get("groups", {}), topics.get("types", {})
        subs = topics.get("sub_groups", {})
        axis_codes = topics.get("_axis_codes", {})
        by_id = {q.get("quest_id"): q for q in data}

        seen_qid = {}
        for tcode, ty in sorted(types.items()):
            qid = ty.get("quest_id")
            q = by_id.get(qid)
            if q is None:
                errors.append(f"[TOPIC] types.{tcode}: 존재하지 않는 quest_id {qid}")
            elif q.get("assignment") != "AUTO" or q.get("disclosure_level") == "HIGH":
                errors.append(f"[TOPIC] types.{tcode}: {qid}가 AUTO/LOW|MEDIUM 조건 불충족")
            else:
                blob = " ".join(q.get("materials", []))
                for k, text in enumerate(ty.get("topics", [])):
                    if text not in blob:
                        errors.append(f"[TOPIC] {qid}.materials에 {tcode}.topics[{k}] "
                                      f"본문이 없음 (런타임은 quests.json만 읽는다)")
                # 내부 제작 개념(유형 코드·명칭)이 사용자 노출 필드에 새면 안 된다
                shown = " ".join([q.get("title", ""), q.get("summary", ""),
                                  q.get("primary_goal", ""), q.get("deliverable", ""),
                                  q.get("completion_condition", {}).get("description", "")]
                                 + q.get("materials", []) + q.get("steps", [])
                                 + q.get("safety_notes", []))
                for leak in (tcode, ty.get("label", ""),
                             groups.get(ty.get("group"), {}).get("label", ""),
                             subs.get(ty.get("sub_group"), {}).get("label", "")):
                    if leak and leak in shown:
                        errors.append(f"[TOPIC] {qid}: 사용자 노출 필드에 내부 제작 개념 "
                                      f"'{leak}' 노출")
            if qid in seen_qid:
                errors.append(f"[TOPIC] {qid}가 {seen_qid[qid]}와 {tcode} 양쪽에 연결됨")
            seen_qid[qid] = tcode

        expected = {a + b + c + d
                    for a in "PA" for b in "LS" for c in "CH" for d in "DI"}
        got = set(types)
        for miss in sorted(expected - got):
            errors.append(f"[TOPIC] 유형 누락: {miss}")
        for extra in sorted(got - expected):
            errors.append(f"[TOPIC] 정의되지 않은 유형 코드: {extra}")
        for miss in sorted({c + d for c in "CH" for d in "DI"} - set(subs)):
            errors.append(f"[TOPIC] 하위 그룹 누락: {miss}")

        # 상위·하위 그룹의 코드 글자와 axes 선언이 일치하는가
        for scope, table in (("groups", groups), ("sub_groups", subs)):
            for code, g in sorted(table.items()):
                for letter in code:
                    spec = axis_codes.get(letter)
                    if spec is None:
                        errors.append(f"[TOPIC] {scope}.{code}: 미정의 축 문자 {letter}")
                    elif g.get("axes", {}).get(spec["axis"]) != spec["value"]:
                        errors.append(f"[TOPIC] {scope}.{code}: 문자 {letter}는 "
                                      f"{spec['axis']}={spec['value']}인데 axes와 불일치")
                for rid in g.get("rule_ids", []):
                    if rid not in known_rules:
                        errors.append(f"[TOPIC] {scope}.{code}.rule_ids: 미정의 {rid}")

        for tcode, t in sorted(types.items()):
            if t.get("group") != tcode[:2]:
                errors.append(f"[TOPIC] {tcode}: group={t.get('group')} (코드상 {tcode[:2]})")
            if t.get("sub_group") != tcode[2:]:
                errors.append(f"[TOPIC] {tcode}: sub_group={t.get('sub_group')} (코드상 {tcode[2:]})")
            if t.get("group") not in groups:
                errors.append(f"[TOPIC] {tcode}: 미정의 그룹 {t.get('group')}")
            if t.get("sub_group") not in subs:
                errors.append(f"[TOPIC] {tcode}: 미정의 하위 그룹 {t.get('sub_group')}")
            tl = t.get("topics", [])
            if len(tl) != 2:
                errors.append(f"[TOPIC] {tcode}: 질문 {len(tl)}개 (2개여야 함)")
            for k, text in enumerate(tl):
                if len(text) < 10:
                    errors.append(f"[TOPIC] {tcode}.topics[{k}]: 너무 짧음")
            if len(set(tl)) != len(tl):
                errors.append(f"[TOPIC] {tcode}: 질문 중복")

        # 런타임 외부 참조 금지: 퀘스트 본문이 topics.json을 가리키면 안 된다
        for q in data:
            for m in q.get("materials", []) + q.get("steps", []):
                if "topics.json" in m:
                    errors.append(f"[TOPIC] {q['quest_id']}: 본문이 topics.json을 참조함 "
                                  f"(백엔드는 quests.json만 읽는다)")
                    break

    missing = ALL_CATEGORIES - {q.get("category") for q in data}
    if missing:
        warnings.append(f"[COVERAGE] 미사용 카테고리: {', '.join(sorted(missing))}")
    if big_team_auto < BIG_TEAM_MIN_COUNT:
        errors.append(f"[COVERAGE] {BIG_TEAM_THRESHOLD}명 이상 자동 퀘스트 {big_team_auto}개 "
                      f"(최소 {BIG_TEAM_MIN_COUNT}개 필요)")

    # SPEC §5.2 - 후보가 없을 때 쓸 범용 폴백이 실제로 존재하는가
    fallbacks = [q for q in data
                 if q.get("is_universal") and is_auto_candidate(q)
                 and q.get("team_size", {}).get("min", 99) <= PRODUCT_TEAM_MIN
                 and q.get("team_size", {}).get("max", 0) >= PRODUCT_TEAM_MAX]
    if not fallbacks:
        errors.append("[FALLBACK] 3~10명 전 구간을 덮는 범용 자동 퀘스트가 없음 (SPEC §5.2)")

    # ---- 리포트 -------------------------------------------------------
    print(f"검사 대상: {len(data)}개 퀘스트  |  "
          f"어휘: rule_id {len(known_rules)}종, 상황 태그 {len(known_tags)}종\n")
    hdr = (f"{'quest_id':<12} {'category':<21} {'인원':<7} {'분':<4} "
           f"{'배정':<7} {'공개':<7} {'활성':<5} {'universal'}")
    print(hdr)
    print("-" * len(hdr))
    for q in data:
        ts = q.get("team_size", {})
        size_range = "{}~{}".format(ts.get("min", 0), ts.get("max", 0))
        print(f"{q.get('quest_id',''):<12} {q.get('category',''):<21} "
              f"{size_range:<7} "
              f"{q.get('duration_minutes',0):<4} {q.get('assignment',''):<7} "
              f"{q.get('disclosure_level',''):<7} {('O' if q.get('is_active') else '-'):<5} "
              f"{'O' if q.get('is_universal') else '-'}")

    dist = defaultdict(list)
    for q in data:
        for c in q.get("best_for", []):
            dist[c].append(q["quest_id"])
    print(f"\nbest_for rule_id 커버리지: {len(dist)}/{len(known_rules)}종")
    unused = sorted(known_rules - set(dist))
    if unused:
        print(f"  best_for 미사용({len(unused)}): {', '.join(unused)}")

    if topics:
        card = {r for g in topics.get("groups", {}).values() for r in g.get("rule_ids", [])}
        card |= {r for s in topics.get("sub_groups", {}).values() for r in s.get("rule_ids", [])}
        print(f"질문 카드 계층(상위+하위) rule_id 커버리지: {len(card)}/{len(known_rules)}종")
        gap = sorted(known_rules - set(dist) - card)
        if gap:
            print(f"  퀘스트 best_for·카드 계층 어디에도 없음({len(gap)}): {', '.join(gap)}")
        else:
            print("  퀘스트 best_for와 카드 계층을 합치면 14종 전부 도달")

    # ---- 배정 시뮬레이션 -----------------------------------------------
    def ranked(rid, n):
        """rule_id 하나가 매칭됐을 때의 AUTO 후보 순위. rule_id에 실제로 걸린 것만."""
        out = []
        for q in data:
            if not fits(q, n):
                continue
            s = score(q, {rid}, default_tags, set())
            if s is None:
                continue
            if not (set(q.get("best_for", [])) | set(q.get("also_for", []))) & {rid}:
                continue          # 상황 태그만으로 붙은 후보는 rule 적합으로 보지 않는다
            out.append((s, q))
        out.sort(key=lambda t: (-t[0], t[1]["disclosure_level"],
                                t[1]["duration_minutes"], t[1]["quest_id"]))
        return out

    fallback_id = fallbacks[0]["quest_id"] if fallbacks else "(없음)"
    print(f"\nrule_id별 AUTO 후보 상위  |  4명 팀 / 상황 태그={sorted(default_tags)}")
    print(f"{'rule_id':<28} {'1위':<14} {'점수':<5} {'2위':<14} {'점수':<5} {'후보수'}")
    print("-" * 78)
    to_fallback = []
    for rid in vocab["rule_ids"]:
        r4 = ranked(rid, 4)
        if not r4:
            to_fallback.append(rid)
            print(f"{rid:<28} {'-- 폴백 --':<14} {'-':<5} {'':<14} {'':<5} 0")
            continue
        first = (r4[0][1]["quest_id"], str(r4[0][0]))
        second = (r4[1][1]["quest_id"], str(r4[1][0])) if len(r4) > 1 else ("", "")
        print(f"{rid:<28} {first[0]:<14} {first[1]:<5} "
              f"{second[0]:<14} {second[1]:<5} {len(r4)}")

    print(f"\n범용 폴백({fallback_id})으로 남는 rule_id: "
          f"{len(to_fallback)}/{len(known_rules)}종"
          + (f" -> {', '.join(to_fallback)}" if to_fallback else " -> 없음"))

    # 10명 팀에서 rule 적합 후보가 사라지는 조합
    shrink = [rid for rid in vocab["rule_ids"] if ranked(rid, 4) and not ranked(rid, 10)]
    if shrink:
        warnings.append(f"[MATCH] 10명 팀에서 rule 적합 후보가 사라지는 rule_id: {', '.join(shrink)}")
    if len(to_fallback) > len(known_rules) // 3:
        warnings.append(f"[MATCH] rule_id {len(to_fallback)}/{len(known_rules)}종이 "
                        f"AUTO 적합 후보 없이 폴백으로 감: {', '.join(to_fallback)}")

    print()
    print(f"실패 {len(errors)}건" if errors else "오류 0건")
    for e in errors:
        print("  " + e)
    if warnings:
        print(f"\n경고 {len(warnings)}건")
        for w in warnings:
            print("  " + w)
    else:
        print("경고 0건")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
