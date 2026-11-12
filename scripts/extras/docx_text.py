import docx

d = docx.Document(r"C:\Users\15362\Downloads\青年学生考评自测（学生自测）操作手册.docx")
print("=== 全部段落 ===")
for i, p in enumerate(d.paragraphs):
    t = p.text.strip()
    if t:
        print("%3d | %s" % (i, t))
