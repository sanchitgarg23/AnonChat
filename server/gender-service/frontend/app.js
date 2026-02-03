document.addEventListener("DOMContentLoaded", () => {
    // Elements
    const video = document.getElementById("camera-feed");
    const canvas = document.getElementById("capture-canvas");
    const startBtn = document.getElementById("start-btn");
    const verifyBtn = document.getElementById("verify-btn");
    const resultArea = document.getElementById("result-area");
    const loader = document.getElementById("loader");
    const resultContent = document.getElementById("result-content");
    const scanOverlay = document.querySelector(".scan-overlay");
    const systemStatus = document.getElementById("system-status");
    const placeholder = document.getElementById("camera-placeholder");

    let stream = null;
    const API_URL = "http://localhost:8000/verify-gender";

    // Start Camera
    startBtn.addEventListener("click", async () => {
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 640, facingMode: "user" }
            });
            video.srcObject = stream;
            
            // UI Updates
            placeholder.style.display = "none";
            startBtn.disabled = true;
            verifyBtn.disabled = false;
            startBtn.innerText = "Camera Active";
            systemStatus.innerHTML = "<span class=\"dot\" style=\"color:#10b981\"></span> Camera Ready";
            
        } catch (err) {
            console.error("Error accessing camera:", err);
            alert("Could not access camera. Please allow camera permissions.");
        }
    });

    // Verify
    verifyBtn.addEventListener("click", async () => {
        if (!stream) return;

        // Visual feedback
        scanOverlay.classList.add("active");
        verifyBtn.disabled = true;
        resultArea.classList.remove("hidden");
        loader.classList.remove("hidden");
        resultContent.classList.add("hidden");

        // Capture frame
        const context = canvas.getContext("2d");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);

        // Convert to blob
        canvas.toBlob(async (blob) => {
            const formData = new FormData();
            formData.append("image", blob, "capture.jpg"); // Filename is important for ext validation

            try {
                const response = await fetch(API_URL, {
                    method: "POST",
                    body: formData
                });

                const data = await response.json();

                // Stop scanning animation
                scanOverlay.classList.remove("active");
                loader.classList.add("hidden");
                resultContent.classList.remove("hidden");
                verifyBtn.disabled = false;

                displayResult(data);

            } catch (err) {
                console.error("API Error:", err);
                scanOverlay.classList.remove("active");
                loader.classList.add("hidden");
                resultContent.classList.remove("hidden");
                verifyBtn.disabled = false;
                
                displayError("Connection failed. Is the backend running?");
            }
        }, "image/jpeg", 0.95);
    });

    function displayResult(data) {
        const title = document.getElementById("result-title");
        const message = document.getElementById("result-message");
        const icon = document.getElementById("result-icon");

        if (data.verified) {
            title.innerText = "Verified Response";
            title.className = "result-success";
            icon.innerText = data.gender === "M" ? "👨" : "👩";
            message.innerText = `Gender classified as: ${data.gender === "M" ? "Male" : "Female"}`;
        } else {
            displayError(data.error || "Verification failed");
        }
    }

    function displayError(msg) {
        const title = document.getElementById("result-title");
        const message = document.getElementById("result-message");
        const icon = document.getElementById("result-icon");

        title.innerText = "Verification Failed";
        title.className = "result-error";
        icon.innerText = "⚠️";
        message.innerText = msg;
    }
});
