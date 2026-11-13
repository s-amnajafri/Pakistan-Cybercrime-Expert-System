"""
rules.py - the KNOWLEDGE BASE of the Cybercrime Complaint Expert System.

This file contains only knowledge (no reasoning code):
  1. QUESTIONS - the 17 questions the user is asked and their allowed answers
  2. RULES     - the 94 IF-THEN rules, in four stages of reasoning
  3. CRITERIA  - the criteria that decide how strongly a diagnosis matches

The reasoning itself (forward chaining) lives in engine.py.

How a rule is written
---------------------
Every rule is a dictionary built with the helper R(...):

    R(id, group, tag, kind, when, then, reason)

    id     unique rule ID, e.g. "DG05"
    group  DF, DG, DD, UR, AC, EV, RT or CP
    tag    D (decision), S (support) or Shared
    kind   what the rule does: derive / primary / fallback / indicator /
           alternative / urgency / action / evidence / route / completeness
    when   the IF part, written with the small condition helpers below
    then   the THEN part (a dictionary)
    reason a plain-language sentence used in the explanation (Inference Trace)

Condition helpers (the IF part)
-------------------------------
    eq(fact, value)         the fact equals the value
    isin(fact, a, b, ...)   the fact is one of the values
    has(fact, a, b, ...)    a multiple-choice fact includes ANY of the values
    lacks(fact, a, b, ...)  a multiple-choice fact was answered and includes NONE of them
    flag(name)              a derived fact is true
    primary(a, b, ...)      the primary diagnosis is one of these
    indicator(a, b, ...)    a secondary indicator (derived by its own rule) is present
    strength(a, b, ...)     the diagnosis strength is one of these
    NOT(c) / AND(c, ...) / OR(c, ...)

Important rule of the design: an unanswered or "not_sure" answer is NEVER
treated as "no". eq/isin/has/lacks are False when the fact is missing, so a
rule only fires on the exact value it asks for.
"""

# --------------------------------------------------------------------------
# Names used by the rules
# --------------------------------------------------------------------------
FRAUD = "Financial fraud"
MARKET = "Marketplace scam"
ACCOUNT = "Account compromise"
IDENT = "Identity misuse or impersonation"
HARASS = "Harassment or stalking"
BLACKMAIL = "Blackmail or extortion"
INTIMATE = "Intimate-content abuse"
HARMFUL = "Harmful online content"
MALWARE = "Malware or ransomware"
DATA = "Data exposure"
UNCLASS = "Unclassified"

DIAGNOSES = [FRAUD, MARKET, ACCOUNT, IDENT, HARASS, BLACKMAIL, INTIMATE,
             HARMFUL, MALWARE, DATA, UNCLASS]

PHISH = "Phishing or social engineering"
ACCOUNT_IND = "Account compromise"
LOSS_IND = "Financial loss"
EXTORT = "Extortion element"

# Secondary indicators are classifications in their own right. Each one has a definition,
# is derived by its own rule (DG23-DG26), and later rules can test for it with indicator(...).
INDICATOR_DEFINITIONS = {
    PHISH: "The user was deceived into paying or sharing details through a call, message, email or link.",
    ACCOUNT_IND: "Someone appears to have accessed an account without permission.",
    LOSS_IND: "Money was lost, even though this is not the main diagnosis.",
    EXTORT: "Money is being demanded alongside a threat to share private content.",
}

# Match strength is COMPUTED from the CRITERIA below (see engine.match_strength).
STRONG, MODERATE, WEAK = "strong", "moderate", "weak"

CRITICAL, HIGH, MEDIUM, LOW = "Critical", "High", "Medium", "Low"
URGENCY_RANK = {LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4}

DO_FIRST, FOLLOW_UP, ALSO, OPTIONAL = "Do first", "Follow up", "Also relevant", "Optional"
ROLE_RANK = {DO_FIRST: 4, FOLLOW_UP: 3, ALSO: 2, OPTIONAL: 1}

DERIVED_FACTS = ["financial_loss_confirmed", "demand_present",
                 "unauthorised_access_suspected", "deception_involved",
                 "private_content_at_stake", "harm_severe", "harm_moderate",
                 "incident_settled"]

# Routes
BANK = "Bank or wallet provider"
NCCIA = "NCCIA"
NCCIA_EXISTING = "NCCIA (existing complaint)"
PLATFORM = "Platform report"
PTA = "PTA web-content complaint"
POLICE = "Police or emergency services"
ORG_IT = "Organisation's IT or security team"
PKCERT = "PKCERT"
MOHTASIB = "Banking Mohtasib"
LAWYER = "Qualified lawyer"


# The action each route turns into in the action plan, and the words that show an
# existing step already covers that route (so the plan does not repeat itself).
ROUTE_ACTIONS = {
    BANK: "Contact your bank or wallet provider through a verified channel",
    NCCIA: "Report the incident to NCCIA",
    NCCIA_EXISTING: "Follow up your existing NCCIA complaint",
    PLATFORM: "Report the account or content to the platform",
    PTA: "If the platform does not resolve it, make a web-content complaint to PTA",
    POLICE: "Contact the police or emergency services",
    ORG_IT: "Notify your organisation's IT or security team",
    PKCERT: "Report the organisational incident to PKCERT",
    MOHTASIB: "If the bank does not reply within 45 days, escalate to the Banking Mohtasib",
    LAWYER: "Consider speaking to a qualified lawyer",
}
ROUTE_KEYWORDS = {
    BANK: ("bank", "wallet", "payment provider"),
    PLATFORM: ("platform",),
    POLICE: ("police", "emergency services"),
    ORG_IT: ("it or security",),
}

PHASES = ["Right now", "Next", "Then"]


# --------------------------------------------------------------------------
# Condition helpers (the small language used in the IF part of each rule)
# --------------------------------------------------------------------------
def eq(fact, value):
    return ("eq", fact, value)


def isin(fact, *values):
    return ("in", fact, values)


def has(fact, *values):
    return ("has", fact, values)


def lacks(fact, *values):
    return ("lacks", fact, values)


def flag(name):
    return ("flag", name)


def primary(*names):
    return ("primary", names)


def indicator(*names):
    return ("indicator", names)


def strength(*values):
    return ("strength", values)


def NOT(cond):
    return ("not", cond)


def AND(*conds):
    return ("and", conds)


def OR(*conds):
    return ("or", conds)


NO_PRIMARY = ("no_primary",)


def R(rule_id, group, tag, kind, when, then, reason):
    return {"id": rule_id, "group": group, "tag": tag, "kind": kind,
            "when": when, "then": then, "reason": reason}


# --------------------------------------------------------------------------
# 1. QUESTIONS (17)
# --------------------------------------------------------------------------
# type: "single" = one answer, "multi" = several answers allowed.
# asked_if: the question is only shown when this condition is true
# (adaptive questionnaire). None means always asked.
QUESTIONS = [
    {"id": "Q1", "fact": "main_symptom", "type": "single", "asked_if": None,
     "text": "What did you notice or what happened?",
     "options": [
         ("money_missing", "Money went missing from my bank, wallet or card"),
         ("paid_after_call_or_link", "I paid or shared details after a call, SMS, email or link"),
         ("goods_not_received", "I paid for goods or services and did not receive them"),
         ("lost_access", "I lost access to an account"),
         ("unusual_activity", "I noticed unknown activity on my account"),
         ("threats_received", "I received threats or demands"),
         ("unwanted_contact", "I keep getting unwanted contact or am being followed online"),
         ("fake_account", "Someone is using my name or photos"),
         ("content_about_me", "Content about me has been posted or shared online"),
         ("device_problem", "My device or files are locked or behaving strangely"),
         ("data_exposed", "My (or my organisation's) data appears to have leaked"),
         ("not_sure", "Not sure"),
     ]},
    {"id": "Q2", "fact": "immediate_danger", "type": "single", "asked_if": None,
     "text": "Is anyone in immediate physical danger?",
     "options": [("yes", "Yes"), ("no", "No"), ("not_sure", "Not sure")]},
    {"id": "Q3", "fact": "minor_involved", "type": "single", "asked_if": None,
     "text": "Is the affected person under 18?",
     "options": [("yes", "Yes"), ("no", "No"), ("prefer_not", "Prefer not to say")]},
    {"id": "Q4", "fact": "money_status", "type": "single", "asked_if": None,
     "text": "Was money lost, demanded, or both?",
     "options": [("lost", "Lost"), ("demanded", "Demanded"), ("both", "Both"),
                 ("neither", "Neither"), ("not_sure", "Not sure")]},
    {"id": "Q5", "fact": "amount_range", "type": "single",
     "asked_if": isin("money_status", "lost", "demanded", "both"),
     "text": "Roughly how much? (optional, used only in the final summary)",
     "options": [("under_10k", "Under PKR 10,000"), ("10k_100k", "PKR 10,000 to 100,000"),
                 ("over_100k", "Over PKR 100,000"), ("not_sure", "Not sure")]},
    {"id": "Q6", "fact": "payment_method", "type": "single",
     "asked_if": isin("money_status", "lost", "demanded", "both"),
     "text": "How was payment made or requested?",
     "options": [("bank", "Bank transfer"), ("wallet", "Mobile wallet"), ("card", "Card"),
                 ("cash", "Cash"), ("crypto", "Cryptocurrency"), ("other", "Other"),
                 ("na", "Not applicable")]},
    {"id": "Q7", "fact": "time_elapsed", "type": "single", "asked_if": None,
     "text": "When did it begin?",
     "options": [("under_24h", "Under 24 hours ago"), ("1_7_days", "1 to 7 days ago"),
                 ("1_4_weeks", "1 to 4 weeks ago"), ("over_month", "More than a month ago"),
                 ("not_sure", "Not sure")]},
    {"id": "Q8", "fact": "ongoing", "type": "single", "asked_if": None,
     "text": "Is it still ongoing?",
     "options": [("yes", "Yes"), ("no", "No"), ("not_sure", "Not sure")]},
    {"id": "Q9", "fact": "offender_known", "type": "single", "asked_if": None,
     "text": "What do you know about the person or account behind it?",
     "options": [("unknown", "Nothing"), ("account_only", "Only a username or account"),
                 ("person", "I know who the person is"),
                 ("organisation", "I know the organisation")]},
    {"id": "Q10", "fact": "platform", "type": "multi", "asked_if": None,
     "text": "Which platforms or channels were involved? (choose all that apply)",
     "options": [("whatsapp", "WhatsApp"), ("facebook", "Facebook"), ("instagram", "Instagram"),
                 ("tiktok", "TikTok"), ("email", "Email"), ("call_sms", "Phone call or SMS"),
                 ("website", "A website"), ("app", "An app"), ("other", "Other")]},
    {"id": "Q11", "fact": "private_content", "type": "single", "asked_if": None,
     "text": "Is private or intimate content involved or threatened?",
     "options": [("yes", "Yes"), ("no", "No"), ("prefer_not", "Prefer not to say")]},
    {"id": "Q12", "fact": "access_status", "type": "single", "asked_if": None,
     "text": "Can you still access the affected account or device?",
     "options": [("full", "Yes, full access"), ("partial", "Partly"),
                 ("none", "No access"), ("na", "Not applicable")]},
    {"id": "Q13", "fact": "evidence_list", "type": "multi", "asked_if": None,
     "text": "What evidence do you have? (choose all that apply)",
     "options": [("screenshots", "Screenshots"), ("messages", "Original messages or emails"),
                 ("receipts", "Receipts or transaction records"), ("links", "Links or usernames"),
                 ("numbers", "Phone numbers"), ("none", "None yet")]},
    {"id": "Q14", "fact": "already_reported", "type": "multi", "asked_if": None,
     "text": "Have you already reported it? (choose all that apply)",
     "options": [("bank", "To my bank or wallet provider"), ("platform", "To the platform"),
                 ("police", "To the police"), ("nccia", "To NCCIA"), ("none", "Not yet")]},
    {"id": "Q15", "fact": "desired_outcome", "type": "single", "asked_if": None,
     "text": "What outcome matters most to you?",
     "options": [("recover_money", "Recover money"), ("secure_account", "Secure my account"),
                 ("remove_content", "Remove content"), ("stop_contact", "Stop the contact"),
                 ("report_crime", "Report a suspected crime"),
                 ("legal_advice", "Get legal advice")]},
    {"id": "Q16", "fact": "environment", "type": "single", "asked_if": None,
     "text": "Is the affected system personal or an organisation's?",
     "options": [("personal", "Personal"), ("organisation", "An organisation's")]},
    {"id": "Q17", "fact": "transaction_circumstances", "type": "single",
     "asked_if": isin("money_status", "lost", "both"),
     "text": "Did you authorise the payment after being deceived, or was money taken without your approval?",
     "options": [("authorised_after_deception", "I authorised it after being deceived"),
                 ("unauthorised", "It was taken without my approval"),
                 ("both", "Both"), ("neither", "Neither"), ("not_sure", "Not sure")]},
]


# --------------------------------------------------------------------------
# 2. RULES (94)
# --------------------------------------------------------------------------
RULES = []

# ---- Stage 1: derived facts (DF01-DF08), tag D ---------------------------
RULES += [
    R("DF01", "DF", "D", "derive", isin("money_status", "lost", "both"),
      {"derive": "financial_loss_confirmed"},
      "Money was reported lost, so a financial loss is confirmed."),
    R("DF02", "DF", "D", "derive", isin("money_status", "demanded", "both"),
      {"derive": "demand_present"},
      "Money was reported demanded, so a demand is present."),
    R("DF03", "DF", "D", "derive",
      OR(isin("access_status", "partial", "none"),
         isin("main_symptom", "lost_access", "unusual_activity")),
      {"derive": "unauthorised_access_suspected"},
      "Lost access or unknown activity suggests someone accessed the account without permission."),
    R("DF04", "DF", "D", "derive",
      OR(isin("main_symptom", "paid_after_call_or_link", "goods_not_received"),
         isin("transaction_circumstances", "authorised_after_deception", "both")),
      {"derive": "deception_involved"},
      "The user was tricked into paying or sharing details, so deception is involved."),
    R("DF05", "DF", "D", "derive", eq("private_content", "yes"),
      {"derive": "private_content_at_stake"},
      "Private or intimate content is involved or threatened."),
    # The next three describe HOW SERIOUS the incident is and WHETHER it is over.
    # They use the flags above, so they must stay after DF01-DF05. The urgency rules use them.
    R("DF06", "DF", "D", "derive",
      OR(flag("financial_loss_confirmed"), flag("demand_present"),
         flag("private_content_at_stake"), eq("access_status", "none")),
      {"derive": "harm_severe"},
      "Serious harm has occurred or is threatened: money lost or demanded, private content at stake, or access lost."),
    R("DF07", "DF", "D", "derive",
      AND(NOT(flag("harm_severe")),
          OR(flag("unauthorised_access_suspected"), flag("deception_involved"),
             isin("main_symptom", "unwanted_contact", "threats_received", "fake_account",
                  "content_about_me", "device_problem", "data_exposed"))),
      {"derive": "harm_moderate"},
      "The harm is moderate: an attempted scam, suspected account access, harassment, an impersonation, harmful content, malware or exposed data."),
    R("DF08", "DF", "D", "derive",
      AND(eq("ongoing", "no"), isin("time_elapsed", "1_4_weeks", "over_month")),
      {"derive": "incident_settled"},
      "The incident is clearly over and began more than a week ago. Unknown timing is not treated as settled."),
]

# ---- Stage 2: primary diagnosis (DG01-DG22), tag D -----------------------
# DG01-DG21 are mutually exclusive: at most one of them can fire.
# DG22 is the fallback and fires only if none of DG01-DG21 fired.
_LOSS = flag("financial_loss_confirmed")
_UNAUTH = flag("unauthorised_access_suspected")
_DEMAND = flag("demand_present")
_PRIV = flag("private_content_at_stake")
_MONEY_MISSING = eq("main_symptom", "money_missing")


def _primary(label, variant=None):
    # No strength here: it is computed from the diagnosis's criteria after the rule fires.
    # Secondary indicators are not set here either: they have their own rules (DG23-DG26).
    return {"diagnosis": label, "variant": variant}


RULES += [
    R("DG01", "DG", "D", "primary",
      AND(_MONEY_MISSING, _LOSS, _UNAUTH),
      _primary(FRAUD),
      "Money went missing and the account was accessed without permission."),
    R("DG02", "DG", "D", "primary",
      AND(_MONEY_MISSING, _LOSS, NOT(_UNAUTH),
          isin("transaction_circumstances", "unauthorised", "both")),
      _primary(FRAUD),
      "Money was taken without the user's approval."),
    R("DG03", "DG", "D", "primary",
      AND(_MONEY_MISSING, _LOSS, NOT(_UNAUTH),
          eq("transaction_circumstances", "authorised_after_deception")),
      _primary(FRAUD, variant="deception-based"),
      "The user authorised the payment only after being deceived."),
    R("DG04", "DG", "D", "primary",
      AND(_MONEY_MISSING, _LOSS, NOT(_UNAUTH),
          isin("transaction_circumstances", "neither", "not_sure")),
      _primary(FRAUD),
      "Money is missing but the circumstances are unclear, so some fraud criteria cannot be confirmed."),
    R("DG05", "DG", "D", "primary",
      AND(eq("main_symptom", "paid_after_call_or_link"), _LOSS),
      _primary(FRAUD),
      "The user paid or shared details after a call, SMS or link and lost money."),
    R("DG06", "DG", "D", "primary",
      AND(eq("main_symptom", "paid_after_call_or_link"), NOT(_LOSS)),
      _primary(FRAUD, variant="attempted"),
      "A call, SMS or link tried to trick the user, but no loss is confirmed."),
    R("DG07", "DG", "D", "primary",
      AND(eq("main_symptom", "goods_not_received"), _LOSS),
      _primary(MARKET),
      "The user paid for goods or services that never arrived."),
    R("DG08", "DG", "D", "primary",
      AND(eq("main_symptom", "goods_not_received"), NOT(_LOSS)),
      _primary(MARKET),
      "Goods did not arrive, but no payment loss is confirmed."),
    R("DG09", "DG", "D", "primary",
      eq("main_symptom", "lost_access"),
      _primary(ACCOUNT),
      "The user lost access to an account."),
    R("DG10", "DG", "D", "primary",
      AND(eq("main_symptom", "unusual_activity"), isin("access_status", "partial", "none")),
      _primary(ACCOUNT),
      "Unknown activity together with reduced access points to a compromised account."),
    R("DG11", "DG", "D", "primary",
      AND(eq("main_symptom", "unusual_activity"), isin("access_status", "full", "na")),
      _primary(ACCOUNT),
      "Unknown activity while the user still has full access suggests a compromise, but not every criterion is confirmed."),
    R("DG12", "DG", "D", "primary",
      eq("main_symptom", "fake_account"),
      _primary(IDENT),
      "Someone is using the user's name or photos."),
    R("DG13", "DG", "D", "primary",
      eq("main_symptom", "unwanted_contact"),
      _primary(HARASS),
      "Repeated unwanted contact fits harassment or stalking."),
    R("DG14", "DG", "D", "primary",
      AND(eq("main_symptom", "threats_received"), _DEMAND),
      _primary(BLACKMAIL),
      "Threats together with a demand for money fit blackmail or extortion."),
    R("DG15", "DG", "D", "primary",
      AND(eq("main_symptom", "threats_received"), NOT(_DEMAND), _PRIV),
      _primary(INTIMATE),
      "Threats involving private content, with no money demand, fit intimate-content abuse."),
    R("DG16", "DG", "D", "primary",
      AND(eq("main_symptom", "threats_received"), NOT(_DEMAND), NOT(_PRIV)),
      _primary(HARASS),
      "Threats with no demand and no private content fit harassment."),
    R("DG17", "DG", "D", "primary",
      AND(eq("main_symptom", "content_about_me"), _PRIV),
      _primary(INTIMATE),
      "Private or intimate content about the user is shared or threatened."),
    R("DG18", "DG", "D", "primary",
      AND(eq("main_symptom", "content_about_me"), NOT(_PRIV)),
      _primary(HARMFUL),
      "Harmful content about the user was posted; this needs further assessment and is not labelled an offence."),
    R("DG19", "DG", "D", "primary",
      AND(eq("main_symptom", "device_problem"), _DEMAND),
      _primary(MALWARE),
      "A locked device together with a money demand fits ransomware."),
    R("DG20", "DG", "D", "primary",
      AND(eq("main_symptom", "device_problem"), NOT(_DEMAND)),
      _primary(MALWARE),
      "A strangely behaving device with no demand is probably malware."),
    R("DG21", "DG", "D", "primary",
      eq("main_symptom", "data_exposed"),
      _primary(DATA),
      "Data appears to have leaked."),
    R("DG22", "DG", "D", "fallback",
      OR(eq("main_symptom", "not_sure"), NO_PRIMARY),
      _primary(UNCLASS),
      "The answers do not give enough information for a reliable diagnosis."),
]

# ---- Stage 2: secondary indicators (DG23-DG26), tag D --------------------
RULES += [
    R("DG23", "DG", "D", "indicator",
      AND(eq("main_symptom", "content_about_me"), _PRIV, _DEMAND),
      {"indicator": EXTORT},
      "Private content is involved and money is being demanded."),
    R("DG24", "DG", "D", "indicator",
      AND(_UNAUTH, NOT(primary(ACCOUNT))),
      {"indicator": ACCOUNT_IND},
      "There are signs of unauthorised account access beyond the main diagnosis."),
    R("DG25", "DG", "D", "indicator",
      AND(_LOSS, NOT(primary(FRAUD, MARKET))),
      {"indicator": LOSS_IND},
      "Money was also lost, even though the main diagnosis is a different one."),
    R("DG26", "DG", "D", "indicator",
      AND(flag("deception_involved"),
          OR(eq("main_symptom", "paid_after_call_or_link"), has("platform", "call_sms", "email"))),
      {"indicator": PHISH},
      "The user was tricked into paying or sharing details, and the contact came through a call, SMS, email or link."),
]

# ---- Stage 2: alternative diagnoses (DD01-DD04), tag D -------------------
RULES += [
    R("DD01", "DD", "D", "alternative",
      AND(primary(ACCOUNT), _LOSS),
      {"alternative": FRAUD},
      "An account problem with money lost could also be financial fraud."),
    R("DD02", "DD", "D", "alternative",
      AND(primary(BLACKMAIL), _PRIV),
      {"alternative": INTIMATE},
      "Blackmail involving private content could also be intimate-content abuse."),
    R("DD03", "DD", "D", "alternative",
      AND(primary(MARKET), has("platform", "call_sms", "email")),
      {"alternative": FRAUD},
      "A shopping scam run through calls or email could also be financial fraud."),
    R("DD04", "DD", "D", "alternative",
      AND(primary(IDENT), eq("desired_outcome", "remove_content")),
      {"alternative": HARMFUL},
      "An impersonation where the user wants content removed could also be harmful online content."),
]

# ---- Stage 3: urgency (UR01-UR16), tag D ---------------------------------
# The engine takes the HIGHEST urgency among fired rules. Every diagnosed incident is covered by a
# rule (UR01-UR16), so urgency is never a silent default.
_SERIOUS_FOR_MINOR = primary(INTIMATE, BLACKMAIL, HARASS)


def _urgency(level, first_step=None, provisional=False):
    # first_step None = the headline step comes from the protective-step rules in the action plan.
    return {"urgency": level, "first_step": first_step, "provisional": provisional}


RULES += [
    R("UR01", "UR", "D", "urgency", eq("immediate_danger", "yes"),
      _urgency(CRITICAL, "Contact the police or emergency services now."),
      "Immediate physical danger is the highest priority."),
    R("UR02", "UR", "D", "urgency",
      AND(eq("minor_involved", "yes"), _SERIOUS_FOR_MINOR),
      _urgency(CRITICAL, "Report without delay, together with a parent or guardian."),
      "A minor is affected by a serious diagnosis (harassment, blackmail or intimate-content abuse)."),
    R("UR03", "UR", "D", "urgency",
      AND(eq("minor_involved", "yes"), NOT(_SERIOUS_FOR_MINOR)),
      _urgency(HIGH, "Involve a parent, guardian or trusted adult."),
      "A minor is affected, so a trusted adult should be involved."),
    R("UR04", "UR", "D", "urgency",
      AND(primary(BLACKMAIL), eq("ongoing", "yes")),
      _urgency(HIGH, "Preserve the evidence and report the demand."),
      "Ongoing blackmail can escalate quickly."),
    R("UR05", "UR", "D", "urgency",
      AND(primary(INTIMATE), eq("ongoing", "yes")),
      _urgency(HIGH, "Report the content to the platform and seek trusted support."),
      "Ongoing intimate-content abuse is time-sensitive."),
    R("UR06", "UR", "D", "urgency",
      AND(_LOSS, isin("transaction_circumstances", "unauthorised", "both"),
          OR(eq("time_elapsed", "under_24h"), eq("ongoing", "yes"))),
      _urgency(HIGH, "Contact your bank or wallet provider through a verified channel now."),
      "A recent or ongoing unauthorised transaction needs fast action."),
    R("UR07", "UR", "D", "urgency",
      AND(_LOSS, flag("deception_involved"), eq("time_elapsed", "under_24h")),
      _urgency(HIGH, "Contact your payment provider quickly; recovery is not guaranteed."),
      "A payment made after deception in the last 24 hours may still be traceable."),
    R("UR08", "UR", "D", "urgency",
      AND(primary(ACCOUNT), eq("access_status", "none")),
      _urgency(HIGH, "Start the platform's official account recovery and secure your email."),
      "The user has no access to the compromised account."),
    R("UR09", "UR", "D", "urgency",
      AND(primary(MALWARE), eq("environment", "organisation"), eq("ongoing", "yes")),
      _urgency(HIGH, "Notify your organisation's IT or security team."),
      "An ongoing malware incident in an organisation can spread."),
    R("UR10", "UR", "D", "urgency",
      AND(flag("harm_moderate"), flag("incident_settled")),
      _urgency(LOW, "Save your evidence and report when ready."),
      "Only moderate harm occurred and the incident is over, so nothing is time-critical."),
    R("UR11", "UR", "D", "urgency",
      OR(eq("immediate_danger", "not_sure"), eq("ongoing", "not_sure"), primary(UNCLASS)),
      _urgency(MEDIUM, "Answer the unclear questions to sharpen the result.", provisional=True),
      "Some key answers are unclear, so the system stays cautious and marks the result provisional."),
    # Baseline policy: urgency = how serious the harm is x whether the incident is recent or ongoing.
    # Together with UR10 these cover every diagnosed incident, so no urgency is ever a silent default.
    R("UR12", "UR", "D", "urgency",
      AND(flag("harm_severe"), NOT(flag("incident_settled"))),
      _urgency(HIGH),
      "Serious harm has occurred or is threatened, and the incident is recent, ongoing or its timing is unclear."),
    R("UR13", "UR", "D", "urgency",
      AND(flag("harm_severe"), flag("incident_settled")),
      _urgency(MEDIUM),
      "Serious harm occurred, but the incident is over, so there is less time pressure. It should still be reported."),
    R("UR14", "UR", "D", "urgency",
      AND(flag("harm_moderate"), NOT(flag("incident_settled"))),
      _urgency(MEDIUM),
      "The harm is moderate and the incident is recent, ongoing or its timing is unclear."),
    # Specific escalations: situations that are more urgent than their general harm level.
    R("UR15", "UR", "D", "urgency",
      AND(primary(ACCOUNT), eq("ongoing", "yes"), isin("access_status", "full", "partial")),
      _urgency(HIGH),
      "The account is being misused right now, but the user can still act on it, so securing it quickly limits the damage."),
    R("UR16", "UR", "D", "urgency",
      AND(eq("main_symptom", "threats_received"), eq("ongoing", "yes")),
      _urgency(HIGH),
      "Threats are still being received, so the situation can escalate."),
]

# ---- Stage 3: protective actions (AC01-AC14), tag Shared -----------------
# steps    = what to do
# avoid    = what NOT to do (shown as precautions)
# priority = 1 "right now", 2 "next" (the engine shifts these later when urgency is Low)


def _steps(*steps, avoid=(), priority=2):
    return {"steps": list(steps), "avoid": list(avoid), "priority": priority}


RULES += [
    R("AC01", "AC", "Shared", "action",
      AND(primary(FRAUD), indicator(PHISH)),
      _steps("Secure the affected accounts.",
             "Contact your bank or wallet through a verified channel.",
             avoid=["Do not click or reopen the link.",
                    "Share no more OTPs, PINs or passwords."],
             priority=1),
      "A deceptive call or link was involved, so credentials must be protected first."),
    R("AC02", "AC", "Shared", "action",
      AND(primary(FRAUD), isin("transaction_circumstances", "unauthorised", "both")),
      _steps("Contact your bank or wallet provider through a verified channel.",
             "Ask the provider to protect the account or card.",
             "Note the reference number the provider gives you.",
             priority=1),
      "Money was taken without approval, so the provider must be told."),
    R("AC03", "AC", "Shared", "action", primary(MARKET),
      _steps("Contact the payment provider about the payment.",
             "Preserve the listing, seller profile, chat and payment proof.",
             "Report the seller to the platform.",
             avoid=["Send no more money."],
             priority=2),
      "A marketplace scam needs the proof preserved and the seller reported."),
    R("AC04", "AC", "Shared", "action",
      AND(primary(ACCOUNT), isin("access_status", "full", "partial")),
      _steps("Change the password.",
             "Review active sessions and log out unknown devices.",
             "Turn on two-factor login.",
             priority=1),
      "The user still has some access, so the account can be secured directly."),
    R("AC05", "AC", "Shared", "action",
      AND(primary(ACCOUNT), eq("access_status", "none")),
      _steps("Use the platform's official recovery process.",
             "Secure the linked email account first.",
             priority=1),
      "Access is lost, so the official recovery route is needed."),
    R("AC06", "AC", "Shared", "action", primary(IDENT, HARMFUL),
      _steps("Preserve the profile or post link and screenshots.",
             "Report it to the platform.",
             priority=2),
      "Impersonation or harmful content is handled by evidence plus a platform report."),
    R("AC07", "AC", "Shared", "action", primary(HARASS),
      _steps("Preserve the messages.",
             "Review your privacy settings.",
             "Block the account where it is safe to do so.",
             priority=2),
      "Harassment is handled by preserving messages and limiting contact."),
    R("AC08", "AC", "Shared", "action", primary(BLACKMAIL),
      _steps("Preserve the evidence.",
             "Report the account to the platform.",
             avoid=["Do not pay or send more content or credentials."],
             priority=1),
      "Paying or sending more usually encourages further demands."),
    R("AC09", "AC", "Shared", "action", primary(INTIMATE),
      _steps("Use the platform's reporting tool for the content.",
             "Reach out to someone you trust.",
             avoid=["Never upload the material to this app."],
             priority=1),
      "Intimate content needs platform removal tools and trusted support, never re-sharing."),
    R("AC10", "AC", "Shared", "action",
      AND(primary(MALWARE), eq("environment", "personal")),
      _steps("Disconnect the device from networks.",
             "Get trusted technical help.",
             avoid=["Do not pay any ransom."],
             priority=1),
      "Disconnecting limits damage, and paying a ransom does not guarantee recovery."),
    R("AC11", "AC", "Shared", "action",
      AND(eq("environment", "organisation"), primary(MALWARE, DATA)),
      _steps("Notify your organisation's IT or security team.",
             "Follow your organisation's incident process.",
             priority=1),
      "Organisational incidents must go through the organisation's own response team."),
    R("AC12", "AC", "Shared", "action",
      AND(primary(DATA), eq("environment", "personal")),
      _steps("Change the affected passwords.",
             "Watch your accounts for unusual activity.",
             "Be alert to follow-up phishing.",
             priority=2),
      "Leaked personal data is often used for follow-up scams."),
    R("AC13", "AC", "Shared", "action", eq("immediate_danger", "yes"),
      _steps("Put personal safety first.",
             "Contact the police or emergency services.",
             priority=1),
      "Safety comes before collecting evidence or completing the questionnaire."),
    R("AC14", "AC", "Shared", "action", eq("minor_involved", "yes"),
      _steps("Involve a parent, guardian or trusted adult.",
             "Leave devices and accounts as they are.",
             avoid=["Do not confront the offender."],
             priority=1),
      "A minor should be supported by a trusted adult and the evidence kept intact."),
]

# ---- Stage 4: evidence checklist (EV01-EV08), tag S ----------------------
RULES += [
    R("EV01", "EV", "S", "evidence", has("evidence_list", "none"),
      {"checklist": "Preserve any messages, records or transaction details you can safely keep. You can still report without them."},
      "No evidence is held yet."),
    R("EV02", "EV", "S", "evidence",
      AND(_LOSS, lacks("evidence_list", "receipts")),
      {"checklist": "Find the transaction reference, receipt or bank statement entry."},
      "Money was lost but there is no proof of payment yet."),
    R("EV03", "EV", "S", "evidence",
      AND(has("platform", "whatsapp", "facebook", "instagram", "tiktok"),
          lacks("evidence_list", "screenshots", "messages")),
      {"checklist": "Save screenshots or the conversation before it is deleted."},
      "Social media content can be deleted at any time."),
    R("EV04", "EV", "S", "evidence",
      AND(primary(IDENT, HARASS, BLACKMAIL, INTIMATE, HARMFUL),
          lacks("evidence_list", "links")),
      {"checklist": "Save the profile and post links and the usernames as text."},
      "Links and usernames identify the account or content."),
    R("EV05", "EV", "S", "evidence",
      AND(has("platform", "call_sms"), lacks("evidence_list", "numbers")),
      {"checklist": "Note the phone number, date, time and message text."},
      "A call or SMS was involved but no number is recorded."),
    R("EV06", "EV", "S", "evidence", primary(ACCOUNT),
      {"checklist": "Note login alerts, security notifications and unknown devices."},
      "Security alerts help show how the account was accessed."),
    R("EV07", "EV", "S", "evidence", eq("environment", "organisation"),
      {"checklist": "Preserve incident records through your organisation's authorised procedure."},
      "Organisational evidence must be handled through authorised procedures."),
    R("EV08", "EV", "S", "evidence", lacks("evidence_list", "none"),
      {"checklist": "Keep the original records and avoid edits or crops that change their context. Report anyway and add missing items later."},
      "Evidence exists; keeping it unaltered preserves its context. Reporting should not wait for missing items."),
]

# ---- Stage 4: reporting routes (RT01-RT12), tag S ------------------------
# Roles: Do first / Follow up / Also relevant / Optional (no points).


def _routes(*items):
    return {"routes": [{"route": r, "role": role, "note": note} for r, role, note in items]}


_SOCIAL_OR_WEB = has("platform", "whatsapp", "facebook", "instagram", "tiktok", "app", "website")

RULES += [
    R("RT01", "RT", "S", "route",
      AND(_LOSS, isin("transaction_circumstances", "unauthorised", "both")),
      _routes((BANK, DO_FIRST, "Money was taken without approval.")),
      "A bank or wallet provider is the fastest place to protect an account after an unauthorised transaction."),
    R("RT02", "RT", "S", "route",
      AND(_LOSS, flag("deception_involved")),
      _routes((BANK, ALSO, "It may help, but recovery is not guaranteed.")),
      "A payment made after deception may still be traceable by the provider."),
    R("RT03", "RT", "S", "route",
      OR(AND(primary(BLACKMAIL, INTIMATE, HARASS, IDENT), eq("environment", "personal")),
         eq("minor_involved", "yes")),
      _routes((NCCIA, DO_FIRST, "Report with a parent or guardian if a minor is involved.")),
      "Threats, intimate-content abuse, harassment and impersonation are reported to the cybercrime agency."),
    R("RT04", "RT", "S", "route",
      AND(primary(FRAUD, MARKET, ACCOUNT), eq("environment", "personal")),
      _routes((NCCIA, ALSO, "Report the suspected cybercrime alongside any bank or platform steps.")),
      "Fraud, scams and account compromise can also be reported to the cybercrime agency."),
    R("RT05", "RT", "S", "route",
      AND(primary(ACCOUNT, IDENT, HARASS, HARMFUL, INTIMATE, BLACKMAIL, MARKET), _SOCIAL_OR_WEB),
      _routes((PLATFORM, ALSO, "Platform reports help with removal or recovery but are not a criminal complaint.")),
      "The platform involved can remove content, close accounts or help with recovery."),
    R("RT06", "RT", "S", "route", eq("desired_outcome", "remove_content"),
      _routes((PLATFORM, DO_FIRST, "Removal is the user's main goal, and the platform acts on its own reporting tools.")),
      "The user wants content removed, which the platform controls."),
    R("RT07", "RT", "S", "route",
      OR(primary(HARMFUL), eq("desired_outcome", "remove_content")),
      _routes((PTA, OPTIONAL, "Only if the platform report does not resolve it.")),
      "A web-content complaint to PTA is a next step after the platform."),
    R("RT08", "RT", "S", "route", eq("immediate_danger", "yes"),
      _routes((POLICE, DO_FIRST, "Immediate danger is handled by the police or emergency services.")),
      "Immediate physical danger is an emergency, not a cyber-reporting matter."),
    R("RT09", "RT", "S", "route",
      AND(eq("environment", "organisation"), primary(MALWARE, DATA)),
      _routes((ORG_IT, DO_FIRST, "Follow the organisation's incident process."),
              (PKCERT, ALSO, "Relevant for organisational incidents.")),
      "Organisational incidents go through the organisation's security team and the national CERT."),
    R("RT10", "RT", "S", "route", has("already_reported", "bank"),
      _routes((MOHTASIB, OPTIONAL, "Only if the bank gives no reply within 45 days or the reply is unsatisfactory.")),
      "The Banking Mohtasib comes after the bank's own complaint process."),
    R("RT11", "RT", "S", "route", has("already_reported", "nccia"),
      _routes((NCCIA_EXISTING, FOLLOW_UP, "Keep your complaint reference number and follow up instead of filing again.")),
      "A complaint already exists, so it should be followed up rather than duplicated."),
    R("RT12", "RT", "S", "route", eq("desired_outcome", "legal_advice"),
      _routes((LAWYER, OPTIONAL, "Optional professional support, not a reporting agency.")),
      "The user wants legal advice, which only a qualified lawyer can give."),
]

# ---- Stage 4: completeness warnings (CP01-CP06), tag S -------------------


def _warn(text, provisional=False):
    return {"warning": text, "provisional": provisional}


RULES += [
    R("CP01", "CP", "S", "completeness", eq("offender_known", "unknown"),
      _warn("You can still report. Include any usernames, numbers or links connected to the offender."),
      "The offender is unknown."),
    R("CP02", "CP", "S", "completeness", eq("immediate_danger", "not_sure"),
      _warn("Safety check: if there is any risk, contact the police now. The system does not assume there is none."),
      "The user is unsure about danger, and unknown is never treated as no."),
    R("CP03", "CP", "S", "completeness",
      OR(eq("minor_involved", "prefer_not"), eq("private_content", "prefer_not")),
      _warn("The assessment continues, but some recommendations are less specific."),
      "A sensitive question was skipped."),
    R("CP04", "CP", "S", "completeness",
      has("already_reported", "bank", "platform", "police", "nccia"),
      _warn("Keep your complaint reference numbers and follow up instead of filing again."),
      "The incident has already been reported somewhere."),
    R("CP05", "CP", "S", "completeness",
      OR(eq("main_symptom", "not_sure"), eq("ongoing", "not_sure"),
         eq("time_elapsed", "not_sure"), strength(WEAK)),
      _warn("The diagnosis is provisional. The unclear answers and alternative diagnoses are listed so you can improve the result.",
            provisional=True),
      "Key answers are unclear or the diagnosis is only a weak match."),
    R("CP06", "CP", "S", "completeness",
      AND(_LOSS, eq("transaction_circumstances", "not_sure")),
      {"warning": "The bank route is shown for both cases, because it is unclear whether you authorised the payment.",
       "provisional": False,
       "routes": [{"route": BANK, "role": ALSO,
                   "note": "Shown for both cases because it is unclear whether you authorised the payment."}]},
      "It is unclear whether the payment was authorised."),
]

# --------------------------------------------------------------------------
# 3. MATCH-STRENGTH CRITERIA
# --------------------------------------------------------------------------
# Each diagnosis has a short list of defining criteria. After a diagnosis is chosen, the
# engine checks how many the user's answers CONFIRM:
#     strong    every criterion is confirmed
#     moderate  at least half are confirmed
#     weak      fewer than half are confirmed
# A criterion that cannot be confirmed (including an unanswered or "not sure" answer)
# counts as not met, so missing information lowers the strength instead of being ignored.
_CHANNEL = ("whatsapp", "facebook", "instagram", "tiktok", "website", "app")

CRITERIA = {
    FRAUD: [
        ("The main symptom fits fraud (money missing, or paying or sharing details after a call or link)",
         isin("main_symptom", "money_missing", "paid_after_call_or_link")),
        ("Money was actually lost", flag("financial_loss_confirmed")),
        ("The cause is identified (deception or unauthorised access)",
         OR(flag("deception_involved"), flag("unauthorised_access_suspected"),
            isin("transaction_circumstances", "unauthorised", "both"))),
    ],
    MARKET: [
        ("Goods or services that were paid for did not arrive", eq("main_symptom", "goods_not_received")),
        ("Money was actually lost", flag("financial_loss_confirmed")),
        ("The buying channel is recorded (social media, website or app)", has("platform", *_CHANNEL)),
    ],
    ACCOUNT: [
        ("The symptom fits (lost access or unknown activity)",
         isin("main_symptom", "lost_access", "unusual_activity")),
        ("Access to the account is reduced", isin("access_status", "partial", "none")),
    ],
    IDENT: [
        ("Someone is using the user's name or photos", eq("main_symptom", "fake_account")),
        ("The platform where it appears is recorded", has("platform", *_CHANNEL, "email")),
    ],
    HARASS: [
        ("The symptom fits (unwanted contact or threats)",
         isin("main_symptom", "unwanted_contact", "threats_received")),
        ("No money demand was reported", isin("money_status", "neither", "lost")),
        ("No private or intimate content is involved", eq("private_content", "no")),
    ],
    BLACKMAIL: [
        ("Threats were received", eq("main_symptom", "threats_received")),
        ("Money is being demanded", flag("demand_present")),
        ("The channel used is recorded", has("platform", *_CHANNEL, "email", "call_sms")),
    ],
    INTIMATE: [
        ("Private or intimate content is involved or threatened", flag("private_content_at_stake")),
        ("The symptom fits (threats, or content about the user shared)",
         isin("main_symptom", "threats_received", "content_about_me")),
        ("The channel used is recorded", has("platform", *_CHANNEL, "email", "call_sms")),
    ],
    HARMFUL: [
        ("Content about the user was posted or shared", eq("main_symptom", "content_about_me")),
        ("No private or intimate content is involved", eq("private_content", "no")),
        ("The channel used is recorded", has("platform", *_CHANNEL, "email")),
    ],
    MALWARE: [
        ("The device or files show the symptom (locked, or behaving strangely)",
         eq("main_symptom", "device_problem")),
        ("A ransom or money demand is present", flag("demand_present")),
    ],
    DATA: [
        ("Data appears to have leaked", eq("main_symptom", "data_exposed")),
        ("Something backs it up (a notice, screenshot or record)",
         has("evidence_list", "screenshots", "messages", "links", "receipts")),
    ],
}

RULE_BY_ID = {rule["id"]: rule for rule in RULES}
assert len(RULE_BY_ID) == len(RULES), "duplicate rule IDs"
