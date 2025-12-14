class Terminal {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.socket = null;
        this.connected = false;
        this.clear();
    }

    clear() {
        this.container.innerHTML = '';
    }

    connect() {
        let wsUrl;
        if (window.location.protocol === 'file:') {
            wsUrl = 'ws://localhost:8765/ws';
        } else {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            wsUrl = `${protocol}//${window.location.host}/ws`;
        }
        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            this.connected = true;
            // this.addTerminalLine('<span class="highlight">Connected to TomatOS server...</span>');
            // Start the session
            this.startSession();
        };

        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleServerMessage(data);
        };

        this.socket.onclose = () => {
            this.connected = false;
            this.addTerminalLine('<span class="highlight">与ssh连接丢失。正在重新连接...</span>');
            setTimeout(() => this.connect(), 3000);
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.addTerminalLine('<span class="highlight">连接错误。</span>');
        };
    }

    handleServerMessage(data) {
        if (data.type === 'output') {
            this.addTerminalLine(data.content, data.className);
        } else if (data.type === 'prompt') {
            this.addInputLine(data.content, (value) => {
                this.socket.send(JSON.stringify({ type: 'input', content: value }));
            }, data.isPassword);
        } else if (data.type === 'clear') {
            this.clear();
        }
    }

    startSession() {
        // Send initial client info
        this.socket.send(JSON.stringify({
            type: 'init',
            userAgent: navigator.userAgent,
            language: navigator.language
        }));
    }

    // 添加终端行
    addTerminalLine(content, className = "line") {
        const line = document.createElement("div");
        line.className = className;
        line.innerHTML = content;
        this.container.appendChild(line);
        this.container.scrollTop = this.container.scrollHeight;
        return line;
    }
    
    // 添加输入行
    addInputLine(promptText, callback, isPassword = false) {
        const inputLine = document.createElement("div");
        inputLine.className = "input-line";
        
        const promptSpan = document.createElement("span");
        promptSpan.className = "prompt";
        promptSpan.innerHTML = promptText; // Use innerHTML to support HTML in prompt
        
        const input = document.createElement("input");
        if (isPassword) {
            input.type = "password";
            input.className = "password-input";
        }
        
        inputLine.appendChild(promptSpan);
        inputLine.appendChild(input);
        this.container.appendChild(inputLine);
        
        input.focus();
        
        // Keep focus
        input.addEventListener('blur', () => {
            setTimeout(() => input.focus(), 10);
        });
        
        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                const value = input.value; // Don't trim passwords? Or maybe trim.
                // if (value) { // Allow empty enter
                    // 显示输入的命令
                    const cmdLine = document.createElement("div");
                    cmdLine.className = "line";
                    const displayValue = isPassword ? "*".repeat(value.length) : value;
                    cmdLine.innerHTML = `<span class="prompt">${promptText}</span> <span class="command">${displayValue}</span>`;
                    
                    // 替换输入行
                    this.container.replaceChild(cmdLine, inputLine);
                    
                    // 调用回调函数
                    callback(value);
                // }
            }
        });
        
        this.container.scrollTop = this.container.scrollHeight;
    }
}

// 主函数
function main() {
    const terminal = new Terminal('terminal');
    terminal.connect();
}

// 页面加载完成后启动
document.addEventListener("DOMContentLoaded", main);