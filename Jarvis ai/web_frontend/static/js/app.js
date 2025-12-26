document.addEventListener('DOMContentLoaded', function() {
    const chat = document.getElementById('chat');
    const input = document.getElementById('message');
    const send = document.getElementById('send');

    function appendMessage(role, text) {
        const m = document.createElement('div');
        m.className = 'message ' + role;
        m.textContent = text;
        chat.appendChild(m);
        chat.scrollTop = chat.scrollHeight;
    }

    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;
        appendMessage('user', text);
        input.value = '';
        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });
            const data = await res.json();
            if (data.reply !== undefined) {
                appendMessage('assistant', data.reply || '(no response)');
            } else if (data.error) {
                appendMessage('assistant', 'Error: ' + data.error);
            } else {
                appendMessage('assistant', 'Unexpected response');
            }
        } catch (e) {
            appendMessage('assistant', 'Network error: ' + e.message);
        }
    }

    send.addEventListener('click', sendMessage);
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') sendMessage();
    });
});