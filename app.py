from flask import Flask, render_template

app = Flask(__name__)


from blueprints.chatbot import chatbot_bp
app.register_blueprint(chatbot_bp)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/chatbot')
def chatbot_page():
    return render_template('chatbot.html')

if __name__ == '__main__':
    app.run()
