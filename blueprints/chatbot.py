import os
import json
import re
from flask import Blueprint, render_template, request, jsonify, session
from dotenv import load_dotenv
from groq import Groq
import psycopg2
import psycopg2.extras
from datetime import datetime

chatbot_bp = Blueprint('chatbot', __name__, template_folder='templates')

# Load environment variables
load_dotenv()
api_key = os.getenv("GROQ_KEY")
client = Groq(api_key=api_key)
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            cursor_factory=psycopg2.extras.DictCursor
        )
        print("Database connection successful")
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise
    

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

# Get predefined Q&A pairs from database
def get_predefined_qa():
    conn = None
    qa_pairs = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT qs, rep, reference FROM questions_reponses")
            qa_pairs = cur.fetchall()
        print(f"Retrieved {len(qa_pairs)} Q&A pairs from database")
    except Exception as e:
        print(f"Error fetching Q&A pairs: {e}")
    finally:
        if conn:
            conn.close()
    return qa_pairs

@chatbot_bp.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    
    # Initialize conversation history if it doesn't exist
    if 'conversation_history' not in session:
        session['conversation_history'] = []
    
    # Get conversation history
    conversation_history = session.get('conversation_history', [])
    
    # Add user message to history
    conversation_history.append({"role": "user", "content": user_message})
    
    # Limit history to last 10 messages to prevent context overflow
    if len(conversation_history) > 20:
        conversation_history = conversation_history[-20:]
    
    # Get predefined Q&A pairs from the database
    qa_pairs = get_predefined_qa()
    
    # Format Q&A pairs for the prompt
    qa_content = "### QUESTIONS ET RÉPONSES PRÉDÉFINIES\n"
    for pair in qa_pairs:
        question = pair[0]
        answer = pair[1]
        reference = pair[2] if len(pair) > 2 and pair[2] else ""
        
        qa_content += f"Q: {question}\nR: {answer}\n"
        if reference:
            qa_content += f"Ref: {reference}\n"
        qa_content += "\n"
    
    # Check if this is likely a greeting or simple interaction
    greeting_keywords = ["bonjour", "salut", "hello", "bonsoir", "salam", "merci", "coucou", "hey", "hi"]
    is_greeting = any(keyword in user_message.lower() for keyword in greeting_keywords) and len(user_message.split()) < 5
    
    # Prepare messages for API call with system prompt and conversation history
    messages = [
        {
            "role": "system",
            "content": f"""
Vous êtes l'assistant virtuel officiel de la Banque Centrale de Tunisie (BCT), un expert financier précis et fiable.

### RÈGLE ABSOLUE
Répondez avec précision aux questions concernant la réglementation bancaire tunisienne. Si vous n'êtes pas certain d'une information, indiquez clairement: "Je ne dispose pas d'informations suffisantes sur ce sujet spécifique."

### MÉMOIRE DE CONVERSATION
- Utilisez le contexte des échanges précédents pour fournir des réponses cohérentes.
- Si l'utilisateur fait référence à une question ou information précédente, assurez-vous de maintenir la continuité.
- Si l'utilisateur pose une question de suivi ou demande une clarification, référez-vous à vos réponses antérieures.

{qa_content}

### RÈGLE DE CORRESPONDANCE EXACTE
- Si la question de l'utilisateur correspond EXACTEMENT ou est TRÈS SIMILAIRE à l'une des questions prédéfinies ci-dessus, vous DEVEZ fournir EXACTEMENT la réponse associée, mot pour mot, sans aucune modification ni ajout.
- N'ajoutez PAS d'introductions, de conclusions ou d'explications supplémentaires pour les correspondances exactes.
- Ne reformulez PAS la réponse prédéfinie, utilisez-la TELLE QUELLE.
- En cas de correspondance, votre réponse doit être IDENTIQUE au texte qui suit "R:" dans la paire question-réponse correspondante.
- Si une référence "Ref:" est présente pour la question correspondante, VOUS DEVEZ l'inclure à la fin de votre réponse sous format: "### Référence: [contenu de la référence]"
- IMPORTANT: Toujours fournir la réponse complète, pas uniquement la référence. Ne jamais omettre le contenu de la réponse.

### RÉPONSES CRÉATIVES POUR QUESTIONS SANS CORRESPONDANCE
- Pour les questions qui ne correspondent pas aux Q&A prédéfinies: utilisez vos connaissances générales sur la finance et le système bancaire pour fournir une réponse complète, précise et détaillée.
- Soyez créatif et utilisez votre raisonnement pour construire une réponse informative.
- Pour les concepts bancaires et financiers, fournissez des définitions claires et des exemples si possible.
- Si la question porte sur un aspect du système bancaire tunisien dont vous connaissez les principes généraux, appliquez ces principes sans spéculer sur les détails spécifiques à la Tunisie.
- N'hésitez pas à utiliser votre expertise sur les concepts bancaires généraux, même si la question n'est pas dans la base de données.

### INTERACTIONS CONVERSATIONNELLES
- Répondez aux salutations de manière chaleureuse.
- Pour les questions techniques, maintenez un ton professionnel et formel.
- Si vous ne pouvez pas répondre avec certitude, proposez des informations générales sur le sujet.

### FORMATAGE DES RÉPONSES
- Utilisez "### Titre" pour les sections principales.
- Utilisez des tirets (-) pour les listes.
- Utilisez des séparateurs (---) entre les sections principales.
- N'utilisez JAMAIS les symboles # ou ## seuls.
"""
        }
    ]
    
    # Add previous conversation history (excluding the latest user message which we'll add separately)
    # Convert previous messages to the format expected by the API
    for msg in conversation_history[:-1]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Add the latest user message
    messages.append({"role": "user", "content": user_message})
    
    # Analyze if the question is likely in our database
    question_in_database = False
    for pair in qa_pairs:
        question = pair[0].lower()
        user_msg_lower = user_message.lower()
        # Check for significant overlap or similarity
        if (question in user_msg_lower or user_msg_lower in question or
            any(term in user_msg_lower for term in question.split() if len(term) > 4)):
            question_in_database = True
            break
    
    # Adjust temperature based on whether the question is likely in our database
    # Higher temperature for more creativity when question is not in database
    temp_value = 0.3 if question_in_database else 0.7
    
    chat_completion = client.chat.completions.create(
        messages=messages,
        model="gemma2-9b-it",
        temperature=temp_value  # More creativity for questions not in database
    )
    
    response = chat_completion.choices[0].message.content
    
    # Add bot response to conversation history
    conversation_history.append({"role": "assistant", "content": response})
    
    # Update session with new conversation history
    session['conversation_history'] = conversation_history
    
    # Skip post-processing only for simple greetings
    if is_greeting:
        return jsonify({"response": response})
    
    # For detailed responses, apply our formatting rules
    lines = response.split('\n')
    filtered_lines = []
    
    for i, line in enumerate(lines):
        # Skip the first non-empty line if it looks like a title (but not for simple responses)
        if i == 0 and line.strip() and not line.startswith('###'):
            continue
        
        # Keep all lines, including reference sections (removed the skip_section logic)
        filtered_lines.append(line)
    
    # Remove any leading empty lines
    while filtered_lines and not filtered_lines[0].strip():
        filtered_lines.pop(0)
        
    response = '\n'.join(filtered_lines)
    
    # Check if the response only contains a reference without the actual answer
    if re.match(r'^(?:\s*|.*?)### Référence:', response, re.DOTALL) and not any(line for line in filtered_lines if line.strip() and not line.startswith('###')):
        # If response contains only a reference, look in the database for a proper answer
        for pair in qa_pairs:
            if pair[2] and pair[2] in response:  # If reference matches
                response = pair[1] + "\n\n### Référence: " + pair[2]
                break
    
    formatted_response = format_response(response)
    
    return jsonify({"response": formatted_response})

