from modules.classifier import classify_topic

def test_technology():
    assert classify_topic("人工智能大模型发展") == "科技"

def test_education():
    assert classify_topic("大学生如何准备考研") == "教育"

def test_other():
    assert classify_topic("没有匹配关键词的标题") == "其他"


def test_topic_summary_can_determine_category():
    assert classify_topic("热门议题", "讨论人工智能工具对工作的影响") == "科技"
