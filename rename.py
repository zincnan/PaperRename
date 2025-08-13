import os
import sys
import re
import unicodedata
from typing import Optional, List

import requests
from PyPDF2 import PdfReader

import map_manager


# Strict DOI regex (Crossref-style), with a clear right boundary
CROSSREF_DOI_RE = re.compile(
    r'(?i)\b10\.\d{4,9}/[-._;()/:A-Z0-9]+(?=$|[\s\)\]\}\.,;:<>\"\'\?])'
)

# Venue acronyms for cleaner filenames
ACRONYM_MAP = {
    # "Proceedings of the ACM International Conference on the Foundations of Software Engineering": "FSE",
    # "Proceedings of the ACM SIGPLAN Conference on Programming Language Design and Implementation": "PLDI",
    # "Proceedings of the International Conference on Software Engineering": "ICSE",
    # "Proceedings of the International Conference on Machine Learning": "ICML",
    # "Proceedings of the AAAI Conference on Artificial Intelligence": "AAAI",
    # "Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition": "CVPR",
    # "Proceedings of the Neural Information Processing Systems": "NeurIPS",
    # "arXiv": "arXiv",
}

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


def _preclean_text(text: str) -> str:
    # Normalize and remove common superscripts to avoid tail-sticking
    text = unicodedata.normalize('NFKC', text)
    superscripts = str.maketrans('', '', '¹²³⁴⁵⁶⁷⁸⁹⁰')
    return text.translate(superscripts)


def prefer_specific_dois(cands: List[str]) -> List[str]:
    # Drop "parent DOIs" that are strict prefixes of more specific ones
    keep = []
    for c in cands:
        drop = False
        for d in cands:
            if d != c and d.startswith(c) and len(d) > len(c):
                next_char = d[len(c)]
                if next_char in ".-_/":
                    drop = True
                    break
        if not drop:
            keep.append(c)
    keep = sorted(set(keep), key=len, reverse=True)
    return keep

def clean_doi_list(cands):
    """
    清理 DOI 列表，移除无效或不完整的 DOI 
    Args:
        cands (list): 包含可能的 DOI 字符串的列表
    Returns:
        list: 清理后的有效 DOI 列表
    """
    cleaned = []
    
    for doi in cands:
        if not doi:  # 跳过空字符串
            continue
            
        # 移除常见的后缀干扰词
        doi_clean = re.sub(r'(Files|PDF|Abstract|Full.*Text|Download).*$', '', doi, flags=re.IGNORECASE)
        
        # 移除首尾空白
        doi_clean = doi_clean.strip()
        
        # 检查是否为有效的 DOI 格式
        # DOI 通常格式为 10.xxxx/xxxxx，至少应该有完整的结构
        if re.match(r'^10\.\d+/.+[^.]$', doi_clean):
            # 确保不是以点号结尾（不完整的 DOI）
            if not doi_clean.endswith('.'):
                cleaned.append(doi_clean)
    
    return cleaned


def extract_all_dois_from_text(text: str) -> List[str]:
    text = _preclean_text(text)
    cands = list({m.group(0) for m in CROSSREF_DOI_RE.finditer(text)})
    cands = clean_doi_list(cands)
    return prefer_specific_dois(cands)


def _try_fetch(doi: str) -> Optional[dict]:
    headers = {'Accept': 'application/vnd.citationstyles.csl+json'}
    url = f'https://doi.org/{doi}'
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            return resp.json()
        print(f"[WARN] DOI metadata HTTP {resp.status_code} for {doi}")
    except Exception as e:
        print(f"[ERROR] DOI metadata fetch failed for {doi}: {e}")
    return None


def fetch_doi_metadata(doi: str) -> Optional[dict]:
    # Try as-is
    meta = _try_fetch(doi)
    if meta:
        return meta
    # Robustness for footnote digits accidentally stuck to the tail
    for k in (1, 2):
        if len(doi) > k and doi[-k:].isdigit():
            trimmed = doi[:-k]
            meta = _try_fetch(trimmed)
            if meta:
                print(f"[INFO] Trimmed trailing digits: {doi} -> {trimmed}")
                return meta
    return None


def _get_year(metadata: dict) -> Optional[int]:
    def year_from(dp):
        try:
            return int(dp.get("date-parts", [[None]])[0][0])
        except Exception:
            return None

    for key in ("issued", "published-print", "published-online", "created"):
        if key in metadata:
            y = year_from(metadata[key])
            if y:
                return y
    return None


def _get_title(metadata: dict) -> str:
    t = metadata.get("title", "")
    if isinstance(t, list):
        t = t[0] if t else ""
    return t.strip() if isinstance(t, str) else ""


def _get_container(metadata: dict) -> str:
    c = metadata.get("container-title", "")
    if isinstance(c, list):
        c = c[0] if c else ""
    return c.strip() if isinstance(c, str) else ""


def generate_filename(metadata: dict) -> str:
    title = _get_title(metadata)
    year = _get_year(metadata) or "unknown"

    container = _get_container(metadata) or "unknown"
    # print(type(ACRONYM_MAP), ACRONYM_MAP)
    for full, short in ACRONYM_MAP.items():
        # if container.lower().startswith(full.lower()):
        if full.lower() in container.lower():
            container = short
            break
    else:
        map_manager.insert_entry(container,"Unkonwn")
        container = smart_filename_transform(container)
        

    title_safe = smart_filename_transform(title or _get_title(metadata) or "untitled")
    return f"[{year}]+[{container}]--{title_safe}"


def collect_pdf_files(paths: List[str]) -> List[str]:
    pdf_files = []
    for path in paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    if file.lower().endswith(".pdf"):
                        pdf_files.append(os.path.join(root, file))
        elif os.path.isfile(path) and path.lower().endswith(".pdf"):
            pdf_files.append(path)
        else:
            print(f"[WARN] Skipped unsupported path: {path}")
    return pdf_files


def extract_best_doi_from_first_page(pdf_path: str) -> Optional[str]:
    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        print(f"[ERROR] Failed to open PDF: {e}")
        return None

    try:
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                pass
    except Exception:
        pass

    try:
        if not reader.pages:
            print("[WARN] PDF has no pages.")
            return None
        text = reader.pages[0].extract_text() or ""
    except Exception as e:
        print(f"[ERROR] Failed to extract text from page 1: {e}")
        return None

    candidates = extract_all_dois_from_text(text)
    print(f"Found DOI candidates on first page: {candidates}")

    preferred_types = {"journal-article", "proceedings-article", "posted-content", "report"}

    for doi in candidates:
        meta = fetch_doi_metadata(doi)
        if not meta:
            continue
        if meta.get("author") and (meta.get("type") in preferred_types):
            return doi

    for doi in candidates:
        if fetch_doi_metadata(doi):
            return doi

    return None


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {os.path.basename(sys.argv[0])} <pdf_or_directory> [...]")
        return

    input_paths = sys.argv[1:]
    pdf_files = collect_pdf_files(input_paths)

    if not pdf_files:
        print("No PDF files found.")
        return

    global ACRONYM_MAP
    ACRONYM_MAP = map_manager.load_map()

    for pdf_path in pdf_files:
        if not os.path.isfile(pdf_path):
            continue

        print("=" * 80)
        print(f"📄 Processing: {pdf_path}")

        try:
            doi = extract_best_doi_from_first_page(pdf_path)
            if not doi:
                print("[ERROR] No valid DOI found on the first page.")
                continue

            metadata = fetch_doi_metadata(doi)
            if not metadata:
                print(f"[ERROR] Failed to fetch metadata for DOI: {doi}")
                continue

            title = _get_title(metadata) or "<no title>"
            year = _get_year(metadata) or "?"
            print(f"Best DOI: {doi}")
            print(f"title={title}, year={year}")

            filename = generate_filename(metadata)
            print(f"Suggested filename: {filename}")

            new_path = os.path.join(os.path.dirname(pdf_path), filename + ".pdf")
            if os.path.exists(new_path):
                print(f"[WARN] Target file already exists: {new_path}")
                continue

            os.rename(pdf_path, new_path)
            print(f"✅ File renamed to: {new_path}")
        except Exception as e:
            print(f"[ERROR] Failed to process {pdf_path}: {e}")


if __name__ == "__main__":
    main()
