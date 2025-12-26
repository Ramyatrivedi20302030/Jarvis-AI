from flask import Flask, render_template, request, jsonify
import threading
import traceback

# Import the core assistant functions
import main_fixed as core

app = Flask(__name__, template_folder='web_frontend/templates', static_folder='web_frontend/static')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.get_json(force=True)
        message = data.get('message', '')
        if not message:
            return jsonify({'error': 'empty message'}), 400
        # Call the assistant's ai_response function (synchronous)
        reply = core.ai_response(message)
        return jsonify({'reply': reply})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/history', methods=['GET'])
def api_history():
    try:
        return jsonify(core.history)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def run_server():
    app.run(host='0.0.0.0', port=5000, debug=True)


if __name__ == '__main__':
    run_server()
