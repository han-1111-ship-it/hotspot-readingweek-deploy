CATEGORY_KEYWORDS = {
    "科技": ["AI", "人工智能", "大模型", "机器人", "手机", "电脑", "芯片", "科技", "软件", "互联网", "算法", "编程"],
    "教育": ["大学", "学生", "考试", "高考", "考研", "学校", "教育", "课程", "老师", "学习", "就业"],
    "社会": ["政策", "社会", "新闻", "城市", "经济", "法律", "交通", "公共", "国家", "国际"],
    "生活": ["健康", "睡眠", "美食", "旅游", "生活", "消费", "购物", "家庭", "运动"],
}
CATEGORY_NAMES = list(CATEGORY_KEYWORDS.keys()) + ["其他"]

def classify_topic(title: str, excerpt: str = "") -> str:
    text = f"{title or ''} {excerpt or ''}".lower()
    scores = {category: sum(1 for word in words if word.lower() in text)
              for category, words in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "其他"
