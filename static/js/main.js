document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('login-form');
    const mainContainer = document.getElementById('main-container');
    const printersList = document.getElementById('printers-list');
    const printForm = document.getElementById('print-form');
    const printerSelect = document.getElementById('printer-select');
    const statusMessages = document.getElementById('status-messages');
    let token = null;
    let websocket = null;

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const clientId = document.getElementById('client-id').value;
        const password = document.getElementById('password').value;

        const response = await fetch('/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `username=${clientId}&password=${password}&grant_type=password`,
        });

        const data = await response.json();
        if (data.access_token) {
            token = data.access_token;
            mainContainer.style.display = 'block';
            loginForm.style.display = 'none';
            fetchPrinters();
            connectWebSocket();
        } else {
            alert('Login failed');
        }
    });

    async function fetchPrinters() {
        const response = await fetch('/printers/', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        const data = await response.json();
        printersList.innerHTML = '';
        data.printers.forEach(printer => {
            const printerDiv = document.createElement('div');
            printerDiv.innerHTML = `
                <h3>${printer.name}</h3>
                <p>Status: ${printer.status}</p>
            `;
            printersList.appendChild(printerDiv);
            const option = document.createElement('option');
            option.value = printer.id;
            option.text = printer.name;
            printerSelect.appendChild(option);
        });
    }

    printForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const printerId = printerSelect.value;
        const fileUrl = document.getElementById('file-url').value;
        const copies = document.getElementById('copies').value;

        const response = await fetch('/print-job/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                printer_id: printerId,
                file_url: fileUrl,
                copies: copies
            })
        });

        const data = await response.json();
        addStatusMessage(`Print job sent to printer: ${data.print_job.printer_id}`);
    });

    function connectWebSocket() {
        websocket = new WebSocket('ws://localhost:8000/ws');
        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.print_job) {
                addStatusMessage(`Received print job for printer: ${data.print_job.printer_id}`);
            }
        };
    }

    function addStatusMessage(message) {
        const messageDiv = document.createElement('div');
        messageDiv.textContent = message;
        statusMessages.appendChild(messageDiv);
        statusMessages.scrollTop = statusMessages.scrollHeight;
    }
});