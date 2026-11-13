
"""
app.py - Streamlit interface of the Pakistani Cybercrime Complaint
Assessment & Reporting Expert System.

Run locally: streamlit run app.py

The page follows the four headings required by the course:
    Diagnosis | Decision Making | Decision Support | Inference Trace

A separate What-if section allows users to try a different answer.

All reasoning is performed by engine.py using rules.py.
This file handles the questionnaire and presentation of results.
"""

import html

import streamlit as st

from engine import assess, compare, evaluate, visible_questions
from rules import (
    QUESTIONS, RULES, RULE_BY_ID, PHASES, INDICATOR_DEFINITIONS,
    DO_FIRST, FOLLOW_UP, ALSO, OPTIONAL,
    CRITICAL, HIGH, MEDIUM, LOW,
    NCCIA, NCCIA_EXISTING, MOHTASIB, PKCERT,
)


TITLE = "Pakistan Cybercrime Complaint Assessment & Reporting"

st.set_page_config(
    page_title="CyberX Pakistan",
    page_icon="🛡️",
    layout="centered",
)


# --------------------------------------------------------------------------
# Look and feel
# --------------------------------------------------------------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&display=swap');

    html, body, .stApp, .stMarkdown, button, input, textarea, label {
        font-family: 'Atkinson Hyperlegible', 'Segoe UI', sans-serif;
    }

    .block-container {
        padding-top: 2rem;
        max-width: 760px;
    }

    h1 {
        font-size: 1.7rem;
        line-height: 1.25;
    }

    .urgency {
        border-left: 10px solid var(--edge);
        background: var(--tint);
        padding: 1rem 1.2rem;
        border-radius: 4px;
        margin: .5rem 0 1rem 0;
    }

    .urgency .level {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--edge);
    }

    .urgency .step {
        margin-top: .3rem;
        font-size: 1.05rem;
    }

    .route {
        border-left: 5px solid var(--edge);
        padding: .35rem 0 .35rem .9rem;
        margin: .6rem 0;
    }

    .route .name {
        font-weight: 700;
    }

    .route .role {
        font-size: .9rem;
        color: #44556a;
    }

    .diagnosis {
        font-size: 1.6rem;
        font-weight: 700;
        margin: 0;
    }

    .muted {
        color: #5a6b7e;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


URGENCY_COLOURS = {
    CRITICAL: ("#B3261E", "#FBEAE8"),
    HIGH: ("#A64B00", "#FDF0E1"),
    MEDIUM: ("#6F5700", "#FBF5DA"),
    LOW: ("#2E6B3A", "#E8F3EA"),
}

ROLE_COLOURS = {
    DO_FIRST: "#0F6B63",
    FOLLOW_UP: "#2F5F9E",
    ALSO: "#5a6b7e",
    OPTIONAL: "#9aa6b2",
}

ROLE_ORDER = [DO_FIRST, FOLLOW_UP, ALSO, OPTIONAL]


# Official pages the reporting routes point to.
ROUTE_LINKS = {
    NCCIA: [
        ("NCCIA website", "https://www.nccia.gov.pk/"),
        ("NCCIA complaint portal", "https://complaint.nccia.gov.pk/"),
    ],
    NCCIA_EXISTING: [
        ("NCCIA website", "https://www.nccia.gov.pk/"),
    ],
    MOHTASIB: [
        ("SBP Sunwai complaint portal", "https://sunwai.sbp.org.pk/"),
    ],
    PKCERT: [
        ("PKCERT incident reporting", "https://pkcert.gov.pk/report-incident/"),
    ],
}


DERIVED_LABELS = {
    "financial_loss_confirmed": "Financial loss confirmed",
    "demand_present": "Money demand present",
    "unauthorised_access_suspected": "Unauthorised access suspected",
    "deception_involved": "Deception involved",
    "private_content_at_stake": "Private content at stake",
    "harm_severe": "Serious harm present",
    "harm_moderate": "Moderate harm present",
    "incident_settled": "Incident is over",
}


FACT_SHORT = {
    "main_symptom": "What you noticed",
    "immediate_danger": "Immediate danger",
    "minor_involved": "Under 18",
    "money_status": "Money",
    "amount_range": "Amount",
    "payment_method": "Payment method",
    "time_elapsed": "Began",
    "ongoing": "Still ongoing",
    "offender_known": "Offender",
    "platform": "Channel",
    "private_content": "Private content",
    "access_status": "Access",
    "evidence_list": "Evidence held",
    "already_reported": "Already reported",
    "desired_outcome": "Your goal",
    "environment": "Setting",
    "transaction_circumstances": "Payment circumstances",
}


QUESTION_BY_ID = {q["id"]: q for q in QUESTIONS}
QUESTION_BY_FACT = {q["fact"]: q for q in QUESTIONS}


SECTIONS = [
    ("What Happened", ["Q1", "Q4", "Q17", "Q5", "Q6", "Q10", "Q7", "Q8"]),
    ("Safety and Access", ["Q2", "Q3", "Q11", "Q12", "Q16"]),
    ("Evidence and Goals", ["Q9", "Q13", "Q14", "Q15"]),
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def label_of(fact, value):
    """Convert an answer value into its user-facing question label."""
    if fact not in QUESTION_BY_FACT:
        return str(value)

    options = dict(QUESTION_BY_FACT[fact]["options"])

    if isinstance(value, list):
        return ", ".join(options.get(v, v) for v in value)

    return options.get(value, value)


def esc(text):
    """Escape text before inserting it into HTML."""
    return html.escape(str(text))


def because_text(items, result=None):
    """
    Convert the facts behind a conclusion into understandable explanations.

    Derived facts are explained using their source facts where available.
    """

    phrases = []

    for item in items:

        if item["kind"] == "answer":
            text = (
                f"{FACT_SHORT.get(item['fact'], item['fact'])}: "
                f"{label_of(item['fact'], item['value'])}"
            )

        elif item["kind"] == "derived":
            text = DERIVED_LABELS.get(item["name"], item["name"])

            source = []

            if result is not None:
                source = next(
                    (
                        entry["because"]
                        for entry in result["trace"]
                        if entry["group"] == "DF"
                        and entry["result"] == f"Derived fact: {item['name']}"
                    ),
                    [],
                )

            origin = because_text(source)

            if origin:
                text += f" (from {'; '.join(origin)})"

        elif item["kind"] == "indicator":
            text = "Indicator: " + ", ".join(item["value"])

        elif item["kind"] == "missing":
            text = (
                f"Not recorded: "
                f"{label_of(item['fact'], item['value']).lower()}"
            )

        else:
            text = f"Diagnosis: {item['value']}"

        if text not in phrases:
            phrases.append(text)

    return phrases


def trace_entry(result, rule_id):
    """Find a particular rule's trace entry."""
    return next(
        entry for entry in result["trace"]
        if entry["rule"] == rule_id
    )


def selected_evidence(result):
    """Return evidence selected by the user, if provided."""
    evidence = result["facts"].get("evidence_list")

    if not evidence:
        return []

    if isinstance(evidence, list):
        return [label_of("evidence_list", evidence)]

    return [label_of("evidence_list", evidence)]


# --------------------------------------------------------------------------
# Questionnaire
# --------------------------------------------------------------------------

def ask(question):
    """Draw one question and return the answer."""

    values = [v for v, _ in question["options"]]
    labels = dict(question["options"])
    key = f"q_{question['fact']}"

    if question["type"] == "multi":
        return st.multiselect(
            question["text"],
            values,
            format_func=labels.get,
            key=key,
            placeholder="Choose all that apply",
        )

    if len(values) <= 4:
        return st.radio(
            question["text"],
            values,
            format_func=labels.get,
            index=None,
            key=key,
            horizontal=len(values) <= 3,
        )

    return st.selectbox(
        question["text"],
        values,
        format_func=labels.get,
        index=None,
        key=key,
        placeholder="Choose an answer",
    )


def draw_questionnaire():
    """Draw visible questions and collect the answers."""

    answers = {}

    for title, ids in SECTIONS:

        st.subheader(title)

        for qid in ids:

            question = QUESTION_BY_ID[qid]

            if question["asked_if"] is not None and not evaluate(
                question["asked_if"],
                {
                    "facts": answers,
                    "derived": {},
                    "primary": None,
                    "strength": None,
                },
            ):
                continue

            value = ask(question)

            if value:
                answers[question["fact"]] = value

    return answers


def clean(answers):
    """Remove answers to questions not asked in this situation."""

    shown = {
        q["fact"]
        for q in visible_questions(answers)
    }

    return {
        fact: value
        for fact, value in answers.items()
        if fact in shown
    }


# --------------------------------------------------------------------------
# Diagnosis
# --------------------------------------------------------------------------

def show_diagnosis(result):

    d = result["diagnosis"]

    st.subheader("Incident Classification")

    st.caption(
        "Based on your answers. This is a classification to guide you, "
        "not a legal conclusion."
    )

    # Main diagnosis: larger, bold and teal.
    st.markdown(
        f'<p class="diagnosis" style="'
        f'font-size:26px; '
        f'font-weight:750; '
        f'color:#42B8A8; '
        f'margin-top:8px; '
        f'margin-bottom:10px;">'
        f'{esc(d["label"])}</p>',
        unsafe_allow_html=True,
    )

    match = d["match"]

    if match:
        st.markdown(
            f'<span class="muted">Assessment confidence: '
            f'<b>{esc(match["strength"])}</b> '
            f'({esc(match["score"])} criteria confirmed)</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="muted">There is not enough information '
            'for a reliable diagnosis.</span>',
            unsafe_allow_html=True,
        )

    if result["decision"]["provisional"]:
        st.warning(
            "This result is provisional because some answers are unclear. "
            "Answer the unclear questions to improve the assessment."
        )

    if d["safeguarding_minor"]:
        st.info(
            "Safeguarding: the affected person is under 18. "
            "A parent, guardian or trusted adult should be involved."
        )

    primary = trace_entry(result, d["rule"])

    facts = because_text(primary["because"], result)

    if facts:
        st.markdown(
            '<p style="font-size:20px; font-weight:700; '
            'color:#FFFFFF; margin-top:22px; margin-bottom:12px;">'
            'Why this assessment?</p>',
            unsafe_allow_html=True,
        )

        for text in facts:
            st.markdown(f"- {text}")

    if match:

        st.markdown(
            '<p style="font-size:20px; font-weight:700; '
            'color:#FFFFFF; margin-top:22px; margin-bottom:12px;">'
            'Assessment Criteria</p>',
            unsafe_allow_html=True,
        )

        for text in match["met"]:
            st.markdown(f"- Confirmed: {text}")

        for text in match["unmet"]:
            st.markdown(f"- Not confirmed: {text}")

        with st.expander("How is confidence calculated?"):

            st.markdown(
                "- **Strong:** All assessment criteria are confirmed.\n"
                "- **Moderate:** At least half of the criteria are confirmed.\n"
                "- **Weak:** Fewer than half are confirmed."
            )

            st.caption(
                "An unanswered or unsure response does not count "
                "as a confirmed criterion."
            )

    extra = [
        entry for entry in result["trace"]
        if entry["group"] == "DG"
        and entry["result"].startswith("Indicator")
    ]

    other = [
        entry for entry in result["trace"]
        if entry["group"] == "DD"
    ]

    if extra or other:

        st.markdown(
            '<p style="font-size:20px; font-weight:700; '
            'color:#FFFFFF; margin-top:22px; margin-bottom:12px;">'
            'Related warning signs</p>',
            unsafe_allow_html=True,
        )

        for entry in extra:

            name = entry["result"].split(": ", 1)[1]

            explanation = INDICATOR_DEFINITIONS.get(name, "")

            st.markdown(
                f"- **{name}:** {explanation}"
            )

        for entry in other:

            name = entry["result"].split(": ", 1)[1]

            st.markdown(
                f"- **Possible additional classification: {name}.** "
                f"{entry['reason']}"
            )

# --------------------------------------------------------------------------
# Decision making: action plan and urgency
# --------------------------------------------------------------------------

def show_actions(result):

    dec = result["decision"]

    st.subheader("Recommended Actions")

    st.caption(
        "Your action plan is based on the assessment, urgency and "
        "information you provided."
    )

    edge, tint = URGENCY_COLOURS[dec["urgency"]]

    deciding = [
        entry for entry in result["trace"]
        if entry["rule"] in dec["deciding_rules"]
    ]

    why = " ".join(
        entry["reason"] for entry in deciding
    ) or "No specific urgency rule matched, so a cautious level is shown."

    st.markdown(
        f'<div class="urgency" style="--edge:{edge};--tint:{tint}">'
        f'<div class="level">{esc(dec["urgency"])} urgency</div>'
        f'<div class="step" style="color:#7F1D1D;">{esc(why)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Show actual user-provided information rather than internal rule IDs.
    facts = result["facts"]

    contributing = []

    relevant_facts = [
        "immediate_danger",
        "minor_involved",
        "money_status",
        "time_elapsed",
        "ongoing",
        "private_content",
        "access_status",
    ]

    for fact in relevant_facts:

        if fact in facts:

            text = (
                f"{FACT_SHORT.get(fact, fact)}: "
                f"{label_of(fact, facts[fact])}"
            )

            if text not in contributing:
                contributing.append(text)

    if contributing:

        st.caption(
            "Information considered: " + "; ".join(contributing) + "."
        )

    with st.expander("How is urgency assessed?"):

        st.markdown(
            """
            The system considers the seriousness of the situation and
            whether the incident is recent or ongoing.

            - Immediate danger or a minor at risk can raise urgency
              to Critical or High.
            - Serious harm that is recent or ongoing is assessed as High.
            - Serious harm that is no longer ongoing is assessed as Medium.
            - Moderate harm that is recent or ongoing is assessed as Medium.
            - Moderate harm that is over is assessed as Low.
            - Unknown timing is treated as recent.
            """
        )

        st.caption(
            "These are this project's own risk levels, not official "
            "government severity classifications."
        )

    plan = dec["plan"]

    if not plan:

        st.write(
            "No actions could be worked out yet. "
            "Answer more questions to get an action plan."
        )

        return

    number = 0

    for phase in PHASES:

        items = [
            item for item in plan
            if item["phase"] == phase
        ]

        if not items:
            continue

        # Larger teal headings for action phases.
        st.markdown(
            f'<p style="font-size:22px; font-weight:750; '
            f'color:#42B8A8; margin-top:20px; margin-bottom:12px;">'
            f'{esc(phase)}</p>',
            unsafe_allow_html=True,
        )

        for item in items:

            number += 1

            role = (
                f" ({item['role'].lower()})"
                if item["role"]
                else ""
            )

            # Slightly larger action descriptions.
            st.markdown(
                f'<p style="font-size:17px; line-height:1.6;">'
                f'{number}. {esc(item["action"])}'
                f'{esc(role)}</p>',
                unsafe_allow_html=True,
            )

        st.write("")

    with st.expander("Why are these actions recommended?"):

        st.caption(
            "The explanations below show why each recommended action "
            "is relevant to your situation."
        )

        for item in plan:

            st.markdown(f"**{item['action']}**")

            if item["reason"]:
                st.write(item["reason"])

            for text in because_text(item["because"], result):
                st.markdown(f"- {text}")

# --------------------------------------------------------------------------
# Copy-ready incident summary
# --------------------------------------------------------------------------

def build_summary(result):

    """Build a plain-text summary containing the user's selected answers."""

    f = result["facts"]
    d = result["diagnosis"]
    dec = result["decision"]
    sup = result["support"]

    def show(fact):
        return (
            label_of(fact, f[fact])
            if fact in f
            else "Not provided"
        )

    lines = [

        "INCIDENT SUMMARY (guidance only, not legal advice)",
        "",

        f"Incident classification: {d['label']}"
        + (f" ({d['strength']} match)" if d["strength"] else ""),

        f"Secondary indicators: {', '.join(d['indicators']) or 'None'}",

        f"Other possible diagnoses: "
        f"{', '.join(d['alternatives']) or 'None'}",

        f"Urgency: {dec['urgency']}"
        + (" (provisional)" if dec["provisional"] else ""),

        "",

        f"What was noticed: {show('main_symptom')}",
        f"Began: {show('time_elapsed')}",
        f"Still ongoing: {show('ongoing')}",
        f"Platforms or channels: {show('platform')}",

        f"Money: {show('money_status')}; "
        f"amount: {show('amount_range')}; "
        f"payment method: {show('payment_method')}",

        f"Payment circumstances: {show('transaction_circumstances')}",
        f"What is known about the offender: {show('offender_known')}",
        f"Evidence held: {show('evidence_list')}",
        f"Already reported to: {show('already_reported')}",
        f"Outcome wanted: {show('desired_outcome')}",

        "",
        "Recommended actions:",
    ]

    lines += [
        f"- [{item['phase']}] {item['action']}"
        for item in dec["plan"]
    ] or ["- None identified yet"]

    lines += ["", "Evidence guidance:"]

    lines += [
        f"- {item}"
        for item in sup["evidence_checklist"]
    ] or ["- Keep original records and preserve relevant information."]

    lines += ["", "Suggested reporting routes:"]

    lines += [
        f"- {route['route']}: {route['role']}"
        for route in sup["routes"]
    ] or ["- None identified yet"]

    lines += [
        "",
        "Confirm details on the official websites before reporting.",
        "The app does not intentionally store or send your answers.",
    ]

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Decision support
# --------------------------------------------------------------------------

def show_support(result):

    sup = result["support"]

    st.subheader("Reporting Guidance & Resources")

    st.caption(
        "Information to help you act and decide. "
        "Open any section you need."
    )

    with st.expander("Where to report in Pakistan", expanded=True):

        st.caption(
            "These routes serve different purposes, and one incident "
            "may require more than one. No route guarantees recovery "
            "of money or removal of content."
        )

        if not sup["routes"]:
            st.write(
                "No specific reporting route was identified "
                "from these answers."
            )

        for role in ROLE_ORDER:

            for route in [
                item for item in sup["routes"]
                if item["role"] == role
            ]:

                colour = ROLE_COLOURS[role]
                notes = " ".join(route["notes"])

                st.markdown(
                    f'<div class="route" style="--edge:{colour}">'
                    f'<div class="name">{esc(route["route"])}</div>'
                    f'<div class="role">{esc(role)}</div>'
                    f'<div>{esc(notes)}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                for text, url in ROUTE_LINKS.get(route["route"], []):

                    st.link_button(text, url)

        st.caption(
            "Confirm contact details and procedures on official "
            "websites before relying on them."
        )

    # Evidence the user has already selected.
    with st.expander("Evidence & Preservation", expanded=True):

        held = selected_evidence(result)

        if held:

            st.markdown("**Evidence you indicated you already have**")

            for item in held:
                st.markdown(f"- {item}")

        else:

            st.info(
                "You have not selected any evidence in the questionnaire."
            )

        if sup["evidence_checklist"]:

            st.markdown("**Additional evidence guidance**")

            for item in sup["evidence_checklist"]:
                st.markdown(f"- {item}")

        else:

            st.write(
                "No additional evidence guidance was generated "
                "for these answers."
            )

        st.caption(
            "Preserve original records and avoid editing or cropping "
            "them in ways that change their context. You do not need "
            "to collect every item before reporting."
        )

    if sup["precautions"] or sup["warnings"]:

        with st.expander("Precautions", expanded=True):

            for item in sup["precautions"]:
                st.markdown(f"- {item}")

            for text in sup["warnings"]:
                st.warning(text)

    with st.expander("Incident summary"):

        summary = build_summary(result)

        st.code(summary, language=None)

        st.download_button(
            "Download summary",
            summary,
            file_name="incident_summary.txt",
        )


# --------------------------------------------------------------------------
# Inference trace: technical details
# --------------------------------------------------------------------------

def show_trace(result):

    with st.expander("How This Assessment Was Reached"):   #inference trace

        st.write(
            "This section shows how the expert system reached its result. "
            "It includes the rules that fired, the facts that matched them, "
            "and the conclusions produced at each stage."
        )

        st.caption(
            f"{len(result['trace'])} of {len(RULES)} rules fired "
            "for these answers."
        )

        stage_names = []

        for entry in result["trace"]:

            if entry["stage_name"] not in stage_names:
                stage_names.append(entry["stage_name"])

        for stage in stage_names:

            st.markdown(f"**{stage}**")

            rows = [

                {
                    "Rule": entry["rule"],

                    "Facts that matched": "; ".join(
                        because_text(entry["because"], result)
                    ),

                    "Conclusion": entry["result"],

                    "Condition": entry["if"],
                }

                for entry in result["trace"]
                if entry["stage_name"] == stage
            ]

            st.dataframe(
                rows,
                hide_index=True,
                width="stretch",
            )

        match = result["diagnosis"]["match"]

        if match:

            st.markdown("**Assessment Confidence Calculation**")

            st.markdown(
                f"{match['score']} criteria confirmed gives "
                f"**{match['strength']}**."
            )

            for text in match["met"]:
                st.markdown(f"- Confirmed: {text}")

            for text in match["unmet"]:
                st.markdown(f"- Not confirmed: {text}")

        st.markdown("**Information Used in This Assessment**")

        for fact, value in result["facts"].items():

            st.markdown(
                f"- `{fact}` = {label_of(fact, value)}"
            )

        for note in result["notes"]:
            st.warning(note)


# --------------------------------------------------------------------------
# What-if analysis
# --------------------------------------------------------------------------

def show_what_if(result):

    st.subheader("Test a Different Situation")

    with st.expander("Try a different answer and see what changes"):

        st.write(
            "Change one answer to see how your assessment, priority, "
            "actions and reporting routes respond. "
            "Your original answers are not changed."
        )

        base = st.session_state["answers"]

        answered = [
            q for q in QUESTIONS
            if q["fact"] in base
        ]

        fact = st.selectbox(
            "Question to change",
            [q["fact"] for q in answered],
            format_func=lambda x: QUESTION_BY_FACT[x]["text"],
            key="whatif_fact",
        )

        question = QUESTION_BY_FACT[fact]

        values = [
            value for value, _ in question["options"]
        ]

        labels = dict(question["options"])

        if question["type"] == "multi":

            new = st.multiselect(
                "Select a different answer",
                values,
                default=base[fact],
                format_func=labels.get,
                key=f"whatif_new_{fact}",
            )

        else:

            new = st.selectbox(
                "New answer",
                values,
                index=values.index(base[fact]),
                format_func=labels.get,
                key=f"whatif_new_{fact}",
            )

        changed = dict(base)

        if new:
            changed[fact] = new
        else:
            changed.pop(fact, None)

        changed = clean(changed)

        after = assess(changed)

        diff = compare(result, after)

        shown = False

        st.markdown("**Changes to Your Assessment**")

        for key, title in (
            ("label", "Incident classification"),
            ("strength", "Assessment confidence"),
            ("urgency", "Urgency"),
            ("indicators", "Indicators"),
            ("alternatives", "Alternative diagnoses"),
        ):

            if key in diff:

                old, now = diff[key]

                old = (
                    ", ".join(old)
                    if isinstance(old, list)
                    else old
                )

                now = (
                    ", ".join(now)
                    if isinstance(now, list)
                    else now
                )

                st.markdown(
                    f"- {title}: **{old or 'none'}** "
                    f"changes to **{now or 'none'}**"
                )

                shown = True

        for action in diff["actions_added"]:

            st.markdown(f"- New action: **{action}**")
            shown = True

        for action in diff["actions_removed"]:

            st.markdown(
                f"- Action no longer needed: **{action}**"
            )

            shown = True

        for action, (old, now) in diff["actions_moved"].items():

            st.markdown(
                f"- Action moves from {old.lower()} to "
                f"{now.lower()}: **{action}**"
            )

            shown = True

        for route, (old, now) in diff.get("routes", {}).items():

            st.markdown(
                f"- Route {route}: **{old or 'not shown'}** "
                f"changes to **{now or 'not shown'}**"
            )

            shown = True

        if not shown:
            st.write("Nothing visible changes with this answer.")

        # Rule changes remain accessible, but are treated as technical details.
        if diff["rules_started"] or diff["rules_stopped"]:

            with st.expander("View technical details of rule changes"):

                st.markdown("**Rules that caused the change**")

                for rule_id in diff["rules_started"]:

                    st.markdown(
                        f"- `{rule_id}` now fires: "
                        f"{RULE_BY_ID[rule_id]['reason']}"
                    )

                for rule_id in diff["rules_stopped"]:

                    st.markdown(
                        f"- `{rule_id}` stops firing: "
                        f"{RULE_BY_ID[rule_id]['reason']}"
                    )


# --------------------------------------------------------------------------
# Main page
# --------------------------------------------------------------------------

st.title(TITLE)

st.write(
    "Answer a few questions about what happened. "
    "The system will assess the type of incident, its urgency, "
    "and possible reporting options."
)

st.info(
    "If anyone is in immediate danger, contact the police "
    "or emergency services first."
)

st.caption(
    "This is not legal advice or an official government service. "
    "Your answers are kept in the browser session and are not "
    "intentionally stored by this app. Never enter passwords, "
    "OTPs, PINs or ID numbers."
)


answers = draw_questionnaire()

col1, col2 = st.columns([3, 1])

with col1:

    run = st.button(
        "Assess my situation",
        type="primary",
        disabled="main_symptom" not in answers,
    )

with col2:

    if st.button("Start over"):

        for key in [
            key for key in st.session_state
            if key.startswith(("q_", "whatif_"))
        ]:

            del st.session_state[key]

        st.session_state.pop("result", None)
        st.session_state.pop("answers", None)

        st.rerun()


if "main_symptom" not in answers:

    st.caption("Choose what happened to start the assessment.")


if run:

    st.session_state["answers"] = clean(answers)

    st.session_state["result"] = assess(
        st.session_state["answers"]
    )


if "result" in st.session_state:

    result = st.session_state["result"]

    if clean(answers) != st.session_state["answers"]:

        st.warning(
            "Your answers changed after this assessment. "
            "Select Assess my situation to update the results."
        )

    st.divider()

    st.header("Your Incident Assessment")

    if result["facts"].get("immediate_danger") == "yes":

        st.error(
            "If anyone is in immediate danger, contact the police "
            "or emergency services first."
        )

    show_diagnosis(result)

    show_actions(result)

    show_support(result)

    show_trace(result)

    st.divider()

    show_what_if(result)


# --------------------------------------------------------------------------
# About this system
# --------------------------------------------------------------------------

with st.expander("About This Service"):

    st.markdown(
        f"""
**How it works.** This service uses a rule-based assessment
system with
{len(RULES)} rules. It uses forward chaining in four stages:
deriving facts from your answers, diagnosing the incident,
deciding urgency and recommended actions, and providing
reporting guidance and precautions.

**What it does not do.** It does not file complaints, investigate
offenders, decide guilt, determine a legal offence, or guarantee
that money can be recovered.

**Privacy.** The questions are multiple choice only. The app does
not intentionally store your answers, but the hosting platform
may retain its own technical logs.

**Sources.** Reporting routes are based on the NCCIA, State Bank
of Pakistan and PTA procedures. Check official websites for
current contact details and procedures.
        """
    )
