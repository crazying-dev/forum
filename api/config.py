# 用户相关变量
USER_ID_PREFIX = 'RL'  # 用户ID前缀
vip = "1"  # 用户默认为VIP

# 服务器相关全局变量
POOL_ENABLED = False  # Vercel数据库不需要连接池，所以为False;传统服务器需要连接池进行优化，当使用传统服务器时改为True
Image_father_URL = "https://img.crazying-dev.top/text/one"

# 邮件相关配置
SMTP_ENABLED = True
SMTP_HOST = "smtp.163.com"
SMTP_PORT = 587
SMTP_USER = "ourpet001@163.com"
SMTP_PASSWORD = "QMujS6PuyYxsd7qY"
SMTP_FROM_NAME = "妖精论坛(二创)"

# 数据库相关变量
allowed_search_keys = ['id', 'name', 'email']  # 用户查找可用键


CREATE_USER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    avatar TEXT NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    gender INTEGER DEFAULT 0,
    age VARCHAR(32) DEFAULT '',
    intro TEXT DEFAULT '',
    vip VARCHAR(32) NOT NULL DEFAULT '0',
    is_banned INTEGER NOT NULL DEFAULT 0,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
"""

CREATE_POST_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS posts (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(64) DEFAULT 'general',
    likes INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    status INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_COMMENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS comments (
    id VARCHAR(64) PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    parent_id VARCHAR(64) DEFAULT NULL,
    likes INTEGER DEFAULT 0,
    status INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES comments(id) ON DELETE CASCADE
);
"""

CREATE_World_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS World (
    id SERIAL PRIMARY KEY,
    sender_id VARCHAR(255) NOT NULL,
    sender_name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    parent_id INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
"""

CREATE_POST_LIKES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_likes (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, user_id),
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_POST_FAVORITES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_favorites (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, user_id),
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_USER_FOLLOWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_follows (
    id SERIAL PRIMARY KEY,
    follower_id VARCHAR(64) NOT NULL,
    following_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(follower_id, following_id),
    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (following_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_VERIFY_TOKENS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS verify_tokens (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    token VARCHAR(255) NOT NULL UNIQUE,
    token_type VARCHAR(32) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_POST_REPORTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS post_reports (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR(64) NOT NULL,
    reporter_id VARCHAR(64) NOT NULL,
    reason VARCHAR(64) NOT NULL,
    detail TEXT DEFAULT '',
    status INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE
);
"""

CREATE_INDEX_SQLS = [
    "CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);",
    "CREATE INDEX IF NOT EXISTS idx_world_created_at ON World(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_post_likes_post_id ON post_likes(post_id);",
    "CREATE INDEX IF NOT EXISTS idx_post_likes_user_id ON post_likes(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_post_favorites_user_id ON post_favorites(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_follows_follower ON user_follows(follower_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_follows_following ON user_follows(following_id);",
    "CREATE INDEX IF NOT EXISTS idx_post_reports_post_id ON post_reports(post_id);",
]

# ========================
# 加密算法配置
# ========================
AUTH_SALT = "120615"

AUTH_NUM_REPLACEMENTS = {
    "0": ["¸ò"],
    "1": ["#¸\\"],
    "2": ["¸‰/"],
    "3": ["δ∞π", "³∛∜", "③⓷❸"],
    "4": ["¸n"],
    "5": ["ξψω", "⁵√∛", "⑤⓹❺"],
    "6": ["∇∂∫", "⁶∛∜", "⑥⓺❻"],
    "7": ["∮≠≈", "⁷√∛", "⑦⓻❼"],
    "8": ["≡≤≥", "⁸∛∜", "⑧⓽❽"],
    "9": ["⊕⊗⊙", "⁹√∛", "⑨⓾❾"]
}

AUTH_LETTER_VERSIONS = [
    {  # 1 - 希腊字母为主
        "a": "α∀â", "b": "β∃b̃", "c": "γ∈ç", "d": "δ∉đ", "e": "ε∊ê",
        "f": "φ∴ƒ", "g": "η∵ĝ", "h": "θ∼ħ", "i": "ι↔î", "j": "κ⇔ĵ",
        "k": "λ∧ǩ", "l": "μ∨ł", "m": "ν¬m̃", "n": "ξ∩ñ", "o": "ο∪ô",
        "p": "π⊂ṕ", "q": "ρ⊃q̃", "r": "σ⊆ŕ", "s": "τ⊇ś", "t": "υ∈t̃",
        "u": "φ∋û", "v": "χ∅ṽ", "w": "ψ∇ŵ", "x": "ω∂x̂", "y": "ζ∫ŷ",
        "z": "θ∮ẑ", "A": "ΑÂÃ", "B": "ΒB̃B̄", "C": "ΓÇÇ", "D": "ΔÐĎ",
        "E": "ΕÊË", "F": "ΦF̃F̄", "G": "ΓĜĞ", "H": "ΗĤḨ", "I": "ΙÎÏ",
        "J": "ΘĴJ̃", "K": "ΚǨK̄", "L": "ΛĹĻ", "M": "ΜM̃M̄", "N": "ΝÑŃ",
        "O": "ΟÔÕ", "P": "ΠṔP̄", "Q": "ΞQ̃Q̄", "R": "ΡŔŖ", "S": "ΣŚŞ",
        "T": "ΤŢT̄", "U": "ΥÛŨ", "V": "ΦṼV̄", "W": "ΩŴW̃", "X": "ΞX̂X̄",
        "Y": "ΨŶŸ", "Z": "ΖẐZ̄"
    },
    {  # 2 - 数学符号为主
        "a": "∀αå", "b": "∃βß", "c": "∈γç", "d": "∂δđ", "e": "∃εê",
        "f": "ƒϕƒ", "g": "∇ηĝ", "h": "ℏθħ", "i": "∫ιî", "j": "∮ȷĵ",
        "k": "κκǩ", "l": "ℓλł", "m": "µμṃ", "n": "ηνñ", "o": "∅οô",
        "p": "ππṕ", "q": "√ρq̃", "r": "ρρŕ", "s": "σςś", "t": "ττṭ",
        "u": "∪υû", "v": "√νṽ", "w": "ωωŵ", "x": "×ξx̂", "y": "ψψŷ",
        "z": "ζζẑ", "A": "∀ÅĀ", "B": "ℬḄḆ", "C": "ℂÇĆ", "D": "ⅅÐĎ",
        "E": "∃ÊĒ", "F": "ℱḞḞ", "G": "ℊĜĞ", "H": "ℋĤḪ", "I": "ℐÎĪ",
        "J": "𝒥ĴJ̃", "K": "𝒦ǨḰ", "L": "ℒĹĻ", "M": "ℳṀṂ", "N": "ℕÑŃ",
        "O": "∅ÔŌ", "P": "ℙṔṖ", "Q": "ℚQ̃Ǫ", "R": "ℝŔŖ", "S": "𝕊ŚŞ",
        "T": "𝕋ŢṪ", "U": "⋃ÛŪ", "V": "√ṼṾ", "W": "𝒲ŴẂ", "X": "𝕏X̂Ẋ",
        "Y": "ΨŶŸ", "Z": "ℤẐŻ"
    },
    {  # 3 - 组合字符为主
        "a": "ãāă", "b": "b̃b̄b̆", "c": "c̃c̄c̆", "d": "d̃d̄d̆", "e": "ẽēĕ",
        "f": "f̃f̄f̆", "g": "g̃ḡğ", "h": "h̃h̄h̆", "i": "ĩīĭ", "j": "j̃j̄j̆",
        "k": "k̃k̄k̆", "l": "l̃l̄l̆", "m": "m̃m̄m̆", "n": "ñn̄n̆", "o": "õōŏ",
        "p": "p̃p̄p̆", "q": "q̃q̄q̆", "r": "r̃r̄r̆", "s": "s̃s̄s̆", "t": "t̃t̄t̆",
        "u": "ũūŭ", "v": "ṽv̄v̆", "w": "w̃w̄w̆", "x": "x̃x̄x̆", "y": "ỹȳy̆",
        "z": "z̃z̄z̆", "A": "ÃĀĂ", "B": "B̃B̄B̆", "C": "C̃C̄C̆", "D": "D̃D̄D̆",
        "E": "ẼĒĔ", "F": "F̃F̄F̆", "G": "G̃ḠĞ", "H": "H̃H̄H̆", "I": "ĨĪĬ",
        "J": "J̃J̄J̆", "K": "K̃K̄K̆", "L": "L̃L̄L̆", "M": "M̃M̄M̆", "N": "ÑN̄N̆",
        "O": "ÕŌŎ", "P": "P̃P̄P̆", "Q": "Q̃Q̄Q̆", "R": "R̃R̄R̆", "S": "S̃S̄S̆",
        "T": "T̃T̄T̆", "U": "ŨŪŬ", "V": "ṼV̄V̆", "W": "W̃W̄W̆", "X": "X̃X̄X̆",
        "Y": "ỸȲY̆", "Z": "Z̃Z̄Z̆"
    }
]

AUTH_SYMBOL_VERSIONS = [
    {  # 1
        "-": "–—−", "_": "‗_̲", "@": "＠@⃗", "/": "／⁄", "\\": "＼⧵",
        "|": "｜ǀ", ":": "：∶", ";": "；⁏", ",": "，‚", "?": "？¿",
        "!": "！¡", "(": "（〔", ")": "）〕", "[": "【〖", "]": "】〗",
        "{": "｛⦃", "}": "｝⦄", "<": "＜‹", ">": "＞›", "'": "＇´",
        '"': "＂¨", "`": "｀ˋ", "~": "～˜", "^": "＾ˆ", "&": "＆⅋",
        "*": "＊∗", "%": "％‰", "#": "＃♯", "+": "＋†", "=": "＝≂"
    },
    {  # 2
        "-": "‐‑‒", "_": "﹍﹎﹏", "@": "©®™", "/": "÷⁄∕", "\\": "﹨∖",
        "|": "‖∣∤", ":": "∶∷⁝", ";": "⁏⁏", ",": "‚„", "?": "¿⁇",
        "!": "¡‼⁉", "(": "〈〈", ")": "〉〉", "[": "⟦⟬", "]": "⟧⟭",
        "{": "⦃⦅", "}": "⦄⦆", "<": "≪⋘", ">": "≫⋙", "'": "ʻʼ",
        '"': "˝¨", "`": "ˋ˴", "~": "∼≈", "^": "ˆˇ", "&": "⅋⅋",
        "*": "∗∙", "%": "‰‱", "#": "♯♭", "+": "⊕⊞", "=": "≡≣"
    }
]

AUTH_COMBINING_SETS = [
    ["\u0300", "\u0301", "\u0302", "\u0303", "\u0304"],  # 声调
    ["\u0306", "\u0307", "\u0308", "\u030a", "\u030b"],  # 变音符
    ["\u030c", "\u0327", "\u0328", "\u0332", "\u0333"],  # 下加符
    ["\u20d0", "\u20d1", "\u20d2", "\u20d3", "\u20d4"],  # 箭头
    ["\u20d5", "\u20d6", "\u20d7", "\u20d8", "\u20d9"],  # 更多箭头
]

AUTH_ZW_SETS = [
    ["\u200b", "\u200c", "\u200d"],  # 基础零宽
    ["\u200e", "\u200f", "\u2060"],  # 方向零宽
    ["\u2061", "\u2062", "\u2063"],  # 数学零宽
    ["\ufe0e", "\ufe0f"],  # 变体选择符
]

AUTH_PADDING_SETS = [
    "¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿",
    "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳",
    "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ",
    "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ",
]

AUTH_LIST_FOR_1 = [
    (".", "5*/¸\\3"),
]

