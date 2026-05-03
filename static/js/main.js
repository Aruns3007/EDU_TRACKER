function createGauge(elementId, value, color) {
    const ctx = document.getElementById(elementId).getContext('2d');
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [value, 100 - value],
                backgroundColor: [color, '#1e293b'],
                borderWidth: 0,
                borderRadius: 10
            }]
        },
        options: {
            cutout: '85%',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { tooltip: { enabled: false } }
        }
    });
}

// Initializing the gauges with sample values 
// (In dashboard.html, you will pass real data from Flask)
window.onload = function() {
    createGauge('attendanceGauge', 78, '#3b82f6'); // Blue for Attendance
    createGauge('readinessGauge', 65, '#fbbf24');  // Yellow/Orange for Readiness
};
function createGauge(elementId, value, color) {
    const ctx = document.getElementById(elementId).getContext('2d');
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [value, 100 - value],
                backgroundColor: [color, 'rgba(255, 255, 255, 0.05)'],
                borderWidth: 0,
                borderRadius: 10
            }]
        },
        options: {
            cutout: '80%',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { tooltip: { enabled: false } },
            animation: { duration: 2000, animateRotate: true }
        }
    });
}

// Use the variables passed from the HTML
window.onload = function() {
    createGauge('attendanceGauge', attendanceVal, '#3b82f6'); 
    createGauge('readinessGauge', readinessVal, '#fbbf24');
};

async function sendMessage() {
    const input = document.getElementById('user-input');
    const chatWindow = document.getElementById('chat-window');
    const message = input.value;

    if (!message) return;

    // Show user message
    chatWindow.innerHTML += `<p><b>You:</b> ${message}</p>`;
    input.value = '';

    // Call Flask AI API
    const response = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message })
    });

    const data = await response.json();

    // Show AI response
    chatWindow.innerHTML += `<p style="color: #3b82f6;"><b>AI:</b> ${data.response}</p>`;
    chatWindow.scrollTop = chatWindow.scrollHeight; // Auto-scroll
}