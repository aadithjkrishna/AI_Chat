const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const modelSelect = document.getElementById('model-select'); // 🤖 Hooked into the model dropdown
const fileInput = document.getElementById('file-input');
const uploadBtn = document.getElementById('upload-btn');
let attachedFileBase64 = null;
let attachedFileName = null;

let conversationHistory = [];

sendBtn.addEventListener('click', handleSendMessage);

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        handleSendMessage();
    }
});

uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', async (e) => {
    const file = e.target.value ? e.target.files[0] : null;
    if (!file) return;

    attachedFileName = file.name;
    const extension = file.name.split('.').pop().toLowerCase();

    if (['jpg', 'jpeg', 'png'].includes(extension)) {
        // Handle images inline via Base64 conversion
        const reader = new FileReader();
        reader.onload = function (event) {
            attachedFileBase64 = event.target.result.split(',')[1]; // Strip prefix data URL metadata
            alert(`Image "${file.name}" attached successfully!`);
        };
        reader.readAsDataURL(file);
    } else {
        // Handle documents/code via background RAG indexing ingestion
        const formData = new FormData();
        formData.append("file", file);
        
        try {
            uploadBtn.textContent = "⏳";
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            if (response.ok) {
                alert(`File "${file.name}" ingested into local RAG store!`);
            } else {
                alert(`Ingestion error: ${data.detail}`);
            }
        } catch (err) {
            console.error(err);
        } finally {
            uploadBtn.textContent = "📎";
        }
    }
});

async function handleSendMessage() {
    const messageText = userInput.value.trim();
    
    // Abort if the user hasn't typed anything AND hasn't attached an image
    if (!messageText && !attachedFileBase64) return;

    // Clear the welcome splash screen if it's still there
    const welcomeContainer = document.getElementById('welcome-container');
    if (welcomeContainer) {
        welcomeContainer.remove();
    }

    userInput.value = '';

    // Determine what to show in the user's chat bubble
    let displayMessage = messageText;
    if (attachedFileName && !messageText) {
        displayMessage = `*[Attached Image: ${attachedFileName}]*`;
    } else if (attachedFileName && messageText) {
        displayMessage = `*[Attached Image: ${attachedFileName}]*\n\n${messageText}`;
    }
    
    // Render user message to the UI
    appendMessage(displayMessage, 'user');

    // Build the message object for the API payload
    const nextMessage = { role: 'user', content: messageText || "Analyze this image." };
    if (attachedFileBase64) {
        nextMessage.images = [attachedFileBase64]; // Inject the base64 string for vision models
    }

    conversationHistory.push(nextMessage);

    // Create the empty assistant bubble with a blinking cursor/streaming state
    const aiBubble = appendMessage('', 'assistant');
    aiBubble.classList.add('streaming');

    let selectedModel = 'llama3.2:3b'; // Standard fallback
    
    const modelSelect = document.getElementById('model-select');
    if (modelSelect) {
        selectedModel = modelSelect.value; // Use dropdown if it exists
    } else if (attachedFileBase64) {
        // If there is no dropdown, but an image is attached, force the vision model!
        selectedModel = 'llama3.2-vision'; 
        console.log("Image detected: Auto-switching to vision model.");
    }

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                history: conversationHistory,
                model: selectedModel
            })
        });

        if (!response.ok) {
            throw new Error(`Server responded with status ${response.status}`);
        }

        // --- Stream Reading Logic ---
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let aiFullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            
            // Fastapi StreamingResponse sends lines starting with "data: "
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataText = line.replace('data: ', '');
                    aiFullResponse += dataText;
                    
                    // Render markdown dynamically. 
                    // Make sure marked.parse() is available via your CDN script tag in index.html
                    aiBubble.innerHTML = marked.parse(aiFullResponse);
                    
                    // Auto-scroll to the bottom as text streams in
                    chatBox.scrollTop = chatBox.scrollHeight; 
                }
            }
        }

        // Finalize the AI message in history so the model remembers it contextually
        conversationHistory.push({ role: 'assistant', content: aiFullResponse });

    } catch (error) {
        console.error("Chat Error:", error);
        aiBubble.innerHTML = `<span style="color: #ff4444;">⚠️ Connection failed: ${error.message}</span>`;
    } finally {
        // Clean up UI states and wipe attachments for the next message
        aiBubble.classList.remove('streaming');
        attachedFileBase64 = null;
        attachedFileName = null;
        if (fileInput) fileInput.value = ""; 
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