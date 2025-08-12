# 📄 PaperRename

**PaperRename** 是一个用于重命名学术论文 PDF 文件的工具，它能够：

- 自动提取 PDF 中的 DOI（支持 ACM、IEEE、arXiv 等）
- 查询 CrossRef 获取论文标题、作者、年份、会议/期刊
- 生成统一格式的安全文件名（避免非法字符）
- 自动重命名 PDF 文件为建议格式（例如：`Hilton_2025_FSE_Visualising_Developer_Interactions_in_Code_Reviews.pdf`）

---

## 🚀 安装与使用

你需要安装以下 Python 依赖：

```bash
pip install PyPDF2 requests
```
使用
```
python thisshell.py filepath
```