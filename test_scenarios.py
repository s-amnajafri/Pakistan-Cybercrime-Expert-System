"""
test_scenarios.py - checks the knowledge base and engine.

Run with:  python test_scenarios.py

It runs:
  1. Structure checks (94 rules, unique IDs, group counts)
  2. The 14 synthetic test scenarios from the design (all invented, no real data)
  3. A fuzz test: thousands of random answer sets, to prove that the primary
     diagnosis rules are mutually exclusive and the engine never crashes
  4. A what-if check
  5. Action plan checks: prioritized, no repeated advice, every action traceable to rules and facts
  6. Urgency policy: loss vs attempt, settled vs ongoing, specific escalations, no silent default
  7. Match strength: computed from the diagnosis criteria, not typed in
  8. Secondary indicators: phishing is a defined indicator with its own rule
"""
import random
from collections import Counter

from rules import RULES, QUESTIONS, URGENCY_RANK, PHASES, CRITERIA
from engine import assess, compare, visible_questions, _same_action

# --------------------------------------------------------------------------
# A base set of answers; each scenario changes only what it needs
# --------------------------------------------------------------------------
BASE = {
    "immediate_danger": "no", "minor_involved": "no", "ongoing": "no",
    "environment": "personal", "offender_known": "unknown", "platform": [],
    "private_content": "no", "access_status": "full", "evidence_list": ["screenshots"],
    "already_reported": ["none"], "money_status": "neither", "time_elapsed": "1_7_days",
}


def case(**changes):
    answers = dict(BASE)
    answers.update(changes)
    return answers


# Each scenario: (name, answers, expected diagnosis label, strength, urgency, routes {route: role})
SCENARIOS = [
    ("T1 fake call + OTP, money lost today",
     case(main_symptom="paid_after_call_or_link", money_status="lost",
          transaction_circumstances="both", time_elapsed="under_24h", platform=["call_sms"]),
     "Financial fraud", "strong", "High",
     {"Bank or wallet provider": "Do first", "NCCIA": "Also relevant"}),

    ("T2 unauthorised wallet transaction today",
     case(main_symptom="money_missing", money_status="lost",
          transaction_circumstances="unauthorised", time_elapsed="under_24h"),
     "Financial fraud", "strong", "High",
     {"Bank or wallet provider": "Do first", "NCCIA": "Also relevant"}),

    ("T3 paid a Facebook seller, nothing arrived",
     case(main_symptom="goods_not_received", money_status="lost",
          transaction_circumstances="authorised_after_deception", platform=["facebook"]),
     "Marketplace scam", "strong", "High",
     {"Bank or wallet provider": "Also relevant", "NCCIA": "Also relevant",
      "Platform report": "Also relevant"}),

    ("T4 Instagram hacked, no access, ongoing",
     case(main_symptom="lost_access", access_status="none", ongoing="yes", platform=["instagram"]),
     "Account compromise", "strong", "High",
     {"NCCIA": "Also relevant", "Platform report": "Also relevant"}),

    ("T5 blackmail with money demand and private content",
     case(main_symptom="threats_received", money_status="demanded", private_content="yes",
          ongoing="yes", platform=["whatsapp"]),
     "Blackmail or extortion", "strong", "High",
     {"NCCIA": "Do first", "Platform report": "Also relevant"}),

    ("T6 threat to share intimate images, minor",
     case(main_symptom="threats_received", private_content="yes", minor_involved="yes",
          platform=["whatsapp"]),
     "Intimate-content abuse", "strong", "Critical",
     {"NCCIA": "Do first"}),

    ("T7 repeated unwanted messages, adult, ongoing",
     case(main_symptom="unwanted_contact", ongoing="yes", platform=["whatsapp"]),
     "Harassment or stalking", "strong", "Medium",
     {"NCCIA": "Do first", "Platform report": "Also relevant"}),

    ("T8 harassment with immediate danger",
     case(main_symptom="unwanted_contact", immediate_danger="yes", ongoing="yes"),
     "Harassment or stalking", "strong", "Critical",
     {"Police or emergency services": "Do first", "NCCIA": "Do first"}),

    ("T9 fake profile, wants content removed",
     case(main_symptom="fake_account", desired_outcome="remove_content",
          ongoing="yes", platform=["instagram"]),
     "Identity misuse or impersonation", "strong", "Medium",
     {"Platform report": "Do first", "NCCIA": "Do first", "PTA web-content complaint": "Optional"}),

    ("T10 ransomware at an organisation",
     case(main_symptom="device_problem", money_status="demanded",
          environment="organisation", ongoing="yes"),
     "Malware or ransomware", "strong", "High",
     {"Organisation's IT or security team": "Do first", "PKCERT": "Also relevant"}),

    ("T11 not sure about anything important",
     {"main_symptom": "not_sure", "immediate_danger": "not_sure"},
     "Unclassified", None, "Medium", {}),

    ("T12 fraud already reported to bank and NCCIA",
     case(main_symptom="paid_after_call_or_link", money_status="lost",
          transaction_circumstances="authorised_after_deception",
          already_reported=["bank", "nccia"]),
     "Financial fraud", "strong", None,
     {"NCCIA (existing complaint)": "Follow up", "Banking Mohtasib": "Optional"}),

    ("T13 contradictory answers (money_missing, no money)",
     case(main_symptom="money_missing", money_status="neither"),
     "Unclassified", None, "Medium", {}),

    ("T14 lost access and money lost",
     case(main_symptom="lost_access", money_status="lost", access_status="none",
          transaction_circumstances="unauthorised", ongoing="yes"),
     "Account compromise", "strong", "High",
     {"Bank or wallet provider": "Do first", "NCCIA": "Also relevant"}),
]


def check_structure():
    print("== Structure ==")
    ids = [r["id"] for r in RULES]
    assert len(ids) == len(set(ids)), "duplicate rule IDs"
    groups = Counter(r["group"] for r in RULES)
    expected = {"DF": 8, "DG": 26, "DD": 4, "UR": 16, "AC": 14, "EV": 8, "RT": 12, "CP": 6}
    assert dict(groups) == expected, f"group counts differ: {dict(groups)}"
    tags = Counter(r["tag"] for r in RULES)
    assert tags == {"D": 54, "Shared": 14, "S": 26}, f"tag counts differ: {dict(tags)}"
    assert len(QUESTIONS) == 17
    print(f"  {len(RULES)} rules, {len(QUESTIONS)} questions, groups {dict(groups)}, tags {dict(tags)}  OK")


def check_scenarios():
    print("== Scenarios ==")
    failures = 0
    for name, answers, label, strength, urgency, routes in SCENARIOS:
        out = assess(answers)
        problems = []
        if out["diagnosis"]["primary"] != label:
            problems.append(f"diagnosis {out['diagnosis']['primary']!r} != {label!r}")
        if out["diagnosis"]["strength"] != strength:
            problems.append(f"strength {out['diagnosis']['strength']!r} != {strength!r}")
        if urgency and out["decision"]["urgency"] != urgency:
            problems.append(f"urgency {out['decision']['urgency']!r} != {urgency!r}")
        got = {r["route"]: r["role"] for r in out["support"]["routes"]}
        for route, role in routes.items():
            if got.get(route) != role:
                problems.append(f"route {route!r}: {got.get(route)!r} != {role!r}")
        if not routes and got:
            problems.append(f"expected no routes, got {got}")
        status = "PASS" if not problems else "FAIL"
        failures += bool(problems)
        print(f"  {status}  {name}")
        for p in problems:
            print("        -", p)
    return failures


def check_extra_expectations():
    """Extra details mentioned in the design document."""
    print("== Extra checks ==")
    ok = True

    out = assess(SCENARIOS[4][1])                      # T5
    ok &= "Intimate-content abuse" in out["diagnosis"]["alternatives"]          # DD02
    out = assess(SCENARIOS[8][1])                      # T9
    ok &= "Harmful online content" in out["diagnosis"]["alternatives"]          # DD04
    out = assess(SCENARIOS[0][1])                      # T1
    ok &= "Phishing or social engineering" in out["diagnosis"]["indicators"]    # DG26
    out = assess(SCENARIOS[13][1])                     # T14
    ok &= "Financial loss" in out["diagnosis"]["indicators"]                    # DG25
    ok &= "Financial fraud" in out["diagnosis"]["alternatives"]                 # DD01
    out = assess(SCENARIOS[10][1])                     # T11
    ok &= out["decision"]["provisional"] and any("Safety check" in w for w in out["support"]["warnings"])  # CP02
    out = assess(SCENARIOS[12][1])                     # T13
    ok &= out["decision"]["provisional"] and out["diagnosis"]["rule"] == "DG22"
    out = assess(SCENARIOS[11][1])                     # T12: existing complaint replaces new NCCIA filing
    ok &= "NCCIA" not in [r["route"] for r in out["support"]["routes"]]
    print("  document details  " + ("OK" if ok else "FAIL"))
    return 0 if ok else 1


def check_plan():
    print("== Action plan ==")
    problems = []

    t1 = assess(SCENARIOS[0][1])
    plan = t1["decision"]["plan"]
    if not (plan and plan[0]["phase"] == "Right now" and "bank" in plan[0]["action"].lower()):
        problems.append("T1: first action should be an urgent bank contact")
    if not any("NCCIA" in i["action"] for i in plan):
        problems.append("T1: plan should include reporting to NCCIA")
    if "Do not click or reopen the link." not in t1["support"]["precautions"]:
        problems.append("T1: 'do not' advice should be a precaution")

    t5 = assess(SCENARIOS[4][1])
    if any(i["action"].lower().startswith(("do not", "never")) for i in t5["decision"]["plan"]):
        problems.append("T5: precautions should not appear as plan actions")
    if not any("pay" in p.lower() for p in t5["support"]["precautions"]):
        problems.append("T5: should warn against paying")

    t8 = assess(SCENARIOS[7][1])
    police = [i for i in t8["decision"]["plan"] if "police" in i["action"].lower()]
    if len(police) != 1 or police[0]["phase"] != "Right now":
        problems.append("T8: exactly one urgent police action expected")

    # Low urgency: nothing is time-critical, so nothing is "Right now"
    low = assess(case(main_symptom="paid_after_call_or_link", money_status="neither",
                      ongoing="no", time_elapsed="over_month"))
    if low["decision"]["urgency"] != "Low" or any(i["phase"] == "Right now" for i in low["decision"]["plan"]):
        problems.append("Low urgency should push actions to later phases")

    # The 'because' facts really come from the user's answers
    t2 = assess(SCENARIOS[1][1])
    primary = next(e for e in t2["trace"] if e["rule"] == "DG02")
    kinds = {(b["kind"], b.get("fact") or b.get("name")) for b in primary["because"]}
    if ("answer", "main_symptom") not in kinds or ("derived", "financial_loss_confirmed") not in kinds:
        problems.append("T2: DG02 should list its symptom and derived loss fact as the reason")

    # What-if reports plan changes
    before = assess(case(main_symptom="money_missing", money_status="lost",
                         transaction_circumstances="unauthorised", time_elapsed="under_24h"))
    after = assess(case(main_symptom="money_missing", money_status="lost",
                        transaction_circumstances="authorised_after_deception", time_elapsed="under_24h"))
    diff = compare(before, after)
    if not (diff["actions_added"] or diff["actions_removed"] or diff["actions_moved"]):
        problems.append("What-if should report changes to the action plan")

    for p in problems:
        print("  FAIL -", p)
    if not problems:
        print("  prioritized, deduplicated, context-dependent and traceable  OK")
    return len(problems)


def urgency_of(**changes):
    return assess(case(**changes))["decision"]


def check_urgency():
    print("== Urgency policy ==")
    problems = []

    def expect(label, got, level, rule=None):
        if got["urgency"] != level:
            problems.append(f"{label}: {got['urgency']} != {level}")
        if rule and rule not in got["deciding_rules"]:
            problems.append(f"{label}: expected {rule} to decide, got {got['deciding_rules']}")

    loss = dict(main_symptom="paid_after_call_or_link", money_status="lost",
                transaction_circumstances="authorised_after_deception")
    attempt = dict(main_symptom="paid_after_call_or_link", money_status="neither")
    # confirmed loss is treated differently from a mere attempt
    expect("loss 3 days ago", urgency_of(time_elapsed="1_7_days", **loss), "High", "UR12")
    expect("attempt 3 days ago", urgency_of(time_elapsed="1_7_days", **attempt), "Medium", "UR14")
    expect("loss 2 months ago", urgency_of(time_elapsed="over_month", **loss), "Medium", "UR13")
    expect("attempt 2 months ago", urgency_of(time_elapsed="over_month", **attempt), "Low", "UR10")
    # unknown timing is not treated as settled
    expect("loss, timing unknown", urgency_of(time_elapsed="not_sure", **loss), "High", "UR12")
    # specific escalations
    expect("ongoing account compromise, still has access",
           urgency_of(main_symptom="unusual_activity", access_status="partial", ongoing="yes"),
           "High", "UR15")
    expect("ongoing threats, no demand",
           urgency_of(main_symptom="threats_received", ongoing="yes"), "High", "UR16")
    expect("immediate danger", urgency_of(main_symptom="unwanted_contact", immediate_danger="yes"),
           "Critical", "UR01")
    # the explanation names the deciding rule and the facts behind it
    out = assess(case(time_elapsed="1_7_days", **loss))
    entry = next(e for e in out["trace"] if e["rule"] == "UR12")
    kinds = {b.get("name") for b in entry["because"]}
    if "harm_severe" not in kinds:
        problems.append("UR12 explanation should list the derived fact harm_severe")
    # High urgency must start something now, even when no urgency rule supplies a headline step
    plan = out["decision"]["plan"]
    if not plan or plan[0]["phase"] != "Right now":
        problems.append("High urgency: the plan must start with a 'Right now' action")

    for p in problems:
        print("  FAIL -", p)
    if not problems:
        print("  loss vs attempt, settled vs ongoing, escalations, explained by named rules  OK")
    return len(problems)


def check_strength():
    print("== Match strength ==")
    problems = []

    def strength_of(**changes):
        return assess(case(**changes))["diagnosis"]["match"]

    full = strength_of(main_symptom="money_missing", money_status="lost",
                       transaction_circumstances="unauthorised")
    if full["strength"] != "strong" or full["unmet"]:
        problems.append("all criteria met should be strong")
    partial = strength_of(main_symptom="money_missing", money_status="lost",
                          transaction_circumstances="not_sure")
    if partial["strength"] != "moderate" or len(partial["unmet"]) != 1 or "cause" not in partial["unmet"][0]:
        problems.append(f"2 of 3 criteria should be moderate and name the missing cause: {partial}")
    weak = strength_of(main_symptom="unwanted_contact", money_status="not_sure", private_content="prefer_not")
    if weak["strength"] != "weak" or weak["score"] != "1 of 3":
        problems.append(f"1 of 3 criteria should be weak: {weak}")
    out = assess(case(main_symptom="unwanted_contact", money_status="not_sure", private_content="prefer_not"))
    if not out["decision"]["provisional"]:
        problems.append("a weak match should make the result provisional")
    unsure = assess({"main_symptom": "not_sure"})["diagnosis"]
    if unsure["match"] is not None or unsure["strength"] is not None:
        problems.append("Unclassified has no criteria and no strength")

    for p in problems:
        print("  FAIL -", p)
    if not problems:
        print("  strength follows from the criteria met (strong / moderate / weak)  OK")
    return len(problems)


def check_indicators():
    print("== Secondary indicators ==")
    problems = []
    out = assess(SCENARIOS[0][1])                                     # fake call + loss
    if "Phishing or social engineering" not in out["diagnosis"]["indicators"]:
        problems.append("phishing indicator missing for a deceptive call")
    if not any(e["rule"] == "DG26" for e in out["trace"]):
        problems.append("the phishing indicator must come from its own rule (DG26)")
    # a later rule uses the indicator: the credential-protection steps (AC01)
    if "AC01" not in out["rules_fired"]:
        problems.append("AC01 should fire because the phishing indicator is present")
    # phishing is also detected from the contact channel, not just one symptom
    via_call = assess(case(main_symptom="goods_not_received", money_status="lost",
                           transaction_circumstances="authorised_after_deception", platform=["call_sms"]))
    if "Phishing or social engineering" not in via_call["diagnosis"]["indicators"]:
        problems.append("a scam run by phone call should carry the phishing indicator")
    # no deception, no indicator
    clean = assess(case(main_symptom="money_missing", money_status="lost",
                        transaction_circumstances="unauthorised"))
    if "Phishing or social engineering" in clean["diagnosis"]["indicators"]:
        problems.append("phishing should not appear when no deception is involved")
    for p in problems:
        print("  FAIL -", p)
    if not problems:
        print("  phishing is a defined indicator, derived by its own rule and used by later rules  OK")
    return len(problems)


def check_what_if():
    print("== What-if ==")
    before = assess(case(main_symptom="money_missing", money_status="lost",
                         transaction_circumstances="unauthorised", time_elapsed="under_24h"))
    after = assess(case(main_symptom="money_missing", money_status="lost",
                        transaction_circumstances="authorised_after_deception", time_elapsed="under_24h"))
    diff = compare(before, after)
    ok = (before["diagnosis"]["rule"] == "DG02" and after["diagnosis"]["rule"] == "DG03"
          and "UR06" in diff["rules_stopped"]
          and diff["routes"]["Bank or wallet provider"] == ("Do first", "Also relevant"))
    print("  DG02 -> DG03, UR06 stops, bank Do first -> Also relevant  " + ("OK" if ok else "FAIL"))
    if not ok:
        print("  diff:", diff)
    return 0 if ok else 1


def check_fuzz(n=20000, seed=7):
    """Random answers: exactly one primary diagnosis, no crashes, no exclusivity conflicts."""
    print("== Fuzz test ==")
    rng = random.Random(seed)
    for i in range(n):
        answers = {}
        for q in QUESTIONS:
            if rng.random() < 0.08:                    # sometimes leave a question unanswered
                continue
            values = [v for v, _ in q["options"]]
            if q["type"] == "single":
                answers[q["fact"]] = rng.choice(values)
            else:
                answers[q["fact"]] = rng.sample(values, rng.randint(0, min(3, len(values))))
        out = assess(answers)
        primaries = [t for t in out["trace"] if t["group"] == "DG" and t["result"].startswith("Diagnosis:")]
        assert len(primaries) == 1, (answers, primaries)
        assert not out["notes"], (answers, out["notes"])
        assert out["decision"]["urgency"] in URGENCY_RANK
        assert out["decision"]["urgency_rules"] and out["decision"]["deciding_rules"], answers
        match = out["diagnosis"]["match"]
        if match:
            total = len(CRITERIA[out["diagnosis"]["primary"]])
            met = len(match["met"])
            expected = "strong" if met == total else "moderate" if met * 2 >= total else "weak"
            assert match["strength"] == expected and out["diagnosis"]["strength"] == expected, match
        plan = out["decision"]["plan"]
        for i, item in enumerate(plan):
            assert item["phase"] in PHASES and item["rules"] and item["action"] and item["reason"], item
            assert all(not _same_action(item["action"], other["action"]) for other in plan[i + 1:]), plan
        assert all("because" in entry for entry in out["trace"])
    print(f"  {n} random answer sets: one diagnosis, urgency always from a rule, strength consistent, clean plan  OK")


def check_adaptive_questions():
    print("== Adaptive questions ==")
    no_money = {q["id"] for q in visible_questions({"money_status": "neither"})}
    lost = {q["id"] for q in visible_questions({"money_status": "lost"})}
    demanded = {q["id"] for q in visible_questions({"money_status": "demanded"})}
    ok = ("Q5" not in no_money and "Q6" not in no_money and "Q17" not in no_money
          and {"Q5", "Q6", "Q17"} <= lost and {"Q5", "Q6"} <= demanded and "Q17" not in demanded)
    print("  Q5/Q6 when money lost or demanded, Q17 only when lost  " + ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    check_structure()
    failures = check_scenarios()
    failures += check_extra_expectations()
    failures += check_plan()
    failures += check_urgency()
    failures += check_strength()
    failures += check_indicators()
    failures += check_what_if()
    failures += check_adaptive_questions()
    check_fuzz()
    print()
    print("ALL CHECKS PASSED" if failures == 0 else f"{failures} CHECK(S) FAILED")
    raise SystemExit(1 if failures else 0)
