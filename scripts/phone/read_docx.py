import os, sys, zipfile

src = sys.argv[1]
print("file:", src, os.path.getsize(src), "bytes")
z = zipfile.ZipFile(src)
media = [n for n in z.namelist() if n.startswith("word/media/")]
print("media:", media)

try:
    import docx
    d = docx.Document(src)
    print("--- 段落 ---")
    for p in d.paragraphs:
        t = p.text.strip()
        if t:
            print(t)
    print("--- 表格 ---")
    for i, tb in enumerate(d.tables):
        for row in tb.rows:
            print(i, " | ".join(c.text.strip() for c in row.cells))
except Exception as e:
    print("docx error:", e)
