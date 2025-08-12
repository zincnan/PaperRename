import os
import sys
import re
import requests
from PyPDF2 import PdfReader
from typing import Optional


def smart_filename_transform(filename: str) -> str:
    mapping = {
        ' ': '_',
        ':': '=',
        '/': '-',
        '\\': '-',
        '|': '-',
        '*': '',
        '?': '',
        '"': "'",
        '<': '',
        '>': '',
    }
    for old, new in mapping.items():
        filename = filename.replace(old, new)
    filename = re.sub(r'_{2,}', '_', filename)
    filename = re.sub(r'-{2,}', '-', filename)
    return filename.strip('_-=')


def extract_all_dois_from_text(text: str) -> list[str]:
    # 匹配更宽松，然后裁剪
    raw_matches = re.findall(r'\b10\.\d{4,9}/[^\s]+', text)
    cleaned = []
    for doi in raw_matches:
        # 去掉末尾非法字符（如拼接英文单词、PDF残留）
        cleaned_doi = re.match(r'(10\.\d{4,9}/[\w.\-();:/]+)', doi)
        if cleaned_doi:
            cleaned.append(cleaned_doi.group(1))
    return list(set(cleaned))  # 去重



def fetch_doi_metadata(doi: str) -> Optional[dict]:
    headers = {'Accept': 'application/vnd.citationstyles.csl+json'}
    url = f'https://doi.org/{doi}'
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[ERROR] DOI metadata fetch failed for {doi}: {e}")
    return None


def extract_best_doi_from_pdf(pdf_path: str) -> Optional[tuple[str, dict]]:
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages[:3]:  # 提取前3页文字
        text += page.extract_text() or ""

    candidates = extract_all_dois_from_text(text)
    print(f"Found DOI candidates: {candidates}")
    for doi in candidates:
        metadata = fetch_doi_metadata(doi)
        if not metadata:
            continue
        if metadata.get("author"):  # 只要有作者，就认为是单篇论文
            return doi, metadata
        else:
            print(f"[WARN] Skipping {doi}, no author info (probably proceedings)")

    return None  # 都不合适，进入 fallback（标题搜索）


def extract_title_like_text(pdf_path: str) -> Optional[str]:
    reader = PdfReader(pdf_path)
    texts = []
    for page in reader.pages[:1]:
        txt = page.extract_text()
        if txt:
            texts += txt.split("\n")

    candidates = [line.strip() for line in texts if len(line.strip()) > 20 and sum(c.isupper() for c in line) < 10]
    return candidates[0] if candidates else None


def search_doi_by_title(title: str) -> Optional[tuple[str, dict]]:
    print(f"Searching DOI for title: {title}")
    url = f"https://api.crossref.org/works?query.bibliographic={requests.utils.quote(title)}&rows=1"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("message", {}).get("items", [])
            if items:
                item = items[0]
                doi = item.get("DOI")
                metadata = fetch_doi_metadata(doi)
                if metadata and metadata.get("author"):
                    return doi, metadata
    except Exception as e:
        print(f"[ERROR] CrossRef title search failed: {e}")
    return None


ACRONYM_MAP = {
    "Proceedings of the 33rd ACM International Conference on the Foundations of Software Engineering": "FSE",
    "Proceedings of the ACM SIGPLAN Conference on Programming Language Design and Implementation": "PLDI",
    "Proceedings of the International Conference on Software Engineering": "ICSE",
    "Proceedings of the International Conference on Machine Learning": "ICML",
    "Proceedings of the AAAI Conference on Artificial Intelligence": "AAAI",
    "Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition": "CVPR",
    "Proceedings of the Neural Information Processing Systems": "NeurIPS",
    "arXiv": "arXiv",
    # 可根据需要继续添加
}


def generate_filename(metadata: dict) -> str:
    title = metadata.get("title", "").strip()
    year = metadata.get("issued", {}).get("date-parts", [[None]])[0][0]

    # 会议或期刊名
    container = metadata.get("container-title", "")
    if isinstance(container, list):
        container = container[0] if container else "unknown"

    # 简写替换（容错大小写）
    container_clean = container.strip()
    for full, short in ACRONYM_MAP.items():
        if container_clean.lower().startswith(full.lower()):
            container_clean = short
            break
    else:
        container_clean = smart_filename_transform(container_clean)

    author = metadata.get("author", [{}])[0].get("family", "unknown")
    title_safe = smart_filename_transform(title)
    result = f"[{year}]+[{container_clean}]--{title_safe}"
    return result



def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path_to_pdf>")
        return

    pdf_path = sys.argv[1]
    print(f"Extracting metadata from: {pdf_path}")

    result = extract_best_doi_from_pdf(pdf_path)
    if not result:
        print("No valid DOI found, attempting title-based fallback...")
        title_guess = extract_title_like_text(pdf_path)
        if not title_guess:
            print("[ERROR] Could not extract title from PDF.")
            return
        result = search_doi_by_title(title_guess)

    if not result:
        print("[ERROR] Could not determine metadata.")
        return

    doi, metadata = result
    title = metadata.get("title", "<no title>")
    year = metadata.get("issued", {}).get("date-parts", [['?']])[0][0]
    print(f"Best DOI: {doi}")
    print(f"title={title}, year={year}")

    filename = generate_filename(metadata)
    print(f"Suggested filename: {filename}")
        # 构造完整路径
    new_path = os.path.join(os.path.dirname(pdf_path), filename + ".pdf")

    # 尝试重命名
    try:
        os.rename(pdf_path, new_path)
        print(f"File renamed to: {new_path}")
    except Exception as e:
        print(f"[ERROR] Failed to rename file: {e}")



if __name__ == '__main__':
    main()
