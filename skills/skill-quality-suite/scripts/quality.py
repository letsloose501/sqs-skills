#!/usr/bin/env python3
"""Whether the instructions read like instructions.

Structure and spec checks answer "is the skill intact". This one answers "is it worth
loading" - and it is the module with the most room to lie, so every rule here reports
something countable and names where it is. A heuristic that cannot point at a line
does not belong in a linter; it belongs in `references/writing-rubric.md`, which a
human reads with judgement.

The vocabulary is bilingual. These scripts run over skills written in Russian and in
English, and a matcher that knows one language does not report less - it silently
reports nothing, which is the failure this whole suite exists to prevent.
"""
import re
import unicodedata

from core import Finding, line_of, strip_code

# A description does two jobs: name the material, and list the branches that should
# trigger reaching it. These are the words that do the second job.
TRIGGER_RE = re.compile(
    r"\b(use when|trigger|triggers? on|when the user|when you|call this|reach for|"
    r"invoke when|before |after |asks? (?:for|to|about)|if the user|"
    r"срабатыв\w*|когда|если|триггер\w*|вызывай|зови|по словам|при\b)",
    re.I)

# Wording that only makes sense addressed to the router: an order to fire or not to fire,
# the user spoken of in the third person, the house phrase for a trigger list. Narrower
# than TRIGGER_RE on purpose - "use when you need a spec" reads as naturally to a person
# choosing from a menu as to a model, so it proves nothing about who the text is for.
# The verb has to be an order, not a description: "hooks that trigger on save" and
# "хуки, которые не срабатывают" are about a hook, and a menu entry may well say so.
# Same split QL014 needed between `do not fire` and `does not fire`. The noun
# `триггер` is out for the same reason - "настроить триггер CI" is a menu line.
ROUTER_RE = re.compile(
    r"\b(?:this skill should be used when|(?<!that )(?<!which )(?<!who )trigger (?:on|when)|"
    r"invoke (?:this |me )?when|(?:do not|don't|never) (?:fire|trigger|activate)|"
    r"(?:when|if) the user|user asks|"
    r"срабатыва(?:й|ть)\b|вызывай|зови|по словам|"
    r"(?:когда|если) (?:он|она|пользователь)\b)", re.I)
# A quoted wording, the other shape a trigger list takes: «...», "...", “...”.
QUOTED_RE = re.compile(r"«[^»]{2,60}»|\"[^\"]{2,60}\"|“[^”]{2,60}”")
QUOTED_MIN = 3

# Kept narrow on purpose. `WIP`, `ПОТОМ` and `ЗАГЛУШКА` were in this set: they matched a
# bad-commit example, the ordinary Russian word for "afterwards", and a sentence
# explaining what a placeholder looks like. A marker that also reads as content is not
# a marker, so only the unambiguous ones survive.
PLACEHOLDER_RE = re.compile(
    r"\b(TODO|FIXME|TBD|lorem ipsum)\b|<[a-z-]*placeholder[a-z-]*>", re.I)

# Instructions with no completion criterion: the agent cannot tell done from not-done.
VAGUE_RE = re.compile(
    r"\b(be thorough|as needed|as appropriate|if appropriate|where appropriate|"
    r"use (?:your |good )?judg?ment|make it good|write clearly|be concise|be careful|"
    r"do your best|properly|as necessary|"
    r"по необходимости|при необходимости|как следует|по возможности|"
    r"качественно|аккуратно|внимательно|живо|естественно)\b",
    re.I)

# Steering by prohibition. Counted, not judged: a hard guardrail is a legitimate use,
# and only the author knows which of these are guardrails.
NEGATION_RE = re.compile(
    r"(?:^|[.;:!?]\s|\n\s*[-*]\s*)\s*(?:never |do not |don't |avoid |no longer |"
    r"не\s+(?:пиши|делай|используй|добавляй|трогай|бери|зови|ставь)|никогда не|"
    r"не\s+надо|запрещ\w+)",
    re.I | re.M)
NEGATION_MIN = 10

# A disclaimer in the description that names a neighbouring skill.
#
# Three shapes, and each of the first two used to be one expression that could not do
# both jobs. `[`/]name[`\b]` looks like "a backtick or a word boundary" and is not: `\b`
# inside a character class is a backspace, so the name had to be followed by a literal
# backtick and `/mistake,` was invisible. Splitting them lets the slash form carry its
# own guard - `(?<![\w/:])` keeps `https://host/docs` and `a/b` out, which a bare
# boundary would have swept in as neighbours called `docs` and `b`.
#
# The lead-ins are case-insensitive because a description states them at the start of a
# sentence: `Не подменяет konspekt` is how the phrase is actually written, and the
# lower-case-only pattern could therefore never match a Russian one.
NEIGHBOUR_RE = re.compile(
    r"`([a-z][a-z0-9-]{2,63})`"
    r"|(?<![\w/:])/([a-z][a-z0-9-]{2,63})\b"
    r"|(?i:\b(?:не подменяет|не путать с|not to be confused|instead of|это |а не ))"
    r"\s*[`/]?([a-z][a-z0-9-]{2,63})`?")

# A negative-scope clause in the description: the skill naming work it will not take.
# The topic such a clause names is the whole problem - see QL013.
# The verb has to be the one that selects a skill, and the negation has to attach to it.
# A looser pattern read `commands that must never reach an agent unreviewed` as a scope
# fence, when it was the subject the skill teaches - so `reach` only counts as `reach
# for`, and a bare `not` is out: on its own it lands in the middle of ordinary prose.
NEGATIVE_SCOPE_RE = re.compile(
    r"(?:\b(?:do not|don't|never)\s+(?:use|trigger|fire|apply|invoke|reach\s+for)\b"
    r"|\bnot\s+for\b|\bdoes\s+not\s+(?:handle|cover|do)\b"
    r"|\bне\s+(?:использу|применя|срабат|для|берис|путат|подменя))"
    r"[^.;·]{0,90}",
    re.I)

# Something named rather than described: a slash command or a backticked identifier.
# A boundary that points at one of these is aimed at a thing, not spelling out a topic
# for the router to match on, so it is outside QL013 even when the thing is not a skill
# in this tree - `/mistake` and `/clean-memory` are commands, and naming them is the fix
# the rule would otherwise ask for.
NAMED_THING_RE = re.compile(r"[`/][a-z][a-z0-9-]{2,63}\b")

# Polarity markers, for telling an opposite branch from a repeated one. Both halves of
# `use when X` / `do not use when X` stem to the same set, because `stems()` keeps only
# words of four letters or more and every negation below is shorter than that.
POLARITY_RE = re.compile(
    r"\b(?:not|don't|dont|never|avoid|except|unless)\b|\bне\b|\bнельзя\b|\bкроме\b",
    re.I)

# A description is an instruction to the agent about when to act. `This skill does X`
# is a paragraph about itself, and first or second person does not fit the system prompt
# the description is injected into. Both are named in the official guidance.
SELF_TALK_RE = re.compile(
    r"^\s*(?:this|the)\s+skill\b|\bthis\s+skill\s+(?:does|is|will|can|provides|helps|"
    r"handles|allows)\b|^\s*I\s+(?:can|will|help)\b|\byou\s+can\s+use\s+this\b|"
    r"^\s*[Ээ]тот\s+скилл\b",
    re.I)

# Agents run in non-interactive shells, so a script that blocks on a prompt hangs until
# something kills it. `sys.stdin.read()` is deliberately absent: taking input from stdin
# is what the guidance asks for, and only a prompt at a terminal is the failure.
INTERACTIVE_RE = re.compile(
    r"(?<![\w.])(?:input|raw_input)\s*\(|\bgetpass\b|\bRead-Host\b|"
    r"\bread\s+-[a-zA-Z]*p\b|\bclick\.(?:prompt|confirm)\b|\binquirer\.|"
    r"\bquestionary\.|\bprompts?\.(?:confirm|select)\b|\bConfirm-Host\b")

# `npx eslint` resolves to whatever is newest today. A scoped package needs the version
# after the package name, so `@scope/pkg` on its own is still unpinned.
UNPINNED_RE = re.compile(
    r"\b(npx|bunx|uvx)\s+(?:--?\S+\s+)*(@?[\w.-]+(?:/[\w.-]+)?)(?![\w./-]*@)")

SCRIPT_EXT = (".py", ".sh", ".bash", ".ps1", ".js", ".ts", ".rb")

# ---- skill smells from "From Anatomy to Smells" (arXiv 2607.01456) -----------------
#
# The paper names 26 smells and detects 21 of them with a model, these four among them.
# What is here is the part a pattern can carry: each rule reads one structural shape the
# smell's definition names, and stays quiet wherever telling the smell apart takes
# reading the text for meaning. The paper also measured how often its model found each
# one in 238 marketplace skills; the counts these rules give on a real tree are far
# lower, and the gap is the difference between the two kinds of detector, not a defect.
#
# "Never Asks Human" (77% in the paper) was tried and withdrawn. A skill needs to ask
# only where it does something a person must decide, so the test needed an action gate:
# delete, push, publish, send. On the 44 installed skills it was calibrated against, all
# six skills it fired on were false: `push-ins` (a camera move), a JavaScript array push,
# deleting the skill's own scratch files, a routing map naming the commit skill, and a
# README skill that does gate its pushes ("without explicit authorization") in words the
# ask-vocabulary missed. The action words are the subject matter of those skills, and an
# ungated version flags every read-only skill for not asking anyone. `SE002` keeps the
# part that is decidable: a destructive command whose step should ask first.

# A step structure: a numbered item, or a heading that names a step. A bulleted list is
# not counted, because the smell is a workflow with no decomposition at all, and an
# unordered list is how reference material is laid out as often as how steps are.
NUMBERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+\S", re.M)
STEP_HEADING_RE = re.compile(r"^#{1,6}\s+(?:(?:step|phase|stage|шаг|этап)\b|\d+[.)]?\s)",
                             re.I | re.M)
# Where a paragraph stops: a blank line, a list item, a heading, a table row, a quote.
# The marker needs the space after it - `**Setup.**` opens a paragraph, not a list item.
BLOCK_START_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|#|\||>)")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s)")
# An ordering word at the start of a clause - `form first` and `next to` are not one.
SEQUENCE_RE = re.compile(
    r"(?:^|[.;:!?]\s+|,\s+|—\s+|\(\s*)(?:first(?:ly)?,|then\b|next,|after that\b|"
    r"afterwards\b|finally\b|once (?:that|this|it) is done\b|"
    r"сначала\b|затем\b|потом\b|после этого\b|далее\b|наконец\b|в конце\b)",
    re.I | re.M)
QUOTED_ANY_RE = re.compile(r"«[^»\n]*»|\"[^\"\n]*\"|“[^”\n]*”")
# One paragraph this long is the "single block" in the definition. Calibrated on 149
# skills (the installed tree, ~/.claude/plugins, a plugin workspace): no paragraph in a
# body without step structure ran between 115 and 221 words, and the one skill above
# the gap is a whole procedure written as three paragraphs of 221-345 words.
STEPLESS_WORDS = 200

# An example in any of the shapes skills give one. Quoted wordings count too, at the
# threshold `QL015` uses for a trigger list: `("n=3", "N=pq" and "AB=AC")` and an
# italic sample reply are examples with no word announcing them.
EXAMPLE_RE = re.compile(r"\b(?:examples?|e\.g\.|for instance|such as|"
                        r"пример\w*|например|напр\.|скажем)|```|~~~|❌|✅|"
                        r"\bbad\b.{0,40}\bgood\b|\bплохо\b.{0,40}\bхорошо\b",
                        re.I | re.S)

# Something the skill leaves behind, in the imperative an instruction is written in as
# well as the third person a description uses. `cases.BODY_MAKE_RE` has only the second
# for Russian, which is right for a description and misses every instruction.
PRODUCE_RE = re.compile(
    r"\b(?:write|writes|create|creates|save|saves|generate|generates|render|renders|"
    r"produce|produces|build|builds|draft|drafts|export|exports|compose|composes|"
    r"напиши|запиши|записывай|пишет|создай|создаёт|создает|сохрани|сохраняй|сохраняет|"
    r"сгенерируй|сформируй|формирует|оформи|оформляет|собери|отрендери)\b", re.I)
# Any sign of a check, read over the raw text so a `--check` flag or a `validate.py`
# in a code span counts. Generous on purpose: this rule reports a skill that never
# mentions checking at all, and every word here can only keep it quiet.
VERIFY_RE = re.compile(
    r"(?:verif|validat|check|confirm|compar|\btests?\b|testing|pytest|make sure|ensur|lint|"
    r"assert|re-?run|review|inspect|провер|убед|свер|сравн|тест|валид|чек-?лист|"
    r"самопровер)", re.I)

# A section that names the output's format, and the sentence that promises one.
FORMAT_HEADING_RE = re.compile(
    r"^#{1,6}\s+.*\b(?:output format|response format|answer format|report format|"
    r"output template|report template|формат (?:ответа|вывода|отчёта|отчета|результата)|"
    r"шаблон (?:ответа|вывода|отчёта|отчета))", re.I | re.M)
FOLLOWING_FORMAT_RE = re.compile(
    r"\b(?:in|use|follow|with) (?:the |this )?following (?:format|structure|template|"
    r"layout|sections|shape)\b[^\n]*:[ \t]*$|"
    r"\b(?:в|по) (?:следующем|следующему|таком|такому) (?:формате|формату|шаблону|виде)"
    r"\b[^\n]*:[ \t]*$", re.I | re.M)
# What a template looks like on the page: a fence, a table, a list of the parts, a
# quoted sample, markup. Or a link to the file that holds it.
TEMPLATE_SHAPE_RE = re.compile(r"^\s*(?:```|~~~|\||[-*+]\s|\d+[.)]\s|>|<\w)", re.M)
TEMPLATE_LINK_RE = re.compile(r"\]\([^)]+\)|`[^`\n]+\.(?:md|txt|json|ya?ml|html|xml|csv)`")


def prose_paragraphs(prose):
    """(first line, text) for each paragraph of running prose.

    A list item takes its indented continuation lines with it, so a step that wraps is
    still a step and not a paragraph."""
    para, start, in_item = [], 0, False
    for n, line in enumerate(prose.split("\n"), 1):
        if not line.strip() or BLOCK_START_RE.match(line):
            if para and not in_item:
                yield start, " ".join(para)
            para, in_item = [], bool(LIST_ITEM_RE.match(line))
            continue
        if in_item:
            continue
        if not para:
            start = n
        para.append(line.strip())
    if para and not in_item:
        yield start, " ".join(para)


def stepless_block(body):
    """(line, words) of the first long ordered paragraph in a body with no steps, or None."""
    prose = strip_code(body)
    if NUMBERED_ITEM_RE.search(prose) or STEP_HEADING_RE.search(prose):
        return None
    for line, para in prose_paragraphs(prose):
        words = len(para.split())
        if words >= STEPLESS_WORDS and SEQUENCE_RE.search(QUOTED_ANY_RE.sub(" ", para)):
            return line, words
    return None


def has_example(texts):
    """Whether any text of the skill gives an example in a shape a reader can see."""
    for _, text in texts:
        if EXAMPLE_RE.search(text) or len(QUOTED_RE.findall(strip_code(text))) >= QUOTED_MIN:
            return True
    return False


def untemplated_formats(text):
    """(line, what) for each output format the text demands and does not show."""
    out = []
    for m in FORMAT_HEADING_RE.finditer(text):
        level = len(m.group(0)) - len(m.group(0).lstrip("#"))
        rest = text[m.end():]
        nxt = re.search(r"^#{1,%d}\s" % level, rest, re.M)
        section = rest[:nxt.start()] if nxt else rest
        if not TEMPLATE_SHAPE_RE.search(section) and not TEMPLATE_LINK_RE.search(section):
            out.append((line_of(text, m.start()), m.group(0).strip("# \t")))
    for m in FOLLOWING_FORMAT_RE.finditer(text):
        block = text[m.end():].lstrip("\n").split("\n\n", 1)[0]
        if not TEMPLATE_SHAPE_RE.match(block) and not TEMPLATE_LINK_RE.search(block):
            out.append((line_of(text, m.start()), m.group(0).strip()))
    return out

WORD_RE = re.compile(r"[^\W\d_]{4,}", re.U)
WORD_RE_LONG = re.compile(r"[^\W\d_]{6,}", re.U)


def stems(text):
    """Rough stems: the first five letters of every word of four letters or more.

    Crude on purpose. Russian inflection puts `разгрузка` and `разгружено` in one
    family and no stdlib stemmer knows that; five characters does, and the rule that
    uses this is only ever an info-level nudge.
    """
    return {unicodedata.normalize("NFC", w).casefold()[:5]
            for w in WORD_RE.findall(text)}


# The stems of `TRIGGER_RE`'s own lead-in words, read out of that pattern rather than
# copied by hand so the two cannot drift apart. `срабатывай`/`триггер`/`вызывай` and
# `trigger`/`invoke` are all six letters or longer, so they survive `content_stems`'s
# length floor - and, being the literal words every skill in this house style opens its
# trigger clause with, they are shared by construction between any two skills that use
# it. Watched turning into a false `EV007` between two otherwise unrelated skills before
# this set existed: both open with "Срабатывай", and that one shared scaffolding word
# was most of what crossed the threshold.
TRIGGER_LEAD_STEMS = {unicodedata.normalize("NFC", w).casefold()[:6]
                      for w in WORD_RE_LONG.findall(TRIGGER_RE.pattern)}


def content_stems(text):
    """Stems of words carrying topical weight - short scaffolding words dropped.

    `stems()`'s four-letter floor is right for comparing segments of ONE description:
    the topic word is what differs there, and connective scaffolding - "when", "user",
    "asks", "where" - repeats identically across every segment of that same skill and
    cancels out of the comparison. Between two DIFFERENT skills the scaffolding is what
    repeats - it is the shared house style of writing a trigger clause - and the topic
    word is what would actually prove a collision. Watched on this project's own test
    fixtures: an invoice skill and a downloads skill, both phrased "use when ... or when
    the user asks where ... went", cleared the four-letter threshold on `when`/`user`/
    `asks`/`where`/`went` alone with no topic word shared at all. Six letters is short
    enough to keep real topic words in both languages and long enough to drop those;
    `TRIGGER_LEAD_STEMS` catches the lead-in words long enough to survive that floor too.
    """
    return ({unicodedata.normalize("NFC", w).casefold()[:6]
            for w in WORD_RE_LONG.findall(text)} - TRIGGER_LEAD_STEMS)


SEGMENT_RE = re.compile(r"[,;·]|\.\s|«|»|\"")


def near_duplicates(desc, threshold=0.6):
    """Pairs of trigger phrases that name one branch twice.

    Counting commas was the first version of this rule and it fired on eleven skills
    out of twenty-three, because a long trigger list is not the same thing as a
    redundant one. What actually costs context is two phrases that overlap in meaning,
    so the rule compares the phrases instead of counting them - and can therefore print
    the pair, which is what makes the finding checkable.

    Polarity is compared separately because the stems cannot carry it. `use when the
    user says` and `do not use when the user says` are opposite branches, and every word
    that distinguishes them is too short for `stems()` to keep - so by stems alone they
    are identical, and the rule called one of the commonest description shapes a
    duplicate. A pair whose two halves disagree about polarity is two branches.
    """
    segs = [s.strip(" -—:") for s in SEGMENT_RE.split(desc)]
    known = [(s, stems(s), bool(POLARITY_RE.search(s))) for s in segs if len(s) > 8]
    pairs = []
    for i, (a, sa, na) in enumerate(known):
        for b, sb, nb in known[i + 1:]:
            if na != nb:
                continue
            small = min(len(sa), len(sb))
            if small >= 3 and len(sa & sb) / small >= threshold:
                pairs.append((a[:48], b[:48]))
    return pairs


# A clause that fences work OUT, which is not the same thing as a clause containing a
# negation. `POLARITY_RE` answers "do these two segments disagree", which is all
# `near_duplicates` needs to avoid pairing opposites; asked instead to classify a segment
# as an exclusion it is wrong most of the time. Measured on 29 real descriptions: of the
# seven segments it marked negative, none was an exclusion branch, and two - "что не так
# с этим текстом", "не звучит как я" - are wordings a user types that SHOULD fire the
# skill, so the label inverted their meaning.
#
# What separates the two is not the negation but what the negation governs. Three
# grammatical roles, not three examples: the act of using the skill, the purpose it would
# be used for, and the neighbour it defers to instead.
# The lookbehinds keep the third person out: `do not fire` is an instruction to the
# router, `a skill does not fire` is a situation somebody describes - and this project's
# own description contains the second, so without them the rule mislabels its own
# strongest trigger phrase as an exclusion.
EXCLUSION_RE = re.compile(
    r"(?<!does )(?<!did )\b(?:do not|don't|dont|never|not)\s+"
    r"(?:use|trigger|fire|invoke|call|run|reach|apply)\b"
    r"|\b(?:not|never)\s+(?:for|about|when)\b"
    r"|\bне\s+(?:для|под|про)\b"
    r"|\bне\s+(?:запускайся|запускай|срабатывай|триггерь|вызывай|зови|бери|используй|"
    r"применяй)\b"
    r"|\bне\s+(?:путать|подменяет|подменяй|заменяет|заменяй)\b"
    r"|\bdo(?:es)?\s+not\s+(?:replace|substitute|cover)\b"
    r"|\bnot\s+to\s+be\s+confused\b",
    re.I)


def boundary_pairs(desc, threshold=0.6):
    """(fires-on phrase, does-not-fire-on phrase, overlap) where the line is too faint.

    The pair `near_duplicates` above deliberately skips. That rule asks *is one branch
    written twice*, so a pair disagreeing about polarity is two branches and not its
    business. Asked a different question - *is the line between fire and do-not-fire
    sharp enough to hold* - the same pair is the whole answer, and it is the one worth
    the most: a description can separate its branches well on average and still be
    misrouted catastrophically by a single exclusion that reads almost exactly like an
    activation.

    Only the worst pair is reported, not an average over all of them. An average would
    be a statistic with nothing to point at, which is the complaint `QL004` already
    earns; a pair can be read and disagreed with.

    `content_stems`, not `stems`: within one description the connective scaffolding -
    `when`, `user`, `asks` - repeats across every branch by construction, so a
    four-letter floor lets an activation and an exclusion match on nothing but the
    house style. That is the same confound `EV007` was calibrated against, in the one
    place where it bites hardest, because here both halves come from the same author.

    `EXCLUSION_RE`, not `POLARITY_RE`: see the note on that pattern. A segment is an
    exclusion because of what its negation governs, not because it contains one.
    """
    segs = [s.strip(" -—:") for s in SEGMENT_RE.split(desc)]
    known = [(s, content_stems(s), bool(EXCLUSION_RE.search(s))) for s in segs
             if len(s) > 8]
    fires = [(s, st) for s, st, neg in known if not neg and st]
    quiet = [(s, st) for s, st, neg in known if neg and st]
    out = []
    for a, sa in fires:
        for b, sb in quiet:
            small = min(len(sa), len(sb))
            if small >= 2 and len(sa & sb) / small >= threshold:
                out.append((a[:48], b[:48], len(sa & sb) / small))
    return sorted(out, key=lambda r: -r[2])


SENTENCE_RE = re.compile(r"[.;]\s+|\n")


def prompt_match(description, prompt_stems):
    """(best score, the sentence that scored it) for a prompt against one description.

    The ranking behind `sqs.py route`, and the same comparison `cases` runs an
    expectation through: *does this skill's description promise the thing that was
    asked for at all*. It lives here rather than inside either caller because the two
    would otherwise each carry their own copy of the same calibration, and one place
    per test is the only thing that stops them drifting.

    `stems()`, not `content_stems()`: the six-letter floor exists to drop scaffolding
    two DESCRIPTIONS share by house-style construction, and a sentence a human wrote
    about what they want does not carry that scaffolding - it carries short topic
    nouns the floor would eat. Watched degenerating into an alphabetical tie-break
    against the real skill tree before this note existed.
    """
    best_score, best_sentence = 0.0, None
    for sent in SENTENCE_RE.split(description):
        sent = sent.strip(" -—:*")
        # A sentence that fences work out ("not for X") is not a route into the skill
        # for that wording - it is the opposite claim, and counting it as a match is
        # how a genuine exclusion clause outscored the skill it was excluding the
        # wording in favour of.
        if len(sent) <= 8 or POLARITY_RE.search(sent):
            continue
        st = stems(sent)
        small = min(len(st), len(prompt_stems))
        if not small:
            continue
        score = len(st & prompt_stems) / small
        if score > best_score:
            best_score, best_sentence = score, sent
    return best_score, best_sentence


def branch_segments(desc):
    """(sentence, content stems, has-negation) for the trigger-branch part of a description.

    House style - the `TEMPLATE` in `sqs.py` states it directly - is one sentence on
    what the skill is, then the branches that should trigger it. `TRIGGER_RE` finds the
    lead-in into that second part; everything before it is the topic sentence and stays
    out of the comparison, because two skills sharing a topic word is not a collision
    and two skills whose *branches* cover one wording is.

    Split at sentence boundaries, not `near_duplicates`' comma-level ones: a real corpus
    of skills that name their own neighbours (`⚠️ Not this, see `other-skill``)
    keeps that whole disclaimer in one sentence, and `NAMED_THING_RE` then drops the
    sentence entirely. Splitting on commas instead cut a disclaimer like `X - see
    `konspekt`, and not this` into a bare quoted trigger phrase in one fragment and the
    neighbour's name in the next, which is how the first version of this function turned
    every skill that disambiguates against a neighbour into a false collision with that
    neighbour - watched happening on the 28 skills actually installed here.
    """
    m = TRIGGER_RE.search(desc)
    if not m:
        return []
    zone = desc[m.start():]
    out = []
    for s in SENTENCE_RE.split(zone):
        s = s.strip(" -—:*")
        if len(s) <= 8 or NAMED_THING_RE.search(s):
            continue
        out.append((s, content_stems(s), bool(POLARITY_RE.search(s))))
    return out


def cross_overlap(skills, threshold=0.6):
    """EV007 - pairs of skills whose trigger branches claim the same wording.

    The within-one-description version of this comparison is `QL003`/`near_duplicates`;
    this runs the identical stem-overlap-with-polarity test between the branch segments
    of every pair of *different* skills instead of between segments of one description.
    A skill compares against itself constantly by construction (every segment shares
    stems with the rest of its own list) - `na == nb` is what keeps that out.
    """
    entries = []
    for s in skills:
        if not s.ok or s.slash_only or not s.description:
            continue
        name = s.name or s.folder
        for seg, st, neg in branch_segments(s.description):
            entries.append((name, s.folder, s.root, seg, st, neg))
    out, seen = [], set()
    for i, (na, fa, ra, sa, sta, nega) in enumerate(entries):
        for nb, fb, rb, sb, stb, negb in entries[i + 1:]:
            if na == nb or nega != negb:
                continue
            small = min(len(sta), len(stb))
            if small < 3 or len(sta & stb) / small < threshold:
                continue
            pair = tuple(sorted((na, nb)))
            key = pair + (sa[:48], sb[:48])
            if key in seen:
                continue
            seen.add(key)
            f = Finding("EV007",
                       f"`{na}` \"{sa[:48]}\" and `{nb}` \"{sb[:48]}\" claim the same "
                       f"wording - only one can win", severity="warning",
                       where="SKILL.md", skill=fa)
            f.root = ra
            out.append(f)
    return out


def lines_of(pattern, text, limit=3):
    """Line numbers of the first `limit` matches, for a message that can be checked."""
    out = []
    for m in pattern.finditer(text):
        out.append(text.count("\n", 0, m.start()) + 1)
        if len(out) >= limit:
            break
    return out


def check(skill, cfg=None, registry=None):
    """`registry` maps skill name -> whether that skill is user-invoked only."""
    cfg = cfg or {}
    registry = registry or {}
    out = []
    if not skill.ok:
        return out
    desc = skill.description

    # QL015 - QL002 turned round. With `disable-model-invocation: true` the description
    # never reaches the model's context, so routing wording in it is addressed to a reader
    # who is not there, spent where the only reader left needs a line about what the
    # command does.
    if desc and skill.slash_only:
        m = ROUTER_RE.search(desc)
        quoted = QUOTED_RE.findall(desc)
        if m or len(quoted) >= QUOTED_MIN:
            what = (f'"{m.group(0)}"' if m else
                    f"{len(quoted)} quoted wordings ({', '.join(quoted[:2])}, ...)")
            out.append(Finding("QL015", f"{what} - this skill is user-invoked only, so the "
                                        f"model never sees its description; routing "
                                        f"wording here has no reader", where="SKILL.md"))

    # QL002 / QL003 / QL009 - the description as a context pointer
    if desc and not skill.slash_only:
        if not TRIGGER_RE.search(desc):
            out.append(Finding("QL002", "description says what the skill is and never when "
                                        "to reach for it", where="SKILL.md"))
        for a, b in near_duplicates(desc)[:2]:
            out.append(Finding("QL003", f"\"{a}\" and \"{b}\" are the same branch written "
                                        f"twice", where="SKILL.md"))
        # QL014 - the pair QL003 skips, asked the other question
        for a, b, overlap in boundary_pairs(desc)[:1]:
            out.append(Finding("QL014", f"\"{b}\" fences out wording that \"{a}\" claims "
                                        f"({overlap:.0%} of the shorter phrase's topic "
                                        f"words are shared)", where="SKILL.md"))
        if re.search(r"\b" + re.escape(skill.folder) + r"\b", desc, re.I):
            out.append(Finding("QL009", f"description repeats `{skill.folder}`", where="SKILL.md"))
        m = SELF_TALK_RE.search(desc)
        if m:
            out.append(Finding("QL010", f'"{m.group(0).strip()}" - a description is read as '
                                        f'an instruction about when to act, not as a '
                                        f'paragraph about the skill', where="SKILL.md"))

        # QL008 - a disclaimer that can only attract. A neighbour with
        # `disable-model-invocation` cannot intercept anything, so naming its topic here
        # buys nothing and makes this skill a candidate for that topic.
        named = {g for m in NEIGHBOUR_RE.finditer(desc) for g in m.groups() if g}
        harmless = sorted(n for n in named
                          if n != skill.folder and registry.get(n) is True)
        if harmless:
            out.append(Finding("QL008", "names " + ", ".join(f"`{n}`" for n in harmless) +
                                        " - user-invoked, so it cannot intercept anything; the "
                                        "boundary belongs in the body", where="SKILL.md"))

        # QL013 - the same trap as QL008 without a name to hang it on, which is the
        # common shape: the description rules out a topic rather than a named skill.
        # QL008 needs the neighbour to be named *and* registered as user-invoked, so a
        # clause like "do not use for optimising code" is invisible to it - while being
        # the version that actually costs, because the topic is spelled out for the
        # router to match on and the negation does not reverse the match.
        for m in NEGATIVE_SCOPE_RE.finditer(desc):
            clause = " ".join(m.group(0).split())
            # A clause that names a skill in this tree is QL008's case, reported by it
            # or deliberately not. The check runs against the registry rather than
            # `named`, because `NEIGHBOUR_RE` only sees a name in backticks or after one
            # of its lead-ins in lower case - so `Не подменяет konspekt, razbor` slipped
            # past it, and this rule then told an author who had named five neighbours
            # to name the neighbour instead of the topic.
            low = clause.casefold()
            if any(n in low for n in named) or any(n.casefold() in low
                                                   for n in registry if n != skill.folder):
                continue
            if NAMED_THING_RE.search(clause):
                continue        # `/mistake` or `other-skill`: a name, not a bare topic
            if len(stems(clause)) < 3:
                continue        # no topic in it, so nothing for the router to match
            out.append(Finding("QL013", f'"{clause[:60]}" names work this skill will not '
                                        f'take - a description attracts on topic match and '
                                        f'does not repel, so the topic belongs in the body',
                               where="SKILL.md"))

        # QL004 - the description fires on wording the instructions never use
        d, b = stems(desc), stems(skill.body)
        if len(d) >= 8:
            overlap = len(d & b) / len(d)
            if overlap < 0.25:
                out.append(Finding("QL004", f"{overlap:.0%} of the description's words appear in "
                                            f"the body - the description has drifted from what "
                                            f"the skill grew into", where="SKILL.md"))

    # QL016 / QL017 / QL018 - the skill smells a pattern can carry; see the note above
    # `NUMBERED_ITEM_RE`. QL016 reads SKILL.md alone, where the workflow is; the two
    # absences read every text, because an example or a check moved into `references/`
    # is the progressive disclosure the structure rules ask for, not a missing one.
    head = line_of(skill.text, len(skill.text) - len(skill.body)) - 1
    block = stepless_block(skill.body)
    if block:
        out.append(Finding("QL016", f"a {block[1]}-word paragraph carries an ordered "
                                    f"procedure and the body has no steps", where="SKILL.md",
                           line=head + block[0]))
    # SKILL.md is read without its frontmatter: a skill named `example-*`, or one whose
    # description says it fires "when the user asks to check X", has given no example and
    # asked for no check.
    texts = [("SKILL.md", skill.body)] + [t for t in skill.texts() if t[0] != "SKILL.md"]
    if skill.body.strip() and not has_example(texts):
        out.append(Finding("QL017", "no example anywhere in the skill - no sample, no "
                                    "fenced block, no quoted wording", where="SKILL.md"))
    # Quoted wordings are blanked too: "Fixed: export no longer drops a row" is a sample
    # line, and its verb is not something the skill tells the agent to do.
    body_prose = QUOTED_ANY_RE.sub(lambda q: " " * len(q.group(0)), strip_code(skill.body))
    m = PRODUCE_RE.search(body_prose)
    if m and not any(VERIFY_RE.search(t) for _, t in texts):
        out.append(Finding("QL018", f'"{m.group(0)}" - the skill produces something and '
                                    f'nothing in it says to check the result',
                           where="SKILL.md", line=head + line_of(body_prose, m.start())))

    # The prose checks. Fenced blocks are blanked first: a `rm -rf` inside a
    # `bad -> good` pair is teaching material, not an instruction.
    for rel, text in skill.texts():
        prose = strip_code(text)

        hits = lines_of(PLACEHOLDER_RE, prose)
        if hits:
            out.append(Finding("QL007", f"placeholder at line{'s' if len(hits) > 1 else ''} "
                                        f"{', '.join(map(str, hits))}", where=rel, line=hits[0]))

        vague = lines_of(VAGUE_RE, prose, limit=4)
        if vague:
            words = {m.group(0).lower() for m in VAGUE_RE.finditer(prose)}
            out.append(Finding("QL006", f"{', '.join(sorted(words)[:4])} - line"
                                        f"{'s' if len(vague) > 1 else ''} "
                                        f"{', '.join(map(str, vague))}", where=rel, line=vague[0]))

        neg = [m.start() for m in NEGATION_RE.finditer(prose)]
        if len(neg) >= NEGATION_MIN:
            first = [prose.count("\n", 0, i) + 1 for i in neg[:3]]
            out.append(Finding("QL005", f"{len(neg)} prohibitions (lines "
                                        f"{', '.join(map(str, first))}, ...) - check which of "
                                        f"them have a positive form",
                               where=rel, line=first[0]))

        # QL019 - a format the output must take, named and never shown. Raw text: the
        # template is usually the fenced block that strip_code would blank.
        for line, what in untemplated_formats(text)[:2]:
            out.append(Finding("QL019", f'"{what[:60]}" - the format is required and no '
                                        f'template, sample or linked file shows it',
                               where=rel, line=line))

        # QL012 - an unpinned one-off command. It lives inside a fence, so the raw text
        # is searched: blanking code here would blank the thing being checked.
        for m in UNPINNED_RE.finditer(text):
            out.append(Finding("QL012", f"`{m.group(1)} {m.group(2)}` has no version",
                               where=rel, line=text.count("\n", 0, m.start()) + 1))

    # QL011 - the worst failure mode in the set: the agent waits forever and nothing
    # explains why. Bundled scripts are read directly; texts() only carries prose.
    for rel, size, _ in sorted(skill.walk()):
        if not rel.lower().endswith(SCRIPT_EXT) or size > 2_000_000:
            continue
        try:
            with open(f"{skill.root}/{rel}", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        found = _interactive_call(text) if rel.lower().endswith(".py") else None
        if found is None:                  # not Python, or Python that does not parse
            for n, line in enumerate(text.split("\n"), 1):
                if line.lstrip().startswith(("#", "//", "*")):
                    continue
                m = INTERACTIVE_RE.search(line)
                if m:
                    found = (m.group(0).strip(), n)
                    break
        if found:
            out.append(Finding("QL011", f"`{found[0]}` waits for a human",
                               where=rel, line=found[1]))
    return out


# The Python calls that stop for a person at a terminal, by the module that owns them.
PROMPT_CALLS = {"getpass": {"getpass"}, "click": {"prompt", "confirm"},
                "prompts": {"confirm", "select"}}
PROMPT_MODULES = {"inquirer", "questionary"}      # every call on these asks something


def _interactive_call(text):
    """(what, line) for the first call that waits for a person, () for none, None if unparsed.

    Read off the syntax tree for Python, where the line pattern misfired on data: a list of
    standard-library module names carries the word `getpass`, and so does a docstring about
    passwords, and neither waits for anyone. Only a call counts - `input(...)`,
    `getpass.getpass(...)` or `getpass(...)` imported by name, `click.prompt(...)`.
    """
    import ast
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    by_name = {"input", "raw_input"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in PROMPT_CALLS:
            by_name |= {a.asname or a.name for a in node.names
                        if a.name in PROMPT_CALLS[node.module]}
    calls = sorted((n for n in ast.walk(tree) if isinstance(n, ast.Call)),
                   key=lambda n: (n.lineno, n.col_offset))
    for node in calls:
        f = node.func
        if isinstance(f, ast.Name) and f.id in by_name:
            return f"{f.id}(", node.lineno
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            base = f.value.id
            if f.attr in PROMPT_CALLS.get(base, ()) or base in PROMPT_MODULES:
                return f"{base}.{f.attr}(", node.lineno
    return ()
