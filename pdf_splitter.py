import streamlit as st
import fitz  # PyMuPDF
import re
import os
import io
import zipfile
import tempfile
import shutil


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="PDF Table Splitter",
    page_icon="📄",
    layout="wide"
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown("""
<style>

.main-title {
    font-size: 38px;
    font-weight: 700;
    margin-bottom: 5px;
}

.subtitle {
    font-size: 17px;
    color: #666;
    margin-bottom: 30px;
}

.upload-box {
    padding: 20px;
    border-radius: 12px;
    border: 1px solid #ddd;
    background-color: #fafafa;
}

.success-box {
    padding: 20px;
    border-radius: 10px;
    background-color: #eaf7ea;
    border: 1px solid #b7dfb7;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# TITLE
# ============================================================

st.markdown(
    '<div class="main-title">📄 PDF Table Splitter</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">'
    'Upload a PDF and automatically split it into individual '
    'table PDFs using the table numbers.'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# FILE UPLOAD
# ============================================================

uploaded_file = st.file_uploader(
    "Upload your PDF",
    type=["pdf"],
    help="Upload the PDF containing numbered tables."
)


# ============================================================
# HELPER: CLEAN FILE NAME
# ============================================================

def clean_filename(text):

    text = re.sub(
        r'[<>:"/\\|?*]',
        '',
        text
    )

    text = re.sub(
        r'\s+',
        '_',
        text
    )

    text = re.sub(
        r'_+',
        '_',
        text
    )

    return text[:120].strip("_")


# ============================================================
# DETECT TABLE HEADINGS
# ============================================================

def detect_table_headings(page):

    """
    Detect headings such as:

    TABLE 1: STATE-WISE GROSS ENROLMENT RATIO

    TABLE 7: STATE-WISE LIFE EXPECTANCY (Concld.)
    """

    text = page.get_text("text")

    matches = []

    # --------------------------------------------------------
    # Find TABLE number + title
    # --------------------------------------------------------

    pattern = re.compile(
        r'TABLE\s+(\d+)\s*:\s*(.*)',
        re.IGNORECASE
    )

    for match in pattern.finditer(text):

        table_number = int(match.group(1))

        title = match.group(2).strip()

        # Remove continuation marker
        title = re.sub(
            r'\s*\(Concld\.?\)',
            '',
            title,
            flags=re.IGNORECASE
        )

        matches.append({
            "table_number": table_number,
            "title": title
        })

    return matches


# ============================================================
# GET TABLES FROM PDF
# ============================================================

def detect_tables(pdf_bytes, progress_bar):

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    tables = {}

    total_pages = len(document)

    for page_index in range(total_pages):

        page = document[page_index]

        page_number = page_index + 1

        detected = detect_table_headings(page)

        # ----------------------------------------------------
        # If this page contains table headings
        # ----------------------------------------------------

        for table in detected:

            table_number = table["table_number"]

            title = table["title"]

            if table_number not in tables:

                tables[table_number] = {
                    "number": table_number,
                    "title": title,
                    "pages": []
                }

            if page_number not in tables[
                table_number
            ]["pages"]:

                tables[
                    table_number
                ]["pages"].append(
                    page_number
                )

        # ----------------------------------------------------
        # Progress
        # ----------------------------------------------------

        progress_bar.progress(
            (page_index + 1) / total_pages
        )

    document.close()

    return tables


# ============================================================
# CREATE TABLE PDF
# ============================================================

def create_table_pdf(
    original_document,
    pages,
    output_path
):

    output_document = fitz.open()

    for page_number in pages:

        output_document.insert_pdf(
            original_document,
            from_page=page_number - 1,
            to_page=page_number - 1
        )

    output_document.save(
        output_path
    )

    output_document.close()


# ============================================================
# PROCESS PDF
# ============================================================

def process_pdf(pdf_bytes):

    temp_dir = tempfile.mkdtemp(
        prefix="pdf_tables_"
    )

    output_dir = os.path.join(
        temp_dir,
        "tables"
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Open original PDF
    # --------------------------------------------------------

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    # --------------------------------------------------------
    # Detect tables
    # --------------------------------------------------------

    progress = st.progress(
        0,
        text="Scanning PDF..."
    )

    tables = detect_tables(
        pdf_bytes,
        progress
    )

    progress.empty()

    # --------------------------------------------------------
    # Create individual PDFs
    # --------------------------------------------------------

    created_files = []

    table_numbers = sorted(
        tables.keys()
    )

    creation_progress = st.progress(
        0,
        text="Creating table PDFs..."
    )

    total_tables = len(
        table_numbers
    )

    for index, table_number in enumerate(
        table_numbers
    ):

        table_info = tables[
            table_number
        ]

        title = table_info["title"]

        pages = table_info["pages"]

        # ----------------------------------------------------
        # Create filename
        # ----------------------------------------------------

        safe_title = clean_filename(
            title
        )

        if safe_title:

            filename = (
                f"Table_{table_number:03d}_"
                f"{safe_title}.pdf"
            )

        else:

            filename = (
                f"Table_{table_number:03d}.pdf"
            )

        output_path = os.path.join(
            output_dir,
            filename
        )

        # ----------------------------------------------------
        # Create PDF
        # ----------------------------------------------------

        create_table_pdf(
            document,
            pages,
            output_path
        )

        created_files.append({
            "number": table_number,
            "title": title,
            "pages": pages,
            "filename": filename,
            "path": output_path
        })

        creation_progress.progress(
            (index + 1) / total_tables,
            text=(
                f"Creating table "
                f"{table_number}..."
            )
        )

    creation_progress.empty()

    document.close()

    # --------------------------------------------------------
    # Create ZIP in memory
    # --------------------------------------------------------

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(
        zip_buffer,
        "w",
        zipfile.ZIP_DEFLATED
    ) as zip_file:

        for table in created_files:

            zip_file.write(
                table["path"],
                arcname=table["filename"]
            )

    zip_buffer.seek(0)

    return (
        zip_buffer.getvalue(),
        created_files,
        temp_dir
    )


# ============================================================
# MAIN APP
# ============================================================

if uploaded_file:

    st.markdown("---")

    # --------------------------------------------------------
    # File information
    # --------------------------------------------------------

    st.subheader("📄 Uploaded PDF")

    file_size_mb = (
        uploaded_file.size
        / (1024 * 1024)
    )

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            f"**File:** {uploaded_file.name}"
        )

    with col2:

        st.write(
            f"**Size:** {file_size_mb:.2f} MB"
        )

    # --------------------------------------------------------
    # Process button
    # --------------------------------------------------------

    if st.button(
        "🚀 Split PDF into Tables",
        type="primary",
        use_container_width=True
    ):

        pdf_bytes = uploaded_file.getvalue()

        try:

            (
                zip_bytes,
                tables,
                temp_dir
            ) = process_pdf(
                pdf_bytes
            )

            # ------------------------------------------------
            # Results
            # ------------------------------------------------

            st.markdown("---")

            st.success(
                f"✅ Successfully detected "
                f"{len(tables)} tables!"
            )

            # ------------------------------------------------
            # Summary
            # ------------------------------------------------

            st.subheader(
                "📊 Split Results"
            )

            # ------------------------------------------------
            # Table information
            # ------------------------------------------------

            for table in tables:

                pages = table["pages"]

                if len(pages) == 1:

                    page_text = (
                        f"Page {pages[0]}"
                    )

                else:

                    page_text = (
                        f"Pages {pages[0]} "
                        f"– {pages[-1]}"
                    )

                with st.expander(
                    f"Table {table['number']}: "
                    f"{table['title']}"
                ):

                    st.write(
                        f"**Pages:** {page_text}"
                    )

                    st.write(
                        f"**Output:** "
                        f"{table['filename']}"
                    )

            # ------------------------------------------------
            # Download
            # ------------------------------------------------

            st.markdown("---")

            st.subheader(
                "📦 Download"
            )

            st.download_button(
                label=(
                    "⬇️ Download All Tables "
                    "as ZIP"
                ),
                data=zip_bytes,
                file_name=(
                    "split_tables.zip"
                ),
                mime="application/zip",
                type="primary",
                use_container_width=True
            )

            # ------------------------------------------------
            # Cleanup
            # ------------------------------------------------

            shutil.rmtree(
                temp_dir,
                ignore_errors=True
            )

        except Exception as e:

            st.error(
                f"❌ Error while processing PDF:\n\n{e}"
            )

            st.exception(e)


else:

    st.info(
        "👆 Upload a PDF above to get started."
    )

    st.markdown("""
    ### How it works

    **1. Upload PDF**

    Select your PDF containing numbered tables.

    **2. Detect tables**

    The application looks for headings such as:

    `TABLE 1: ...`

    `TABLE 2: ...`

    `TABLE 3: ...`

    **3. Handle multi-page tables**

    If `TABLE 7` appears on multiple pages, all those pages
    are placed into the same `Table_007.pdf`.

    **4. Create ZIP**

    All individual table PDFs are placed into one ZIP file.

    **5. Download**

    Click **Download All Tables as ZIP**.
    """)