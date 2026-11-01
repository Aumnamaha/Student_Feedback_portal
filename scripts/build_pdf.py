#!/usr/bin/env python3
"""Build PDF from Project_Report.docx with correct page breaks and TOC page numbers.

Pipeline:
1. Extract images from DOCX (word/media/) to build/media/
2. Convert DOCX → HTML via pandoc  
3. Fix image references in HTML, inject CSS for page breaks + formatting
4. Render PDF via Playwright Chromium
5. Use PyMuPDF to find where each chapter/section heading appears
6. Update the static TOC in DOCX with real page numbers
7. Rebuild DOCX → Regenerate PDF
8. Verify output

Usage: python scripts/build_pdf.py [--rebuild-docx]
"""

import os, sys, re, subprocess, shutil, zipfile, tempfile, glob as _glob
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"
DOCX_PATH = BUILD_DIR / "Project_Report.docx"
HTML_PATH = BUILD_DIR / "_converted.html"
PDF_PATH = BUILD_DIR / "Project_Report.pdf"
MEDIA_DIR = BUILD_DIR / "media"

# ---------------------------------------------------------------------------
# Helper: Build HTML-based TOC from markdown source
# ---------------------------------------------------------------------------
def _build_html_toc(md_path):
    """Parse Project_Report.md for chapter/section headings and generate a <ul> TOC."""
    try:
        with open(md_path, encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("[PDF] WARNING: Markdown not found at", md_path)
        return ""
    
    toc_items = []  # list of (level, text, anchor_id)
    current_chapter_num = None
    in_code = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        
        # Chapter heading: # Chapter X: Title
        m1 = re.match(r'^#\s+(Chapter\s+(\d+):\s+.+)$', line)
        if m1:
            heading_text = m1.group(1).strip()
            current_chapter_num = int(m1.group(2))
            anchor = f'chapter-{current_chapter_num}'
            # Clean text for display (remove trailing page numbers from TOC entries)
            clean_text = re.sub(r'\s+\d+$', '', heading_text).strip()
            toc_items.append((1, clean_text, anchor))
            continue
        
        # Section heading: ## X.Y Title  
        m2 = re.match(r'^##\s+(\d+\.\d+)\s+(.+)$', line)
        if m2 and current_chapter_num is not None:
            section_text = f"{m2.group(1)} {m2.group(2).strip()}"
            anchor = f'chapter-{current_chapter_num}-{re.sub(r"[^a-zA-Z0-9]", "", m2.group(2).lower())}'
            toc_items.append((2, section_text, anchor))
    
    if not toc_items:
        return ""
    
    # Generate HTML<ul> with proper indentation
    html_lines = ['<div class="html-toc" style="margin-left:1in;">']
    for level, text, anchor in toc_items:
        indent = '  ' if level == 2 else ''
        bold = 'font-weight:bold;' if level == 1 else ''
        html_lines.append(
            f'{indent}<p style="{bold}margin:2px 0;">'
            f'<a href="#{anchor}" style="text-decoration:none;color:#000;">{text}</a>'
            f' &nbsp;&nbsp;...&nbsp;<span class="toc-page" data-anchor="{anchor}"></span></p>'
        )
    html_lines.append('</div>')
    return '\n'.join(html_lines)


# ---------------------------------------------------------------------------
# Step 1 — Extract images from DOCX to build/media/
# ---------------------------------------------------------------------------
def extract_images():
    """Extract embedded images from the DOCX to build/media/."""
    MEDIA_DIR.mkdir(exist_ok=True)
    rel_map = {}  # rId -> local filename
    
    with zipfile.ZipFile(DOCX_PATH) as zf:
        if "word/_rels/document.xml.rels" in zf.namelist():
            doc_rels_xml = zf.read("word/_rels/document.xml.rels").decode()
            for m in re.finditer(
                r'<Relationship\s+Id="([^"]+)"[^>]+Target="([^"]+)"',
                doc_rels_xml,
            ):
                rel_id, target = m.group(1), m.group(2)
                if "image" in target.lower() or any(
                    ext in target.lower() for ext in (".png", ".jpg", ".jpeg")
                ):
                    img_name = os.path.basename(target)  # e.g., rId82.png
                    out_path = MEDIA_DIR / img_name
                    src_path_in_zip = f"word/media/{img_name}"
                    if not out_path.exists() and src_path_in_zip in zf.namelist():
                        with zf.open(src_path_in_zip) as src, open(out_path, 'wb') as dst:
                            dst.write(src.read())
                    rel_map[rel_id] = f"media/{img_name}"
    
    extracted_count = len([f for f in os.listdir(MEDIA_DIR) if f.endswith('.png')])
    print(f"[PDF] Extracted {extracted_count} images -> build/media/")
    return rel_map


# ---------------------------------------------------------------------------
# Helper: Strip static TOC paragraphs from the DOCX
# ---------------------------------------------------------------------------
def _strip_toc_from_docx():
    """Remove all Normal-style TOC paragraph entries from the DOCX before pandoc conversion.
    
    IMPORTANT: Only strip Normal-style paragraphs. Do NOT touch Heading 1/Heading 2
    paragraphs — those are actual document content with embedded page numbers that
    will be corrected by the HTML-based TOC approach.
    """
    try:
        from docx import Document
    except ImportError:
        print("[PDF] FATAL: python-docx not available")
        return

    doc = Document(str(DOCX_PATH))
    paragraphs_to_remove = []

    for i, p in enumerate(doc.paragraphs):
        text = (p.text or '').strip()
        style_name = (p.style.name or '').lower() if p.style else ''

        # ONLY strip Normal-style paragraphs
        # Skip anything with "heading" or "title" in the style name
        if not (style_name == 'normal' or ('body text' in style_name and 'first' not in style_name)):
            continue

        # Skip the "Table of Contents" heading itself
        if 'table of contents' in text.lower():
            continue

        # Remove Normal-style paragraphs that look like TOC entries:
        # - Chapter X: Title (with tab+page number at end)
        # - N.N Section title (with tab+page number at end)
        if re.match(r'^Chapter\s+\d+:.+\t\d+$', text):
            paragraphs_to_remove.append(i)
            continue
        if re.match(r'^\d+\.\d+\s+.+\t\d+$', text):
            paragraphs_to_remove.append(i)
            continue

    # Remove in reverse order to preserve indices
    for i in reversed(paragraphs_to_remove):
        p_elem = doc.paragraphs[i]._element
        p_elem.getparent().remove(p_elem)

    if paragraphs_to_remove:
        doc.save(str(DOCX_PATH))
        print(f"[PDF] Stripped {len(paragraphs_to_remove)} TOC paragraph entries from DOCX")
    else:
        print("[PDF] No TOC paragraphs to strip (already clean)")


# ---------------------------------------------------------------------------
# Step 2 — Strip TOC paragraphs from DOCX and convert to HTML via pandoc
# ---------------------------------------------------------------------------
def convert_to_html():
    """Strip static TOC paragraphs from DOCX, then convert to HTML using pandoc."""
    try:
        import pypandoc
    except ImportError:
        print("[PDF] FATAL: pypandoc not available")
        sys.exit(1)

    # Strip all static TOC paragraph entries from the DOCX before conversion.
    # These are Normal-style paragraphs containing "Chapter X" or "N.N Title" with tab+page numbers.
    # Pandoc renders them as blockquotes/visible text that duplicates our HTML-based TOC.
    _strip_toc_from_docx()

    pandoc_path = pypandoc.get_pandoc_path()
    cmd = [pandoc_path, str(DOCX_PATH), "-o", str(HTML_PATH)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"[PDF] pandoc failed: {r.stderr[:300]}")
        sys.exit(1)

    size = os.path.getsize(HTML_PATH)
    print(f"[PDF] HTML generated: {size:,} bytes")


# ---------------------------------------------------------------------------
# Step 3 — Fix HTML (image refs, CSS page breaks, formatting)
# ---------------------------------------------------------------------------
def fix_html(rel_map):
    """Fix image references and inject CSS for page breaks."""
    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()

    # Fix image src paths
    for rel_id, media_path in rel_map.items():
        pattern = re.escape(media_path.split("/")[-1])
        html = re.sub(
            rf'src="[^"]*{pattern}[^"]*" ',
            f'src="{media_path}" ',
            html,
        )


    
    # Build a proper HTML-based Table of Contents from the markdown source.
    # Read chapter/section headings from Project_Report.md and generate <ul> entries.
    md_path = REPO_ROOT / "Project_Report.md"
    toc_html = _build_html_toc(md_path)
    if toc_html:
        # Find the "Table of Contents" heading and insert TOC entries after it
        toc_marker = '<h1 id="table-of-contents">'  # pandoc converts this to an h1 with id
        if toc_marker in html:
            html = html.replace(toc_marker, f'{toc_marker}\n{toc_html}')
        else:
            # Fallback: find any heading containing "Table of Contents"
            m = re.search(r'<h1[^>]*>[^<]*Table of Contents[^<]*</h1>', html)
            if m:
                insert_pos = m.end()
                html = html[:insert_pos] + '\n' + toc_html + html[insert_pos:]
    
    # Remove ALL remaining blockquote sections (these are TOC entries that pandoc
    # rendered from DOCX Heading 1 paragraphs with embedded page numbers)
    # These appear both before AND after the HTML-based TOC.
    html = re.sub(
        r'<p><strong>(Chapter \d+:.+?)</strong></p>\s*<blockquote>[\s\S]*?</blockquote>',
        '',  # remove chapter blockquote blocks
        html,
    )
    
    # Remove standalone <p><strong>Chapter X: ...</strong></p> entries that appear
    # after the HTML-based TOC (these are pandoc duplicates of our toc div)
    html = re.sub(
        r'<p><strong>(Chapter \d+:.+?)</strong></p>',
        '',  # remove orphaned chapter heading paragraphs
        html,
    )
    
    # Remove remaining standalone section-level <p> entries that look like TOC content
    html = re.sub(
        r'<p>(\d+\.\d+)\s+(.+?)</p>',
        '',  # remove orphaned section paragraphs
        html,
        flags=re.DOTALL,
    )
    
    # Wrap all bare <p><img.../></p> blocks (Ch19 screenshots) into a single two-column grid div.
    import re as _re
    
    # Find the start and end of the screenshot section (between table close and achieved outcomes)
    table_close = html.find('</table>')
    if table_close == -1:
        table_close = 0
    achieved_heading = html.find('<h2 id="achieved-outcomes">')
    
    if achieved_heading > table_close + 100:  # there's content between them
        section = html[table_close+8:achieved_heading]
        img_blocks = _re.findall(r'<p><img[^>]+/></p>', section)
        
        if len(img_blocks) >= 2:
            # Build replacement with all blocks in one grid div
            all_img_html = '\n'.join(img_blocks)
            new_grid = f'<div class="screenshot-grid">\n{all_img_html}\n</div>'
            
            # Find the first and last img block positions to replace them
            first_match = _re.search(r'<p><img[^>]+/></p>', section)
            last_match = None
            for m in _re.finditer(r'<p><img[^>]+/></p>', section):
                last_match = m
            
            if first_match and last_match:
                start_pos = table_close + 8 + first_match.start()
                end_pos = table_close + 8 + last_match.end()
                html = html[:start_pos] + new_grid + html[end_pos:]
    
    # Inject CSS for page breaks and formatting
    css_rules = """
<style>
  @page { size: A4; margin: 1in; }
  body { font-family: "Times New Roman", serif; font-size: 12pt; line-height: 1.5; }
  
  /* Page breaks for front-matter sections */
  h1#certificate,
  h1#declaration,
  h1#abstract {
    page-break-before: always !important;
  }
  
  /* Chapter headings should also break to new page */
  h1[id^="chapter-"] {
    page-break-before: always !important;
  }
  
  /* Keep images with their captions */
  p[role="doc-subtitle"], figure, img {
    page-break-inside: avoid;
    keep-with-next: always;
  }
  
  /* TOC styling */
  .TOC-Heading {
    font-size: 16pt;
    font-weight: bold;
    font-family: "Times New Roman", serif;
    page-break-before: always !important;
  }
  
  /* Table formatting */
  table { border-collapse: collapse; width: 100%; page-break-inside: avoid; }
  th, td { border: 1px solid #888; padding: 4px 8px; font-size: 10pt; }
  th { background-color: #f0f0f0; font-weight: bold; }
  
  /* Prevent headings from being alone at bottom of page */
  h1, h2, h3 { page-break-after: avoid !important; }
  
  /* Two-column layout for screenshot figures (Ch19) */
  .figure-group {
    column-count: 2;
    column-gap: 0.5in;
    page-break-inside: avoid;
  }
  .figure-group img {
    max-width: 48%;
    height: auto !important;
    display: block;
    margin-bottom: 0.1in;
  }
  .figure-caption {
    font-size: 9pt;
    color: #333;
    page-break-inside: avoid;
    break-inside: avoid;
  }
  
  /* Screenshot images — two-column float layout */
  .screenshot-grid {
    overflow: hidden;
    margin: 0.2in 0;
  }
  .screenshot-grid > p {
    float: left;
    width: 46%;
    margin: 0.15in 2%;
    page-break-inside: avoid;
  }
  .screenshot-grid > p img {
    max-width: 100% !important;
    height: auto !important;
    display: block;
  }
  
  /* HTML-based TOC styling */
  .html-toc p { margin: 1px 0; font-size: 10pt; line-height: 1.3; }
  .html-toc p a:hover { text-decoration: underline; }
  .toc-page {
    display: inline;
    float: right;
    min-width: 2em;
    text-align: right;
    font-size: 10pt;
  }
</style>
"""

    if "<head>" in html:
        html = html.replace("<head>", f"<head>\n{css_rules}")
    else:
        html = css_rules + "\n" + html

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    
    print("[PDF] HTML fixed with page break CSS")


# ---------------------------------------------------------------------------
# Step 4 — Render PDF via Playwright (two-pass for TOC page numbers)
# ---------------------------------------------------------------------------
def render_pdf_with_toc():
    """Render HTML to PDF with correct TOC page numbers using two-pass approach."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[PDF] FATAL: playwright not available")
        sys.exit(1)
    
    def _do_render():
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            
            page.goto(f"file:///{str(HTML_PATH).replace(chr(92), '/')}", wait_until="networkidle")
            page.wait_for_timeout(1500)
            
            pdf_bytes = page.pdf(
                path=str(PDF_PATH),
                format="A4",
                margin={"top": "1in", "bottom": "1in", "left": "1in", "right": "1in"},
                print_background=True,
            )
            browser.close()
        
        size = os.path.getsize(PDF_PATH) if PDF_PATH.exists() else 0
        print(f"[PDF] Rendered: {size:,} bytes")
    
    # Pass 1: Render without page numbers (TOC shows empty spans)
    print('[PDF] Pass 1: Rendering HTML -> PDF (no TOC page numbers)')
    _do_render()
    
    # Measure where each heading appears in the PDF
    page_map = measure_heading_pages()
    
    # Inject page numbers into HTML TOC spans
    toc_updated = _inject_toc_page_numbers(page_map)
    if toc_updated:
        print(f"[PDF] Injected {toc_updated} page numbers into TOC")
    else:
        print("[PDF] WARNING: Could not inject TOC page numbers")
    
    # Pass 2: Re-render with correct page numbers
    if PDF_PATH.exists():
        os.unlink(PDF_PATH)
    print('[PDF] Pass 2: Re-rendering HTML -> PDF (with TOC page numbers)')
    _do_render()


# ---------------------------------------------------------------------------
# Step 5 — Measure heading positions and get page numbers from PDF
# ---------------------------------------------------------------------------
def measure_heading_pages():
    """Use PyMuPDF to find where each chapter/section heading appears."""
    
    import fitz
    
    if not PDF_PATH.exists():
        print("[PDF] ERROR: PDF not found")
        return {}

    doc = fitz.open(str(PDF_PATH))
    total_pages = len(doc)
    print(f"[PDF] Total pages in PDF: {total_pages}")
    
    # Collect all chapter headings from the markdown
    md_path = REPO_ROOT / "Project_Report.md"
    with open(md_path, encoding="utf-8") as f:
        md_lines = f.readlines()
    
    chapters = {}  # heading_text -> page_number (1-indexed)
    sections = {}  # section_heading_text -> page_number
    
    in_code = False
    current_chapter_num = None
    for line in md_lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m1 = re.match(r'^#\s+(Chapter\s+(\d+):.+)$', line)
        if m1:
            heading_text = m1.group(1)
            current_chapter_num = int(m1.group(2))
            chapters[heading_text] = None
            continue
        
        m2 = re.match(r'^##\s+(\d+\.\d+)\s+(.+)$', line)
        if m2 and current_chapter_num is not None:
            section_key = f"{m2.group(1)} {m2.group(2)}"
            sections[section_key] = None
    
    print(f"[PDF] Found {len(chapters)} chapters, {len(sections)} sections to locate")
    
    # Find where actual content starts.
    # Strategy: find the Abstract heading first (it's after front-matter + TOC),
    # then search from there for chapter/section headings.
    abstract_page = None
    for pg_idx in range(total_pages):
        page_text = doc[pg_idx].get_text()
        clean = ''.join(c for c in page_text if ord(c) < 128)
        if 'Abstract' in clean[:50]:
            abstract_page = pg_idx
            break
    
    # Search from Abstract onwards (or from the first chapter heading found)
    search_start = abstract_page if abstract_page is not None else total_pages - 1
    for pg_idx in range(search_start, total_pages):
        page_text = doc[pg_idx].get_text()
        clean = ''.join(c for c in page_text if ord(c) < 128)
        if re.search(r'chapter \d+:', clean[:300]):
            search_start = pg_idx
            break
    
    print(f"[PDF] Content search starts at page {search_start + 1}")
    
    for heading_text in list(chapters.keys()):
        found_page = None
        clean_heading = re.sub(r'[^a-zA-Z0-9\s]', '', heading_text).lower()[:30]
        
        for pg_idx in range(search_start, total_pages):
            page_text = doc[pg_idx].get_text()
            clean_text = re.sub(r'[^a-zA-Z0-9\s]', '', page_text.lower())[:200]
            if clean_heading in clean_text:
                found_page = pg_idx + 1  # 1-indexed
                break
        
        chapters[heading_text] = found_page
    
    for section_key in list(sections.keys()):
        found_page = None
        clean_section = re.sub(r'[^a-zA-Z0-9\s]', '', section_key).lower()[:40]
        
        for pg_idx in range(search_start, total_pages):
            page_text = doc[pg_idx].get_text()
            # Search full page text for section headings (they can appear late on the page)
            clean_text = re.sub(r'[^a-zA-Z0-9\s]', '', page_text.lower())
            if clean_section in clean_text:
                found_page = pg_idx + 1
                break
        
        sections[section_key] = found_page
    
    # Print summary
    for h, p in list(chapters.items())[:5]:
        print(f"       Chapter '{h}' -> page {p}")
    
    doc.close()
    return {"chapters": chapters, "sections": sections}


def _inject_toc_page_numbers(page_map):
    """Update the HTML TOC spans with actual page numbers from PyMuPDF measurement."""
    try:
        import fitz
    except ImportError:
        return 0
    
    if not PDF_PATH.exists():
        print("[PDF] ERROR: Cannot inject TOC without PDF")
        return 0
    
    doc = fitz.open(str(PDF_PATH))
    total_pages = len(doc)
    chapters = page_map.get("chapters", {})
    sections = page_map.get("sections", {})
    
    # Build anchor -> page number mapping
    # Chapter anchors: chapter-1, chapter-2, ...
    anchor_to_page = {}
    for ch_text, pg in chapters.items():
        if pg:
            m = re.match(r'Chapter\s+(\d+):', ch_text)
            if m:
                anchor_to_page[f"chapter-{m.group(1)}"] = pg
    
    # Section anchors: chapter-N-sectiontext (from _build_html_toc)
    for sec_key, pg in sections.items():
        if pg:
            sm = re.match(r'(\d+\.\d+)\s+(.+)', sec_key)
            if sm:
                ch_num = sm.group(1).split('.')[0]
                section_text = sm.group(2).lower()
                clean_section = re.sub(r'[^a-zA-Z0-9]', '', section_text)
                anchor_to_page[f"chapter-{ch_num}-{clean_section}"] = pg
    
    # Chapter anchors: chapter-N (from _build_html_toc, for the main chapter headings)
    for ch_text, pg in chapters.items():
        if pg:
            m = re.match(r'Chapter\s+(\d+):', ch_text)
            if m and f"chapter-{m.group(1)}" not in anchor_to_page:
                anchor_to_page[f"chapter-{m.group(1)}"] = pg
    
    # Read HTML and update spans
    with open(HTML_PATH, encoding='utf-8') as f:
        html = f.read()
    
    updated = 0
    for anchor, page_num in anchor_to_page.items():
        # Use literal string match (anchors are alphanumeric + hyphens only)
        pattern = '<span class="toc-page" data-anchor="' + anchor + '"></span>'
        replacement = '<span class="toc-page" data-anchor="' + anchor + '">' + str(page_num) + '</span>'
        count = html.count(pattern)
        if count > 0:
            html = html.replace(pattern, replacement, count)
            updated += count
    
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    
    doc.close()
    return updated


# ---------------------------------------------------------------------------
# Step 6 — Update TOC entries in DOCX with real page numbers
# ----------------------------------------------------------------===========
def update_toc_in_docx(page_map):
    """Update the static TOC paragraphs in the DOCX with actual page numbers."""
    
    from docx import Document
    from docx.shared import Pt, Inches as D_Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    
    if not PDF_PATH.exists():
        print("[PDF] ERROR: Cannot update TOC without PDF")
        return False
    
    chapters = page_map.get("chapters", {})
    sections = page_map.get("sections", {})
    
    # Read the DOCX
    doc = Document(str(DOCX_PATH))
    
    toc_start_idx = None
    for i, p in enumerate(doc.paragraphs):
        if "Table of Contents" in (p.text or ""):
            toc_start_idx = i
            break
    
    if toc_start_idx is None:
        print("[PDF] ERROR: Could not find TOC heading")
        return False
    
    # Find the section after TOC that has entries (skip any manual table)
    entry_start = None
    for i in range(toc_start_idx + 1, len(doc.paragraphs)):
        p = doc.paragraphs[i]
        text = (p.text or "").strip()
        if re.match(r'(Chapter\s+\d+|^\d+\.\d+\s)', text):
            entry_start = i
            break
    
    if entry_start is None:
        print("[PDF] ERROR: Could not find TOC entries")
        return False
    
    # Update each TOC entry with page numbers
    updated_count = 0
    for i in range(entry_start, len(doc.paragraphs)):
        p = doc.paragraphs[i]
        text = (p.text or "").strip()
        
        if not text:
            break
        
        page_num = None
        
        # Check if it's a chapter heading
        m_chapter = re.match(r'(Chapter\s+\d+:.+)', text)
        if m_chapter:
            page_num = chapters.get(m_chapter.group(1))
        
        # Check if it's a section (indented entry like "1.1 Overview...")
        m_section = re.match(r'(\d+\.\d+)\s+(.+)', text)
        if m_section and not m_chapter:
            # Build lookup from section number prefix -> page
            section_num_to_page = {}
            for skey, spage in sections.items():
                if spage:
                    sm = re.match(r'(\d+\.\d+)\s+', skey)
                    if sm:
                        section_num_to_page[sm.group(1)] = spage
            page_num = section_num_to_page.get(m_section.group(1))
        
        # Also check for direct key match as fallback
        if page_num is None and re.match(r'^\d+\.\d+', text):
            page_num = sections.get(text)
        
        if page_num:
            # Update the paragraph with tab + page number
            for run in p.runs:
                current_text = run.text
                if '\t' in current_text:
                    # Replace existing tab placeholder with real page number
                    run.text = current_text.replace('\t', f'\t{page_num}')
                elif re.search(r'\t\d+$', current_text):
                    # Already has a tab+number at end (from previous pass) - replace it
                    run.text = re.sub(r'\t\d+$', f'\t{page_num}', current_text)
                else:
                    # Section/chapter entry without page number - append it
                    run.text = current_text + f'\t{page_num}'
            
            updated_count += 1
    
    if updated_count > 0:
        doc.save(str(DOCX_PATH))
        print(f"[PDF] Updated {updated_count} TOC entries with page numbers")
        return True
    else:
        print("[PDF] WARNING: No TOC entries were updated")
        return False


# ---------------------------------------------------------------------------
# Step 7 — Rebuild and verify
# ---------------------------------------------------------------------------
def rebuild_and_verify():
    """Re-run the full pipeline after TOC update."""
    
    # Remove old PDF so we get a fresh one
    if PDF_PATH.exists():
        PDF_PATH.unlink()
    
    # Regenerate HTML from updated DOCX
    convert_to_html()
    rel_map = extract_images()  # Re-extract (should be same)
    fix_html(rel_map)
    render_pdf()
    
    print("\n[PDF] === VERIFICATION ===")
    import fitz
    
    doc = fitz.open(str(PDF_PATH))
    total_pages = len(doc)
    print(f"  Total pages: {total_pages}")
    
    # Check front matter page breaks
    for i in range(min(10, total_pages)):
        text = doc[i].get_text()[:100]
        clean = ''.join(c if ord(c) < 128 else '?' for c in text)
        print(f"  Page {i+1}: {clean}")
    
    # Check TOC has page numbers
    toc_page = None
    for i in range(total_pages):
        if "Table of Contents" in doc[i].get_text():
            toc_page = i + 1
            break
    
    if toc_page:
        print(f"\n  TOC starts on page {toc_page}")
        # Show first few lines from TOC pages
        for pg_idx in range(toc_page - 1, min(toc_page + 2, total_pages)):
            text = doc[pg_idx].get_text()[:300]
            clean = ''.join(c if ord(c) < 128 else '?' for c in text)
            print(f"    TOC page {pg_idx+1}: {clean[:150]}...")
    
    # Check for blank pages (< 10 words)
    blank_pages = []
    underfilled = []
    for i in range(total_pages):
        text = doc[i].get_text()
        word_count = len(text.split())
        if word_count < 10:
            blank_pages.append(i + 1)
        elif word_count < 60:
            underfilled.append((i + 1, word_count))
    
    print(f"\n  Blank pages (< 10 words): {blank_pages}")
    print(f"  Under-filled pages (10-60 words): {underfilled[:10]}")
    
    doc.close()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main():
    os.makedirs(BUILD_DIR, exist_ok=True)
    
    print("=" * 60)
    print("PDF Builder Pipeline (with HTML-based TOC + page numbers)")
    print(f"  DOCX: {DOCX_PATH}")
    print(f"  Output: {PDF_PATH}")
    print("=" * 60)
    
    # Extract images
    rel_map = extract_images()
    
    # Convert DOCX → HTML
    convert_to_html()
    
    # Fix HTML: remove blockquotes, inject CSS, build TOC
    fix_html(rel_map)
    
    # Render PDF with two-pass approach for correct TOC page numbers
    render_pdf_with_toc()
    
    print("\n" + "=" * 60)
    print("PDF build complete!")
    if PDF_PATH.exists():
        size = os.path.getsize(PDF_PATH)
        import fitz
        doc = fitz.open(str(PDF_PATH))
        print(f"  Pages: {len(doc)}")
        print(f"  Size: {size:,} bytes")
        
        # Quick verification of TOC content on first TOC page
        toc_page = None
        for i in range(len(doc)):
            if "Table of Contents" in doc[i].get_text():
                toc_page = i + 1
                break
        if toc_page:
            print(f"\n  TOC starts on page {toc_page}")
            for pg_idx in range(toc_page - 1, min(toc_page + 2, len(doc))):
                text = doc[pg_idx].get_text()[:300]
                clean = ''.join(c if ord(c) < 128 else '?' for c in text)
                print(f"    TOC page {pg_idx+1}: {clean[:150]}...")
        
        doc.close()
    print("=" * 60)


if __name__ == "__main__":
    main()
