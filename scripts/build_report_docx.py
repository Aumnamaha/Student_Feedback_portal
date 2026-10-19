#!/usr/bin/env python3
"""Generate build/Project_Report.docx from Project_Report.md.

Usage (from repo root):
    source build/.venv/bin/activate     # activate venv
    python scripts/build_report_docx.py # generate docx
"""

import os, shutil, subprocess, sys, re as _re, glob as _glob, zipfile
from io import BytesIO
import xml.etree.ElementTree as ET
import tempfile as _tempfile

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join(REPO_ROOT, "build")
INPUT_MD = os.path.join(REPO_ROOT, "Project_Report.md")
PREPROC_MD = os.path.join(BUILD_DIR, "_preprocessed.md")
REF_DOCX = os.path.join(BUILD_DIR, "_ref.docx")
RAW_DOCX = os.path.join(BUILD_DIR, "_raw.docx")
OUTPUT_DOCX = os.path.join(BUILD_DIR, "Project_Report.docx")

# ---------------------------------------------------------------------------
# STEP A — preprocess a temp copy of the markdown in build/
# ---------------------------------------------------------------------------

SCREENSHOT_ROWS = [
    ("Student Registration Form", "docs/screenshots/registration.png"),
    ("Login Page", "docs/screenshots/login.png"),
    ("Student Dashboard", "docs/screenshots/student_dashboard.png"),
    ("Admin Dashboard (All Feedback)", "docs/screenshots/admin_dashboard_all.png"),
    ("Admin Dashboard (Filtered)", "docs/screenshots/admin_dashboard_filtered.png"),
    ("Anonymous Feedback in Admin View", "docs/screenshots/anonymous_feedback.png"),
    ("Status Update Interface", "docs/screenshots/status_update.png"),
    ("Reports Page — Average Ratings", "docs/screenshots/reports_ratings.png"),
    ("Reports Page — Category Distribution", "docs/screenshots/reports_distribution.png"),
    ("Reports Page — Submission Trends", "docs/screenshots/reports_trends.png"),
    ("Faculty Dashboard", "docs/screenshots/faculty_dashboard.png"),
    ("Faculty Feedback Detail with Comment Thread", "docs/screenshots/faculty_feedback_detail.png"),
    ("Admin Faculty Management", "docs/screenshots/admin_faculty.png"),
    ("Verification (Verify / Fail on a Resolved item)", "docs/screenshots/verification.png"),
    ("Student view of comment thread (read-only)", "docs/screenshots/student_comment_view.png"),
]

TALL_IMAGES = {
    "01_use_case_diagram.png",
    "02_class_diagram.png",
    "04a_activity_status_lifecycle.png",
    "04b_activity_student_registration.png",
    "04c_activity_admin_filtering.png",
}
NARROW_IMAGES = {
    "03_sequence_diagram_submit_feedback.png",
    "03b_sequence_faculty_login_dashboard.png",
    "03c_sequence_post_comment.png",
    "03d_sequence_verification.png",
    "05_er_diagram.png",
}


def preprocess_markdown():
    """Read Project_Report.md → write build/_preprocessed.md."""
    with open(INPUT_MD) as f:
        content = f.read()

    # (a) Replace page-break divs with pandoc raw openxml block
    page_break_xml = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```\n'
    content = content.replace(
        '<div style="page-break-after: always;"></div>',
        page_break_xml,
    )

    # (b) Remove manual TOC section; replace with [[TOC]] marker.
    #     Keep the "Table of Contents" heading itself but strip everything
    #     between it and its closing ---  (including numbered table and notes).
    lines = content.split("\n")
    new_lines = []
    in_toc = False
    for line in lines:
        stripped = line.strip()
        if not in_toc and stripped == "# Table of Contents":
            new_lines.append(line)          # keep the heading
            in_toc = True
            continue
        if in_toc:
            if stripped == "---":
                new_lines.append("")
                new_lines.append("[[TOC]]")
                new_lines.append("")
                in_toc = False
            continue                        # skip TOC body
        new_lines.append(line)

    content = "\n".join(new_lines)

    # (c) Image sizing — append pandoc attributes to docs/images/ images.
    def _size_image(m):
        alt = m.group(1)
        full_path = m.group(2)
        base = os.path.basename(full_path)
        if base in TALL_IMAGES:
            # Constrain height to fit A4 printable area (~8 in) while
            # keeping width proportional but no wider than 5.5 in.
            return f'![{alt}]({full_path}){{width=5.5in;height=7.8in}}'
        elif base in NARROW_IMAGES:
            return f'![{alt}]({full_path}){{width=6.3in}}'
        return m.group(0)

    content = _re.sub(r'!\[(.*?)\]\((docs/images/[^)]+)\)', _size_image, content)

    # (d) Screenshot placeholders after the Chapter 19.4 table ends.
    lines = content.split("\n")
    new_lines = []
    past_194_table = False
    for i, line in enumerate(lines):
        if not past_194_table:
            stripped = line.strip()
            # Detect the last row of the screenshot table (contains docs/screenshots)
            if "## 19.4 Screenshots Placeholder" in line:
                new_lines.append(line)
                continue
            if stripped.startswith("|") and "docs/screenshots" not in stripped:
                new_lines.append(line)
                continue
            elif stripped.startswith("|") and "docs/screenshots" in stripped:
                past_194_table = True
                # Insert placeholders after this table row.
                for idx, (name, path) in enumerate(SCREENSHOT_ROWS, 1):
                    caption = f"*Figure 19.{idx}: {name}*"
                    if os.path.exists(os.path.join(REPO_ROOT, path)):
                        new_lines.append("")
                        new_lines.append(caption)
                        new_lines.append(f'![Figure 19.{idx}: {name}]({path}){{width=6.0in}}')
                    else:
                        new_lines.append("")
                        new_lines.append(caption)
                        new_lines.append(
                            '```{=openxml}\n'
                            f'<w:p><w:r><w:t>Insert screenshot: {name} ({path})</w:t></w:r></w:p>\n'
                            '```\n'
                        )
                continue
            else:
                new_lines.append(line)
                continue
        # past_194_table is True — append all remaining lines.
        new_lines.append(line)

    content = "\n".join(new_lines)

    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(PREPROC_MD, "w") as f:
        f.write(content)
    print(f"[A] Preprocessed markdown → {PREPROC_MD} ({os.path.getsize(PREPROC_MD)} bytes)")


# ---------------------------------------------------------------------------
# Reference docx generator (Step B)
# ---------------------------------------------------------------------------

def generate_reference_docx():
    """Create a minimal reference.docx with proper base styles."""
    from docx import Document
    from docx.shared import Pt, Inches, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # Page setup: A4, 1-inch margins
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    for margin_name in ("top", "bottom", "left", "right"):
        setattr(section, f"{margin_name}_margin", Inches(1))

    # Body text style
    body_style = doc.styles["Normal"]
    body_font = body_style.font
    body_font.name = "Times New Roman"
    body_font.size = Pt(12)
    body_pf = body_style.paragraph_format
    body_pf.line_spacing = 1.15
    body_pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    body_pf.space_after = Pt(6)

    # Heading styles: all Times New Roman, black, specified sizes.
    for level, (pt_val, bold, page_break_before) in [
        (1, (16, True, True)),
        (2, (14, True, False)),
        (3, (12, True, False)),
        (4, (12, True, False)),
    ]:
        h = doc.styles[f"Heading {level}"]
        h.font.name = "Times New Roman"
        h.font.size = Pt(pt_val)
        h.font.bold = bold
        if page_break_before:
            h.paragraph_format.page_break_before = True

    # Title style — for the title-page heading (not in TOC).
    from docx.enum.style import WD_STYLE_TYPE
    try:
        title_style = doc.styles["Title"]
    except KeyError:
        title_style = doc.styles.add_style("Title", WD_STYLE_TYPE.PARAGRAPH)
    title_font = title_style.font
    title_font.name = "Times New Roman"
    title_font.size = Pt(24)
    title_font.bold = True
    title_pf = title_style.paragraph_format
    title_pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_pf.space_after = Pt(12)

    # Code block / Source Code style.
    try:
        code_style = doc.styles["Source Code"]
    except KeyError:
        code_style = doc.styles.add_style("Source Code", WD_STYLE_TYPE.PARAGRAPH)
    code_font = code_style.font
    code_font.name = "Consolas"
    code_font.size = Pt(9)

    # Caption style (italic, 10 pt, centered).
    try:
        cap_style = doc.styles["Caption"]
    except KeyError:
        cap_style = doc.styles.add_style("Caption", WD_STYLE_TYPE.PARAGRAPH)
    cap_font = cap_style.font
    cap_font.name = "Times New Roman"
    cap_font.size = Pt(10)
    cap_font.italic = True
    cap_pf = cap_style.paragraph_format
    cap_pf.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.save(REF_DOCX)
    print(f"[B] Reference docx → {REF_DOCX}")


# ---------------------------------------------------------------------------
# Step B — convert with pypandoc
# ---------------------------------------------------------------------------

def run_pandoc():
    """Run pandoc to convert preprocessed markdown → build/_raw.docx."""
    try:
        import pypandoc
    except ImportError as e:
        print(f"[B] FATAL: pypandoc not available: {e}")
        sys.exit(1)

    pandoc_path = pypandoc.get_pandoc_path()
    cmd = [
        pandoc_path,
        PREPROC_MD,
        "-o", RAW_DOCX,
        "--from=markdown+pipe_tables+raw_attribute",
        "--resource-path=" + REPO_ROOT,
        "--reference-doc=" + REF_DOCX,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[B] pandoc stderr:\n{result.stderr}")
        sys.exit(1)
    size = os.path.getsize(RAW_DOCX)
    print(f"[B] Raw docx → {RAW_DOCX} ({size:,} bytes)")


# ---------------------------------------------------------------------------
# Step C — post-process with python-docx
# ---------------------------------------------------------------------------

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _set_update_fields(docx_path):
    """Set w:updateFields w:val=\"true\" in word/settings.xml."""
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    tmp_dir = None
    try:
        tmp_dir = _tempfile.mkdtemp(dir=BUILD_DIR, prefix="_uf_tmp_")
        with zipfile.ZipFile(docx_path) as zf:
            zf.extractall(tmp_dir)
        settings_path = os.path.join(tmp_dir, "word", "settings.xml")
        if not os.path.exists(settings_path):
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            ET.ElementTree(ET.Element(f"{{{ns_w}}}settings")).write(
                settings_path, xml_declaration=True, encoding="UTF-8",
            )
        tree = ET.parse(settings_path)
        root = tree.getroot()
        tag_local = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        if tag_local != "settings":
            new_root = ET.Element(f"{{{ns_w}}}settings")
            for child in list(root):
                new_root.append(child)
            root = new_root
            tree = ET.ElementTree(root)
        uf_found = False
        for child in root:
            gtag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if gtag == "updateFields":
                child.set(f"{{{ns_w}}}val", "true")
                uf_found = True
        if not uf_found:
            ET.SubElement(root, f"{{{ns_w}}}updateFields").set(
                f"{{{ns_w}}}val", "true",
            )
        tree.write(settings_path, xml_declaration=True, encoding="UTF-8")
        with zipfile.ZipFile(docx_path, "w") as zf_out:
            for root_dir, dirs, files in os.walk(tmp_dir):
                for fname in sorted(files):
                    full = os.path.join(root_dir, fname)
                    arcname = os.path.relpath(full, tmp_dir)
                    zf_out.write(full, arcname)
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def post_process():
    """Final polish on the raw docx."""
    from docx import Document
    from docx.shared import Pt, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from lxml import etree as _lxml_et
    import tempfile as _tempfile
    import xml.etree.ElementTree as _ET
    import zipfile as _zf

    doc = Document(RAW_DOCX)
    w_ns = W_NS
    r_ns = R_NS

    # ---- (a) Title page centering ---
    first_h1 = None
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading 1"):
            first_h1 = p
            break

    title_text = "Student Feedback Management System"
    if first_h1 is not None and title_text in first_h1.text:
        # Center the heading, set to Title style (not in TOC), remove page-break-before.
        first_h1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in first_h1.runs:
            run.font.size = Pt(24)
            run.font.bold = True
        try:
            first_h1.style = doc.styles["Title"]
        except KeyError:
            pass  # Title style may not exist; that's OK.
        first_h1.paragraph_format.page_break_before = False

        # Center all following paragraphs until next H1 or page-break div.
        for p in doc.paragraphs:
            if p == first_h1:
                continue
            body_xml = str(p._element.xml)
            has_pagebreak = '<w:br w:type="page"/>' in body_xml
            if (p.style.name.startswith("Heading 1")
                    and title_text not in p.text):
                break
            if has_pagebreak:
                break
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---- (b) Replace [[TOC]] marker with Word TOC field ----
    for p in list(doc.paragraphs):
        text = "".join(run.text for run in p.runs)
        if "[[TOC]]" in text:
            p.clear()
            r1 = p.add_run()
            fc_start = _lxml_et.SubElement(
                r1._element, f"{w_ns}fldChar",
                {f"{w_ns}fldCharType": "begin"},
            )
            r2 = p.add_run()
            instr_t = _lxml_et.SubElement(
                r2._element, f"{w_ns}instrText",
                {"{http://www.w3.org/XML/1998/namespace}space": "preserve"},
            )
            instr_t.text = 'TOC \\o "1-2" \\h \\z \\u'
            r3 = p.add_run()
            fc_end = _lxml_et.SubElement(
                r3._element, f"{w_ns}fldChar",
                {f"{w_ns}fldCharType": "end"},
            )

    # ---- (c) Footer with centered PAGE field on all sections ----
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        if not footer.paragraphs:
            fp = footer.add_paragraph()
        else:
            fp = footer.paragraphs[0]
        for run in list(fp.runs):
            run.text = ""

        _lxml_et.SubElement(
            fp._element, f"{w_ns}fldChar",
            {f"{w_ns}fldCharType": "begin"},
        )
        r_instr = fp.add_run()
        instr_t = _lxml_et.SubElement(
            r_instr._element, f"{w_ns}instrText",
            {"{http://www.w3.org/XML/1998/namespace}space": "preserve"},
        )
        instr_t.text = " PAGE "
        _lxml_et.SubElement(
            fp._element, f"{w_ns}fldChar",
            {f"{w_ns}fldCharType": "end"},
        )
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Ensure A4 page setup with 1-inch margins.
    from docx.shared import Cm as D_Cm
    section = doc.sections[0]
    if not section.page_width:
        section.page_width = D_Cm(21.0)
    if not section.page_height:
        section.page_height = D_Cm(29.7)
    for margin_name in ("top", "bottom", "left", "right"):
        if getattr(section, f"{margin_name}_margin") is None:
            setattr(section, f"{margin_name}_margin", Inches(1))

    # ---- (d) Table formatting: header-row repetition + autofit to window ----
    page_width = doc.sections[0].page_width.inches
    left_m = doc.sections[0].left_margin.inches
    right_m = doc.sections[0].right_margin.inches
    max_width_emu = int((page_width - left_m - right_m) * 914400)

    for table in doc.tables:
        tbl = table._element
        tblPr = tbl.find(f"{w_ns}tblPr")
        if tblPr is None:
            tblPr = ET.SubElement(tbl, f"{w_ns}tblPr")
        # Set autofit to window.
        tw = tblPr.find(f"{w_ns}tblW")
        if tw is not None:
            tw.set("{0}type".format(w_ns), "auto")
        else:
            ET.SubElement(tblPr, f"{w_ns}tblW", {"{0}type".format(w_ns): "auto"})

        # Header row formatting.
        if table.rows and len(table.rows) > 0:
            first_row = table.rows[0]
            for cell in first_row.cells:
                for p_cell in cell.paragraphs:
                    for run in p_cell.runs:
                        run.font.bold = True
                        run.font.size = Pt(10)

    # ---- (d2) Replace screenshot placeholders with images or frames ----
    from docx.shared import Inches as DInches

    for idx, (name, path) in enumerate(SCREENSHOT_ROWS, 1):
        placeholder_text = f"*Figure 19.{idx}: {name}*"
        full_path = os.path.join(REPO_ROOT, path)
        target_para = None
        for p in doc.paragraphs:
            text = "".join(run.text for run in p.runs)
            if placeholder_text == text.strip():
                target_para = p
                break

        if target_para is None:
            # Caption was italicized by pandoc (asterisks stripped).
            # Match on the figure number pattern instead.
            fig_pattern = _re.compile(rf"Figure 19\.{idx}:")
            found = False
            for p in doc.paragraphs:
                text = "".join(run.text for run in p.runs)
                if fig_pattern.search(text):
                    target_para = p
                    found = True
                    break
            if not found:
                print(f"  [C] Warning: no paragraph found for screenshot frame {idx}")
                continue

        parent_elem = target_para._element.getparent()
        idx_in_parent = list(parent_elem).index(target_para._element)

        # Remove the placeholder paragraph.
        parent_elem.remove(target_para._element)

        if os.path.exists(full_path):
            # Embed actual image at this position.
            temp_img_p = doc.add_paragraph()
            try:
                temp_img_p.clear()
                run = temp_img_p.add_run()
                run.add_picture(full_path, width=DInches(6.0))
                img_body_elem = temp_img_p._element
                parent_elem.insert(idx_in_parent, img_body_elem)
            except Exception as e:
                print(f"  [C] Warning: could not embed image {path}: {e}")
        else:
            # Create a bordered table frame (3 inches tall, light grey fill).
            tbl_el = parent_elem.makeelement("{0}tbl".format(w_ns), {})

            # Table properties.
            tblPr2 = _lxml_et.SubElement(tbl_el, "{0}tblPr".format(w_ns))
            _lxml_et.SubElement(
                tblPr2, "{0}tblW"
                .format(w_ns), {"{0}type".format(w_ns): "auto"},
            )

            # Borders.
            borders = _lxml_et.SubElement(tbl_el, "{0}tblBorders".format(w_ns))
            for edge in ["top", "left", "bottom", "right"]:
                _lxml_et.SubElement(
                    borders, "{0}{1}".format(w_ns, edge),
                    {"{0}val".format(w_ns): "single",
                     "{0}sz".format(w_ns): "4",
                     "{0}space".format(w_ns): "0",
                     "{0}color".format(w_ns): "999999"},
                )

            # Shading (light grey).
            shd = _lxml_et.SubElement(tblPr2, "{0}shd".format(w_ns))
            shd.set("{0}fill".format(w_ns), "F2F2F2")
            shd.set("{0}val".format(w_ns), "clear")

            # Table grid (single column).
            grid = _lxml_et.SubElement(tbl_el, "{0}tblGrid".format(w_ns))
            _lxml_et.SubElement(
                grid, "{0}col"
                .format(w_ns), {"{0}w".format(w_ns): str(max_width_emu)},
            )

            # Single-cell row — 3 inches tall (3 * 1440 = 4320 EMUs).
            tr = _lxml_et.SubElement(tbl_el, "{0}tr".format(w_ns))
            trPr = _lxml_et.SubElement(tr, "{0}trPr".format(w_ns))
            _lxml_et.SubElement(
                trPr, "{0}trHeight"
                .format(w_ns),
                {"{0}val".format(w_ns): str(int(3 * 1440)),
                 "{0}hRule".format(w_ns): "atLeast"},
            )

            tc = _lxml_et.SubElement(tr, "{0}tc".format(w_ns))
            tcPr = _lxml_et.SubElement(tc, "{0}tcPr".format(w_ns))
            _lxml_et.SubElement(
                tcPr, "{0}vAlign"
                .format(w_ns), {"{0}val".format(w_ns): "center"},
            )
            tcBody = _lxml_et.SubElement(tc, "{0}tcBody".format(w_ns))
            tc_p = _lxml_et.SubElement(tcBody, "{0}p".format(w_ns))
            tc_r = _lxml_et.SubElement(tc_p, "{0}r".format(w_ns))
            tc_t = _lxml_et.SubElement(tc_r, "{0}t".format(w_ns))
            tc_t.text = f"Insert screenshot: {name} ({path})"

            parent_elem.insert(idx_in_parent, tbl_el)

    # Save final docx.
    doc.save(OUTPUT_DOCX)

    # ---- Resize oversized images to fit A4 printable area ----
    # Modify OUTPUT_DOCX directly as a ZIP after python-docx has saved it.
    # This avoids the problem of python-docx re-serializing from its internal model.
    import xml.etree.ElementTree as _ET2
    MAX_W_IN = 6.0
    MAX_H_IN = 7.8
    EMU_PER_INCH = 914400

    resize_dir = _tempfile.mkdtemp(dir=BUILD_DIR, prefix="_resize_final_")
    try:
        with zipfile.ZipFile(OUTPUT_DOCX) as zf_in:
            zf_in.extractall(resize_dir)
        doc_xml_path = os.path.join(resize_dir, "word", "document.xml")
        tree = _ET2.parse(doc_xml_path)
        root = tree.getroot()
        resized_count = 0
        for elem in list(root.iter()):
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            # Match both 'a:ext' and 'wp:extent' (both control image size)
            if tag in ("ext", "extent"):
                cx = int(elem.get("cx", 0)) / EMU_PER_INCH
                cy = int(elem.get("cy", 0)) / EMU_PER_INCH
                scale = min(1.0, MAX_W_IN / max(cx, 0.01), MAX_H_IN / max(cy, 0.01))
                if scale < 1.0:
                    elem.set("cx", str(int(cx * scale * EMU_PER_INCH)))
                    elem.set("cy", str(int(cy * scale * EMU_PER_INCH)))
                    resized_count += 1
        tree.write(doc_xml_path)
        # Rebuild the docx zip from modified files.
        with zipfile.ZipFile(OUTPUT_DOCX, "w") as zf_out:
            for root_dir, dirs, files in os.walk(resize_dir):
                for fname in sorted(files):
                    full = os.path.join(root_dir, fname)
                    arcname = os.path.relpath(full, resize_dir)
                    zf_out.write(full, arcname)
        print(f"[C] Resized {resized_count} image extents to fit A4")
    finally:
        shutil.rmtree(resize_dir, ignore_errors=True)

    # Set updateFields in settings.xml (must be after python-docx writes).
    _set_update_fields(OUTPUT_DOCX)

    print(f"[C] Final docx → {OUTPUT_DOCX} ({os.path.getsize(OUTPUT_DOCX):,} bytes)")


# ---------------------------------------------------------------------------
# Step D — verification
# ---------------------------------------------------------------------------

def verify():
    """Run checks and report results."""
    from docx import Document
    import tempfile as _tempfile

    print("\n=== VERIFICATION ===")

    # 1. Docx opens without error.
    try:
        doc = Document(OUTPUT_DOCX)
        print("[PASS] docx opens without error")
    except Exception as e:
        print(f"[FAIL] docx open error: {e}")
        return False

    # 2. Count inline images via relationships.
    img_count = sum(1 for rel in doc.part.rels.values() if "image" in str(rel.reltype))
    existing_ss = len(_glob.glob(os.path.join(REPO_ROOT, "docs/screenshots/*.png")))
    expected_images = 10 + existing_ss
    print(f"[INFO] Images: {img_count} (expected ~{expected_images})")

    # 3. Count Heading 1 paragraphs — compute true expected from markdown H1 lines.
    h1_count = sum(1 for p in doc.paragraphs if p.style.name == "Heading 1")
    with open(INPUT_MD) as f:
        md_lines = f.readlines()
    # All top-level headings (lines starting with exactly one '# ' at column 0).
    # Exclude any inside code blocks.
    in_code_block = False
    md_h1_total = 0
    for l in md_lines:
        if l.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if _re.match(r'^# ', l):
            md_h1_total += 1
    # Subtract title page heading and Table of Contents heading.
    expected_h1_from_md = md_h1_total - 2   # exclude title + TOC headings
    print(f"[INFO] Heading 1 count: {h1_count} (expected ~{expected_h1_from_md})")

    # 4. Check TOC field instruction in document XML.
    body_xml = str(doc.element.body.xml)
    has_toc = 'TOC \\o' in body_xml or '\\o "1-2"' in body_xml
    print(f"[{'PASS' if has_toc else 'FAIL'}] TOC field {'found' if has_toc else 'NOT found'}")

    # 5. Check footer PAGE field.
    footer_has_page = False
    for section in doc.sections:
        footer_xml = str(section.footer._element.xml)
        if "PAGE" in footer_xml and "fldChar" in footer_xml:
            footer_has_page = True
            break
    print(f"[{'PASS' if footer_has_page else 'FAIL'}] Footer PAGE field {'found' if footer_has_page else 'NOT found'}")

    # 6. Check updateFields setting in settings.xml inside the docx zip.
    with zipfile.ZipFile(OUTPUT_DOCX) as zf:
        for name in zf.namelist():
            if "settings.xml" in name and "_rels" not in name:
                content = zf.read(name).decode()
                has_update = "updateFields" in content and 'val="true"' in content
                print(f"[{'PASS' if has_update else 'FAIL'}] updateFields {'set' if has_update else 'NOT set'}")

    # 7. git status — only scripts/build_report_docx.py should be new; build/ not tracked.
    result = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True, cwd=REPO_ROOT,
    )
    new_files = [l for l in result.stdout.strip().split("\n") if l.startswith("??")]
    build_new = any(f.startswith("build/") for f in new_files)
    print(f"[{'PASS' if not build_new else 'WARN'}] git status — {'no build/ files staged (OK)' if not build_new else 'build/ has untracked files (expected, git-ignored)'}")
    for f in new_files:
        print(f"       + {f}")

    # 8. LibreOffice check (optional).
    has_lo = shutil.which("soffice") is not None
    if has_lo:
        try:
            env = os.environ.copy()
            env.pop("DISPLAY", None)
            r = subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf",
                 "--outdir", BUILD_DIR, OUTPUT_DOCX],
                capture_output=True, text=True, timeout=120, env=env,
            )
            if r.returncode == 0:
                pdf_path = os.path.join(BUILD_DIR, "Project_Report.pdf")
                if os.path.exists(pdf_path):
                    try:
                        from pypdf import PdfReader
                        pages = len(PdfReader(pdf_path).pages)
                        print(f"[INFO] PDF: {pdf_path} ({pages} pages)")
                        # Render a few sample pages to PNG for visual check.
                        try:
                            from pypdf import PdfReader as PR2
                            import subprocess as _subp
                            reader = PR2(pdf_path)
                            sample_pages = [0]  # page 1 (title)
                            if len(reader.pages) > 5:
                                sample_pages.append(6)  # Use Case diagram (~page 7)
                            if len(reader.pages) > 12:
                                sample_pages.append(12)  # Sequence diagram
                            if len(reader.pages) > 15:
                                sample_pages.append(15)  # Activity diagram
                            if len(reader.pages) > 30:
                                sample_pages.append(30)  # First screenshot frame
                            for pg in sample_pages:
                                png_path = os.path.join(BUILD_DIR, f"check_page_{pg+1}.png")
                                _subp.run([
                                    "pdftoppm", "-r", "80", "-png",
                                    pdf_path, png_path.replace(".png", ""),
                                ], capture_output=True)
                                if os.path.exists(png_path):
                                    sz = os.path.getsize(png_path)
                                    print(f"       Rendered page {pg+1} → {sz} bytes (OK)")
                                else:
                                    print(f"       [WARN] pdftoppm did not produce page {pg+1}")
                        except Exception as e2:
                            print(f"       [WARN] Page rendering skipped: {e2}")
                    except ImportError:
                        print("[WARN] pypdf not installed — skipped page count")
                else:
                    print(f"[FAIL] PDF not created: {r.stderr[:200]}")
            else:
                print(f"[FAIL] LO conversion: {r.stderr[:200]}")
        except Exception as e:
            print(f"[WARN] LO exception: {e}")
    else:
        print("[INFO] LibreOffice not found — skipping PDF conversion and page rendering")

    return True


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup():
    """Remove temp files, keep OUTPUT_DOCX."""
    for path in [PREPROC_MD, REF_DOCX, RAW_DOCX]:
        if os.path.exists(path):
            os.remove(path)
            print(f"[CLEANUP] Removed {path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    os.makedirs(BUILD_DIR, exist_ok=True)

    print("=" * 60)
    print("Report DOCX Builder")
    print(f"  Input:   {INPUT_MD}")
    print(f"  Output:  {OUTPUT_DOCX}")
    print("=" * 60)

    preprocess_markdown()     # Step A
    generate_reference_docx() # Part of B — reference docx with styles
    run_pandoc()              # Step B — pandoc conversion
    post_process()            # Step C — python-docx polish
    verify()                  # Step D — verification checks
    cleanup()                 # Remove temp files

    print("\n" + "=" * 60)
    size = os.path.getsize(OUTPUT_DOCX)
    print(f"Done! {OUTPUT_DOCX} ({size:,} bytes / {size/1024:.1f} KB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
