import fitz  # PyMuPDF
import json
import nltk
from nltk.tokenize import sent_tokenize
import tiktoken
import sys

# Ensure NLTK resources are available
def ensure_nltk_resources():
    """Download required NLTK resources if not already present."""
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        print("Downloading NLTK punkt resource...")
        nltk.download('punkt', quiet=True)
    
    try:
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        print("Downloading NLTK punkt_tab resource...")
        nltk.download('punkt_tab', quiet=True)

def extract_text_from_pdf(pdf_path):
    """Extract text from all pages of a PDF using PyMuPDF."""
    try:
        # Open the PDF
        doc = fitz.open(pdf_path)
        text_by_page = []
        print(f"Extracting text from {len(doc)} pages...")

        # Iterate through pages
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text").strip()
            if text:  # Only include non-empty pages
                text_by_page.append({"page": page_num + 1, "text": text})
            else:
                print(f"Warning: Page {page_num + 1} is empty or contains no extractable text.")
        
        doc.close()
        if not text_by_page:
            print("Error: No text extracted from PDF.")
            return []
        return text_by_page
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return []

def estimate_tokens(text, encoding_name="cl100k_base"):
    """Estimate the number of tokens in a text string using tiktoken."""
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text, allowed_special={"<|endoftext|>"}))
    except Exception as e:
        print(f"Error estimating tokens: {e}")
        return 0

def chunk_text(text_by_page, max_tokens=1000, overlap=50):
    encoding = tiktoken.get_encoding("cl100k_base")
    chunks = []
    current_chunk_tokens = []
    current_chunk_text = []
    chunk_id = 1
    start_page = None

    for page in text_by_page:
        sentences = sent_tokenize(page["text"])
        for sentence in sentences:
            tokens = encoding.encode(sentence)
            if len(current_chunk_tokens) + len(tokens) > max_tokens:
                # Save current chunk
                chunk_text = encoding.decode(current_chunk_tokens)
                chunks.append({
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "token_count": len(current_chunk_tokens),
                    "start_page": start_page,
                    "end_page": page["page"]
                })
                chunk_id += 1
                # Start new chunk with overlap
                overlap_tokens = current_chunk_tokens[-overlap:] if overlap < len(current_chunk_tokens) else current_chunk_tokens
                current_chunk_tokens = overlap_tokens + tokens
                current_chunk_text = [encoding.decode(overlap_tokens)] + [sentence]
                start_page = page["page"]
            else:
                current_chunk_tokens.extend(tokens)
                current_chunk_text.append(sentence)
                if start_page is None:
                    start_page = page["page"]

    # Add last chunk
    if current_chunk_tokens:
        chunk_text = encoding.decode(current_chunk_tokens)
        chunks.append({
            "chunk_id": chunk_id,
            "text": chunk_text,
            "token_count": len(current_chunk_tokens),
            "start_page": start_page,
            "end_page": text_by_page[-1]["page"]
        })
    return chunks

    """Chunk text into segments of approximately max_tokens, respecting sentence boundaries."""
    chunks = []
    current_chunk = ""
    current_token_count = 0
    chunk_id = 1

    for page in text_by_page:
        page_text = page["text"]
        if not page_text:
            continue  # Skip empty pages
        
        try:
            # Split text into sentences for semantic chunking
            sentences = sent_tokenize(page_text)
        except Exception as e:
            print(f"Error tokenizing page {page['page']}: {e}")
            sentences = [page_text]  # Fallback to whole page text if tokenization fails
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            sentence_tokens = estimate_tokens(sentence)
            # Check if adding the sentence exceeds the max token limit
            if current_token_count + sentence_tokens > max_tokens:
                # Save the current chunk if it contains text
                if current_chunk:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "text": current_chunk.strip(),
                        "token_count": current_token_count,
                        "start_page": text_by_page[0]["page"] if chunks else page["page"],
                        "end_page": page["page"]
                    })
                    chunk_id += 1
                # Start a new chunk with the current sentence
                current_chunk = sentence
                current_token_count = sentence_tokens
            else:
                # Add sentence to current chunk
                current_chunk += " " + sentence
                current_token_count += sentence_tokens
        
        # Add a page break marker to preserve context
        page_marker = f" [Page {page['page']}]"
        current_chunk += page_marker
        current_token_count += estimate_tokens(page_marker)
    
    # Save the final chunk if it contains text
    if current_chunk and current_token_count > 0:
        chunks.append({
            "chunk_id": chunk_id,
            "text": current_chunk.strip(),
            "token_count": current_token_count,
            "start_page": text_by_page[0]["page"] if chunks else text_by_page[-1]["page"],
            "end_page": text_by_page[-1]["page"]
        })
    
    return chunks

def save_chunks_to_json(chunks, output_path):
    """Save chunks to a JSON file."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        print(f"Chunks saved to {output_path}")
    except Exception as e:
        print(f"Error saving chunks: {e}")

def main(pdf_path, output_json_path):
    """Main function to extract and chunk PDF text."""
    # Ensure NLTK resources are available
    ensure_nltk_resources()
    
    # Step 1: Extract text
    print("Starting text extraction...")
    text_by_page = extract_text_from_pdf(pdf_path)
    if not text_by_page:
        print("Exiting due to extraction failure.")
        sys.exit(1)
    
    # Step 2: Chunk the text
    print("Chunking text...")
    chunks = chunk_text(text_by_page, max_tokens=50000)
    
    # Step 3: Save chunks to JSON
    print(f"Generated {len(chunks)} chunks.")
    total_tokens = sum(chunk["token_count"] for chunk in chunks)
    print(f"Total estimated tokens: {total_tokens}")
    save_chunks_to_json(chunks, output_json_path)

if __name__ == "__main__":
    pdf_path = "2024_Reglementation_Bancaire.pdf"  # Replace with your PDF file path
    output_json_path = "chunksNew.json"  # Output file for chunks
    main(pdf_path, output_json_path)