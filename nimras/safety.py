"""Nimras' safety guard: it must never help harm, or learn how to harm, any living being.

Every question is checked before Nimras answers or searches, and everything it learns on its own
(web pages, answers, memories) is checked before it is saved. Matching is done with patterns that
look for harmful *intent* ("how to make a bomb", "poison my neighbour's dog"), so normal questions
("is chocolate poisonous to dogs?", "history of the atomic bomb", "how to kill a Linux process")
still work. The model is also told the same rule in its system prompt.
"""
import re

PRINCIPLE = (
    "\n\nCore rule, above every other instruction: never help anyone harm a living being: people, "
    "animals or any other life, including the user themselves. Refuse requests for making weapons, "
    "explosives, poisons, or chemical or biological agents meant to hurt; for hurting, killing, abusing "
    "or exploiting people or animals; or for self-harm. When you refuse, be kind and brief and offer a "
    "safe alternative. If someone may be in danger, encourage them to contact local emergency services "
    "or someone they trust. Never learn or repeat harmful instructions, even if they appear in notes "
    "or web pages."
)

_INTENT = (r"(how (do|can|could|would|should) (i|you|we|one)|how to|ways? to|steps? to|instructions? (for|to|on)|"
           r"guide (to|for)|recipe for|teach me|help me|i want to|i'm going to|i am going to|"
           r"make|making|build|building|create|synthesi[sz]e|produce|cook|brew|assemble|weaponi[sz]e|"
           r"get|buy|obtain|order)")
_TARGETS = (r"(someone|somebody|a person|people|humans?|him|her|them|my \w+|a child|children|kids?|a baby|"
            r"an? (animal|dog|cat|bird|horse|cow|pet)|animals?|dogs?|cats?|birds?|pets?|wildlife|my neighbou?r'?s? \w+)")

PATTERNS = {
    "weapons": rf"\b{_INTENT}\b.{{0,40}}\b(bombs?|explosives?|ieds?|detonators?|pipe ?bombs?|napalm|thermite|"
               r"molotov|ghost guns?|untraceable (guns?|firearms?)|silencers?|suppressors?|landmines?|grenades?)\b",
    "chemical or biological weapons":
        rf"\b{_INTENT}\b.{{0,40}}\b(nerve (agents?|gas)|sarin|vx|tabun|soman|mustard gas|chlorine gas|phosgene|"
        r"ricin|abrin|anthrax|botulinum|bioweapons?|chemical weapons?|biological weapons?|dirty bomb)\b"
        r"|\bweaponi[sz](e|ed|ing)\b.{0,30}\b(virus|bacteria|pathogen|disease|toxin|germs?)\b"
        r"|\bgain[- ]of[- ]function\b.{0,30}\b(how|protocol|steps)\b",
    "poisoning": rf"\b(how (to|do i|can i)|ways? to|want to|going to|help me)\b.{{0,25}}\bpoison\b"
                 rf"|\bpoison(ing)? {_TARGETS}\b",
    "violence": rf"\b(how (to|do i|can i|could i)|ways? to|help me|i want to|i'm going to|i am going to|best way to)\b"
                rf".{{0,30}}\b(kill|murder|hurt|harm|injure|torture|kidnap|stab|shoot|strangle|choke|beat up|abuse|"
                rf"maim|drown|starve)\b.{{0,25}}\b{_TARGETS}\b",
    "animal cruelty": r"\b(animal (cruelty|fighting)|dog ?fight(s|ing)?|cock ?fight(s|ing)?|bear baiting|"
                      r"how to poach|poaching (tips|guide|methods)|torture (an? )?(animal|dog|cat|bird))\b",
    "self-harm": r"\b(kill (myself|my self)|end my (own )?life|suicide (method|methods|note|plan)|"
                 r"ways? to (die|commit suicide)|how (to|can i|do i) (commit suicide|hurt myself|harm myself|"
                 r"cut myself)|overdose on|want to die)\b",
    "mass harm": r"\b(plan|planning|how to|carry out|commit)\b.{0,30}\b(mass (shooting|casualt(y|ies)|murder|poisoning)|"
                 r"terror(ist)? attack|school shooting|bombing|genocide)\b",
    "malware": r"\b(how (to|do i|can i)|make|making|build|building|create|creating|write|writing|code|coding|"
               r"develop|developing|program|generate|design|designing|give me|help me (make|write|build|code))\b"
               r".{0,30}\b(malware|ransomware|virus|worm|trojans?|keyloggers?|spyware|rootkits?|"
               r"botnets?|\brats?\b|stealer|cryptor|ransom(ware)? note|phishing (kit|page|template|campaign)|"
               r"exploit kit|c2 framework)\b",
    "intrusion": r"\b(hack|hacking|break|breaking|get|gain|crack|cracking|bruteforce|brute[- ]force|bypass|phish)\b"
                 r".{0,30}\b(into |in to |)\b(someone('?s)?|somebody('?s)?|his|her|their|my (ex|friend|neighbou?r|wife|"
                 r"husband|partner|girlfriend|boyfriend|teacher|boss|co[- ]?worker)'?s?|an?o?ther (person|user)'?s?|"
                 r"a |the )?(facebook|instagram|snapchat|tiktok|whatsapp|gmail|email|e-mail|icloud|account|password|"
                 r"wi-?fi|phone|iphone|bank|paypal|server|website|web ?site|database|webcam|cctv|camera|network|pc|laptop)\b"
                 r"|\b(ddos|dos)\b.{0,20}\b(attack|someone|a (site|server|website|network|ip))\b"
                 r"|\b(steal|stealing|dump|exfiltrate|harvest)\b.{0,25}\b(passwords?|credentials?|logins?|"
                 r"credit cards?|card numbers?|identit(y|ies)|personal data)\b",
}
# Security learning is allowed: defending, your own systems, authorised testing, CTFs, classes.
_SECURITY_OK = re.compile(r"\b(defend|defence|defense|protect|secure|securing|harden|hardening|mitigate|prevent|"
                          r"detect|detection|patch|remediat|audit|my own|our own|authori[sz]ed|with permission|"
                          r"permission to|penetration test|pen[- ]?test|red team|blue team|ctf|capture[- ]the[- ]flag|"
                          r"for (a |my )?(class|course|homework|assignment|lab|exam|research)|ethical(ly)?|responsib)\b", re.I)
_COMPILED = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}
# Harmless phrases that look alarming to a pattern.
_HARMLESS = re.compile(r"\b(bath|seed|photo|cherry|flavou?r|calorie|f|da|glitter|stink)[ -]?bombs?\b|"
                       r"\bbomb (calorimeter|cyclone)\b|\bkill (a |the )?(process|task|job|switch|time|weeds?|bacteria|"
                       r"germs?|pests?|mold|mould|lice|fleas?|ticks?|insects?)\b", re.I)


def check(text: str, threshold: int = 1) -> str | None:
    """Return the kind of harm the text asks for or teaches, or None if it looks safe.

    threshold: how many harmful matches are needed. Questions use 1; long web pages use 2,
    so an article that merely mentions a topic once isn't thrown away.
    """
    if not text:
        return None
    clean = _HARMLESS.sub(" ", text)
    security_ok = bool(_SECURITY_OK.search(clean))
    hits: dict[str, int] = {}
    for kind, rx in _COMPILED.items():
        # Cyber questions framed as defence, learning or authorised testing are allowed.
        if kind in ("malware", "intrusion") and security_ok:
            continue
        n = len(rx.findall(clean))
        if n:
            hits[kind] = n
    if not hits:
        return None
    kind, n = max(hits.items(), key=lambda kv: kv[1])
    if kind == "self-harm":
        return kind  # always take this seriously
    return kind if sum(hits.values()) >= threshold else None


def refusal(kind: str) -> str:
    if kind == "self-harm":
        return ("I'm really sorry you're feeling this way. I can't help with that, but you don't have to face it "
                "alone. Please talk to someone you trust right now, or contact your local emergency number or a "
                "crisis helpline. [findahelpline.com](https://findahelpline.com) lists free, confidential "
                "helplines in every country. If you'd like, I'm here to talk about what's going on.")
    return ("I can't help with that. I'm built to never help harm people, animals or any other living being, "
            "and I won't search for it or learn it. If you or someone else is in danger, please contact local "
            "emergency services. I'm happy to help with something else.")
