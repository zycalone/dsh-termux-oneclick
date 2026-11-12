import os, sys
out = os.path.expanduser("~/dsh日常工作区/产出测试")
os.makedirs(out, exist_ok=True)

# 1) PPTX
from pptx import Presentation
from pptx.util import Inches, Pt
prs = Presentation()
s = prs.slides.add_slide(prs.slide_layouts[0])
s.shapes.title.text = "手机端 dsh 能力自测"
s.placeholders[1].text = "由 python-pptx 直接生成"
s2 = prs.slides.add_slide(prs.slide_layouts[1])
s2.shapes.title.text = "要点"
tf = s2.placeholders[1].text_frame
tf.text = "识图：read_image + glm-5v-turbo"
for line in ["搜索：web_fetch 抓 Bing", "文档：python-pptx / docx / reportlab"]:
    p = tf.add_paragraph(); p.text = line; p.font.size = Pt(20)
prs.save(os.path.join(out, "test.pptx"))

# 2) DOCX
import docx
d = docx.Document()
d.add_heading("手机端 dsh 文档自测", 0)
d.add_paragraph("python-docx 在 Termux 上可用。")
t = d.add_table(rows=2, cols=2)
t.cell(0, 0).text = "能力"; t.cell(0, 1).text = "状态"
t.cell(1, 0).text = "识图"; t.cell(1, 1).text = "通"
d.save(os.path.join(out, "test.docx"))

# 3) PDF
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
c = canvas.Canvas(os.path.join(out, "test.pdf"))
c.setFont("STSong-Light", 20)
c.drawString(80, 760, "手机端 dsh PDF 自测")
c.setFont("STSong-Light", 12)
c.drawString(80, 720, "reportlab + 中文字体 STSong-Light，可直接出中文 PDF。")
c.showPage(); c.save()

for f in sorted(os.listdir(out)):
    p = os.path.join(out, f)
    print(f, os.path.getsize(p), "bytes")
print("ALL_OK")
