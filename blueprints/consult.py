import os
import json
import re
from flask import Blueprint, render_template, request, jsonify, session
from dotenv import load_dotenv
from groq import Groq
import psycopg2
import psycopg2.extras
from datetime import datetime

consult_bp = Blueprint('consult', __name__, template_folder='templates')

# Load environment variables
load_dotenv()

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

def create_admin_tables():
    """Create necessary tables for the admin consultation functionality if they don't exist."""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Create table for validating questions
            cur.execute('''
                CREATE TABLE IF NOT EXISTS questions_validation (
                    id SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'rejected')),
                    comments TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    verified_by VARCHAR(100)
                )
            ''')
            conn.commit()
            print("Admin tables created successfully")
    except Exception as e:
        print(f"Error creating admin tables: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# Routes for consultation page
@consult_bp.route('/consult', methods=['GET'])
def consult_page():
    """Render the admin consultation page."""
    # Get all questions from the database
    questions = get_all_questions()
    return render_template('consult.html', questions=questions)

def get_all_questions():
    """Get all questions from the database with their validation status."""
    conn = None
    questions = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('''
                SELECT id, question, status, comments, created_at, updated_at, verified_by
                FROM questions_validation
                ORDER BY created_at DESC
            ''')
            questions = cur.fetchall()
    except Exception as e:
        print(f"Error fetching questions: {e}")
    finally:
        if conn:
            conn.close()
    return questions

@consult_bp.route('/add_question', methods=['POST'])
def add_question():
    """Add a new question to be validated."""
    question = request.form.get('question')
    if not question:
        return jsonify({"status": "error", "message": "Question cannot be empty"})
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO questions_validation (question)
                VALUES (%s)
                RETURNING id
            ''', (question,))
            question_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({"status": "success", "message": "Question added successfully", "id": question_id})
    except Exception as e:
        print(f"Error adding question: {e}")
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": f"Error adding question: {str(e)}"})
    finally:
        if conn:
            conn.close()

@consult_bp.route('/update_question', methods=['POST'])
def update_question():
    """Update the status and comments for a question."""
    question_id = request.form.get('id')
    status = request.form.get('status')
    comments = request.form.get('comments')
    verified_by = request.form.get('verified_by')
    
    if not question_id or not status:
        return jsonify({"status": "error", "message": "Missing required fields"})
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('''
                UPDATE questions_validation
                SET status = %s, comments = %s, verified_by = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (status, comments, verified_by, question_id))
            conn.commit()
            return jsonify({"status": "success", "message": "Question updated successfully"})
    except Exception as e:
        print(f"Error updating question: {e}")
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": f"Error updating question: {str(e)}"})
    finally:
        if conn:
            conn.close()

@consult_bp.route('/delete_question', methods=['POST'])
def delete_question():
    """Delete a question from the database."""
    question_id = request.form.get('id')
    
    if not question_id:
        return jsonify({"status": "error", "message": "Missing question ID"})
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('DELETE FROM questions_validation WHERE id = %s', (question_id,))
            if cur.rowcount == 0:
                return jsonify({"status": "error", "message": "Question not found"})
            conn.commit()
            return jsonify({"status": "success", "message": "Question deleted successfully"})
    except Exception as e:
        print(f"Error deleting question: {e}")
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": f"Error deleting question: {str(e)}"})
    finally:
        if conn:
            conn.close()

# Call create tables function when the blueprint is registered
create_admin_tables()