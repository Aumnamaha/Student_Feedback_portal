#!/usr/bin/env python3
"""Generate build/Project_Report.docx from Project_Report.md.

Usage (from repo root):
    source build/.venv/bin/activate     # activate venv
    python scripts/build_report_docx.py # generate docx
"""

import os, shutil, subprocess, sys, re as _re, glob as _glob, zipfile
from io import BytesIO
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

    # (d) Screenshot placeholders after the Chapter 19.4 table ENDS.
    #     Strategy: collect all lines of the screenshot table verbatim, then
    #     insert frames immediately after the last data row.
    lines = content.split("\n")
    new_lines = []
    past_194_table = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not past_194_table:
            # Look for the start of Chapter 19.4 Screenshots Placeholder section
            if "## 19.4 Screenshots Placeholder" in line:
                new_lines.append(line)
                i += 1
                continue

            # If we're inside a table (lines starting with |), collect them all
            if stripped.startswith("|"):
                # Append this row and keep collecting until non-table line
                new_lines.append(line)
                i += 1
                continue

            # Non-table, non-heading content before 19.4 → just append
            new_lines.append(line)
            i += 1
            continue

        # past_194_table is True — append all remaining lines.
        new_lines.append(line)
        i += 1

    content = "\n".join(new_lines)

    # --- Now insert screenshot frames AFTER the 19.4 table ONLY ---
    lines2 = content.split("\n")
    new_lines2 = []
    in_194_section = False
    inside_194_table = False
    for j, line in enumerate(lines2):
        stripped = line.strip()

        if "## 19.4 Screenshots Placeholder" in line:
            # Start of the screenshot section — begin tracking table rows.
            in_194_section = True
            inside_194_table = False
            new_lines2.append(line)
            continue

        if in_194_section and stripped.startswith("|"):
            # Inside the 19.4 section's table — keep collecting rows.
            inside_194_table = True
            new_lines2.append(line)
            continue

        # Non-table line after being inside the 19.4 table → insert frames now.
        if in_194_section and inside_194_table:
            for idx, (name, path) in enumerate(SCREENSHOT_ROWS, 1):
                caption = f"*Figure 19.{idx}: {name}*"
                full_path = os.path.join(REPO_ROOT, path)
                if os.path.exists(full_path):
                    new_lines2.append("")
                    new_lines2.append(caption)
                    new_lines2.append(
                        f'![Figure 19.{idx}: {name}]({path}){{width=6.0in}}'
                    )
                else:
                    new_lines2.append("")
                    new_lines2.append(caption)
                    new_lines2.append(
                        '```{=openxml}\n'
                        f'<w:p><w:r><w:t>Insert screenshot: {name} ({path})</w:t></w:r></w:p>\n'
                        '```\n'
                    )
            in_194_section = False
            inside_194_table = False

        new_lines2.append(line)

    content = "\n".join(new_lines2)

    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(PREPROC_MD, "w") as f:
        f.write(content)
    print(f"[A] Preprocessed markdown → {PREPROC_MD} ({os.path.getsize(PREPROC_MD)} bytes)")


# ---------------------------------------------------------------------------
# Reference docx generator — from PANDOC's bundled default, then modify styles
# ---------------------------------------------------------------------------

def generate_reference_docx():
    """Create reference.docx from pandoc's bundled default data file."""
    import pypandoc
    from lxml import etree as _lxml_et

    pandoc_path = pypandoc.get_pandoc_path()
    cmd = [pandoc_path, "-o", REF_DOCX, "--print-default-data-file=reference.docx"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[B] pandoc --print-default-data-file failed: {r.stderr}")
        sys.exit(1)

    # Now open the generated docx with python-docx and modify styles in place.
    from docx import Document
    from docx.shared import Pt, Cm, Inches as D_Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document(REF_DOCX)

    # Page setup: A4 (210×297 mm), 1-inch margins.
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    for margin_name in ("top", "bottom", "left", "right"):
        setattr(section, f"{margin_name}_margin", D_Inches(1))

    # ---- Modify body styles via python-docx ----
    def _set_body_style(style_name, size_pt, bold=False, italic=False,
                       alignment=None, space_after_pt=6, line_spacing=1.15):
        """Set font/size/bold/italic/alignment/space-after for a style."""
        try:
            sty = doc.styles[style_name]
        except KeyError:
            return  # Style doesn't exist — skip.

        fnt = sty.font
        fnt.name = "Times New Roman"
        fnt.size = Pt(size_pt)
        if bold is not None:
            fnt.bold = bold
        if italic is not None:
            fnt.italic = italic

        pf = sty.paragraph_format
        if alignment is not None:
            pf.alignment = alignment
        pf.line_spacing = line_spacing
        pf.space_after = Pt(space_after_pt)

    _set_body_style("Normal", 12, bold=False, italic=False,
                    alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after_pt=6)
    _set_body_style("Body Text", 12, bold=False, italic=False,
                    alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after_pt=6)
    _set_body_style("First Paragraph", 12, bold=False, italic=False,
                    alignment=WD_ALIGN_PARAGRAPH.JUSTIFY, space_after_pt=0)
    _set_body_style("Compact", 10.5, bold=False, italic=False,
                    alignment=WD_ALIGN_PARAGRAPH.LEFT, space_after_pt=2)

    # ---- Heading styles ----
    def _set_heading(level, size_pt, bold=True, page_break_before=False):
        try:
            sty = doc.styles[f"Heading {level}"]
        except KeyError:
            return
        fnt = sty.font
        fnt.name = "Times New Roman"
        fnt.size = Pt(size_pt)
        fnt.bold = bold
        pf = sty.paragraph_format
        if page_break_before:
            pf.page_break_before = True

    _set_heading(1, 16, bold=True, page_break_before=True)
    _set_heading(2, 14, bold=True, page_break_before=False)
    _set_heading(3, 12, bold=True, page_break_before=False)
    _set_heading(4, 12, bold=True, page_break_before=False)

    # Title style.
    try:
        title_style = doc.styles["Title"]
    except KeyError:
        from docx.enum.style import WD_STYLE_TYPE
        title_style = doc.styles.add_style("Title", WD_STYLE_TYPE.PARAGRAPH)
    tf = title_style.font
    tf.name = "Times New Roman"
    tf.size = Pt(24)
    tf.bold = True
    tp = title_style.paragraph_format
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Source Code / Verbatim Char.
    try:
        code_style = doc.styles["Source Code"]
    except KeyError:
        from docx.enum.style import WD_STYLE_TYPE
        code_style = doc.styles.add_style("Source Code", WD_STYLE_TYPE.PARAGRAPH)
    cf = code_style.font
    cf.name = "Courier New"
    cf.size = Pt(9)

    # Caption / Image Caption / Captioned Figure.
    for cap_name in ("Caption", "Image Caption", "Captioned Figure"):
        try:
            sty = doc.styles[cap_name]
        except KeyError:
            continue
        fnt = sty.font
        fnt.name = "Times New Roman"
        fnt.size = Pt(10)
        fnt.italic = True
        pf = sty.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---- Remove theme attributes from styles.xml via lxml ----
    # This MUST happen after python-docx has opened/saved the file, because
    # python-docx may have added its own elements.  We edit the raw XML of
    # word/styles.xml in-place using lxml (preserves prefixes).

    import xml.etree.ElementTree as _ET2

    tmp_dir = _tempfile.mkdtemp(dir=BUILD_DIR, prefix="_styles_tmp_")
    try:
        with zipfile.ZipFile(REF_DOCX) as zf_in:
            zf_in.extractall(tmp_dir)
        styles_path = os.path.join(tmp_dir, "word", "styles.xml")

        tree = _lxml_et.parse(styles_path)
        root = tree.getroot()

        # --- Namespace helpers (Clark notation with curly braces) ---
        NS  = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        VAL = NS + "val"   # attribute key for w:val

        def _tag(name):
            """Return Clark-notation tag string."""
            return NS + name

        def _get_val(el, default=None):
            """Get the w:val attribute from an element."""
            return el.get(VAL, default)

        # ---- Step 1 — strip theme attrs from ALL rFonts ----
        for rfonts in root.iter(_tag("rFonts")):
            for attr in ("asciiTheme", "hAnsiTheme",
                         "eastAsiaTheme", "cstheme"):
                key = NS + attr
                if key in rfonts.attrib:
                    del rfonts.attrib[key]

        # ---- Step 2 — strip theme attrs from ALL w:color; force black ----
        for color_el in root.iter(_tag("color")):
            for attr in ("themeColor", "themeShade", "themeTint"):
                key = NS + attr
                if key in color_el.attrib:
                    del color_el.attrib[key]
            color_el.set(VAL, "000000")

        # ---- Step 3 — comprehensive heading style fix ----
        H1_SPEC = {"sz": "32", "bold": True, "page_break_before": True,
                   "space_before": "0", "space_after": "240"}
        H2_SPEC = {"sz": "28", "bold": True, "space_before": "240",
                   "space_after": "120"}
        H3_SPEC = {"sz": "24", "bold": True, "space_before": "200",
                   "space_after": "80"}
        H4_SPEC = {"sz": "24", "bold": True, "italic": True}
        TITLE_SPEC = {"sz": "48", "bold": True}

        spec_map = {
            "heading 1": H1_SPEC,
            "heading 2": H2_SPEC,
            "heading 3": H3_SPEC,
            "heading 4": H4_SPEC,
            "title": TITLE_SPEC,
        }

        # Helper: find direct child by local name (no namespace prefix bug).
        def _child(parent, local_name):
            for c in parent:
                cl = c.tag.split("}")[-1] if "}" in c.tag else c.tag
                if cl == local_name:
                    return c
            return None

        # Helper: find rPr — check style-level first, then docDefaults.
        def _find_rpr(style_elem):
            rp = _child(style_elem, "rPr")
            if rp is not None:
                return rp
            rpd = _child(style_elem, "rPrDefault")
            if rpd is not None:
                return _child(rpd, "rPr")
            return None

        # Helper: insert element before a reference sibling.
        def _insert_before(parent, new_el, ref_el):
            siblings = list(parent)
            idx = siblings.index(ref_el) if ref_el in siblings else len(siblings)
            parent.insert(idx, new_el)

        for style_elem in root.iter(_tag("style")):
            name_el = _child(style_elem, "name")
            if name_el is None:
                continue
            sname = _get_val(name_el, "")
            spec  = spec_map.get(sname.lower())

            rp = _find_rpr(style_elem)

            # --- Body styles: size only (theme attrs already stripped) ---
            if sname in ("Normal", "Body Text") and rp is not None:
                for sz_el in rp.iter(_tag("sz")):
                    sz_el.set(VAL, "24")
                for szcs_el in rp.iter(_tag("szCs")):
                    szcs_el.set(VAL, "24")
            elif sname == "Compact" and rp is not None:
                for sz_el in rp.iter(_tag("sz")):
                    sz_el.set(VAL, "21")
                for szcs_el in rp.iter(_tag("szCs")):
                    szcs_el.set(VAL, "21")
            elif sname == "Source Code" and rp is not None:
                for sz_el in rp.iter(_tag("sz")):
                    sz_el.set(VAL, "18")
                for szcs_el in rp.iter(_tag("szCs")):
                    szcs_el.set(VAL, "18")
            elif sname in ("Caption", "Image Caption",
                           "Captioned Figure") and rp is not None:
                for sz_el in rp.iter(_tag("sz")):
                    sz_el.set(VAL, "20")
                for szcs_el in rp.iter(_tag("szCs")):
                    szcs_el.set(VAL, "20")
            elif sname == "Table" and rp is not None:
                for sz_el in rp.iter(_tag("sz")):
                    sz_el.set(VAL, "24")
                for szcs_el in rp.iter(_tag("szCs")):
                    szcs_el.set(VAL, "24")

            # --- Heading / Title styles: full formatting fix ---
            elif spec is not None and rp is not None:
                # (a) Explicit w:rFonts with Times New Roman.
                rfonts = _child(rp, "rFonts")
                if rfonts is None:
                    sz_el = _child(rp, "sz")
                    before = sz_el if sz_el is not None else (
                        rp[0] if len(rp) > 0 else None)
                    rfonts = _lxml_et.SubElement(
                        rp, _tag("rFonts"),
                        {NS + "ascii": "Times New Roman",
                         NS + "hAnsi": "Times New Roman",
                         NS + "cs": "Times New Roman",
                         NS + "eastAsia": "Times New Roman"})
                    if before:
                        _insert_before(rp, rfonts, before)
                else:
                    for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
                        rfonts.set(NS + attr, "Times New Roman")
                    for tattr in ("asciiTheme", "hAnsiTheme",
                                  "eastAsiaTheme", "cstheme"):
                        key = NS + tattr
                        if key in rfonts.attrib:
                            del rfonts.attrib[key]

                # (b) Bold element.
                if spec["bold"] and _child(rp, "b") is None:
                    sz_el = _child(rp, "sz")
                    before = sz_el if sz_el is not None else (
                        rp[0] if len(rp) > 0 else None)
                    b_el = _lxml_et.SubElement(rp, _tag("b"))
                    if before is not None:
                        _insert_before(rp, b_el, before)

                # (c) Italic element (Heading 4).
                if spec.get("italic") and _child(rp, "i") is None:
                    sz_el = _child(rp, "sz")
                    before = sz_el if sz_el is not None else (
                        rp[0] if len(rp) > 0 else None)
                    i_el = _lxml_et.SubElement(rp, _tag("i"))
                    if before is not None:
                        _insert_before(rp, i_el, before)

                # (d) Size and szCs.
                for sz_el in rp.iter(_tag("sz")):
                    sz_el.set(VAL, spec["sz"])
                for szcs_el in rp.iter(_tag("szCs")):
                    szcs_el.set(VAL, spec["sz"])

                # (e) Black colour.
                has_color = False
                for color_el in rp.iter(_tag("color")):
                    has_color = True
                    for attr in ("themeColor", "themeShade", "themeTint"):
                        key = NS + attr
                        if key in color_el.attrib:
                            del color_el.attrib[key]
                    color_el.set(VAL, "000000")
                if not has_color:
                    sz_el = _child(rp, "sz")
                    before = sz_el if sz_el is not None else (
                        rp[0] if len(rp) > 0 else None)
                    color_el = _lxml_et.SubElement(
                        rp, _tag("color"), {VAL: "000000"})
                    if before is not None:
                        _insert_before(rp, color_el, before)

                # (f) pPr — pageBreakBefore and spacing.
                pp = _child(style_elem, "pPr")
                needs_pp = (spec.get("page_break_before")
                            or spec.get("space_before") is not None
                            or spec.get("space_after") is not None)
                if needs_pp:
                    if pp is None:
                        # Insert pPr right after the name element.
                        children = list(style_elem)
                        for i, ch in enumerate(children):
                            cl = (ch.tag.split("}")[-1]
                                  if "}" in ch.tag else ch.tag)
                            if cl == "name":
                                pp = _lxml_et.SubElement(
                                    style_elem, _tag("pPr"),
                                    {NS + "docId": "0D51A601"})
                                style_elem.remove(ch)
                                style_elem.insert(i + 1, pp)
                                break
                        if pp is None:
                            pp = _lxml_et.SubElement(
                                style_elem, _tag("pPr"),
                                {NS + "docId": "0D51A601"})

                    # pageBreakBefore for Heading 1.
                    if spec.get("page_break_before"):
                        if _child(pp, "pageBreakBefore") is None:
                            _lxml_et.SubElement(pp, _tag("pageBreakBefore"))

                    # Spacing before / after (val in twentieths of a point).
                    # In DOCX these are ATTRIBUTES on the <spacing> element,
                    # not child elements.
                    spc = _child(pp, "spacing")
                    if spc is None:
                        spc = _lxml_et.SubElement(pp, _tag("spacing"))
                    for attr_name in ("before", "after"):
                        spec_key = f"space_{attr_name}"
                        val_str = spec.get(spec_key)
                        if val_str is not None:
                            spc.set(NS + attr_name, str(int(val_str)))

                    # Remove semiHidden / unhideWhenUsed from Heading 2.
                    if sname.lower() == "heading 2":
                        for attr_name in ("semiHidden", "unhideWhenUsed"):
                            el = _child(pp, attr_name)
                            if el is not None:
                                pp.remove(el)

        # 4. (redundant — step 2 already forced all colours to black)

        # 5. Table style — add visible borders (w:tblBorders).
        for style_elem in root.iter(_tag("style")):
            name_el = _child(style_elem, "name")
            if name_el is None:
                continue
            sname = _get_val(name_el, "")
            if sname == "Table":
                tblPr = _child(style_elem, "tblPr")
                if tblPr is None:
                    tblPr = _lxml_et.SubElement(style_elem, _tag("tblPr"))

                for old_borders in list(tblPr.iter(_tag("tblBorders"))):
                    tblPr.remove(old_borders)

                borders = _lxml_et.SubElement(tblPr, _tag("tblBorders"))
                for edge in ("top", "left", "bottom",
                             "right", "insideH", "insideV"):
                    _lxml_et.SubElement(
                        borders, _tag(edge),
                        {VAL: "single",
                         NS + "sz": "4",
                         NS + "space": "0",
                         NS + "color": "808080"},
                    )

                tblW = _child(tblPr, "tblW")
                if tblW is None:
                    tblW = _lxml_et.SubElement(tblPr, _tag("tblW"))
                tblW.set(NS + "type", "auto")

        tree.write(styles_path, xml_declaration=True, encoding="UTF-8", standalone=True)

        # Rebuild the reference docx zip.
        with zipfile.ZipFile(REF_DOCX, "w") as zf_out:
            for root_dir, dirs, files in os.walk(tmp_dir):
                for fname in sorted(files):
                    full = os.path.join(root_dir, fname)
                    arcname = os.path.relpath(full, tmp_dir)
                    zf_out.write(full, arcname)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

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
# Step C — post-process with python-docx / lxml only (no ElementTree on document.xml)
# ---------------------------------------------------------------------------

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _set_update_fields(docx_path):
    """Set w:updateFields w:val=\"true\" in word/settings.xml using lxml."""
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    tmp_dir = None
    try:
        from lxml import etree as _lxml_et
        tmp_dir = _tempfile.mkdtemp(dir=BUILD_DIR, prefix="_uf_tmp_")
        with zipfile.ZipFile(docx_path) as zf:
            zf.extractall(tmp_dir)
        settings_path = os.path.join(tmp_dir, "word", "settings.xml")
        if not os.path.exists(settings_path):
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            # Create minimal settings element.
            root_el = _lxml_et.Element(f"{{{ns_w}}}settings")
            tree = _lxml_et.ElementTree(root_el)
            tree.write(settings_path, xml_declaration=True, encoding="UTF-8", standalone=True)

        tree = _lxml_et.parse(settings_path)
        root = tree.getroot()
        tag_local = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        if tag_local != "settings":
            new_root = _lxml_et.Element(f"{{{ns_w}}}settings")
            for child in list(root):
                new_root.append(child)
            root = new_root

        uf_found = False
        for child in root:
            gtag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if gtag == "updateFields":
                child.set(f"{{{ns_w}}}val", "true")
                uf_found = True
        if not uf_found:
            _lxml_et.SubElement(root, f"{{{ns_w}}}updateFields").set(
                f"{{{ns_w}}}val", "true",
            )

        tree.write(settings_path, xml_declaration=True, encoding="UTF-8", standalone=True)

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
    from docx.shared import Pt, Inches as D_Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from lxml import etree as _lxml_et

    doc = Document(RAW_DOCX)
    w_ns = W_NS

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
            ns_xml = "{http://www.w3.org/XML/1998/namespace}space"

            # Run 0: fldChar begin
            r1 = p.add_run()
            _lxml_et.SubElement(r1._element, f"{w_ns}fldChar",
                                {f"{w_ns}fldCharType": "begin"})
            # Run 1: instrText
            r2 = p.add_run()
            _lxml_et.SubElement(
                r2._element, f"{w_ns}instrText", {ns_xml: "preserve"}).text = 'TOC \\o "1-2" \\h \\z \\u'
            # Run 2: fldChar separate
            r3 = p.add_run()
            _lxml_et.SubElement(r3._element, f"{w_ns}fldChar",
                                {f"{w_ns}fldCharType": "separate"})
            # Run 3: placeholder text
            r4 = p.add_run()
            r4.text = "Right-click here and choose Update Field to build the table of contents."
            # Run 4: fldChar end
            r5 = p.add_run()
            _lxml_et.SubElement(r5._element, f"{w_ns}fldChar",
                                {f"{w_ns}fldCharType": "end"})

    VAL = w_ns + "val"  # attribute key for w:val

    def _is_pagebreak_only_para(p_elem):
        """Check if a paragraph element contains ONLY break elements (page-breaks,
        line-breaks) with no text.  Used to remove explicit page-break divs that
        are redundant because Heading 1 / TOC Heading styles carry pageBreakBefore."""
        # Check for any text content.
        for t_el in p_elem.iter(f"{w_ns}t"):
            if t_el.text and t_el.text.strip():
                return False
        # Must contain at least one page break to be removed.
        has_page_break = False
        for child in p_elem:
            tag_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag_local == "r":
                for subchild in child:
                    sub_local = (subchild.tag.split("}")[-1]
                                 if "}" in subchild.tag else subchild.tag)
                    if (sub_local == "br"
                            and subchild.get(f"{{{w_ns}}}type") == "page"):
                        has_page_break = True
        return has_page_break

    def _is_empty_para(p_elem):
        """Check if a paragraph has no text content at all."""
        for t_el in p_elem.iter(f"{w_ns}t"):
            if t_el.text and t_el.text.strip():
                return False
        # Also check for non-text elements (images, tables etc).
        for child in p_elem:
            tag_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag_local not in ("r",):
                return False  # has an image/table/etc — not empty
        return True

    # ---- (c) Create "TOC Heading" style and apply to Table of Contents
    #         heading so the TOC does not list itself.
    try:
        toc_sty = doc.styles["TOC Heading"]
    except KeyError:
        from docx.enum.style import WD_STYLE_TYPE as WST
        h1_sty = doc.styles["Heading 1"]
        toc_sty = doc.styles.add_style("TOC Heading", WST.PARAGRAPH)
        tf = toc_sty.font
        tf.name = "Times New Roman"
        tf.size = Pt(16)
        tf.bold = True
        tp = toc_sty.paragraph_format
        tp.page_break_before = True
        tp.space_after = Pt(240 / 20)  # 240 twentieths of a point ≈ 12 pt
    
    # Apply "TOC Heading" to the "Table of Contents" paragraph.
    toc_para = None
    for p in doc.paragraphs:
        text = "".join(run.text for run in p.runs).strip()
        if text == "Table of Contents":
            toc_para = p
            break
    if toc_para is not None:
        try:
            toc_para.style = toc_sty
        except KeyError:
            pass  # style may have been removed — harmless.

    # Remove explicit page-break-only paragraphs (<w:br w:type="page"/>).
    # These are redundant because Heading 1 / TOC Heading / Title already
    # carry <w:pageBreakBefore/> in their styles, and pandoc inserts them
    # from the markdown div blocks.  Keep only breaks that share a run with
    # text (inline page breaks) — those must stay.
    body = doc.element.body
    new_body_elems = []
    for p_elem in list(body):
        if _is_pagebreak_only_para(p_elem):
            continue  # skip this explicit break paragraph
        new_body_elems.append(p_elem)
    # Also strip empty paragraphs that directly follow a removed page-break.
    final_elems = []
    prev_was_removed_pb = False
    for pe in new_body_elems:
        if prev_was_removed_pb and _is_empty_para(pe):
            prev_was_removed_pb = False  # skip this empty para too
        else:
            final_elems.append(pe)
            prev_was_removed_pb = False
    # Rebuild body.
    for old in list(body):
        body.remove(old)
    for pe in final_elems:
        body.append(pe)

    # ---- (d) Footer with centered PAGE field on all sections ----
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        if not footer.paragraphs:
            fp = footer.add_paragraph()
        else:
            fp = footer.paragraphs[0]
        # Clear existing runs.
        for run in list(fp.runs):
            run.text = ""

        # Build the PAGE field using lxml — each fldChar/instrText must be
        # inside its own <w:r> run element.  Directly appending to fp._element
        # without wrapping in runs gets stripped by python-docx on save.
        ns_w = w_ns
        ns_xml = "{http://www.w3.org/XML/1998/namespace}space"

        # Run 0: fldChar begin
        r_begin = fp.add_run()
        _lxml_et.SubElement(r_begin._element, f"{ns_w}fldChar",
                            {f"{ns_w}fldCharType": "begin"})

        # Run 1: instrText with field code
        r_instr_text = fp.add_run()
        _lxml_et.SubElement(
            r_instr_text._element, f"{ns_w}instrText",
            {ns_xml: "preserve"}).text = " PAGE "

        # Run 2: fldChar separate (starts the result portion)
        r_sep = fp.add_run()
        _lxml_et.SubElement(r_sep._element, f"{ns_w}fldChar",
                            {f"{ns_w}fldCharType": "separate"})

        # Run 3: displayed value placeholder
        r_val = fp.add_run()
        r_val.text = "1"

        # Run 4: fldChar end
        r_end = fp.add_run()
        _lxml_et.SubElement(r_end._element, f"{ns_w}fldChar",
                            {f"{ns_w}fldCharType": "end"})

        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Ensure A4 page setup with 1-inch margins.
    section = doc.sections[0]
    if not section.page_width:
        section.page_width = D_Inches(8.267)  # ~21cm
    if not section.page_height:
        section.page_height = D_Inches(11.693)  # ~29.7cm
    for margin_name in ("top", "bottom", "left", "right"):
        if getattr(section, f"{margin_name}_margin") is None:
            setattr(section, f"{margin_name}_margin", D_Inches(1))

    # ---- (d) Table formatting ----
    page_width = doc.sections[0].page_width.inches
    left_m = doc.sections[0].left_margin.inches
    right_m = doc.sections[0].right_margin.inches
    max_width_emu = int((page_width - left_m - right_m) * 914400)

    for table in doc.tables:
        tbl = table._element
        tblPr = tbl.find(f"{w_ns}tblPr")
        if tblPr is None:
            tblPr = _lxml_et.SubElement(tbl, f"{{{w_ns}}}tblPr")

        # Set total width to 9026 twips (A4 minus margins).
        tw = tblPr.find(f"{w_ns}tblW")
        if tw is not None:
            tw.set("{0}type".format(w_ns), "dxa")
            tw.set("{0}w".format(w_ns), str(max_width_emu))
        else:
            _lxml_et.SubElement(
                tblPr, f"{{{w_ns}}}tblW",
                {"{0}type".format(w_ns): "dxa", "{0}w".format(w_ns): str(max_width_emu)},
            )

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
        insert_screenshot_para = None
        for p in doc.paragraphs:
            text = "".join(run.text for run in p.runs)
            if placeholder_text == text.strip():
                target_para = p
            # Also track the "Insert screenshot:" paragraph that follows.
            if "Insert screenshot: " + name in text:
                insert_screenshot_para = p

        if target_para is None:
            # Caption was italicized by pandoc (asterisks stripped).
            fig_pattern = _re.compile(rf"Figure 19\.{idx}:")
            found = False
            for p in doc.paragraphs:
                text = "".join(run.text for run in p.runs)
                if fig_pattern.search(text):
                    target_para = p
                    found = True
                    break
            # Also find the Insert screenshot paragraph.
            if insert_screenshot_para is None and not found:
                print(f"  [C] Warning: no paragraphs found for screenshot frame {idx}")
                continue
            elif not found:
                continue

        parent_elem = target_para._element.getparent()
        idx_in_parent = list(parent_elem).index(target_para._element)

        # Remove the placeholder caption paragraph.
        parent_elem.remove(target_para._element)

        # Also remove the "Insert screenshot:" openxml paragraph that pandoc
        # generated from the ```{=openxml} block.  It's a sibling of the
        # removed paragraph.
        if insert_screenshot_para is not None:
            ins_parent = insert_screenshot_para._element.getparent()
            ins_idx = list(ins_parent).index(insert_screenshot_para._element)
            ins_parent.remove(insert_screenshot_para._element)

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
                .format(w_ns), {"{0}type".format(w_ns): "dxa", "{0}w".format(w_ns): str(max_width_emu)},
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

            # Single-cell row — 3 inches tall (3 * 1440 = 4320 twips).
            tr = _lxml_et.SubElement(tbl_el, "{0}tr".format(w_ns))
            trPr = _lxml_et.SubElement(tr, "{0}trPr".format(w_ns))
            _lxml_et.SubElement(
                trPr, "{0}trHeight"
                .format(w_ns),
                {"{0}val".format(w_ns): str(int(3 * 1440)),
                 "{0}hRule".format(w_ns): "exact"},
            )

            tc = _lxml_et.SubElement(tr, "{0}tc".format(w_ns))
            tcPr = _lxml_et.SubElement(tc, "{0}tcPr".format(w_ns))
            # Cell margins 80 twips.
            tcPr.set("{0}marLeft".format(w_ns), str(80))
            tcPr.set("{0}marRight".format(w_ns), str(80))
            tcPr.set("{0}marTop".format(w_ns), str(80))
            tcPr.set("{0}marBottom".format(w_ns), str(80))

            _lxml_et.SubElement(
                tcPr, "{0}vAlign"
                .format(w_ns), {"{0}val".format(w_ns): "center"},
            )
            # Cell shading.
            shd2 = _lxml_et.SubElement(tcPr, "{0}shd".format(w_ns))
            shd2.set("{0}fill".format(w_ns), "F2F2F2")
            shd2.set("{0}val".format(w_ns), "clear")

            tcBody = _lxml_et.SubElement(tc, "{0}tcBody".format(w_ns))
            tc_p = _lxml_et.SubElement(tcBody, "{0}p".format(w_ns))
            tc_r = _lxml_et.SubElement(tc_p, "{0}r".format(w_ns))
            tc_t = _lxml_et.SubElement(tc_r, "{0}t".format(w_ns))
            tc_t.text = f"Insert screenshot: {name} ({path})"

            parent_elem.insert(idx_in_parent, tbl_el)

    # Save final docx.
    doc.save(OUTPUT_DOCX)

    # ---- (e) Remove explicit page-break-only paragraphs via lxml pass ----
    # python-docx's internal state may not reflect lxml body edits made
    # before save.  Do this as a post-save XML pass on document.xml.
    _pb_dir = _tempfile.mkdtemp(dir=BUILD_DIR, prefix="_pbfix_")
    try:
        with zipfile.ZipFile(OUTPUT_DOCX) as zf_in:
            zf_in.extractall(_pb_dir)
        doc_xml_path = os.path.join(_pb_dir, "word", "document.xml")
        tree_pb = _lxml_et.parse(doc_xml_path)
        root_pb = tree_pb.getroot()
        ns_w_pb = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

        def _tag_pb(name):
            return f"{{{ns_w_pb}}}{name}"

        VAL_PB = f"{{{ns_w_pb}}}val"

        def _is_pagebreak_only_elem(p_elem):
            """Check if a <w:p> contains ONLY break elements (no text)."""
            for t_el in p_elem.iter(f"{{{ns_w_pb}}}t"):
                if t_el.text and t_el.text.strip():
                    return False
            has_pb = False
            for child in p_elem:
                tag_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag_local == "r":
                    for subchild in child:
                        sub_local = (subchild.tag.split("}")[-1]
                                     if "}" in subchild.tag else subchild.tag)
                        if (sub_local == "br"
                                and subchild.get(f"{{{ns_w_pb}}}type") == "page"):
                            has_pb = True
            return has_pb

        body_elem = None
        for ch in root_pb:
            tag_local = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
            if tag_local == "body":
                body_elem = ch
                break
        if body_elem is None:
            body_elem = root_pb

        # Remove page-break-only paragraphs.
        new_body_elems = []
        for p_elem in list(body_elem):
            tag_local = p_elem.tag.split("}")[-1] if "}" in p_elem.tag else p_elem.tag
            if tag_local == "p" and _is_pagebreak_only_elem(p_elem):
                continue  # skip explicit page-break paragraph
            new_body_elems.append(p_elem)
        # Also strip empty paragraphs that directly follow a removed page-break.
        final_elems = []
        prev_was_removed_pb = False
        for pe in new_body_elems:
            tag_local_pe = pe.tag.split("}")[-1] if "}" in pe.tag else pe.tag
            is_empty = (tag_local_pe == "p"
                        and not any(t.text and t.text.strip()
                                    for t in pe.iter(f"{{{ns_w_pb}}}t")
                                    if True))  # no text content
            # Also check it has no images/tables etc.
            if is_empty:
                for child in pe:
                    cl = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if cl not in ("r",):
                        is_empty = False  # has image/table/etc
                        break
            if prev_was_removed_pb and is_empty:
                prev_was_removed_pb = False
            else:
                final_elems.append(pe)
                prev_was_removed_pb = False
        # Rebuild body.
        for old in list(body_elem):
            body_elem.remove(old)
        for pe in final_elems:
            body_elem.append(pe)

        tree_pb.write(doc_xml_path, xml_declaration=True,
                      encoding="UTF-8", standalone=True)

        # Rebuild the docx with modified document.xml.
        with zipfile.ZipFile(OUTPUT_DOCX, "w") as zf_out:
            for root_dir2, dirs, files in os.walk(_pb_dir):
                for fname in sorted(files):
                    full = os.path.join(root_dir2, fname)
                    arcname = os.path.relpath(full, _pb_dir)
                    zf_out.write(full, arcname)
        print("[C] Removed explicit page-break-only paragraphs")
    finally:
        shutil.rmtree(_pb_dir, ignore_errors=True)

    # ---- (f) TOCHeading + custom-style font fix via lxml pass on styles.xml ----
    _fix_dir = _tempfile.mkdtemp(dir=BUILD_DIR, prefix="_tocfix_")
    try:
        with zipfile.ZipFile(OUTPUT_DOCX) as zf_in:
            zf_in.extractall(_fix_dir)
        styles_path = os.path.join(_fix_dir, "word", "styles.xml")
        if not os.path.exists(styles_path):
            print("[C] Warning: styles.xml missing — skipping TOCHeading fix")
        else:
            tree_styles = _lxml_et.parse(styles_path)
            root_s = tree_styles.getroot()
            ns_w_sf = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

            def _tag(name):
                return f"{{{ns_w_sf}}}{name}"

            VAL_SF = f"{{{ns_w_sf}}}val"

            def _child(parent, local_name):
                for c in parent:
                    cl = c.tag.split("}")[-1] if "}" in c.tag else c.tag
                    if cl == local_name:
                        return c
                return None

            def _find_rpr(style_elem):
                rp = _child(style_elem, "rPr")
                if rp is not None:
                    return rp
                rpd = _child(style_elem, "rPrDefault")
                if rpd is not None:
                    return _child(rpd, "rPr")
                return None

            def _insert_before(parent, new_el, ref_el):
                siblings = list(parent)
                idx = siblings.index(ref_el) if ref_el in siblings else len(siblings)
                parent.insert(idx, new_el)

            # ---- TOC Heading fix ----
            for style_elem in root_s.iter(_tag("style")):
                name_el = _child(style_elem, "name")
                if name_el is None:
                    continue
                sname = name_el.get(VAL_SF, "")
                if sname.lower() != "toc heading":
                    continue

                rp = _find_rpr(style_elem)
                if rp is not None:
                    # (1) Fix rFonts — explicit Times New Roman on all scripts.
                    rfonts = _child(rp, "rFonts")
                    if rfonts is None:
                        sz_el = _child(rp, "sz")
                        before = sz_el if sz_el is not None else (
                            rp[0] if len(rp) > 0 else None)
                        rfonts = _lxml_et.SubElement(
                            rp, _tag("rFonts"),
                            {_tag("ascii"): "Times New Roman",
                             _tag("hAnsi"): "Times New Roman",
                             _tag("cs"): "Times New Roman",
                             _tag("eastAsia"): "Times New Roman"})
                        if before:
                            _insert_before(rp, rfonts, before)
                    else:
                        for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
                            rfonts.set(_tag(attr), "Times New Roman")

                    # (2) Remove bold-off (w:b w:val="0") and set bold on.
                    b_el = _child(rp, "b")
                    if b_el is not None:
                        b_val = b_el.get(VAL_SF)
                        if b_val == "0":
                            rp.remove(b_el)  # remove the element
                            # Re-add bold on.
                            sz_el2 = _child(rp, "sz")
                            before2 = sz_el2 if sz_el2 is not None else (
                                rp[0] if len(rp) > 0 else None)
                            b_on = _lxml_et.SubElement(rp, _tag("b"))
                            if before2:
                                _insert_before(rp, b_on, before2)
                        # If bold was already on, leave it.

                    # (3) Size — ensure sz and szCs are 32 (16 pt × 2).
                    for sz_el in rp.iter(_tag("sz")):
                        sz_el.set(VAL_SF, "32")
                    for szcs_el in rp.iter(_tag("szCs")):
                        szcs_el.set(VAL_SF, "32")

                    # (4) Color — force black.
                    has_color = False
                    for color_el in rp.iter(_tag("color")):
                        has_color = True
                        for attr in ("themeColor", "themeShade", "themeTint"):
                            key = ns_w_sf + attr
                            if key in color_el.attrib:
                                del color_el.attrib[key]
                        color_el.set(VAL_SF, "000000")
                    if not has_color:
                        sz_el3 = _child(rp, "sz")
                        before3 = sz_el3 if sz_el3 is not None else (
                            rp[0] if len(rp) > 0 else None)
                        color_el = _lxml_et.SubElement(
                            rp, _tag("color"), {VAL_SF: "000000"})
                        if before3:
                            _insert_before(rp, color_el, before3)

                    # (5) pPr — keepNext, keepLines, pageBreakBefore,
                    #     spacing before=0 after=240, outlineLvl="9".
                    pp = _child(style_elem, "pPr")
                    if pp is None:
                        children = list(style_elem)
                        for i, ch in enumerate(children):
                            cl = (ch.tag.split("}")[-1]
                                  if "}" in ch.tag else ch.tag)
                            if cl == "name":
                                pp = _lxml_et.SubElement(
                                    style_elem, _tag("pPr"),
                                    {ns_w_sf + "docId": "0D51A601"})
                                style_elem.remove(ch)
                                style_elem.insert(i + 1, pp)
                                break
                        if pp is None:
                            pp = _lxml_et.SubElement(
                                style_elem, _tag("pPr"),
                                {ns_w_sf + "docId": "0D51A601"})
                    # Set keepNext.
                    if _child(pp, "keepNext") is None:
                        _lxml_et.SubElement(pp, _tag("keepNext"),
                                            {VAL_SF: "0"})
                    # Set keepLines.
                    if _child(pp, "keepLines") is None:
                        _lxml_et.SubElement(pp, _tag("keepLines"),
                                            {VAL_SF: "0"})
                    # Set pageBreakBefore (may already exist).
                    pbb = _child(pp, "pageBreakBefore")
                    if pbb is None:
                        _lxml_et.SubElement(pp, _tag("pageBreakBefore"))
                    # Spacing before=0 after=240.
                    spc = _child(pp, "spacing")
                    if spc is None:
                        spc = _lxml_et.SubElement(pp, _tag("spacing"))
                    spc.set(_tag("before"), "0")
                    spc.set(_tag("after"), "240")
                    # Remove outlineLvl if it exists (set to 9).
                    ol = _child(pp, "outlineLvl")
                    if ol is not None:
                        ol.set(VAL_SF, "9")
                    else:
                        _lxml_et.SubElement(pp, _tag("outlineLvl"),
                                            {VAL_SF: "9"})

                print("[C] Fixed TOC Heading style (Times New Roman 16 pt bold black)")

            # ---- Fix all other custom styles with empty rFonts ----
            for style_elem in root_s.iter(_tag("style")):
                name_el = _child(style_elem, "name")
                if name_el is None:
                    continue
                sname = name_el.get(VAL_SF, "").lower()
                # Skip built-in styles that already have proper fonts.
                skip_names = {
                    "heading 1", "heading 2", "heading 3", "heading 4",
                    "title", "normal", "body text", "first paragraph",
                    "compact", "caption", "image caption", "captioned figure",
                    "table", "toc heading"}
                if sname in skip_names:
                    continue

                rp = _find_rpr(style_elem)
                if rp is None:
                    continue

                rfonts = _child(rp, "rFonts")
                has_empty_rfonts = (rfonts is not None
                                    and all(
                                        attr in rfonts.attrib
                                        for attr in ("ascii", "hAnsi",
                                                     "cs", "eastAsia")
                                        if True))  # check any attr exists
                # More robust: check if rFonts element has NO font attrs.
                font_attrs = [k for k in rfonts.attrib.keys()
                              if k.endswith('ascii') or k == f'{ns_w_sf}cs'] if rfonts is not None else []
                needs_fix = False
                if rfonts is not None:
                    # Has empty rFonts — no ascii/hAnsi/cs/eastAsia set.
                    has_any_font = any(
                        rfonts.get(ns_w_sf + a) for a in
                        ("ascii", "hAnsi", "cs", "eastAsia")
                    )
                    if not has_any_font:
                        needs_fix = True
                
                if needs_fix:
                    # Set Times New Roman unless this is Source Code / Verbatim.
                    font_family = ("Courier New"
                                   if sname in ("source code", "verbatim char")
                                   else "Times New Roman")
                    for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
                        rfonts.set(_tag(attr), font_family)

            tree_styles.write(styles_path, xml_declaration=True,
                              encoding="UTF-8", standalone=True)
    finally:
        shutil.rmtree(_fix_dir, ignore_errors=True)
    # After python-docx saves, do a raw XML pass on styles.xml to strip
    # any remaining theme attributes that cause blue headings.  Also verify
    # the footer PAGE field structure is correct.
    post_dir = _tempfile.mkdtemp(dir=BUILD_DIR, prefix="_postfix_")
    try:
        with zipfile.ZipFile(OUTPUT_DOCX) as zf_in:
            zf_in.extractall(post_dir)
        ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

        # --- Fix styles.xml: strip ALL theme attrs from rFonts & color ---
        styles_path = os.path.join(post_dir, "word", "styles.xml")
        if os.path.exists(styles_path):
            tree_s = _lxml_et.parse(styles_path)
            root_s = tree_s.getroot()

            # Remove theme attributes from ALL rFonts (including docDefaults).
            for rfonts in root_s.iter(f"{{{ns_w}}}rFonts"):
                for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
                    key = f"{{{ns_w}}}{attr}"
                    if key in rfonts.attrib:
                        del rfonts.attrib[key]

            # Remove themeColor/shade/tint from ALL color elements; force black.
            for color_el in root_s.iter(f"{{{ns_w}}}color"):
                for attr in ("themeColor", "themeShade", "themeTint"):
                    key = f"{{{ns_w}}}{attr}"
                    if key in color_el.attrib:
                        del color_el.attrib[key]
                color_el.set(f"{{{ns_w}}}val", "000000")

            # Also strip theme attrs from docDefaults rPr (global defaults).
            for def_rpr in root_s.iter(f"{{{ns_w}}}rPrDefault/{ns_w}rPr"):
                for rfonts in def_rpr.iter(f"{{{ns_w}}}rFonts"):
                    for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
                        key = f"{{{ns_w}}}{attr}"
                        if key in rfonts.attrib:
                            del rfonts.attrib[key]
                for color_el in def_rpr.iter(f"{{{ns_w}}}color"):
                    for attr in ("themeColor", "themeShade", "themeTint"):
                        key = f"{{{ns_w}}}{attr}"
                        if key in color_el.attrib:
                            del color_el.attrib[key]
                    color_el.set(f"{{{ns_w}}}val", "000000")

            tree_s.write(styles_path, xml_declaration=True,
                         encoding="UTF-8", standalone=True)

        # --- Fix footer: rebuild PAGE field if fldChar was stripped ---
        for fname in sorted(os.listdir(os.path.join(post_dir, "word"))):
            if not fname.startswith("footer") or "_rels" in fname:
                continue
            fpath = os.path.join(post_dir, "word", fname)
            tree_f = _lxml_et.parse(fpath)
            root_f = tree_f.getroot()
            ns_w_footer = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

            for p_elem in list(root_f.iter(f"{{{ns_w_footer}}}p")):
                # Check if this paragraph already has a proper PAGE field.
                fc_elements = list(p_elem.iter(f"{{{ns_w_footer}}}fldChar"))
                instr_elements = list(p_elem.iter(f"{{{ns_w_footer}}}instrText"))

                if len(fc_elements) >= 3 and len(instr_elements) >= 1:
                    # Already has correct PAGE field structure — skip.
                    continue

                # No proper field → rebuild from scratch.
                p_elem.clear()
                ns_xml = "{http://www.w3.org/XML/1998/namespace}space"

                # Run: fldChar begin
                r0 = _lxml_et.SubElement(p_elem, f"{{{ns_w_footer}}}r")
                _lxml_et.SubElement(r0, f"{{{ns_w_footer}}}fldChar",
                                    {f"{{{ns_w_footer}}}fldCharType": "begin"})

                # Run: instrText
                r1 = _lxml_et.SubElement(p_elem, f"{{{ns_w_footer}}}r")
                it = _lxml_et.SubElement(r1, f"{{{ns_w_footer}}}instrText",
                                         {ns_xml: "preserve"})
                it.text = " PAGE "

                # Run: fldChar separate
                r2 = _lxml_et.SubElement(p_elem, f"{{{ns_w_footer}}}r")
                _lxml_et.SubElement(r2, f"{{{ns_w_footer}}}fldChar",
                                    {f"{{{ns_w_footer}}}fldCharType": "separate"})

                # Run: value placeholder
                r3 = _lxml_et.SubElement(p_elem, f"{{{ns_w_footer}}}r")
                t_el = _lxml_et.SubElement(r3, f"{{{ns_w_footer}}}t")
                t_el.text = "1"

                # Run: fldChar end
                r4 = _lxml_et.SubElement(p_elem, f"{{{ns_w_footer}}}r")
                _lxml_et.SubElement(r4, f"{{{ns_w_footer}}}fldChar",
                                    {f"{{{ns_w_footer}}}fldCharType": "end"})

            tree_f.write(fpath, xml_declaration=True,
                         encoding="UTF-8", standalone=True)

        # Rebuild the docx zip from modified files.
        with zipfile.ZipFile(OUTPUT_DOCX, "w") as zf_out:
            for root_dir, dirs, files in os.walk(post_dir):
                for fname2 in sorted(files):
                    full = os.path.join(root_dir, fname2)
                    arcname = os.path.relpath(full, post_dir)
                    zf_out.write(full, arcname)
        print("[C] Post-save lxml pass: fixed headings & footer")
    finally:
        shutil.rmtree(post_dir, ignore_errors=True)

    # ---- Resize oversized images to fit A4 printable area ----
    # Single source of truth: native pixel size from PIL image file.
    # Set EXACTLY the same (cx, cy) on BOTH wp:extent and a:xfrm/a:ext.
    MAX_W_IN = 6.0
    MAX_H_IN = 8.4          # usable page height is ~9.7 in; caption + heading need rest
    EMU_PER_INCH = 914400
    DPI = 150                # baseline dpi for width/height conversion

    from PIL import Image as _PIL_Image

    resize_dir = _tempfile.mkdtemp(dir=BUILD_DIR, prefix="_resize_final_")
    try:
        with zipfile.ZipFile(OUTPUT_DOCX) as zf_in:
            zf_in.extractall(resize_dir)
        doc_xml_path = os.path.join(resize_dir, "word", "document.xml")

        tree = _lxml_et.parse(doc_xml_path)
        root = tree.getroot()
        ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        resized_count = 0

        # Namespace helpers for Clark notation.
        NS_W = ns_w
        NS_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
        NS_PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
        REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

        # ---- (F) keepNext / keepLines for orphan prevention ---
        body_elem = None
        for ch in root:
            tag_local = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
            if tag_local == "body":
                body_elem = ch
                break
        if body_elem is None:
            body_elem = root
        para_list = [e for e in body_elem if e.tag == f"{{{NS_W}}}p"]

        # Remove keepNext from text paragraphs BEFORE image paragraphs.
        img_para_indices = set()
        for idx, p in enumerate(para_list):
            drawings = list(p.iter(f"{NS_W}drawing"))
            if drawings:
                img_para_indices.add(idx)
        
        # Clear keepNext on preceding text paragraphs (not empty ones).
        for idx in sorted(img_para_indices):
            j = idx - 1
            while j >= 0:
                prev_p = para_list[j]
                pp_prev = prev_p.find(f"{NS_W}pPr")
                if pp_prev is not None:
                    ps = pp_prev.find(f"{NS_W}pStyle")
                    if ps is not None and ps.get(VAL) == "Heading1":
                        break
                has_text = any(
                    t_el.text and t_el.text.strip()
                    for t_el in prev_p.iter(f"{{{NS_W}}}t")
                )
                if has_text:
                    pp_prev2 = prev_p.find(f"{NS_W}pPr")
                    if pp_prev2 is not None:
                        kn = pp_prev2.find(f"{NS_W}keepNext")
                        if kn is not None:
                            pp_prev2.remove(kn)
                j -= 1
        
        # Set keepLines on image paragraphs (so diagram stays with its caption).
        for idx in img_para_indices:
            p = para_list[idx]
            pp = p.find(f"{NS_W}pPr")
            if pp is None:
                pp = _lxml_et.SubElement(p, f"{{{NS_W}}}pPr",
                                         {f"{{{NS_W}}}docId": "0D51A601"})
            kl = pp.find(f"{NS_W}keepLines")
            if kl is None:
                _lxml_et.SubElement(pp, f"{{{NS_W}}}keepLines",
                                    {f"{{{NS_W}}}val": "0"})

        # ---- Resize each inline drawing from native pixel dimensions ---
        for elem in list(root.iter()):
            tag_local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag_local != "inline":
                continue

            ext_el = elem.find(f"{{{NS_WP}}}extent")
            if ext_el is None:
                continue

            # Get image file name from pic:cNvPr (first occurrence).
            cnp_el = None
            for _el in elem.iter():
                tl = _el.tag.split("}")[-1] if "}" in _el.tag else _el.tag
                if tl == "cNvPr" and NS_PIC in _el.tag:
                    cnp_el = _el
                    break
            img_name = cnp_el.get("descr", "") if cnp_el else ""

            # Get rId from a:blip (first occurrence inside this inline).
            blip_el = None
            for _el in elem.iter():
                tl = _el.tag.split("}")[-1] if "}" in _el.tag else _el.tag
                if tl == "blip" and NS_A in _el.tag:
                    blip_el = _el
                    break
            rId = None
            if blip_el is not None:
                rId = (blip_el.get(
                    f"{{{REL_NS}}}embed") or "")

            # Determine the image file path.
            img_path = None
            if img_name.startswith("docs/images/") or img_name.startswith("docs/screenshots/"):
                full_img_path = os.path.join(REPO_ROOT, img_name)
                if os.path.exists(full_img_path):
                    img_path = full_img_path

            # Compute target size from native pixel dimensions.
            if img_path is not None:
                try:
                    with _PIL_Image.open(img_path) as img:
                        w_px, h_px = img.size
                    width_in = w_px / DPI
                    height_in = h_px / DPI
                    scale = min(1.0,
                                MAX_W_IN / max(width_in, 0.01),
                                MAX_H_IN / max(height_in, 0.01))
                    new_cx = int(width_in * scale * EMU_PER_INCH)
                    new_cy = int(height_in * scale * EMU_PER_INCH)
                except Exception:
                    continue
            else:
                # Fallback: use existing wp:extent values and apply cap.
                old_cx = int(ext_el.get("cx", 0))
                old_cy = int(ext_el.get("cy", 0))
                cx_in = old_cx / EMU_PER_INCH
                cy_in = old_cy / EMU_PER_INCH
                scale = min(1.0,
                            MAX_W_IN / max(cx_in, 0.01),
                            MAX_H_IN / max(cy_in, 0.01))
                new_cx = int(old_cx * scale)
                new_cy = int(old_cy * scale)

            # Update BOTH wp:extent and a:xfrm/a:ext to the same values.
            if int(ext_el.get("cx", 0)) != new_cx or \
               int(ext_el.get("cy", 0)) != new_cy:
                ext_el.set("cx", str(new_cx))
                ext_el.set("cy", str(new_cy))

                # Update a:ext inside pic:spPr/a:xfrm.
                for _el in elem.iter():
                    tl = _el.tag.split("}")[-1] if "}" in _el.tag else _el.tag
                    if tl == "xfrm" and NS_A in _el.tag:
                        # Found a:xfrm; look inside for a:ext child.
                        for _child in list(_el):
                            cl = _child.tag.split("}")[-1] if "}" in _child.tag else _child.tag
                            if cl == "ext" and NS_A in _child.tag:
                                _child.set("cx", str(new_cx))
                                _child.set("cy", str(new_cy))
                        break

                # Zero out wp:effectExtent if present.
                eff_el = elem.find(f"{{{NS_WP}}}effectExtent")
                if eff_el is not None:
                    for attr in ("b", "l", "r", "t"):
                        eff_el.set(attr, "0")

                resized_count += 1

        tree.write(doc_xml_path, xml_declaration=True,
                   encoding="UTF-8", standalone=True)

        # Rebuild the docx zip from modified files — lxml preserves prefixes.
        with zipfile.ZipFile(OUTPUT_DOCX, "w") as zf_out:
            for root_dir, dirs, files in os.walk(resize_dir):
                for fname in sorted(files):
                    full = os.path.join(root_dir, fname)
                    arcname = os.path.relpath(full, resize_dir)
                    zf_out.write(full, arcname)

        print(f"[C] Resized {resized_count} image extents to fit A4")
    finally:
        shutil.rmtree(resize_dir, ignore_errors=True)

    # ---- Remove blank-page-causing empty/drawing-only paragraphs before H1 ---
    try:
        with zipfile.ZipFile(OUTPUT_DOCX) as zf_in:
            zf_in.extractall(resize_dir + "_blank")
        doc_xml_path2 = os.path.join(
            resize_dir + "_blank", "word", "document.xml")

        tree2 = _lxml_et.parse(doc_xml_path2)
        root2 = tree2.getroot()

        body2 = None
        for ch in root2:
            tl = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
            if tl == "body":
                body2 = ch
                break
        if body2 is None:
            body2 = root2

        para_list2 = [e for e in body2 if e.tag == f"{{{ns_w}}}p"]

        def _is_empty_para(p):
            """Return True if paragraph has no text and no drawing."""
            has_text = any(
                t_el.text and t_el.text.strip()
                for t_el in p.iter(f"{{{ns_w}}}t")
            )
            has_drawing = len(list(p.iter(f"{ns_w}drawing"))) > 0 or \
                          len(list(p.iter(f"{ns_w}pict"))) > 0
            return not has_text and not has_drawing

        blank_removed = 0
        to_remove = []
        for i, p in enumerate(para_list2):
            pp = p.find(f"{{{ns_w}}}pPr")
            if pp is None:
                continue
            ps = pp.find(f"{{{ns_w}}}pStyle")
            if ps is None:
                continue
            style_val = ps.get(VAL, "")
            if style_val in ("Heading1", "TOCHeading"):
                # Remove immediately preceding empty paragraph.
                prev_idx = i - 1
                while prev_idx >= 0 and _is_empty_para(para_list2[prev_idx]):
                    to_remove.append(prev_idx)
                    prev_idx -= 1

        for idx in sorted(set(to_remove), reverse=True):
            body2.remove(para_list2[idx])
            blank_removed += 1

        tree2.write(doc_xml_path2, xml_declaration=True,
                    encoding="UTF-8", standalone=True)

        with zipfile.ZipFile(OUTPUT_DOCX, "w") as zf_out:
            for root_dir, dirs, files in os.walk(resize_dir + "_blank"):
                for fname in sorted(files):
                    full = os.path.join(root_dir, fname)
                    arcname = os.path.relpath(full, resize_dir + "_blank")
                    zf_out.write(full, arcname)

        print(f"[C] Removed {blank_removed} blank paragraphs before headings")
    finally:
        shutil.rmtree(resize_dir + "_blank", ignore_errors=True)

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
    # Exclude title page heading and Table of Contents heading.
    expected_h1_from_md = md_h1_total - 2   # exclude title + TOC headings
    print(f"[INFO] Heading 1 count: {h1_count} (expected ~{expected_h1_from_md})")

    # 4. Check TOC field instruction in document XML.
    body_xml = str(doc.element.body.xml)
    has_toc = 'TOC \\o' in body_xml or '\\o "1-2"' in body_xml
    print(f"[{'PASS' if has_toc else 'FAIL'}] TOC field {'found' if has_toc else 'NOT found'}")

    # 5. Check footer PAGE field — must contain fldChar AND no literal "PAGE" inside w:t.
    footer_has_page = False
    footer_no_literal_page = True
    for section in doc.sections:
        footer_xml = str(section.footer._element.xml)
        if "fldChar" in footer_xml and " PAGE " in footer_xml:
            # Check no literal "PAGE" inside w:t elements.
            import re as _re2
            t_elements = _re2.findall(r'<w:t[^>]*>.*?</w:t>', footer_xml)
            for te in t_elements:
                text_content = _re2.sub(r'<[^>]+>', '', te).strip()
                if text_content == "PAGE":
                    footer_no_literal_page = False
            footer_has_page = True

    print(f"[{'PASS' if footer_has_page else 'FAIL'}] Footer PAGE field {'found' if footer_has_page else 'NOT found'}")
    print(f"[{'PASS' if footer_no_literal_page else 'FAIL'}] No literal 'PAGE' in footer w:t")

    # 6. Check updateFields setting in settings.xml inside the docx zip.
    with zipfile.ZipFile(OUTPUT_DOCX) as zf:
        for name in zf.namelist():
            if "settings.xml" in name and "_rels" not in name:
                content = zf.read(name).decode()
                has_update = "updateFields" in content and 'val="true"' in content
                print(f"[{'PASS' if has_update else 'FAIL'}] updateFields {'set' if has_update else 'NOT set'}")

    # 7. Count tables — must be >30, no ns0: prefix.
    with zipfile.ZipFile(OUTPUT_DOCX) as zf:
        doc_xml = zf.read("word/document.xml").decode()
        table_count = doc_xml.count("<w:tbl>")
        ns_prefix_count = doc_xml.count("ns0:")
        print(f"[{'PASS' if table_count > 30 else 'FAIL'}] Tables: {table_count} (need >30)")
        print(f"[{'PASS' if ns_prefix_count == 0 else 'FAIL'}] No ns0: prefix in document.xml ({ns_prefix_count})")

    # 8. Check 19.4 screenshot table has 16 rows (header + 15).
    from docx import Document as D2
    doc_check = D2(OUTPUT_DOCX)
    # Find the first table that looks like a screenshot table.
    screenshot_table_rows = 0
    for table in doc_check.tables:
        if len(table.rows) > 1:
            first_row_text = " ".join(cell.text.strip() for cell in table.rows[0].cells)
            # The markdown uses "Screen | Description | Screenshot Location"
            # or similar; look for any of the screenshot-related keywords.
            if "Screenshot" in first_row_text or ("Name" in first_row_text and "Path" in first_row_text):
                screenshot_table_rows = len(table.rows)
                break
    print(f"[{'PASS' if screenshot_table_rows == 16 else 'FAIL'}] Screenshot table rows: {screenshot_table_rows} (expected 16)")

    # 9. git status — only scripts/build_report_docx.py should be changed.
    result = subprocess.run(
        ["git", "status", "--short"], capture_output=True, text=True, cwd=REPO_ROOT,
    )
    staged_files = [l for l in result.stdout.strip().split("\n") if l and not l.startswith("??")]
    only_script_changed = all(
        "scripts/build_report_docx.py" in f or "build/" in f for f in staged_files
    ) if staged_files else True
    print(f"[{'PASS' if only_script_changed else 'FAIL'}] git status — only build script changed")
    for f in result.stdout.strip().split("\n"):
        if f:
            print(f"       {f}")

    # 10. LibreOffice PDF conversion + page count check (acceptance criterion).
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
                        print(f"[INFO] PDF page count: {pages}")
                        if 70 <= pages <= 130:
                            print(f"[PASS] Page count within acceptance range [70,130]")
                        else:
                            print(f"[FAIL] Page count {pages} OUTSIDE acceptance range [70,130]")

                        # Near-empty page check (using pdftotext).
                        import tempfile as _tmpf2
                        empty_count = 0
                        empty_pages = []
                        tmp_txt_dir = _tmpf2.mkdtemp(dir=BUILD_DIR, prefix="_empty_check_")
                        try:
                            for pg in range(1, pages + 1):
                                r2 = subprocess.run(
                                    ["pdftotext", "-f", str(pg), "-l", str(pg),
                                     pdf_path, os.path.join(tmp_txt_dir, f"pg_{pg}.txt")],
                                    capture_output=True, text=True, timeout=30,
                                )
                                if r2.returncode == 0:
                                    txt_path = os.path.join(tmp_txt_dir, f"pg_{pg}.txt")
                                    with open(txt_path) as tf:
                                        words = len(tf.read().split())
                                    if words < 25:
                                        empty_count += 1
                                        empty_pages.append(pg)
                            print(f"[INFO] Near-empty pages (<25 words): {empty_count}")
                            print(f"       Page numbers: {empty_pages[:10]}{'...' if len(empty_pages) > 10 else ''}")
                            if empty_count <= 35:
                                print(f"[PASS] Near-empty page count within limit (≤35)")
                            else:
                                print(f"[FAIL] Near-empty pages {empty_count} exceeds limit 35")
                        finally:
                            shutil.rmtree(tmp_txt_dir, ignore_errors=True)

                        # Render sample pages to PNG for visual check.
                        try:
                            import subprocess as _subp2
                            reader = PdfReader(pdf_path)
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
                                _subp2.run([
                                    "pdftoppm", "-r", "60", "-png",
                                    pdf_path, png_path.replace(".png", ""),
                                ], capture_output=True)
                                if os.path.exists(png_path):
                                    sz = os.path.getsize(png_path)
                                    print(f"       Rendered page {pg+1} → {sz} bytes")
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
    """Remove temp files in build/, keep Project_Report.docx and .venv."""
    for path in [PREPROC_MD, REF_DOCX, RAW_DOCX]:
        if os.path.exists(path):
            os.remove(path)
            print(f"[CLEANUP] Removed {path}")

    # Remove any other temp files/dirs in build/ except Project_Report.docx and .venv.
    for item in sorted(os.listdir(BUILD_DIR)):
        full = os.path.join(BUILD_DIR, item)
        if item == "Project_Report.docx" or item == ".venv":
            continue
        # Remove temp directories (prefix _).
        if os.path.isdir(full) and item.startswith("_"):
            shutil.rmtree(full, ignore_errors=True)
            print(f"[CLEANUP] Removed dir {full}")


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
    generate_reference_docx() # Part of B — reference docx from pandoc default
    run_pandoc()              # Step B — pandoc conversion
    post_process()            # Step C — python-docx/lxml polish
    verify()                  # Step D — verification checks
    cleanup()

    print("\n" + "=" * 60)
    size = os.path.getsize(OUTPUT_DOCX)
    print(f"Done! {OUTPUT_DOCX} ({size:,} bytes / {size/1024:.1f} KB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
