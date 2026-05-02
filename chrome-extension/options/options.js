document.addEventListener('DOMContentLoaded', async () => {
  const grantBtn = document.getElementById('grant-btn');
  const statusEl = document.getElementById('status');

  // Check if already granted
  try {
    const status = await navigator.permissions.query({ name: 'microphone' });
    if (status.state === 'granted') {
      showSuccess();
    }
  } catch (e) {
    console.warn("Permissions API not fully supported:", e);
  }

  grantBtn.addEventListener('click', async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Stop the stream immediately, we only wanted the permission
      stream.getTracks().forEach(track => track.stop());
      showSuccess();
    } catch (err) {
      statusEl.className = 'error';
      statusEl.textContent = '✕ Permission denied. Please check your browser settings and try again.';
    }
  });

  function showSuccess() {
    statusEl.className = 'success';
    statusEl.textContent = '✓ Permission granted! You can close this tab and return to the extension.';
    grantBtn.style.display = 'none';
  }
});
