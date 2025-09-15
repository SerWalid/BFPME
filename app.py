from flask import Flask, render_template
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure secret key for sessions
secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    print("WARNING: No SECRET_KEY environment variable found. Using a default key for development only.")
    secret_key = 'bfpme-development-key-change-in-production'
    
app.secret_key = secret_key

from blueprints.chatbot import chatbot_bp
from blueprints.consult import consult_bp

app.register_blueprint(chatbot_bp)
app.register_blueprint(consult_bp)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/chatbot')
def chatbot_page():
    return render_template('chatbot.html')

if __name__ == '__main__':
    app.run()
