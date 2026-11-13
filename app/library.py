"""library.py - reads your PDF books, cuts them into passages and searches them.

How a book is added:
  1. PyMuPDF pulls the text out of every page.
  2. The text is cut into overlapping passages of about 180 words.
  3. The search engine turns each passage into a vector (384 numbers).
  4. Two files are saved per book in data\\library\\:
        <book_id>.jsonl  - the passages (one per line, with page numbers)
        <book_id>.npy    - the vectors, row i belongs to line i
Only NEW or CHANGED PDFs are processed, so adding book 21 does not redo books 1-20.

How a question is searched:
  The question becomes a vector too. Comparing it with every passage vector
  (a "dot product") gives a similarity score; the highest scores win.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

import numpy as np

from . import llm
from .settings import BOOKS_DIR, CONFIG, LIBRARY_DIR, write_json_atomic

MANIFEST = LIBRARY_DIR / "books.json"
_lock = threading.Lock()

# Live progress, read by the web page while books are being added.
PROGRESS = {"running": False, "book": "", "done_books": 0, "total_books": 0,
            "step": "", "percent": 0, "messages": []}


# --------------------------------------------------------------------------- manifest
def load_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def book_id_for(pdf: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", pdf.stem.lower()).strip("-")[:40] or "book"
    short = hashlib.sha1(pdf.name.encode("utf-8")).hexdigest()[:6]
    return f"{slug}-{short}"


def pretty_title(pdf: Path, meta_title: str | None) -> str:
    if meta_title and len(meta_title.strip()) > 3:
        return meta_title.strip()
    name = re.sub(r"(?i)\((?:z-library|z-lib|1lib)[^)]*\)", "", pdf.stem)   # "(z-library.sk, ...)"
    name = re.sub(r"(?i)oceanofpdf\.?com", "", name)
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"(?i)\b\d+nbsped\b|\b97[89]\d{10}\b|\b\d{9}[\dx]\b|\bcompress(ed)?\b|\bfinal release\b", "", name)
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)                       # JavaCompleteReference
    name = re.sub(r"\s+", " ", name).strip() or pdf.stem
    if name == name.lower():                                                 # all lower case -> Title Case
        small = {"a", "an", "and", "the", "of", "to", "for", "in", "with", "on"}
        name = " ".join(w if (i and w in small) else w.capitalize() for i, w in enumerate(name.split()))
    return name


# --------------------------------------------------------------------------- reading
SOURCE_TYPES = (".pdf", ".epub", ".txt", ".md", ".docx", ".pptx")   # books AND your own notes

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _pages_from_text(raw: str, words_per_page: int = 400) -> list[tuple[int, str]]:
    """Cut plain text into 'pages' of about 400 words, keeping whole lines together."""
    pages, buf, count = [], [], 0
    for line in raw.splitlines(keepends=True):
        buf.append(line); count += len(line.split())
        if count >= words_per_page:
            pages.append((len(pages) + 1, "".join(buf).strip())); buf, count = [], 0
    if "".join(buf).strip():
        pages.append((len(pages) + 1, "".join(buf).strip()))
    return pages


def _office_title(z) -> str | None:
    """The title saved inside a Word or PowerPoint file (File > Info > Title), if any."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(z.read("docProps/core.xml"))
        el = root.find("{http://purl.org/dc/elements/1.1/}title")
        return (el.text or "").strip() or None if el is not None else None
    except (KeyError, ET.ParseError):
        return None


def _docx_pages(path: Path) -> tuple[list[tuple[int, str]], str | None]:
    """Word (.docx): every paragraph and table cell, in order. Uses only built-in Python."""
    import xml.etree.ElementTree as ET
    import zipfile
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        title = _office_title(z)
    lines = []
    for p in root.iter(_W + "p"):
        parts = []
        for el in p.iter():
            if el.tag == _W + "t" and el.text:
                parts.append(el.text)
            elif el.tag == _W + "tab":
                parts.append("\t")
            elif el.tag in (_W + "br", _W + "cr"):
                parts.append("\n")
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return _pages_from_text("\n".join(lines) + "\n"), title


def _pptx_pages(path: Path) -> tuple[list[tuple[int, str]], str | None]:
    """PowerPoint (.pptx): one 'page' per slide (so page 3 = slide 3), with the speaker notes."""
    import posixpath
    import xml.etree.ElementTree as ET
    import zipfile

    def slide_text(xml: bytes) -> str:
        root = ET.fromstring(xml)
        paras = ["".join(t.text or "" for t in p.iter(_A + "t")).strip() for p in root.iter(_A + "p")]
        return "\n".join(x for x in paras if x)

    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        pages = []
        for n in slides:
            text = slide_text(z.read(n))
            rels = n.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
            if rels in names:   # find this slide's speaker notes, if it has any
                m = re.search(rb'Target="([^"]*notesSlide\d+\.xml)"', z.read(rels))
                if m:
                    target = posixpath.normpath(posixpath.join("ppt/slides", m.group(1).decode()))
                    if target in names:
                        notes = slide_text(z.read(target))
                        notes = re.sub(r"^\d+$", "", notes, flags=re.M).strip()   # drop the slide-number box
                        if notes:
                            text += "\nSpeaker notes: " + notes
            number = int(re.search(r"(\d+)\.xml$", n).group(1))
            pages.append((number, text))
        title = _office_title(z)
    return pages, title


def source_files() -> list[Path]:
    """Every readable file in the books folder: PDF/EPUB books and .txt/.md notes."""
    return [p for p in BOOKS_DIR.iterdir() if p.is_file() and p.suffix.lower() in SOURCE_TYPES]


def extract_pages(pdf: Path) -> tuple[list[tuple[int, str]], str | None]:
    """Return [(page_number, text), ...] using 1-based PDF page numbers.
    Plain-text notes (.txt/.md) and Word files are cut into 'pages' of about 400 words;
    PowerPoint files use one page per slide."""
    kind = pdf.suffix.lower()
    if kind in (".txt", ".md"):
        return _pages_from_text(pdf.read_text(encoding="utf-8", errors="replace")), None
    if kind == ".docx":
        return _docx_pages(pdf)
    if kind == ".pptx":
        return _pptx_pages(pdf)
    import pymupdf  # imported here so the rest of the app starts even if it is missing

    pages = []
    with pymupdf.open(pdf) as doc:
        meta_title = (doc.metadata or {}).get("title")
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            text = re.sub(r"-\n(?=[a-z])", "", text)        # join words split by hyphen at line end
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{2,}", "\n\n", text).strip()
            pages.append((i, text))
    return pages, meta_title


def make_passages(book_id: str, pages: list[tuple[int, str]]) -> list[dict]:
    """Cut the whole book into overlapping windows of words, remembering page numbers."""
    size = int(CONFIG["chunk_words"])
    step = max(20, size - int(CONFIG["chunk_overlap_words"]))
    words: list[str] = []
    word_page: list[int] = []
    for page_no, text in pages:
        for w in text.split():
            words.append(w)
            word_page.append(page_no)
    passages = []
    for start in range(0, len(words), step):
        chunk = words[start:start + size]
        if len(chunk) < 25 and passages:   # tiny leftover at the end: skip
            break
        passages.append({
            "id": f"{book_id}-{len(passages):05d}",
            "book_id": book_id,
            "page": word_page[start],
            "page_end": word_page[min(start + len(chunk), len(words)) - 1],
            "text": " ".join(chunk),
        })
        if start + size >= len(words):
            break
    return passages


# --------------------------------------------------------------------------- categories
# Each subject: (name, what books in it are like, title words that give it away, group).
# The description is also used to guess a subject from a book's CONTENT when its title says nothing.
# Order matters for title words: the first match wins, so specific subjects come before broad ones
# ("Python for Cybersecurity" -> Cybersecurity, "Mathematics for Machine Learning" -> Machine Learning).
SEC, DATA, CODE, COMP, SCI, FAITH, FIC, NONFIC, LIFE, STUDY = (
    "Cybersecurity", "Data & AI", "Programming & Software", "Computers & Electronics", "Maths & Science",
    "Faith", "Fiction & Literature", "Non-fiction", "Life & Skills", "Study")
SUBJECTS = [
    # --- cybersecurity
    ("Web Application Security", "attacking and defending web applications: OWASP, SQL injection, XSS, Burp Suite and bug bounties",
     r"web application hack|web app hack|web hacking|web penetration|web security|owasp|burp suite|\bxss\b|sql injection|bug bounty", SEC),
    ("Penetration Testing & Ethical Hacking", "ethical hacking and penetration testing: reconnaissance, scanning, exploits, Metasploit, Kali and red teams",
     r"penetration|pen ?test|hacking|hacker|exploit|\bnmap\b|metasploit|\bkali\b|red team|privilege escalation|\bctf\b", SEC),
    ("Cryptography", "cryptography: ciphers, encryption, hashing, keys and secure protocols",
     r"cryptograph|cipher|encryption|crypto\b", SEC),
    ("Malware & Digital Forensics", "malware analysis, reverse engineering, digital forensics and incident response",
     r"malware|reverse engineer|forensic|incident response|threat hunt|ransomware|rootkit", SEC),
    ("Cybersecurity & Defence", "cybersecurity, defending systems and networks, security operations and risk",
     r"cyber|security|blue team|\bsoc\b|firewall|intrusion|infosec|\bcissp\b|security\+", SEC),
    ("Networking", "computer networks: TCP/IP, routing, switching, protocols, subnets and network administration",
     r"computer network|networking|tcp ?/? ?ip|\bcisco\b|\bccna\b|wireshark|subnet|network\+|routing|network admin", SEC),
    ("Linux & Operating Systems", "Linux, Unix, Windows, the command line, shell scripting and operating systems",
     r"linux|unix|\bbash\b|shell script|command line|operating system|powershell|windows server|\bkernel\b", SEC),
    # --- data and AI
    ("Machine Learning & AI", "machine learning, neural networks, models, training and artificial intelligence",
     r"machine learning|statistical learning|pattern recognition|reinforcement learning|deep learning|neural|artificial intelligence|\bai\b|\bllms?\b|computer vision|natural language processing|\bnlp\b", DATA),
    ("Statistics & Probability", "statistics, probability, distributions, hypothesis tests and Bayesian inference",
     r"probability|statistic|\bstats\b|bayes|regression analysis|stochastic", DATA),
    ("Data Science", "data science, data analysis, data mining and analytics",
     r"data science|data mining|big data|data analy|analytics|weapons of math|pandas|data scientist", DATA),
    ("Data Visualisation", "charts, dashboards and visualising data with tools like Tableau, Power BI and matplotlib",
     r"visuali[sz]|tableau|power ?bi|dashboard|matplotlib|infographic|storytelling with data", DATA),
    ("Excel & Spreadsheets", "Microsoft Excel and spreadsheets: formulas, pivot tables and spreadsheet models",
     r"\bexcel\b|spreadsheet|pivot table|vba\b", DATA),
    ("Data Engineering", "data pipelines, warehouses, ETL and big data systems such as Spark and Kafka",
     r"data engineering|data pipeline|\bspark\b|kafka|airflow|warehouse|\betl\b|hadoop", DATA),
    ("Databases & SQL", "databases and SQL: tables, queries, joins, PostgreSQL, MySQL and MongoDB",
     r"\bsql\b|database|postgres|mysql|mongodb|sqlite|nosql|\bdbms\b", DATA),
    # --- programming and software
    ("Git & Version Control", "using git, commits, branches, merges and version control of source code",
     r"\bgit\b|github|gitlab|version control", CODE),
    ("Web Development", "building websites with HTML, CSS, web design, PHP and back-end web frameworks",
     r"html|\bcss\b|web design|web development|web tech|frontend|front end|backend|back end|\bphp\b|wordpress|django|flask|express", CODE),
    ("JavaScript & TypeScript", "the JavaScript and TypeScript languages, Node.js, React and browser programming",
     r"java ?script|type ?script|node\.?js|\breact\b|\bvue\b|angular|jquery", CODE),
    ("Java", "programming in the Java language: classes, objects, methods and the JDK",
     r"\bjava\b|javafx|spring boot", CODE),
    ("Python", "programming in the Python language: scripts, functions, modules and libraries",
     r"python", CODE),
    ("C & C++", "programming in C and C++: pointers, memory, the standard library and compiled code",
     r"c\+\+|c ?plus ?plus|cpp\b|primer.plus|\bc programming|programming in c\b|\bk ?& ?r\b", CODE),
    ("C# & .NET", "programming in C# and the .NET platform",
     r"c#|csharp|c sharp|\.net\b|asp\.net|\bc\s+\d+(\.\d)? in a nutshell", CODE),
    ("Mobile App Development", "building mobile apps for Android and iOS with Kotlin, Swift and Flutter",
     r"android|\bios\b|kotlin|swift|flutter|react native|mobile app", CODE),
    ("Game Development", "making video games: game design, Unity, Unreal, Godot and game programming",
     r"game dev|game design|game programming|\bunity\b|unreal|godot|pygame|making games", CODE),
    ("Cloud & DevOps", "cloud computing and DevOps: AWS, Azure, Docker, Kubernetes and deployment",
     r"\baws\b|azure|google cloud|docker|kubernetes|devops|cloud computing|cloud native|terraform|ci ?/ ?cd", CODE),
    ("Software Engineering", "software engineering: design patterns, clean code, testing, agile and architecture",
     r"software engineering|design pattern|clean code|refactor|agile|scrum|\buml\b|software architecture|test.driven|pragmatic programmer", CODE),
    ("Programming", "computer programming in general, coding practice and software development",
     r"programming|coding|software development|\bgolang\b|\brust\b|cheat ?sheet|for professionals", CODE),
    # --- computers and electronics
    ("Computer Science & Algorithms", "algorithms, data structures, complexity and theory of computation",
     r"algorithm|data structure|computer science|compiler|theory of computation|automata", COMP),
    ("Computer Architecture", "how computers work inside: CPUs, memory, instruction sets, assembly language and logic gates",
     r"computer architecture|computer organi[sz]ation|assembly|microprocessor|\bcpu\b|risc|digital design|hidden language", COMP),
    ("Electronics & Digital Logic", "electronics and digital logic: circuits, transistors, logic gates, Arduino and microcontrollers",
     r"electronic|digital logic|logic design|circuit|arduino|raspberry pi|microcontroller|embedded|semiconductor", COMP),
    # --- maths and science
    ("Mathematics", "mathematics: calculus, algebra, geometry, proofs and equations",
     r"mathematic|calculus|algebra|geometry|trigonometry|discrete math|differential|mathematical methods|\bmaths?\b", SCI),
    ("Physics", "physics: motion, forces, energy, electricity, waves and quantum theory",
     r"physics|mechanics|thermodynamics|electromagnet|quantum|relativity", SCI),
    ("Astronomy & Space", "astronomy, planets, stars, galaxies and space exploration",
     r"astronom|astrophysic|cosmolog|cosmos|solar system|space exploration|\bnasa\b", SCI),
    ("Chemistry", "chemistry: atoms, molecules, reactions, elements and compounds",
     r"chemistry|chemical|organic chem", SCI),
    ("Biology", "biology: cells, genetics, evolution, plants, animals and the human body",
     r"biology|genetic|evolution|anatomy|botany|zoology|ecology|microbio", SCI),
    ("Earth & Environment", "geology, climate, weather, the environment and conservation",
     r"geolog|climate|environment|weather|conservation|sustainab|earth science", SCI),
    ("Agriculture & Farming", "farming, crops, livestock, soil and agriculture",
     r"agricultur|farming|\bfarm\b|\bcrops?\b|livestock|\bsoil\b|agronom|poultry", SCI),
    ("Engineering", "engineering design: mechanical, civil, electrical and chemical engineering",
     r"engineering|mechanical|civil eng|electrical", SCI),
    ("Popular Science", "science explained for everyone: discoveries, big ideas and how the world works",
     r"popular science|brief history of time|how things work|science of|science behind", SCI),
    # --- faith
    ("Bible & Christianity", "the Bible, scripture, Jesus, the gospels, God, prayer and Christian faith",
     r"\bbible\b|gospel|scripture|testament|\bkjv\b|\bniv\b|\besv\b|psalm|proverbs|christian|jesus|sermon|devotional", FAITH),
    ("Religion & Spirituality", "religion, faith, spirituality, prayer and sacred texts of any tradition",
     r"quran|koran|torah|talmud|islam|buddh|hindu|bhagavad|spiritual|religio|meditation|theology", FAITH),
    # --- fiction and literature
    ("Fantasy", "a fantasy story with magic, wizards, dragons, quests and other worlds",
     r"fantasy|dragon|wizard|sorcer|witch|\bmagic\b|throne", FIC),
    ("Science Fiction", "a science fiction story about space, the future, robots, aliens and technology",
     r"sci.?fi|science fiction|galaxy|dystopia|cyberpunk|robot|alien", FIC),
    ("Mystery & Thriller", "a mystery, crime or thriller story with detectives, murder and suspense",
     r"mystery|thriller|detective|murder|crime|sherlock|suspense", FIC),
    ("Horror", "a horror story with fear, ghosts, monsters and the supernatural",
     r"horror|ghost|haunt|vampire|zombie|stephen king", FIC),
    ("Adventure & Action", "an adventure or action story with journeys, danger, battles and heroes",
     r"adventure|action|quest|survival|pirate", FIC),
    ("Romance", "a romance story about love and relationships between characters",
     r"romance|love story", FIC),
    ("Historical Fiction", "a novel set in the past, telling a story against real historical events",
     r"historical fiction|historical novel", FIC),
    ("African Literature", "novels, stories and poems by African writers about African life",
     r"african (literature|writ|novel|stor)|achebe|ngugi|adichie|soyinka|things fall apart", FIC),
    ("Classics & Literature", "classic literature and literary fiction by famous authors",
     r"classic|shakespeare|dickens|austen|tolstoy|homer|orwell|literature", FIC),
    ("Novels & Stories", "a novel or story told through characters, dialogue, scenes and a plot",
     r"\bnovel\b|stories|a tale|fiction", FIC),
    ("Poetry & Drama", "poems, poetry collections, verse, plays and drama",
     r"poem|poetry|verse|\bplays?\b|drama", FIC),
    ("Comics & Manga", "comics, manga and graphic novels told in panels",
     r"manga|comic|graphic novel|manhwa|anime", FIC),
    ("Children & Young Adult", "books for children and teenagers",
     r"children|kids|young adult|\bya\b", FIC),
    # --- non-fiction
    ("History", "history: past events, wars, empires, civilisations and historical figures",
     r"history|historical|war\b|empire|ancient|century", NONFIC),
    ("Biography & Memoir", "the life story of a real person, a biography, autobiography or memoir",
     r"biography|memoir|autobiograph|life of|my life", NONFIC),
    ("Philosophy", "philosophy: ethics, logic, meaning, mind and great thinkers",
     r"philosoph|ethics|stoic|plato|aristotle|nietzsche|meditations", NONFIC),
    ("Psychology", "psychology: the mind, behaviour, emotions, persuasion and mental health",
     r"psycholog|mind\b|behaviou?r|cognitive|persuasion|influence|manipulat", NONFIC),
    ("Politics & Law", "politics, government, law, rights and society",
     r"politic|government|\blaw\b|legal|constitution|democracy", NONFIC),
    ("Economics", "economics: markets, trade, inequality and economic policy",
     r"economic|economy", NONFIC),
    ("Business & Entrepreneurship", "business, management, start-ups and running a company",
     r"business|management|entrepreneur|startup|start.up|company|strategy", NONFIC),
    ("Marketing & Sales", "marketing, advertising, branding, selling and customers",
     r"marketing|sales|selling|advertis|branding|copywriting", NONFIC),
    ("Money & Investing", "personal finance, saving, budgeting, investing and wealth",
     r"finance|invest|money|wealth|rich|stock market|budget|accounting|crypto ?currenc", NONFIC),
    ("Health & Medicine", "health, medicine, disease, nutrition and the body",
     r"health|medic|nutrition|disease|nursing|diet", NONFIC),
    ("Sports & Fitness", "sport, exercise, fitness and training",
     r"sport|fitness|exercise|workout|football|soccer|chess", NONFIC),
    ("Cooking & Food", "cooking, recipes, food and drink",
     r"cook|recipe|food|baking|kitchen", NONFIC),
    ("Travel & Geography", "travel, places, countries and geography",
     r"travel|geograph|guidebook|zambia|africa\b", NONFIC),
    ("Art, Design & Photography", "art, drawing, painting, design and photography",
     r"\bart\b|drawing|painting|design|photograph|illustrat|sketch|animation", NONFIC),
    ("Music & Film", "music, songs, instruments, film and media",
     r"music|guitar|piano|song|film|cinema|screenwrit", NONFIC),
    ("Video Games & Gaming", "video games, gaming culture, game guides and esports",
     r"video game|gaming|gamer|esport|walkthrough|strategy guide", NONFIC),
    # --- life and skills
    ("Self-Help & Personal Growth", "self-help, habits, motivation, confidence and personal growth",
     r"self.?help|habit|motivation|success|mindset|how to win|confidence|discipline", LIFE),
    ("Productivity & Time Management", "productivity, focus, time management and getting things done",
     r"productiv|time management|getting things done|deep work|focus", LIFE),
    ("Leadership", "leadership, leading teams, influence and decision making",
     r"leader|leading|decision making", LIFE),
    ("Careers & Job Hunting", "careers, CVs, interviews, job hunting and the workplace",
     r"career|\bcv\b|resume|résumé|interview|job hunt|job search|workplace", LIFE),
    ("Relationships & Family", "relationships, love, friendship, marriage, parenting and family life",
     r"relationship|marriage|parenting|family|friendship|dating", LIFE),
    ("Language & Writing", "learning a language, grammar, vocabulary and writing skills",
     r"grammar|vocabulary|language|writing|english|french|spanish|bemba|chinese|dictionary", LIFE),
    ("Communication & Public Speaking", "communication skills, presentations, public speaking and conversation",
     r"communication|presentation|public speaking|conversation|speech|negotiat", LIFE),
    # --- study
    ("Study Skills", "how to study, learn faster, take notes, remember and revise",
     r"study skills|how to study|learning how to learn|memory|note.taking|speed reading", STUDY),
    ("Education & Exams", "textbooks, course material, revision and exam preparation",
     r"exam|revision|syllabus|textbook|course|lecture|past papers?|tutorial", STUDY),
    ("My Notes", "personal notes, lecture notes, summaries and project notes",
     r"\bnotes?\b|my notes|summary", STUDY),
    ("Other", "anything else", r"$^", "Other"),
]
BASE_CATEGORIES = [s[0] for s in SUBJECTS]
GROUP_OF = {s[0]: s[3] for s in SUBJECTS}
# subjects whose title words are reliable on their own (technical books name their topic);
# for everything else the book's content has the final say once it is added
TRUSTED_TITLE_SUBJECTS = {s[0] for s in SUBJECTS if s[3] in (SEC, DATA, CODE, COMP, SCI)}
CATEGORY_FILE = LIBRARY_DIR / "categories.json"   # your own choices and new subjects, kept even if a book is re-added


def _category_choices() -> dict:
    try:
        data = json.loads(CATEGORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# categories.json holds your library customisations:
#   "<book file name>": "<subject>"   your choice for one book (built-in subjects by their original name)
#   "_custom":  [subjects you added]
#   "_groups":  {your subject: the group it is listed under}
#   "_renames": {built-in subject: the name you gave it}
RESERVED = ("_custom", "_groups", "_renames")
YOUR_GROUP = "Your subjects"


def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "")).strip()[:40]


def _renames(choices: dict | None = None) -> dict:
    r = (choices if choices is not None else _category_choices()).get("_renames", {})
    return r if isinstance(r, dict) else {}


def display_name(subject: str, choices: dict | None = None) -> str:
    """The name shown for a subject: your new name for a built-in one, else the subject itself."""
    return _renames(choices).get(subject, subject)


def _canonical(name: str, choices: dict) -> str:
    """Turn a shown name back into the stored one (a renamed built-in subject -> its original name)."""
    for base, shown in _renames(choices).items():
        if shown == name:
            return base
    return name


def _custom(choices: dict) -> list[str]:
    return [c for c in choices.get("_custom", []) if c not in BASE_CATEGORIES]


def all_categories() -> list[str]:
    """Every subject by its shown name: built-in ones, then yours, then Other."""
    choices = _category_choices()
    return ([display_name(c, choices) for c in BASE_CATEGORIES[:-1]] + _custom(choices)
            + [display_name("Other", choices)])


def category_groups() -> list[dict]:
    """Subjects in their groups, for the menus: [{"group": ..., "subjects": [...], "custom": [...]}]."""
    choices = _category_choices()
    my_groups = choices.get("_groups", {}) if isinstance(choices.get("_groups"), dict) else {}
    groups: dict[str, list[str]] = {}
    for base in BASE_CATEGORIES:
        groups.setdefault(GROUP_OF[base], []).append(display_name(base, choices))
    custom = _custom(choices)
    for c in custom:
        groups.setdefault(my_groups.get(c, YOUR_GROUP), []).append(c)
    order = list(dict.fromkeys([s[3] for s in SUBJECTS[:-1]] + [YOUR_GROUP, "Other"]))
    order += [g for g in groups if g not in order]
    return [{"group": g, "subjects": groups[g], "custom": [c for c in groups[g] if c in custom]}
            for g in order if g in groups]


def subject_groups() -> list[str]:
    """Group names a new subject can be listed under."""
    return list(dict.fromkeys([s[3] for s in SUBJECTS[:-1]] + [YOUR_GROUP]))


def _save_choices(choices: dict) -> None:
    write_json_atomic(CATEGORY_FILE, choices)
    INDEX.loaded = False          # rebuild the book-to-subject map on the next search


def add_subject(name: str, group: str = YOUR_GROUP) -> str:
    name = _clean_name(name)
    if not name or name.startswith("_"):
        raise ValueError("Type a name for the subject (it can't start with _).")
    if name.lower() in {c.lower() for c in all_categories()}:
        raise ValueError(f"There is already a subject called {name}.")
    choices = _category_choices()
    choices["_custom"] = _custom(choices) + [name]
    group = _clean_name(group) or YOUR_GROUP
    if group != YOUR_GROUP:
        choices.setdefault("_groups", {})[name] = group
    _save_choices(choices)
    return name


def rename_subject(old: str, new: str) -> str:
    """Rename any subject. Built-in subjects keep their original name inside, so automatic
    sorting still works; books you placed in a subject of your own move with it."""
    old, new = _clean_name(old), _clean_name(new)
    if not new or new.startswith("_"):
        raise ValueError("Type the new name (it can't start with _).")
    choices = _category_choices()
    if old not in all_categories():
        raise ValueError(f"There is no subject called {old}.")
    if new != old and new.lower() in {c.lower() for c in all_categories() if c != old}:
        raise ValueError(f"There is already a subject called {new}.")
    base = _canonical(old, choices)
    if base in BASE_CATEGORIES:
        renames = _renames(choices)
        if new == base:
            renames.pop(base, None)                    # back to its original name
        else:
            renames[base] = new
        choices["_renames"] = renames
    else:                                              # one of yours
        choices["_custom"] = [new if c == old else c for c in _custom(choices)]
        groups = choices.get("_groups", {})
        if old in groups:
            groups[new] = groups.pop(old)
        for k in [k for k in choices if k not in RESERVED and choices[k] == old]:
            choices[k] = new
    _save_choices(choices)
    return new


def delete_subject(name: str) -> int:
    """Delete one of your own subjects. Its books go back to automatic sorting. Returns how many."""
    name = _clean_name(name)
    choices = _category_choices()
    if name not in _custom(choices):
        raise ValueError("Only subjects you added can be deleted. Built-in subjects can be renamed.")
    choices["_custom"] = [c for c in _custom(choices) if c != name]
    choices.get("_groups", {}).pop(name, None)
    moved = [k for k in choices if k not in RESERVED and choices[k] == name]
    for k in moved:
        del choices[k]
    _save_choices(choices)
    return len(moved)


def category_rank(name: str) -> int:
    cats = all_categories()
    return cats.index(name) if name in cats else len(cats)


def guess_category(title: str, file: str = "") -> str:
    """Guess from the title and file name alone (quick, used before a book is added)."""
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", f"{title} {file}")   # JavaCompleteReference -> Java Complete Reference
    text = text.lower().replace("_", " ").replace("-", " ")
    for cat, _desc, pattern, _group in SUBJECTS:
        if re.search(pattern, text):
            return cat
    return "Other"


_SUBJECT_VECTORS: np.ndarray | None = None


def guess_category_from_content(matrix: np.ndarray) -> str | None:
    """Compare the book's overall meaning (the average of its passage vectors) with each
    subject's description and return the closest subject."""
    global _SUBJECT_VECTORS
    if matrix is None or not len(matrix):
        return None
    try:
        if _SUBJECT_VECTORS is None:
            descs = [f"{name}: {desc}" for name, desc, _p, _g in SUBJECTS[:-1]]
            _SUBJECT_VECTORS = llm.embed(descs)
        centre = matrix.mean(axis=0)
        centre = centre / (np.linalg.norm(centre) or 1.0)
        sims = _SUBJECT_VECTORS @ centre
        return SUBJECTS[int(np.argmax(sims))][0]
    except Exception:
        return None


def set_category(file: str, category: str) -> None:
    category = _clean_name(category)
    if not category or category.startswith("_") or file in RESERVED:
        raise ValueError("The subject name is empty")
    choices = _category_choices()
    category = _canonical(category, choices)          # a renamed built-in subject is stored by its original name
    if category not in BASE_CATEGORIES and category not in _custom(choices):
        choices["_custom"] = _custom(choices) + [category]      # a new subject of your own
    choices[file] = category
    _save_choices(choices)


def category_of(file: str, title: str, auto: str | None = None) -> str:
    """Your choice first, then the guess made from the book's content, then the title guess.
    Returned by its shown name (your new name if you renamed it)."""
    choices = _category_choices()
    choice = choices.get(file) if file not in RESERVED else None
    if isinstance(choice, str) and choice and (choice in BASE_CATEGORIES or choice in _custom(choices)):
        return display_name(choice, choices)
    return display_name(auto or guess_category(title, file), choices)


# --------------------------------------------------------------------------- adding books
QUEUE: list[str] = []      # file names waiting to be added, quickest first
_queue_lock = threading.Lock()


def _add_cost(name: str) -> float:
    """Rough work needed to add a book: its page count (the same estimate the Library page
    shows), or its size when the pages can't be counted. Smaller = added sooner."""
    path = BOOKS_DIR / name
    try:
        pages = _page_count(path)
        return float(pages) if pages else path.stat().st_size / 50_000   # about 50 KB per page
    except OSError:
        return float("inf")


def _sort_queue() -> None:
    """Quickest books first, so short books and notes are ready to search within minutes
    instead of waiting behind a 900-page textbook."""
    with _queue_lock:
        QUEUE.sort(key=lambda n: (_add_cost(n), n.lower()))


def _set(**kw):
    PROGRESS.update(kw)


def _say(msg: str):
    PROGRESS["messages"] = (PROGRESS["messages"] + [msg])[-50:]


def _needs_adding(manifest: dict) -> list[Path]:
    todo = []
    for pdf in sorted(source_files(), key=lambda p: p.name.lower()):
        st = pdf.stat()
        old = manifest.get(book_id_for(pdf))
        if old and old["size"] == st.st_size and abs(old["mtime"] - st.st_mtime) < 2:
            continue
        todo.append(pdf)
    return todo


def _forget_deleted(manifest: dict) -> None:
    current = {book_id_for(p) for p in source_files()}
    for bid in [b for b in manifest if b not in current]:
        _say(f"Removed from index: {manifest[bid]['title']}")
        for ext in (".jsonl", ".npy"):
            (LIBRARY_DIR / f"{bid}{ext}").unlink(missing_ok=True)
        manifest.pop(bid)
    write_json_atomic(MANIFEST, manifest)


def request_add(files: list[str] | None = None) -> int:
    """Queue books to add: the given file names, or every new/changed book if None.
    Returns how many were queued. One worker adds them one after another."""
    manifest = load_manifest()
    wanted = {p.name for p in _needs_adding(manifest)} if files is None else set(files)
    names = {p.name for p in source_files()}
    added = 0
    for name in sorted(wanted):
        if name in names and name not in QUEUE and name != PROGRESS.get("book"):
            with _queue_lock:
                QUEUE.append(name)
            added += 1
    if added:
        _sort_queue()
    if added and _lock.acquire(blocking=False):
        threading.Thread(target=_worker, daemon=True).start()
    return added


def scan_and_add() -> None:
    """'Add all new': queue every new or changed book (kept for the Add all button)."""
    if request_add(None) == 0 and not PROGRESS.get("running"):
        _say("Nothing new to add. Put books in the books folder first.")


def _worker() -> None:
    try:
        _set(running=True, done_books=0, total_books=len(QUEUE), percent=0, step="Starting", messages=[])
        manifest = load_manifest()
        _forget_deleted(manifest)
        n = 0
        while QUEUE:
            _sort_queue()                      # books queued while one was being added find their place too
            with _queue_lock:
                name = QUEUE.pop(0)
            pdf = BOOKS_DIR / name
            _set(book=name, step="Reading pages", percent=0, total_books=n + 1 + len(QUEUE))
            if pdf.exists():
                try:
                    _add_one(book_id_for(pdf), pdf, manifest)
                    INDEX.loaded = False           # new book is searchable straight away
                except Exception as e:  # one bad book must not stop the others
                    _say(f"FAILED {name}: {e}")
            n += 1
            _set(done_books=n)
        INDEX.reload()
        _set(step="Finished", percent=100, book="")
    finally:
        _set(running=False)
        _lock.release()
        if QUEUE and _lock.acquire(blocking=False):   # something was queued at the last moment
            threading.Thread(target=_worker, daemon=True).start()


def _auto_subject(pdf: Path, title: str, matrix: np.ndarray) -> str:
    """Title words win when they are clear (they are reliable for textbooks); otherwise the
    book's content decides - this is how a novel or a scripture with a vague title is sorted."""
    by_title = guess_category(title, pdf.name)
    if by_title in TRUSTED_TITLE_SUBJECTS:
        return by_title                       # "Head First Java" really is about Java
    by_content = guess_category_from_content(matrix)
    if by_content:
        return by_content                     # "...Philosopher's Stone" reads like fantasy, not philosophy
    if by_title != "Other":
        return by_title
    return "My Notes" if pdf.suffix.lower() in (".txt", ".md", ".docx", ".pptx") else "Other"


def _add_one(bid: str, pdf: Path, manifest: dict) -> None:
    t0 = time.time()
    pages, meta_title = extract_pages(pdf)
    empty = sum(1 for _, t in pages if len(t) < 20)
    passages = make_passages(bid, pages)
    if not passages:
        raise ValueError("no text found - it may be a scanned book (pictures of pages)")
    _set(step=f"Building search index ({len(passages)} passages)")
    vectors = []
    batch = 16
    for i in range(0, len(passages), batch):
        vectors.append(llm.embed([p["text"] for p in passages[i:i + batch]]))
        _set(percent=int(100 * min(i + batch, len(passages)) / len(passages)))
    matrix = np.vstack(vectors).astype(np.float32)
    np.save(LIBRARY_DIR / f"{bid}.npy", matrix)
    with open(LIBRARY_DIR / f"{bid}.jsonl", "w", encoding="utf-8") as f:
        for p in passages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    st = pdf.stat()
    manifest[bid] = {
        "file": pdf.name, "title": pretty_title(pdf, meta_title),
        "pages": len(pages), "empty_pages": empty, "passages": len(passages),
        "size": st.st_size, "mtime": st.st_mtime,
        "added": time.strftime("%Y-%m-%d %H:%M"),
        "seconds": round(time.time() - t0),
        "category_auto": _auto_subject(pdf, pretty_title(pdf, meta_title), matrix),
    }
    write_json_atomic(MANIFEST, manifest)
    warn = f" ({empty} pages had no text - pictures or scans)" if empty > 5 else ""
    _say(f"Added {manifest[bid]['title']}: {len(pages)} pages, {len(passages)} passages "
         f"in {time.time() - t0:.0f} s{warn}")


# --------------------------------------------------------------------------- searching
_STOP = set("""a an and are as at be been but by can could did do does for from had has have how i if in into
is it its may more most must no not of on or our should so such than that the their them then there these
they this those to was we were what when where which while who why will with would you your about also""".split())


# everyday words that may not appear in your books but are not typos
_COMMON = set("""explain explained explaining example examples difference differences between please tell show
give make write simple simply simpler meaning means mean define definition describe understand understanding
help helping question questions answer answers about would could should whats hows thing things really
using used uses work works working different same similar compare comparison summary summarise summarize
teach learn learning step steps easy hard quick quickly detail details detailed""".split())


def _terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", text.lower()) if len(w) > 1 and w not in _STOP]


class Index:
    """All passages of all books, held in memory for fast searching.

    Search uses TWO methods and combines them:
      - meaning search (vectors): finds passages that say the same thing in other words
      - keyword search (BM25): finds passages that use the exact terms, names and formulas
    Combining them finds the right pages far more often than either alone."""

    def __init__(self):
        self.matrix = np.zeros((0, 384), dtype=np.float32)
        self.passages: list[dict] = []
        self.titles: dict[str, str] = {}
        self.postings: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self.doc_len = np.zeros(0, dtype=np.float32)
        self.book_cat: dict[str, str] = {}
        self.cat_of_row = np.array([], dtype=object)
        self.last_categories: list[str] = []
        self.last_corrections: dict[str, str] = {}
        self.loaded = False

    def _build_keywords(self) -> None:
        from collections import Counter, defaultdict
        raw: dict[str, list[tuple[int, int]]] = defaultdict(list)
        lengths = []
        for i, p in enumerate(self.passages):
            words = _terms(p["text"])
            lengths.append(len(words))
            for w, n in Counter(words).items():
                raw[w].append((i, n))
        self.doc_len = np.asarray(lengths, dtype=np.float32)
        self.postings = {w: (np.fromiter((d for d, _ in v), np.int32, len(v)),
                             np.fromiter((n for _, n in v), np.float32, len(v))) for w, v in raw.items()}

    def _bm25(self, question: str) -> np.ndarray:
        scores = np.zeros(len(self.passages), dtype=np.float32)
        if not len(scores):
            return scores
        n, avg = len(scores), float(self.doc_len.mean() or 1.0)
        k1, b = 1.4, 0.75
        for w in set(_terms(question)):
            if w not in self.postings:
                continue
            docs, tf = self.postings[w]
            idf = np.log(1 + (n - len(docs) + 0.5) / (len(docs) + 0.5))
            norm = tf + k1 * (1 - b + b * self.doc_len[docs] / avg)
            scores[docs] += idf * tf * (k1 + 1) / norm
        return scores

    def reload(self) -> None:
        manifest = load_manifest()
        mats, passages = [], []
        for bid, info in manifest.items():
            npy, jsonl = LIBRARY_DIR / f"{bid}.npy", LIBRARY_DIR / f"{bid}.jsonl"
            if not (npy.exists() and jsonl.exists()):
                continue
            m = np.load(npy)
            with open(jsonl, encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
            if len(rows) != len(m):
                continue  # damaged pair of files; skip rather than give wrong pages
            mats.append(m)
            passages.extend(rows)
        self.matrix = np.vstack(mats) if mats else np.zeros((0, 384), dtype=np.float32)
        self.passages = passages
        self.titles = {bid: info["title"] for bid, info in manifest.items()}
        self.book_cat = {bid: category_of(info["file"], info["title"], info.get("category_auto"))
                         for bid, info in manifest.items()}
        self.cat_of_row = np.array([self.book_cat.get(p["book_id"], "Other") for p in passages])
        self._build_keywords()
        self.loaded = True

    # ------------------------------------------------------------ spelling
    _LETTERS = "abcdefghijklmnopqrstuvwxyz"

    def _edits1(self, w: str) -> set[str]:
        splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
        return ({a + b[1:] for a, b in splits if b}                                   # missing letter
                | {a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1}          # swapped letters
                | {a + c + b[1:] for a, b in splits if b for c in self._LETTERS}      # wrong letter
                | {a + c + b for a, b in splits for c in self._LETTERS})              # extra letter

    def _best_spelling(self, w: str) -> str | None:
        """Closest word that actually appears in your books (1 or 2 typing mistakes away),
        preferring words that appear in many passages."""
        df = lambda x: len(self.postings[x][0]) if x in self.postings else 0
        near = [x for x in self._edits1(w) if df(x) >= 2]
        if not near and len(w) >= 6:
            near = [y for x in self._edits1(w) for y in self._edits1(x) if df(y) >= 3]
        return max(near, key=df) if near else None

    def correct(self, question: str) -> tuple[str, dict[str, str]]:
        """Fix likely spelling mistakes in a question, for searching only. Words that appear
        in your books, short words, numbers and common English words are left alone."""
        fixes: dict[str, str] = {}
        if not self.postings:
            return question, fixes

        def fix(m: re.Match) -> str:
            word = m.group(0)
            w = word.lower()
            if len(w) < 4 or w in self.postings or w in _STOP or not w.isalpha() or w in _COMMON:
                return word
            if w not in fixes:
                best = self._best_spelling(w)
                if not best:
                    return word
                fixes[w] = best
            return fixes[w]

        fixed = re.sub(r"[A-Za-z]+", fix, question)
        return fixed, fixes

    def pick_categories(self, meaning: np.ndarray, keyword: np.ndarray) -> list[str]:
        """Decide which subject(s) the question belongs to: each category is scored by how
        well its best few passages match, and close runners-up are kept too."""
        cats = sorted(set(self.cat_of_row.tolist()))
        if len(cats) <= 1:
            return cats
        kw = keyword / (keyword.max() or 1.0)
        scores = {}
        for c in cats:
            mask = self.cat_of_row == c
            best = np.sort(meaning[mask] + 0.15 * kw[mask])[-3:]
            scores[c] = float(best.mean())
        ranked = sorted(scores, key=scores.get, reverse=True)
        top = scores[ranked[0]]
        return [c for c in ranked[:3] if scores[c] >= top - 0.03]

    def search(self, question: str, k: int, category: str | None = None) -> list[dict]:
        if not self.loaded:
            self.reload()
        if not self.passages:
            return []
        question, self.last_corrections = self.correct(question)    # "inheritence" -> "inheritance"
        q = llm.embed([question], is_query=True)[0]
        meaning = self.matrix @ q
        keyword = self._bm25(question)
        # 1. choose the subject area: the one you picked, or the best match automatically
        if category and category != "auto" and category in set(self.cat_of_row.tolist()):
            chosen = [category]
        else:
            chosen = self.pick_categories(meaning, keyword)
        self.last_categories = chosen
        allowed = np.isin(self.cat_of_row, chosen) if chosen else np.ones(len(meaning), bool)
        meaning = np.where(allowed, meaning, -1.0)
        keyword = np.where(allowed, keyword, 0.0)
        pool = max(30, k * 6)
        by_meaning = np.argsort(-meaning)[:pool]
        by_keyword = np.argsort(-keyword)[:pool] if keyword.max() > 0 else np.array([], dtype=int)
        # reciprocal rank fusion: a passage ranked high by either method rises to the top
        fused: dict[int, float] = {}
        for rank, i in enumerate(by_meaning):
            fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (60 + rank)
        for rank, i in enumerate(by_keyword):
            fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (60 + rank)
        top_kw = float(keyword.max()) or 1.0
        hits: list[dict] = []
        for i in sorted(fused, key=fused.get, reverse=True):
            if not allowed[i]:
                continue
            p = self.passages[i]
            # skip near-duplicates: overlapping passages from the same pages of the same book
            if any(h["book_id"] == p["book_id"] and p["page"] <= h["page_end"] and h["page"] <= p["page_end"]
                   for h in hits):
                continue
            hit = dict(p)
            hit["score"] = round(float(meaning[i]), 3)            # meaning match, 0 to 1
            hit["keyword"] = round(float(keyword[i]) / top_kw, 3)  # keyword match, 0 to 1
            hit["title"] = self.titles.get(p["book_id"], p["book_id"])
            hit["category"] = self.book_cat.get(p["book_id"], "Other")
            hits.append(hit)
            if len(hits) >= k:
                break
        return hits


INDEX = Index()


_PAGE_CACHE: dict[tuple, int | None] = {}


def _page_count(path: Path) -> int | None:
    """Quick page count without reading the text (cached), used for time estimates."""
    st = path.stat()
    key = (path.name, st.st_size, int(st.st_mtime))
    if key not in _PAGE_CACHE:
        n = None
        try:
            kind = path.suffix.lower()
            if kind in (".pdf", ".epub"):
                import pymupdf
                with pymupdf.open(path) as doc:
                    n = doc.page_count
            elif kind == ".pptx":
                import zipfile
                with zipfile.ZipFile(path) as z:
                    n = sum(1 for x in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", x))
            else:                                   # .docx/.txt/.md: about 400 words per page
                n = max(1, int(st.st_size / (25_000 if kind == ".docx" else 2_400)))
        except Exception:
            n = None
        _PAGE_CACHE[key] = n
    return _PAGE_CACHE[key]


def seconds_per_page(manifest: dict) -> float:
    """Learned from the books already added (falls back to about 1.1 s per page)."""
    timed = [(b["seconds"], b["pages"]) for b in manifest.values() if b.get("seconds") and b.get("pages")]
    if not timed:
        return 1.1
    return max(0.2, sum(s for s, _ in timed) / max(1, sum(p for _, p in timed)))


def list_books() -> list[dict]:
    manifest = load_manifest()
    rate = seconds_per_page(manifest)
    indexed_files = {info["file"] for info in manifest.values()}
    books = [dict(info, book_id=bid, status="ready") for bid, info in manifest.items()]
    for pdf in sorted(source_files()):
        if pdf.name not in indexed_files:
            books.append({"book_id": book_id_for(pdf), "file": pdf.name,
                          "title": pretty_title(pdf, None), "status": "new"})
    for b in books:
        b["category"] = category_of(b["file"], b["title"], b.get("category_auto"))
        path = BOOKS_DIR / b["file"]
        if path.exists():
            b["size_mb"] = round(path.stat().st_size / 1_048_576, 1)
            if b["status"] == "new":
                pages = _page_count(path)
                if pages:
                    b["pages"] = pages
                    b["estimate_seconds"] = int(pages * rate)
        if b["file"] == PROGRESS.get("book") and PROGRESS.get("running"):
            b["status"] = "adding"
        elif b["file"] in QUEUE:
            b["status"] = "queued"
            b["queue_pos"] = QUEUE.index(b["file"]) + 1      # 1 = added next (the quickest waits at the front)
    return sorted(books, key=lambda b: (category_rank(b["category"]), b["title"].lower()))
