import json
from pathlib import Path

MAP_FILE = Path("/home/zinc/workstation/mytools/acronym_map.json")

def load_map():
    """读取 JSON 文件并返回 dict"""
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_map(data):
    """将 dict 写回 JSON 文件"""
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def find_acronym(text):
    """在 text 中查找是否包含任意 map 的 key"""
    data = load_map()
    for key, value in data.items():
        if key in text:
            return value
    return None

def insert_entry(key, value):
    """插入新的 key-value 对"""
    data = load_map()
    data[key] = value
    save_map(data)

def print_map():
    """按 JSON 格式打印 map"""
    data = load_map()
    print(json.dumps(data, ensure_ascii=False, indent=4))

if __name__ == "__main__":
    # 示例：查找
    
    # s = "This paper was published in Proceedings of the International Conference on Machine Learning."
    # result = find_acronym(s)
    # print(f"匹配到: {result}")

    # # 示例：插入新条目
    insert_entry("Proceedings of the ACM Symposiumdd on Operating Systems Principles", "SOSPd")
    # print("已插入新条目。")
    print_map()
