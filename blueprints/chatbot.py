import os
import json
import re
from flask import Blueprint, render_template, request, jsonify
from dotenv import load_dotenv
from groq import Groq

chatbot_bp = Blueprint('chatbot', __name__, template_folder='templates')

# Load environment variables
load_dotenv()
api_key = os.getenv("GROQ_KEY")
client = Groq(api_key=api_key)

# Load document chunks data
def load_chunks():
    chunks_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chunksNew.json')
    with open(chunks_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# Initialize chunks data
chunks_data = load_chunks()

# Format chunks as context string
chunks_context = "Knowledge Base Information:\n"
for i, chunk in enumerate(chunks_data):
    chunk_id = chunk.get("chunk_id", i+1)
    end_page = chunk.get("end_page", "unknown")
    content = chunk.get("content", "No content available")
    chunks_context += f"Document section {chunk_id} (up to page {end_page}):\n{content}\n\n"

def format_response(text):
    """Format the response with proper Markdown styling"""
    # First pass: Eliminate any standalone # characters and excessive whitespace
    lines = text.split('\n')
    formatted_lines = []
    
    skip_line = False
    prev_was_empty = False
    prev_was_heading = False
    
    for i, line in enumerate(lines):
        # Skip this line if marked
        if skip_line:
            skip_line = False
            continue
            
        # Completely remove lines that only contain #
        if re.match(r'^\s*#\s*$', line):
            continue
            
        # Convert # followed by text to proper heading
        if re.match(r'^\s*#\s+\w', line):
            line = re.sub(r'^\s*#\s+', '### ', line)
        
        # Check if current line is a heading
        is_heading = line.strip().startswith('###')
        
        # Control spacing - don't add multiple empty lines and no empty lines before headings
        if line.strip() == '':
            if prev_was_empty or prev_was_heading:
                continue
            prev_was_empty = True
            prev_was_heading = False
        else:
            if is_heading and prev_was_empty:
                # Remove the last empty line before a heading
                if formatted_lines and not formatted_lines[-1].strip():
                    formatted_lines.pop()
            prev_was_empty = False
            prev_was_heading = is_heading
        
        formatted_lines.append(line)
    
    # Rejoin with controlled line breaks
    text = '\n'.join(formatted_lines)
    
    # Replace ** bold patterns with proper heading or styling
    text = re.sub(r'\*\*(.*?)\s*:\*\*', r'### \1:', text)
    
    # Add horizontal separators between major sections (but not after the title)
    sections = re.split(r'(?=\n### )', text)
    if len(sections) > 1:
        title = sections[0]
        rest = sections[1:]
        with_separators = [title]
        for section in rest:
            # Ensure exactly one newline before the separator
            with_separators.append(f"\n---\n{section.lstrip()}")
        text = ''.join(with_separators)
    
    # Final cleanup: Ensure no excessive newlines
    text = re.sub(r'\n{2,}', '\n\n', text)  # Limit to max 2 consecutive newlines
    
    # Special handling for spacing around headings
    text = re.sub(r'\n\n### ', '\n### ', text)  # Only one newline before headings
    
    return text

@chatbot_bp.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    
    # Check if this is likely a greeting or simple interaction
    greeting_keywords = ["bonjour", "salut", "hello", "bonsoir", "salam", "merci", "coucou", "hey", "hi"]
    is_greeting = any(keyword in user_message.lower() for keyword in greeting_keywords) and len(user_message.split()) < 5
    
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": f"""
Vous êtes l'assistant virtuel officiel de la Banque Centrale de Tunisie (BCT). Votre rôle est de fournir des réponses précises et professionnelles, tout en étant chaleureux et engageant.

### INTERACTIONS CONVERSATIONNELLES
- Répondez TOUJOURS aux salutations (bonjour, salut, bonsoir, etc.) de manière chaleureuse.
- Engagez la conversation en posant des questions pertinentes quand approprié.
- Adaptez votre ton en fonction du contexte - formel pour les questions techniques, plus convivial pour les échanges simples.
- Si l'utilisateur vous remercie, répondez poliment (ex: "Je vous en prie, c'est avec plaisir").
- Pour les questions simples ou les salutations, répondez de manière concise et naturelle, sans structure formelle.

### FORMATAGE OBLIGATOIRE (pour les réponses informatives uniquement)
- N'UTILISEZ JAMAIS LE CARACTÈRE # ISOLÉ. Pour les titres, utilisez uniquement "### Titre".
- NE LAISSEZ PAS DE LIGNES VIDES EXCESSIVES entre les sections.
- Pour les séparations, n'utilisez PAS de ligne contenant uniquement # ou ##.
- Pour les listes, utilisez toujours des tirets (-).
- Supprimez tout espace excessif dans votre réponse.
- NE RÉPÉTEZ PAS le titre du document au début de votre réponse.
- N'INCLUEZ PAS de section "Référence" à la fin de votre réponse.

### STRUCTURE POUR LES RÉPONSES INFORMATIVES
1. Commencez directement par une introduction professionnelle qui explique le sujet.
2. Continuez avec les sections importantes, en utilisant "### Nom de section".
3. Entre les sections, ne laissez qu'UNE SEULE ligne vide.
4. Pour les listes, utilisez des tirets (-) sans espace excessif.

### EXEMPLES DE RÉPONSES

# Exemple 1: Réponse à une salutation
Bonjour ! Je suis ravi de vous accueillir. Comment puis-je vous aider aujourd'hui concernant les services ou informations de la Banque Centrale de Tunisie ?

# Exemple 2: Réponse informative
La circulaire n°91-24 du 17 décembre 1991 est une directive émise par la Banque Centrale de Tunisie qui établit des règles importantes.

### Objectif de la circulaire
Contenu de la section.

### Principales dispositions
- Premier point
- Deuxième point

IMPORTANT: N'utilisez JAMAIS le symbole # seul ou le double dièse ##. Utilisez uniquement ### pour les titres.

Notre documentation contient les sections suivantes:
{chunks_context}
"""
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        model="llama-3.1-8b-instant",
        temperature=0.7  # Balanced between creativity and consistency
    )
    
    response = chat_completion.choices[0].message.content
    
    # Skip post-processing for greetings and simple interactions
    if is_greeting or len(response) < 100:
        return jsonify({"response": response})
    
    # For detailed responses, apply our formatting rules
    lines = response.split('\n')
    filtered_lines = []
    skip_section = False
    
    for i, line in enumerate(lines):
        # Skip the first non-empty line if it looks like a title (but not for simple responses)
        if i == 0 and line.strip() and not line.startswith('###'):
            continue
            
        # Check for reference section headers
        if line.strip().lower().startswith('### référence') or line.strip().lower().startswith('### reference'):
            skip_section = True
            continue
            
        if skip_section:
            continue
            
        filtered_lines.append(line)
    
    # Remove any leading empty lines
    while filtered_lines and not filtered_lines[0].strip():
        filtered_lines.pop(0)
        
    response = '\n'.join(filtered_lines)
    formatted_response = format_response(response)
    
    return jsonify({"response": formatted_response})

