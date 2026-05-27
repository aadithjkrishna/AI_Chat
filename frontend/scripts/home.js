const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const modelSelect = document.getElementById('model-select'); // 🤖 Hooked into the model dropdown

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

    // 🎯 Grab the active model selection dynamically on every submission
    const selectedModel = modelSelect ? modelSelect.value : 'llama3.2:3b';

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                history: conversationHistory,
                model: selectedModel // 🚀 Injected dynamic selection into the backend payload!
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

// Append this tracking code inside the try block of your existing loadAvailableModels() function in home.js
async function loadAvailableModels() {
    const selectElement = document.getElementById('model-select');
    const headerTitle = document.getElementById('chat-header-title'); // Grab the header text reference
    if (!selectElement) return;

    try {
        const response = await fetch('/api/models');
        const data = await response.json();

        selectElement.innerHTML = '';

        data.models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            selectElement.appendChild(option);
        });

        // 🚀 Set the initial header text to match the default selected model right away
        if (headerTitle && selectElement.value) {
            headerTitle.textContent = selectElement.value;
        }

        // 🔄 Watch for the user changing the dropdown selection, and update the header on the fly!
        selectElement.addEventListener('change', () => {
            if (headerTitle) {
                headerTitle.textContent = selectElement.value;
            }
        });

    } catch (error) {
        console.error("Failed to load models:", error);
        selectElement.innerHTML = '<option value="llama3.2:3b">llama3.2:3b (Fallback)</option>';
        if (headerTitle) headerTitle.textContent = "llama3.2:3b";
    }
}

// Fire the function when the page boots up
window.addEventListener('DOMContentLoaded', loadAvailableModels);