// CtlNodeのIPアドレスとポート番号を設定
const ctlNodeIp = '192.168.200.10';
const serverPort = 8000;
const baseUrl = `http://${ctlNodeIp}:${serverPort}`;

// APIを呼び出す関数
async function sendCommand(endpoint) {
    const url = `${baseUrl}/${endpoint}`;
    console.log(`Sending command to: ${url}`);
    
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('Success:', data);
        alert(`コマンド送信成功: ${data.message}`);
        
    } catch (error) {
        console.error('Error:', error);
        alert(`コマンド送信失敗: ${error.message}`);
    }
}

// 各ボタンのクリックイベントを設定
document.getElementById('start-cam-node').addEventListener('click', () => {
    sendCommand('start_cam_node');
});

document.getElementById('start-relay-node2').addEventListener('click', () => {
    sendCommand('start_relay_node2');
});

document.getElementById('start-relay-node1').addEventListener('click', () => {
    sendCommand('start_relay_node1');
});