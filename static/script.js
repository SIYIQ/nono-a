const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const systemPromptInput = document.getElementById('system-prompt');
const saveButton = document.getElementById('save-button');
const loadButton = document.getElementById('load-button');
const newChatButton = document.getElementById('new-chat-button');
const fileInput = document.getElementById('file-input');
const providerSelect = document.getElementById('provider-select');

let conversationHistory = [];

async function sendMessage() {
    const messageText = userInput.value.trim();
    if (messageText === '' || sendButton.disabled) return;

    if (conversationHistory.length === 0) {
        const systemPromptText = systemPromptInput.value.trim();
        if (systemPromptText) {
            conversationHistory.push({ role: 'system', content: systemPromptText });
        }
        systemPromptInput.disabled = true;
    }

    appendMessage('user', messageText);
    conversationHistory.push({ role: 'user', content: messageText });
    userInput.value = '';
    sendButton.disabled = true;
    providerSelect.disabled = true; // Disable provider selection during conversation

    const assistantMessageDiv = appendMessage('assistant', '', true); 
    let assistantContent = '';

    try {
        const selectedProvider = providerSelect.value;
        const response = await fetch('http://127.0.0.1:8000/api/chat', { // Corrected port
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                history: conversationHistory,
                provider: selectedProvider // Send selected provider
            })
        });

        if (!response.ok) { throw new Error(`HTTP error! status: ${response.status}`); }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            let boundary;
            while ((boundary = buffer.indexOf('\n\n')) >= 0) {
                const message = buffer.slice(0, boundary);
                buffer = buffer.slice(boundary + 2);

                if (message.startsWith('data: ')) {
                    const data = JSON.parse(message.slice(6));
                    
                    if (data.type === 'start_answer') {
                        assistantMessageDiv.querySelector('.blinking-cursor')?.remove();
                    } 
                    else if (data.type === 'answer' && data.content) {
                        assistantContent += data.content;
                        assistantMessageDiv.textContent = assistantContent;
                        chatBox.scrollTop = chatBox.scrollHeight;
                    } 
                    else if (data.type === 'end') {
                        try {
                            let clean_json_string = data.full_answer.trim();
                            if (clean_json_string.startsWith('```json')) {
                                clean_json_string = clean_json_string.substring(7, clean_json_string.length - 3).trim();
                            } else if (clean_json_string.startsWith('json')) {
                                clean_json_string = clean_json_string.substring(4).trim();
                            }
                            const parsed_json = JSON.parse(clean_json_string);
                            const { character_name, expression, action, dialogue } = parsed_json;

                            if (character_name && expression && action && dialogue) {
                                const formatted_answer = `[${character_name} (${expression})] ${action} "${dialogue}"`;
                                assistantMessageDiv.textContent = formatted_answer;
                            }
                        } catch (e) {
                            // Not a valid JSON, just use the raw text which is already in the div.
                        }

                        if (data.full_answer.trim() === '') {
                            assistantMessageDiv.parentElement.remove();
                        } else {
                            // Still save the original full answer to history
                            conversationHistory.push({ role: 'assistant', content: data.full_answer });
                        }
                        saveToLocalStorage();
                    } 
                    else if (data.type === 'error') {
                        throw new Error(data.content);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Error:', error);
        assistantMessageDiv.textContent = `抱歉，出错了: ${error.message}`;
        assistantMessageDiv.style.color = 'red';
    } finally {
        sendButton.disabled = false;
        userInput.focus();
    }
}

function appendMessage(role, content, isStreaming = false) {
    const messageWrapper = document.createElement('div');
    messageWrapper.classList.add('message', role, 'd-flex', 'flex-column', 'mb-3');
    
    const contentDiv = document.createElement('div');
    contentDiv.classList.add('content');
    
    if (role === 'user') {
        contentDiv.classList.add('align-self-end');
    } else {
        contentDiv.classList.add('align-self-start');
    }

    if (isStreaming) {
        contentDiv.innerHTML = '<span class="blinking-cursor">▍</span>';
    } else {
        contentDiv.textContent = content;
    }
    
    messageWrapper.appendChild(contentDiv);
    chatBox.appendChild(messageWrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
    return contentDiv;
}

function renderHistory(history) {
    chatBox.innerHTML = '';
    systemPromptInput.value = '';
    systemPromptInput.disabled = false;
    providerSelect.disabled = false;
    let tempHistory = [];
    history.forEach(message => {
        if (message.role === 'system') {
            systemPromptInput.value = message.content;
            systemPromptInput.disabled = true;
        } else {
            appendMessage(message.role, message.content);
            tempHistory.push(message);
        }
    });
    if (tempHistory.length > 0) {
         systemPromptInput.disabled = true;
         providerSelect.disabled = true;
    }
}

function startNewChat() {
    conversationHistory = [];
    chatBox.innerHTML = '';
    systemPromptInput.value = '';
    systemPromptInput.disabled = false;
    providerSelect.disabled = false;
    userInput.value = '';
    userInput.focus();
    localStorage.removeItem('chatHistory');
    appendMessage('assistant', '你好！这是一个新的对话。你可以先设定一个角色，然后开始提问。');
}

function saveChatToFile() {
    if (conversationHistory.length === 0) {
        alert('对话为空，无需保存。');
        return;
    }
    const blob = new Blob([JSON.stringify(conversationHistory, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat_history_${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function saveToLocalStorage() {
    if (conversationHistory.length > 0) {
        localStorage.setItem('chatHistory', JSON.stringify(conversationHistory));
    }
}

function loadFromLocalStorage() {
    const savedHistory = localStorage.getItem('chatHistory');
    if (savedHistory) {
        conversationHistory = JSON.parse(savedHistory);
        renderHistory(conversationHistory);
    } else {
        appendMessage('assistant', '你好！我是你的AI助手，有什么可以帮你的吗？');
    }
}

sendButton.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
});

saveButton.addEventListener('click', saveChatToFile);
newChatButton.addEventListener('click', startNewChat);
loadButton.addEventListener('click', () => fileInput.click()); 
fileInput.addEventListener('change', (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const loadedHistory = JSON.parse(e.target.result);
            if (Array.isArray(loadedHistory)) {
                conversationHistory = loadedHistory;
                renderHistory(conversationHistory);
                saveToLocalStorage();
            } else {
                alert('文件格式不正确。');
            }
        } catch (error) {
            alert('读取或解析文件时出错！');
        }
    };
    reader.readAsText(file);
    event.target.value = ''; 
});

window.addEventListener('load', loadFromLocalStorage);
