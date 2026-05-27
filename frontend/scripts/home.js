const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');

let conversationHistory = [];

sendBtn.addEventListener('click', handleSendMessage);

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        handleSendMessage();
    }
});

async function handleSendMessage() {
    const messageText = userInput.value.trim();
    if (!messageText) return;
    
    const welcomeContainer = document.getElementById('welcome-container');
    if (welcomeContainer) {
        welcomeContainer.remove(); 
    }

    userInput.value = '';

    appendMessage(messageText, 'user');

    conversationHistory.push({ role: 'user', content: messageText });

    const aiBubble = appendMessage('', 'assistant');
    aiBubble.classList.add('streaming');

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                history: conversationHistory 
            })
        });        
        if (!response.ok) throw new Error('Network response was not ok');

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');

        let done = false;
        let completeAiResponse = '';
        
        while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            
            if (value) {
                const chunkStr = decoder.decode(value, { stream: !done });
                
                const text = parseSSE(chunkStr);

                completeAiResponse += text;
                aiBubble.innerHTML = marked.parse(completeAiResponse);
                chatBox.scrollTop = chatBox.scrollHeight;
            }
        }
        aiBubble.classList.remove('streaming');
        conversationHistory.push({ role: 'assistant', content: completeAiResponse });

    } catch (error) {
        console.error('Streaming error:', error);
        aiBubble.classList.remove('streaming');
        aiBubble.textContent = '⚠️ Sorry, an error occurred while processing your request.';
    }
}

function parseSSE(chunkStr) {
    const lines = chunkStr.split('\n');
    let pulledText = '';

    for (const line of lines) {
        if (line.startsWith('data: ')) {
            pulledText += line.slice(6); 
        }
    }
    
    return pulledText;
}

function appendMessage(text, sender) {
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', `${sender}-message`);
    
    if (text) {
        messageElement.innerHTML = marked.parse(text);
    }
    
    chatBox.appendChild(messageElement);
    chatBox.scrollTop = chatBox.scrollHeight;
    return messageElement;
}
