"""
engine.py - the INFERENCE ENGINE of the Cybercrime Complaint Expert System.

It reads the knowledge base (rules.py), takes the user's answers (the "facts")
and reasons with FORWARD CHAINING in four stages. Each stage uses the facts
produced by the stage before it, so the Inference Trace shows a real chain:

    answers -> derived facts -> diagnosis -> urgency/first step -> routes, checklists, warnings

    Stage 1  Derive facts        DF rules
    Stage 2  Diagnose            DG rules (primary diagnosis, indicators), DD rules (alternatives)
    Stage 3  Decide              UR rules (urgency), AC rules (protective actions)
    Stage 4  Support             EV rules (evidence), RT rules (routes), CP rules (warnings)

Main functions
--------------
    assess(answers)          run the whole reasoning and return a result dictionary
    compare(before, after)   what-if helper: what changed between two assessments
    visible_questions(ans)   which questions to show (adaptive questionnaire)
    describe(condition)      turn a rule's IF part into readable text
    rules_as_text()          every rule as readable text (useful for the PDF)

Key design rule: a missing or "not_sure" answer is never treated as "no".

How the four required concepts connect in the result
----------------------------------------------------
    Diagnosis        stage 2 -> primary diagnosis, match strength (computed from criteria),
                     secondary indicators (each from its own rule), alternative diagnoses
    Inferencing      every fired rule is recorded with the facts that made it fire
    Decision making  the prioritized ACTION PLAN, built from the diagnosis, the urgency,
                     the protective-step rules and the route roles
    Decision support routes, evidence checklist, precautions, warnings, alternatives
"""

import re

from rules import (
    QUESTIONS, RULES, CRITERIA, DERIVED_FACTS, URGENCY_RANK, ROLE_RANK,
    STRONG, MODERATE, WEAK, MEDIUM, LOW, UNCLASS, NCCIA, NCCIA_EXISTING,
    DO_FIRST, FOLLOW_UP, ALSO, ROUTE_ACTIONS, ROUTE_KEYWORDS, PHASES,
)

STAGE_NAMES = {
    1: "Stage 1: derive facts",
    2: "Stage 2: diagnose",
    3: "Stage 3: decide",
    4: "Stage 4: support",
}

_QUESTION_BY_FACT = {q["fact"]: q for q in QUESTIONS}


# --------------------------------------------------------------------------
# Evaluating the IF part of a rule
# --------------------------------------------------------------------------
def evaluate(cond, ctx):
    """Return True/False for a condition, using the current facts in ctx."""
    op = cond[0]
    facts = ctx["facts"]
    if op == "eq":
        return facts.get(cond[1]) == cond[2]
    if op == "in":
        return facts.get(cond[1]) in cond[2]
    if op == "has":
        value = facts.get(cond[1])
        return value is not None and any(v in value for v in cond[2])
    if op == "lacks":
        # Needs the question to be answered: unanswered is NOT the same as "none".
        value = facts.get(cond[1])
        return value is not None and not any(v in value for v in cond[2])
    if op == "flag":
        return ctx["derived"].get(cond[1], False)
    if op == "primary":
        return ctx["primary"] in cond[1]
    if op == "indicator":
        return any(name in ctx.get("indicators", []) for name in cond[1])
    if op == "strength":
        return ctx["strength"] in cond[1]
    if op == "no_primary":
        return ctx["primary"] is None
    if op == "not":
        return not evaluate(cond[1], ctx)
    if op == "and":
        return all(evaluate(c, ctx) for c in cond[1])
    if op == "or":
        return any(evaluate(c, ctx) for c in cond[1])
    raise ValueError(f"unknown condition type: {op}")


def _join(values):
    values = [str(v) for v in values]
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " or " + values[-1]


def describe(cond, top=True):
    """Readable text for a condition (used by the explanation and the PDF)."""
    op = cond[0]
    if op == "eq":
        return f"{cond[1]} = {cond[2]}"
    if op == "in":
        return f"{cond[1]} is {_join(cond[2])}"
    if op == "has":
        return f"{cond[1]} includes {_join(cond[2])}"
    if op == "lacks":
        return f"none of {_join(cond[2])} in {cond[1]}"
    if op == "flag":
        return cond[1]
    if op == "primary":
        return f"primary diagnosis is {_join(cond[1])}"
    if op == "indicator":
        return f"indicator present: {_join(cond[1])}"
    if op == "strength":
        return f"diagnosis strength is {_join(cond[1])}"
    if op == "no_primary":
        return "no primary diagnosis rule fired"
    if op == "not":
        return "NOT " + describe(cond[1], top=False)
    if op in ("and", "or"):
        word = " AND " if op == "and" else " OR "
        text = word.join(describe(c, top=False) for c in cond[1])
        return text if top else f"({text})"
    raise ValueError(f"unknown condition type: {op}")


def supporting_facts(cond, ctx):
    """
    The actual facts behind a rule that fired: which answers, derived facts and
    diagnosis made its IF part true. This is the "because" shown in the explanation.
    """
    op = cond[0]
    facts = ctx["facts"]
    if op in ("eq", "in"):
        if evaluate(cond, ctx):
            return [{"kind": "answer", "fact": cond[1], "value": facts[cond[1]]}]
        return []
    if op == "has":
        value = facts.get(cond[1])
        matched = [v for v in cond[2] if value is not None and v in value]
        return [{"kind": "answer", "fact": cond[1], "value": matched}] if matched else []
    if op == "lacks":
        if evaluate(cond, ctx):
            return [{"kind": "missing", "fact": cond[1], "value": list(cond[2])}]
        return []
    if op == "flag":
        return [{"kind": "derived", "name": cond[1]}] if evaluate(cond, ctx) else []
    if op == "primary":
        return [{"kind": "diagnosis", "value": ctx["primary"]}] if evaluate(cond, ctx) else []
    if op == "indicator":
        found = [n for n in cond[1] if n in ctx.get("indicators", [])]
        return [{"kind": "indicator", "value": found}] if found else []
    if op == "and":
        found = []
        for sub in cond[1]:
            found += supporting_facts(sub, ctx)
        return found
    if op == "or":
        found = []
        for sub in cond[1]:
            if evaluate(sub, ctx):
                found += supporting_facts(sub, ctx)
        return found
    return []                                     # NOT, strength, no_primary: nothing to show


# --------------------------------------------------------------------------
# Checking and cleaning the answers
# --------------------------------------------------------------------------
def validate_answers(answers):
    """
    Check every answer against the allowed values and return a clean copy.
    - unknown question keys or invalid values raise ValueError
    - missing answers stay missing (they are never turned into "no")
    - multiple-choice answers become lists; an empty evidence/reported list
      means ["none"]; "none" is dropped if other choices are present
    """
    facts = {}
    for fact, value in answers.items():
        question = _QUESTION_BY_FACT.get(fact)
        if question is None:
            raise ValueError(f"unknown answer key: {fact}")
        allowed = [v for v, _ in question["options"]]
        if value is None:
            continue
        if question["type"] == "single":
            if value not in allowed:
                raise ValueError(f"invalid value for {fact}: {value!r}")
            facts[fact] = value
        else:
            if isinstance(value, str):
                value = [value]
            value = list(value)
            for v in value:
                if v not in allowed:
                    raise ValueError(f"invalid value for {fact}: {v!r}")
            if "none" in allowed:
                if not value:
                    value = ["none"]
                elif "none" in value and len(value) > 1:
                    value = [v for v in value if v != "none"]
            facts[fact] = value
    return facts


def visible_questions(answers):
    """Questions to show now (adaptive questionnaire), given the answers so far."""
    ctx = {"facts": dict(answers), "derived": {}, "primary": None, "strength": None}
    return [q for q in QUESTIONS if q["asked_if"] is None or evaluate(q["asked_if"], ctx)]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _rules_of(kind):
    return [r for r in RULES if r["kind"] == kind]


def _label(diagnosis, variant):
    return f"{diagnosis} ({variant})" if variant else diagnosis


def _summarise(rule):
    """One short line describing what a fired rule concluded."""
    then, kind = rule["then"], rule["kind"]
    if kind == "derive":
        return f"Derived fact: {then['derive']}"
    if kind in ("primary", "fallback"):
        return f"Diagnosis: {_label(then['diagnosis'], then['variant'])}"
    if kind == "indicator":
        return f"Indicator: {then['indicator']}"
    if kind == "alternative":
        return f"Alternative diagnosis: {then['alternative']}"
    if kind == "urgency":
        return f"Urgency: {then['urgency']}"
    if kind == "action":
        text = "Protective steps: " + " ".join(then["steps"])
        if then["avoid"]:
            text += " Avoid: " + " ".join(then["avoid"])
        return text
    if kind == "evidence":
        return "Checklist: " + then["checklist"]
    if kind == "route":
        return "; ".join(f"{r['route']}: {r['role']}" for r in then["routes"])
    if kind == "completeness":
        return "Warning: " + then["warning"]
    return ""


def _add_unique(items, value):
    if value not in items:
        items.append(value)


# --------------------------------------------------------------------------
# Match strength: how well the answers confirm the chosen diagnosis
# --------------------------------------------------------------------------
def match_strength(diagnosis, ctx):
    """
    Check the diagnosis's defining criteria (rules.CRITERIA) against the answers.
        strong    every criterion is confirmed
        moderate  at least half are confirmed
        weak      fewer than half are confirmed
    A criterion that cannot be confirmed (including an unanswered or "not sure" answer)
    counts as not met. Returns None for diagnoses without criteria (Unclassified).
    """
    criteria = CRITERIA.get(diagnosis)
    if not criteria:
        return None
    met = [text for text, cond in criteria if evaluate(cond, ctx)]
    unmet = [text for text, cond in criteria if not evaluate(cond, ctx)]
    if not unmet:
        level = STRONG
    elif len(met) * 2 >= len(criteria):
        level = MODERATE
    else:
        level = WEAK
    return {"strength": level, "met": met, "unmet": unmet,
            "score": f"{len(met)} of {len(criteria)}"}


# --------------------------------------------------------------------------
# The action plan (decision making)
# --------------------------------------------------------------------------
def _tokens(text):
    return set(re.findall(r"[a-z']+", text.lower()))


def _same_action(a, b):
    """True when two action texts say essentially the same thing (word overlap)."""
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / max(1, len(ta | tb)) >= 0.7


def _merge_because(items, more):
    for entry in more:
        if entry not in items:
            items.append(entry)


def _build_plan(urgency, top_urgency_rules, actions, routes, because):
    """
    Turn the diagnosis, urgency, protective-step rules and route roles into one
    ordered list of actions. Each item says WHEN (phase), WHAT, and WHY (the rules
    and facts behind it). Nothing here is fixed text: which actions appear, and in
    which phase, depends on the rules that fired for this user's answers.

        Right now  urgent steps (the highest-urgency rule's first step, priority-1 steps)
        Next       remaining protective steps and the routes to report to first
        Then       other relevant or optional routes

    When urgency is Low, nothing is time-critical, so every action moves one phase later.
    """
    plan = []
    shift = 1 if urgency == LOW else 0

    def add(phase_index, action, rule_ids, reason, role=None):
        phase = PHASES[min(phase_index + shift, len(PHASES) - 1)]
        for item in plan:
            if _same_action(action, item["action"]):          # already covered: just link the rule
                for rid in rule_ids:
                    if rid not in item["rules"]:
                        item["rules"].append(rid)
                        _merge_because(item["because"], because.get(rid, []))
                return
        item = {"phase": phase, "action": action, "rules": list(rule_ids), "reason": reason,
                "role": role, "because": []}
        for rid in rule_ids:
            _merge_because(item["because"], because.get(rid, []))
        plan.append(item)

    # The highest-urgency rule gives the headline step: urgent levels go first, Medium goes
    # next, Low goes later. Other urgent circumstances are covered by the steps below.
    headline = next((r for r in top_urgency_rules if r["then"]["first_step"]), None)
    if headline:
        index = 0 if URGENCY_RANK[headline["then"]["urgency"]] >= URGENCY_RANK["High"] else 1
        add(index, headline["then"]["first_step"], [headline["id"]], headline["reason"])

    # Protective steps from the AC rules (danger first), by their priority.
    for rule in actions:
        index = rule["then"]["priority"] - 1
        for step in rule["then"]["steps"]:
            add(index, step, [rule["id"]], rule["reason"])

    # Routes: Do first / Follow up become actions, the rest follow. Skip a route when an
    # existing step already tells the user to contact it.
    all_text = " ".join(item["action"].lower() for item in plan)
    for entry in routes:
        words = ROUTE_KEYWORDS.get(entry["route"], ())
        if any(w in all_text for w in words):
            continue
        phase_index = 1 if entry["role"] in (DO_FIRST, FOLLOW_UP) else 2
        add(phase_index, ROUTE_ACTIONS[entry["route"]], entry["rules"], " ".join(entry["notes"]),
            role=entry["role"])

    plan.sort(key=lambda item: PHASES.index(item["phase"]))   # stable: keeps order inside a phase
    # High or Critical urgency means something must start now: if no step is urgent yet,
    # the first step of the plan moves to "Right now".
    if URGENCY_RANK[urgency] >= URGENCY_RANK["High"] and plan and plan[0]["phase"] != PHASES[0]:
        plan[0]["phase"] = PHASES[0]
    return plan


# --------------------------------------------------------------------------
# The inference: assess()
# --------------------------------------------------------------------------
def assess(answers):
    """
    Run the expert system on the user's answers (a dict of fact -> value)
    and return the full result:

        result["diagnosis"]  primary diagnosis, strength, indicators, alternatives
        result["decision"]   urgency, first step, provisional flag
        result["support"]    routes with roles, protective steps, evidence checklist, warnings
        result["trace"]      every rule that fired, in order (the Inference Trace)
    """
    facts = validate_answers(answers)
    ctx = {
        "facts": facts,
        "derived": {name: False for name in DERIVED_FACTS},
        "primary": None,
        "strength": None,
        "indicators": [],
    }
    trace = []
    notes = []
    because = {}                      # rule ID -> the facts that made it fire

    def record(stage, rule):
        because[rule["id"]] = supporting_facts(rule["when"], ctx)
        trace.append({
            "stage": stage,
            "stage_name": STAGE_NAMES[stage],
            "rule": rule["id"],
            "group": rule["group"],
            "tag": rule["tag"],
            "if": describe(rule["when"]),
            "because": because[rule["id"]],
            "result": _summarise(rule),
            "reason": rule["reason"],
        })

    # ---- Stage 1: derive facts -------------------------------------------
    for rule in _rules_of("derive"):
        if evaluate(rule["when"], ctx):
            ctx["derived"][rule["then"]["derive"]] = True
            record(1, rule)

    # ---- Stage 2: diagnose -----------------------------------------------
    diagnosis = {"primary": None, "variant": None, "strength": None, "match": None, "rule": None,
                 "indicators": ctx["indicators"], "alternatives": []}

    fired_primary = [r for r in _rules_of("primary") if evaluate(r["when"], ctx)]
    if len(fired_primary) > 1:
        # Should never happen (the rules are mutually exclusive); keep the first.
        notes.append("Conflict: more than one primary rule fired (" +
                     ", ".join(r["id"] for r in fired_primary) + "); the first was used.")
    chosen = fired_primary[0] if fired_primary else None
    if chosen is None:
        for rule in _rules_of("fallback"):
            if evaluate(rule["when"], ctx):
                chosen = rule
                break
    if chosen is not None:
        then = chosen["then"]
        ctx["primary"] = then["diagnosis"]
        match = match_strength(then["diagnosis"], ctx)          # computed, not typed in
        ctx["strength"] = match["strength"] if match else None
        diagnosis.update(primary=then["diagnosis"], variant=then["variant"],
                         strength=ctx["strength"], match=match, rule=chosen["id"])
        record(2, chosen)

    # Secondary indicators: each has its own rule, and the result is added to ctx["indicators"]
    # (the same list as diagnosis["indicators"]) so that later rules can test for them.
    for rule in _rules_of("indicator"):
        if evaluate(rule["when"], ctx):
            _add_unique(ctx["indicators"], rule["then"]["indicator"])
            record(2, rule)
    for rule in _rules_of("alternative"):
        if evaluate(rule["when"], ctx):
            _add_unique(diagnosis["alternatives"], rule["then"]["alternative"])
            record(2, rule)

    diagnosis["label"] = _label(diagnosis["primary"], diagnosis["variant"])
    diagnosis["safeguarding_minor"] = facts.get("minor_involved") == "yes"

    # ---- Stage 3: decide (urgency + protective actions) -------------------
    fired_urgency = []
    provisional = False
    for rule in _rules_of("urgency"):
        if evaluate(rule["when"], ctx):
            fired_urgency.append(rule)
            provisional = provisional or rule["then"]["provisional"]
            record(3, rule)

    if fired_urgency:
        top = max(URGENCY_RANK[r["then"]["urgency"]] for r in fired_urgency)
        top_rules = [r for r in fired_urgency if URGENCY_RANK[r["then"]["urgency"]] == top]
        urgency = top_rules[0]["then"]["urgency"]
        urgency_first_step = next((r["then"]["first_step"] for r in top_rules
                                   if r["then"]["first_step"]), None)
        urgency_rules = [r["id"] for r in fired_urgency]
    else:
        # Safety net only: the urgency rules cover every diagnosed incident, so this should
        # never happen. If it does, say so openly and stay cautious.
        top_rules = []
        urgency, urgency_first_step, urgency_rules = MEDIUM, None, []
        provisional = True
        notes.append("No urgency rule matched these answers, so a cautious Medium was applied.")

    actions = []
    for rule in _rules_of("action"):
        if evaluate(rule["when"], ctx):
            actions.append(rule)
            record(3, rule)
    # Safety first: the danger rule (AC13) always leads the checklist.
    actions.sort(key=lambda r: (r["id"] != "AC13", r["id"]))
    protective_steps, precautions = [], []
    for rule in actions:
        for step in rule["then"]["steps"]:
            _add_unique(protective_steps, step)
        for item in rule["then"]["avoid"]:
            _add_unique(precautions, item)

    if urgency_first_step:
        first_step = urgency_first_step
    elif actions:
        first_step = min(actions, key=lambda r: r["then"]["priority"])["then"]["steps"][0]
    else:
        first_step = "Review the support guidance below and report when you are ready."

    # ---- Stage 4: support (evidence, routes, warnings) --------------------
    checklist = []
    for rule in _rules_of("evidence"):
        if evaluate(rule["when"], ctx):
            _add_unique(checklist, rule["then"]["checklist"])
            record(4, rule)

    routes = {}

    def add_routes(rule):
        for item in rule["then"]["routes"]:
            entry = routes.setdefault(item["route"], {"route": item["route"], "role": item["role"],
                                                       "notes": [], "rules": []})
            if ROLE_RANK[item["role"]] > ROLE_RANK[entry["role"]]:
                entry["role"] = item["role"]          # the strongest role wins
            _add_unique(entry["notes"], item["note"])
            _add_unique(entry["rules"], rule["id"])

    for rule in _rules_of("route"):
        if evaluate(rule["when"], ctx):
            add_routes(rule)
            record(4, rule)

    warnings = []
    for rule in _rules_of("completeness"):
        if evaluate(rule["when"], ctx):
            _add_unique(warnings, rule["then"]["warning"])
            provisional = provisional or rule["then"]["provisional"]
            if "routes" in rule["then"]:
                add_routes(rule)
            record(4, rule)

    # If a complaint already exists, follow it up instead of filing a new one.
    if NCCIA_EXISTING in routes and NCCIA in routes:
        for note in routes[NCCIA]["notes"]:
            _add_unique(routes[NCCIA_EXISTING]["notes"], note)
        del routes[NCCIA]

    ordered_routes = sorted(routes.values(), key=lambda r: -ROLE_RANK[r["role"]])

    # The plan needs the diagnosis, the urgency AND the route roles, so it is assembled last.
    plan = _build_plan(urgency, top_rules, actions, ordered_routes, because)

    return {
        "facts": facts,
        "derived": dict(ctx["derived"]),
        "diagnosis": diagnosis,
        "decision": {
            "urgency": urgency,
            "first_step": first_step,
            "provisional": provisional,
            "urgency_rules": urgency_rules,
            "deciding_rules": [r["id"] for r in top_rules],
            "plan": plan,
        },
        "support": {
            "routes": ordered_routes,
            "protective_steps": protective_steps,
            "precautions": precautions,
            "evidence_checklist": checklist,
            "warnings": warnings,
        },
        "trace": trace,
        "rules_fired": [t["rule"] for t in trace],
        "notes": notes,
    }


# --------------------------------------------------------------------------
# What-if support
# --------------------------------------------------------------------------
def compare(before, after):
    """
    Compare two assessment results (before and after changing an answer).
    Returns only what changed, plus the rules that started or stopped firing.
    """
    changes = {}
    b_d, a_d = before["diagnosis"], after["diagnosis"]
    for key in ("label", "strength"):
        if b_d[key] != a_d[key]:
            changes[key] = (b_d[key], a_d[key])
    for key in ("indicators", "alternatives"):
        if b_d[key] != a_d[key]:
            changes[key] = (b_d[key], a_d[key])
    if before["decision"]["urgency"] != after["decision"]["urgency"]:
        changes["urgency"] = (before["decision"]["urgency"], after["decision"]["urgency"])
    if before["decision"]["provisional"] != after["decision"]["provisional"]:
        changes["provisional"] = (before["decision"]["provisional"], after["decision"]["provisional"])

    b_routes = {r["route"]: r["role"] for r in before["support"]["routes"]}
    a_routes = {r["route"]: r["role"] for r in after["support"]["routes"]}
    route_changes = {}
    for route in sorted(set(b_routes) | set(a_routes)):
        if b_routes.get(route) != a_routes.get(route):
            route_changes[route] = (b_routes.get(route), a_routes.get(route))
    if route_changes:
        changes["routes"] = route_changes

    b_plan = {i["action"]: i["phase"] for i in before["decision"]["plan"]}
    a_plan = {i["action"]: i["phase"] for i in after["decision"]["plan"]}
    changes["actions_added"] = [a for a in a_plan if a not in b_plan]
    changes["actions_removed"] = [a for a in b_plan if a not in a_plan]
    changes["actions_moved"] = {a: (b_plan[a], a_plan[a]) for a in a_plan
                                if a in b_plan and a_plan[a] != b_plan[a]}

    b_rules, a_rules = set(before["rules_fired"]), set(after["rules_fired"])
    changes["rules_started"] = sorted(a_rules - b_rules)
    changes["rules_stopped"] = sorted(b_rules - a_rules)
    return changes


# --------------------------------------------------------------------------
# Readable rule listing (handy for the PDF and the viva)
# --------------------------------------------------------------------------
def rules_as_text():
    """Every rule as 'ID [tag]: IF ... THEN ...' text."""
    lines = []
    for rule in RULES:
        lines.append(f"{rule['id']} [{rule['tag']}]: IF {describe(rule['when'])} "
                     f"THEN {_summarise(rule)}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Tiny demo: a fake bank call followed by a loss of money.
    demo = {
        "main_symptom": "paid_after_call_or_link", "money_status": "lost",
        "transaction_circumstances": "both", "time_elapsed": "under_24h",
        "access_status": "full", "ongoing": "no", "immediate_danger": "no",
        "minor_involved": "no", "environment": "personal",
        "platform": ["call_sms"], "evidence_list": ["screenshots"],
        "already_reported": ["none"],
    }
    out = assess(demo)
    print("Diagnosis:", out["diagnosis"]["label"], f"({out['diagnosis']['strength']})")
    print("Urgency:  ", out["decision"]["urgency"], "-", out["decision"]["first_step"])
    for r in out["support"]["routes"]:
        print("Route:    ", r["route"], "->", r["role"])
    print("\nInference trace:")
    for t in out["trace"]:
        print(f"  {t['rule']:5} {t['result']}")
