// OMNIPREP FRONTEND APP LOGIC

// App States
let currentScreen = "setup-screen";
let candidateEmail = "candidate@example.com";
let targetRole = "Software Engineer";
let resumeText = "";
let jobDescription = "";
let activePersona = "alex";
let customQuestions = "";

// Interview state
let interviewQuestions = [];
let currentQuestionIndex = 0;
let sessionQuestionsAnswered = [];
let currentAnswerTranscript = "";
let speechRecognitionObj = null;

// Conversational History State
let conversationHistory = [];
let currentStage = 1;
let lastQuestionAsked = "";
let hasSpokenForVAD = false;
let lastSpeechTime = null;
let vadTimerInterval = null;

// Telemetry counters for current question
let currentFillerCounts = { like: 0, um: 0, uh: 0, youknow: 0, yeah: 0, basically: 0 };
let currentEyeContactScores = [];
let currentHeadScores = [];
let questionStartTime = null;

// State indicator and beep sound utilities
let currentInterviewerState = "listening";

function setInterviewerState(state) {
    currentInterviewerState = state;
    const stateLabel = document.getElementById("interviewer-state");
    const liveBadge = document.getElementById("interviewer-live-badge");
    const avatarRing = document.getElementById("avatar-ring");
    if (!stateLabel || !liveBadge || !avatarRing) return;
    
    // Clear old classes
    stateLabel.className = "font-mono";
    liveBadge.className = "badge";
    liveBadge.style.animation = "";
    
    if (state === "listening") {
        stateLabel.textContent = "LISTENING";
        stateLabel.classList.add("text-green");
        liveBadge.classList.add("success-green", "animate-pulse");
        liveBadge.style.backgroundColor = "rgba(0, 229, 153, 0.15)";
        liveBadge.style.color = "var(--success-green)";
        liveBadge.style.borderColor = "var(--success-glow)";
        avatarRing.style.borderColor = "var(--success-green)";
        avatarRing.style.boxShadow = "0 0 15px var(--success-glow)";
    } else if (state === "thinking") {
        stateLabel.textContent = "THINKING...";
        stateLabel.classList.add("text-amber");
        liveBadge.classList.add("alert-amber", "animate-pulse");
        liveBadge.style.backgroundColor = "rgba(255, 184, 0, 0.15)";
        liveBadge.style.color = "var(--alert-amber)";
        liveBadge.style.borderColor = "var(--alert-glow)";
        avatarRing.style.borderColor = "var(--alert-amber)";
        avatarRing.style.boxShadow = "0 0 15px var(--alert-glow)";
    } else if (state === "speaking") {
        stateLabel.textContent = "SPEAKING";
        stateLabel.classList.add("text-cyan");
        liveBadge.classList.add("neon-cyan", "animate-pulse");
        liveBadge.style.backgroundColor = "rgba(0, 240, 255, 0.15)";
        liveBadge.style.color = "var(--neon-cyan)";
        liveBadge.style.borderColor = "var(--neon-cyan-glow)";
        avatarRing.style.borderColor = "var(--neon-cyan)";
        avatarRing.style.boxShadow = "0 0 15px var(--neon-cyan-glow)";
    }
}

function showLiveHint(text, type = "info") {
    const overlay = document.getElementById("live-hints-overlay");
    if (!overlay) return;

    // Prevent immediate warning spam
    const existing = Array.from(overlay.children).find(child => child.textContent.includes(text));
    if (existing) return;

    const hint = document.createElement("div");
    hint.className = `live-hint ${type}`;
    
    let icon = "💡";
    if (type === "warning") icon = "⚠️";
    else if (type === "danger") icon = "🚨";
    else if (type === "success") icon = "✓";

    hint.innerHTML = `<span>${icon} ${text}</span>`;
    overlay.appendChild(hint);

    // Fade out and remove after 3.5 seconds
    setTimeout(() => {
        hint.style.animation = "slide-out 0.3s ease-in forwards";
        setTimeout(() => {
            if (hint.parentNode) {
                overlay.removeChild(hint);
            }
        }, 300);
    }, 3500);
}

function playTurnBeep(isUserTurn) {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioCtx.createOscillator();
        const gainNode = audioCtx.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        
        if (isUserTurn) {
            // High double chirp for "your turn"
            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(880, audioCtx.currentTime); // A5
            gainNode.gain.setValueAtTime(0.04, audioCtx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.12);
            oscillator.start();
            oscillator.stop(audioCtx.currentTime + 0.12);
        } else {
            // Lower single beep for "submitting/processing"
            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(440, audioCtx.currentTime); // A4
            gainNode.gain.setValueAtTime(0.03, audioCtx.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.1);
            oscillator.start();
            oscillator.stop(audioCtx.currentTime + 0.1);
        }
    } catch (err) {
        console.error("Audio Context beep failed:", err);
    }
}

function startVADLoop() {
    if (vadTimerInterval) clearInterval(vadTimerInterval);
    vadTimerInterval = setInterval(() => {
        if (currentScreen !== "interview-screen" || isMicMuted || isInterviewerSpeaking) {
            return;
        }
        
        const words = (currentAnswerTranscript + " ").trim().split(/\s+/).filter(w => w.length > 0);
        const wordCount = words.length;
        
        if (hasSpokenForVAD && wordCount >= 3 && lastSpeechTime) {
            const silenceElapsed = Date.now() - lastSpeechTime;
            if (silenceElapsed > 1500) {
                console.log("VAD: Silence detected. Submitting turn.");
                hasSpokenForVAD = false;
                lastSpeechTime = null;
                handleAnswerCompleted();
            }
        }
    }, 200);
}

// Media streams
let localStream = null;
let frameCaptureInterval = null;
let audioContext = null;
let micAnalyser = null;
let micSource = null;
let isMicMuted = false;
let isCamOff = false;

// Audio player for ElevenLabs / Speech fallback
let audioPlayer = new Audio();
let interviewerAudioContext = null;
let interviewerAnalyser = null;
let interviewerSource = null;
let isInterviewerSpeaking = false;

// Three.js 3D Spatial Backdrop Variables
let threeScene, threeCamera, threeRenderer;
let particleSystem, gridHelper;
let mouseX = 0, mouseY = 0;

// Initialize App
document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide icons
    lucide.createIcons();

    // Ingest components & listeners
    setupEventListeners();
    initThreeJSBackdrop();
    checkConfigStatus();
});

async function checkConfigStatus() {
    try {
        const response = await fetch("/api/config-status");
        if (response.ok) {
            const data = await response.json();
            const banner = document.getElementById("ai-status-banner");
            const statusText = document.getElementById("ai-status-text");
            const icon = document.getElementById("ai-status-icon");
            
            if (banner && statusText) {
                banner.style.display = "flex";
                if (data.gemini_active) {
                    banner.style.borderLeft = "3px solid var(--success-green)";
                    banner.style.backgroundColor = "rgba(0, 229, 153, 0.02)";
                    statusText.textContent = "✓ GEMINI AI ACTIVE // Dynamic, personalized interview questions enabled.";
                    statusText.style.color = "var(--success-green)";
                    if (icon) {
                        icon.style.color = "var(--success-green)";
                    }
                } else {
                    banner.style.borderLeft = "3px solid var(--alert-amber)";
                    banner.style.backgroundColor = "rgba(255, 179, 0, 0.02)";
                    statusText.textContent = "⚠️ SANDBOX FALLBACK ACTIVE // GEMINI_API_KEY absent. Run 'export GEMINI_API_KEY=your_key' in your terminal tab to unlock live AI question generation.";
                    statusText.style.color = "var(--alert-amber)";
                    if (icon) {
                        icon.style.color = "var(--alert-amber)";
                    }
                }
            }
        }
    } catch (e) {
        console.error("Config check failed:", e);
    }
}

// 1. SETUP EVENT LISTENERS
function setupEventListeners() {
    // Screen transitions
    const launchBtn = document.getElementById("launch-btn");
    const nextBtn = document.getElementById("next-btn");
    const endBtn = document.getElementById("end-btn");
    const restartBtn = document.getElementById("restart-btn");
    const webhookTriggerBtn = document.getElementById("webhook-trigger-btn");

    // File Drag and Drop
    const dropzone = document.getElementById("resume-dropzone");
    const fileInput = document.getElementById("resume-file");

    dropzone.addEventListener("click", () => fileInput.click());
    
    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            handleResumeUpload(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleResumeUpload(e.target.files[0]);
        }
    });

    // Preset buttons
    const presets = {
        stripe: "Frontend Engineer @ Stripe\nRequirements: 3+ years experience with React, TypeScript, Tailwind, CSS animations, and Next.js. Focus on polished user experiences, performance metrics, and low-latency client integrations. Candidates must show strong system design skills and experience handling high-throughput web applications.",
        td: "Software Engineer Co-op @ TD Bank\nRequirements: Current enrollment in Computer Science or Software Engineering. Familiarity with Java, Spring Boot, REST APIs, and database fundamentals. Focus on collaboration, agile methodologies, behavioral alignment, and software testing practices.",
        deloitte: "Product Analyst @ Deloitte\nRequirements: Experience in agile project management, user stories, metrics definition, and client-facing communication. Strong analytical mindset, experience matching business constraints with technical specifications, and presenting trade-offs to stakeholders."
    };

    document.querySelectorAll(".preset-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const type = btn.getAttribute("data-preset");
            document.getElementById("job-description").value = presets[type];
            // Highlight active preset
            document.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
        });
    });

    // Default preset
    document.querySelector('[data-preset="stripe"]').click();

    // Persona cards selection
    const personaCards = document.querySelectorAll(".persona-card");
    personaCards.forEach(card => {
        card.addEventListener("click", () => {
            personaCards.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            activePersona = card.getAttribute("data-persona");
        });
    });

    // Media control toggles
    document.getElementById("toggle-mic").addEventListener("click", toggleMicrophone);
    document.getElementById("toggle-cam").addEventListener("click", toggleCamera);

    // Navigation CTAs
    launchBtn.addEventListener("click", startSimulation);
    nextBtn.addEventListener("click", handleAnswerCompleted);
    endBtn.addEventListener("click", finishAndEvaluate);
    restartBtn.addEventListener("click", () => transitionScreen("setup-screen"));
    webhookTriggerBtn.addEventListener("click", dispatchWebhookToN8N);

    // Track mouse coordinates for ThreeJS spatial boardroom parallax
    document.addEventListener("mousemove", (e) => {
        mouseX = (e.clientX - window.innerWidth / 2) / 100;
        mouseY = (e.clientY - window.innerHeight / 2) / 100;
    });
}

// 2. RESUME FILE UPLOAD HANDLER
async function handleResumeUpload(file) {
    const dropzoneIcon = document.querySelector(".dropzone-icon");
    const dropzoneText = document.querySelector(".dropzone-text");
    const fileStatus = document.getElementById("file-status");
    const nameDisplay = document.getElementById("file-name-display");

    showLoading("PARSING RESUME PDF...");

    const formData = new FormData();
    formData.append("file", file);

    try {
        const response = await fetch("/api/upload-resume", {
            method: "POST",
            body: formData
        });
        const data = await response.json();
        
        hideLoading();

        if (response.ok) {
            resumeText = data.text;
            nameDisplay.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
            fileStatus.style.display = "flex";
            dropzoneIcon.style.color = "var(--success-green)";
            dropzoneText.innerHTML = "Resume processed successfully. Select your persona.";
        } else {
            alert("Failed to parse resume: " + data.detail);
        }
    } catch (err) {
        hideLoading();
        console.error("Resume upload error:", err);
        alert("An error occurred during resume ingestion.");
    }
}

// 3. THREE.JS SPATIAL BOARDROOM BACKDROP
function initThreeJSBackdrop() {
    const container = document.getElementById("spatial-backdrop");
    if (!container) return;

    // Dimensions
    const width = container.clientWidth || 400;
    const height = container.clientHeight || 300;

    // Scene & Camera
    threeScene = new THREE.Scene();
    threeScene.fog = new THREE.FogExp2(0x030508, 0.015);

    threeCamera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    threeCamera.position.set(0, 5, 20);
    threeCamera.lookAt(0, 0, 0);

    // Renderer
    threeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    threeRenderer.setSize(width, height);
    threeRenderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(threeRenderer.domElement);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x0f172a, 0.6);
    threeScene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0x00f0ff, 0.8);
    directionalLight.position.set(10, 20, 10);
    threeScene.add(directionalLight);

    // Boardroom floor grid (neon lines)
    gridHelper = new THREE.GridHelper(50, 25, 0x00f0ff, 0x1f293d);
    gridHelper.position.y = -2;
    threeScene.add(gridHelper);

    // Floating boardroom particles (simulating dust/ambient light nodes)
    const particleCount = 150;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {
        // Spatial boardroom coordinates (box room)
        positions[i * 3] = (Math.random() - 0.5) * 40;
        positions[i * 3 + 1] = Math.random() * 15 - 2;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 40;

        // Color mix (mostly cyan and some slate highlights)
        if (Math.random() > 0.3) {
            colors[i * 3] = 0.0;   // R
            colors[i * 3 + 1] = 0.94; // G
            colors[i * 3 + 2] = 1.0;  // B
        } else {
            colors[i * 3] = 0.0;
            colors[i * 3 + 1] = 0.9;
            colors[i * 3 + 2] = 0.6;
        }
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    // Particle texture
    const material = new THREE.PointsMaterial({
        size: 0.15,
        vertexColors: true,
        transparent: true,
        opacity: 0.8,
        blending: THREE.AdditiveBlending
    });

    particleSystem = new THREE.Points(geometry, material);
    threeScene.add(particleSystem);

    // Glowing boardroom virtual walls (wireframe panels)
    const panelGeo = new THREE.BoxGeometry(4, 8, 0.2);
    const panelMat = new THREE.MeshBasicMaterial({
        color: 0x1f293d,
        wireframe: true,
        transparent: true,
        opacity: 0.15
    });

    // Generate wall panels to give structural depth
    for (let i = -3; i <= 3; i += 2) {
        if (i === 0) continue;
        const panel = new THREE.Mesh(panelGeo, panelMat);
        panel.position.set(i * 5, 2, -10);
        threeScene.add(panel);
    }

    // Window beam lights
    const beamGeo = new THREE.ConeGeometry(5, 30, 4);
    const beamMat = new THREE.MeshBasicMaterial({
        color: 0x00f0ff,
        transparent: true,
        opacity: 0.03,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide
    });
    const beam = new THREE.Mesh(beamGeo, beamMat);
    beam.position.set(0, 10, -15);
    beam.rotation.x = Math.PI / 4;
    threeScene.add(beam);

    // Resize Handler
    window.addEventListener("resize", onWindowResize);

    // Start rendering loop
    animateThreeJS();
}

function onWindowResize() {
    const container = document.getElementById("spatial-backdrop");
    if (!container || !threeRenderer) return;
    const width = container.clientWidth;
    const height = container.clientHeight;

    threeCamera.aspect = width / height;
    threeCamera.updateProjectionMatrix();
    threeRenderer.setSize(width, height);
}

function animateThreeJS() {
    requestAnimationFrame(animateThreeJS);

    // Parallax mouse follow (creates 3D boardroom spatial movement)
    // Lerping the camera to look natural
    const targetCamX = mouseX * 0.5;
    const targetCamY = 5 - mouseY * 0.3;
    
    threeCamera.position.x += (targetCamX - threeCamera.position.x) * 0.05;
    threeCamera.position.y += (targetCamY - threeCamera.position.y) * 0.05;
    threeCamera.lookAt(0, 1, 0);

    // Slowly rotate particles to make environment feel alive
    if (particleSystem) {
        particleSystem.rotation.y += 0.001;
    }

    threeRenderer.render(threeScene, threeCamera);
}

// 4. TRANSITION BETWEEN SCREENS
function transitionScreen(screenId) {
    document.querySelectorAll(".screen-section").forEach(s => s.classList.remove("active"));
    document.getElementById(screenId).classList.add("active");
    currentScreen = screenId;

    // Reset animations/triggers if returning to setup
    if (screenId === "setup-screen") {
        stopMediaStreams();
        sessionQuestionsAnswered = [];
        currentQuestionIndex = 0;
    }
}

// 5. START INTERVIEW SIMULATION
async function startSimulation() {
    targetRole = document.getElementById("target-role").value.trim() || "Software Engineer";
    candidateEmail = document.getElementById("candidate-email").value.trim();
    jobDescription = document.getElementById("job-description").value.trim();
    customQuestions = document.getElementById("custom-questions").value.trim();

    if (!candidateEmail) {
        alert("Please enter a valid email address.");
        return;
    }

    showLoading("INITIALIZING INTERVIEW SIMULATION...");

    try {
        // Generate questions from backend
        const response = await fetch("/api/generate-questions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                resume_text: resumeText || "[No resume uploaded. Generic Software Engineer profile]",
                job_description: jobDescription,
                custom_questions: customQuestions
            })
        });

        const data = await response.json();
        hideLoading();

        if (response.ok) {
            interviewQuestions = data.questions;
            currentQuestionIndex = 0;
            currentStage = 1;
            sessionQuestionsAnswered = [];
            
            // Initialize conversation history with first question
            const firstQuestion = interviewQuestions[0].question;
            lastQuestionAsked = firstQuestion;
            conversationHistory = [
                { role: "interviewer", text: firstQuestion }
            ];

            // Setup Persona display info
            updatePersonaHUD();

            // Transition to Room
            transitionScreen("interview-screen");

            // Start webcam & microphone
            await startMediaStreams();
            
            // Start VAD monitoring loop
            startVADLoop();

            // Trigger play of first question
            loadConversationalQuestion(firstQuestion);
        } else {
            alert("Failed to initialize session: " + data.detail);
        }
    } catch (err) {
        hideLoading();
        console.error("Launch simulation error:", err);
        alert("An error occurred launching the simulation room.");
    }
}

// 6. UPDATE PERSONA HUD LABELS
function updatePersonaHUD() {
    const avatarLabel = document.getElementById("active-avatar-label");
    const nameLabel = document.getElementById("active-interviewer-name");
    const avatarRing = document.getElementById("avatar-ring");

    // Remove old classes
    avatarLabel.className = "active-avatar";
    avatarRing.style.borderColor = "var(--neon-cyan)";

    if (activePersona === "alex") {
        avatarLabel.textContent = "A";
        avatarLabel.classList.add("alex");
        nameLabel.textContent = "Alex // Tech Lead";
        avatarRing.style.borderColor = "var(--neon-cyan)";
    } else if (activePersona === "sarah") {
        avatarLabel.textContent = "S";
        avatarLabel.classList.add("sarah");
        nameLabel.textContent = "Sarah // Talent Partner";
        avatarRing.style.borderColor = "var(--success-green)";
    } else if (activePersona === "marcus") {
        avatarLabel.textContent = "M";
        avatarLabel.classList.add("marcus");
        nameLabel.textContent = "Marcus // Executive VP";
        avatarRing.style.borderColor = "var(--alert-amber)";
    }
}

// 7. WEBCAM & MIC STREAMS AND VISUALIZERS
async function startMediaStreams() {
    try {
        localStream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480 },
            audio: true
        });

        // Set webcam video source
        const videoElement = document.getElementById("webcam-feed");
        videoElement.srcObject = localStream;

        // Initialize Candidate Mic Waveform
        setupAudioVisualizer(localStream);

        // Start Speech Recognition
        setupSpeechRecognition();

        // Start Periodic Vision Telemetry Frame Capture (every 600ms)
        startVisionTrackingLoop();

    } catch (err) {
        console.error("Error accessing camera/microphone:", err);
        alert("Camera and microphone access are required for simulated interview telemetry.");
    }
}

function stopMediaStreams() {
    if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
    }
    isInterviewerSpeaking = false;
    isMicMuted = false;

    if (vadTimerInterval) {
        clearInterval(vadTimerInterval);
        vadTimerInterval = null;
    }
    if (frameCaptureInterval) {
        clearInterval(frameCaptureInterval);
        frameCaptureInterval = null;
    }
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
    }
    if (speechRecognitionObj) {
        try {
            speechRecognitionObj.stop();
        } catch (e) {}
        speechRecognitionObj = null;
    }
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
}

// Draw reactive candidate microphone waves in canvas
function setupAudioVisualizer(stream) {
    const canvas = document.getElementById("candidate-mic-wave");
    if (!canvas) return;
    const canvasCtx = canvas.getContext("2d");

    // Audio Context Setup
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    micAnalyser = audioContext.createAnalyser();
    micAnalyser.fftSize = 256;
    
    // Filter audio track out of the stream
    micSource = audioContext.createMediaStreamSource(stream);
    micSource.connect(micAnalyser);

    const bufferLength = micAnalyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function drawWave() {
        if (!audioContext || !micAnalyser) return;
        requestAnimationFrame(drawWave);

        micAnalyser.getByteTimeDomainData(dataArray);

        // Adjust for retina screens
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }

        canvasCtx.fillStyle = "rgba(22, 28, 44, 0.4)";
        canvasCtx.fillRect(0, 0, width, height);

        canvasCtx.lineWidth = 2;
        
        let waveColor = "var(--success-green)";
        let shadowColor = "var(--success-glow)";
        if (isMicMuted) {
            waveColor = "#FF4D4D";
            shadowColor = "rgba(255, 77, 77, 0.4)";
        } else if (currentInterviewerState === "thinking") {
            waveColor = "var(--alert-amber)";
            shadowColor = "var(--alert-glow)";
        } else if (currentInterviewerState === "speaking") {
            waveColor = "var(--neon-cyan)";
            shadowColor = "var(--neon-cyan-glow)";
        }
        
        canvasCtx.strokeStyle = waveColor;
        canvasCtx.shadowBlur = 4;
        canvasCtx.shadowColor = shadowColor;

        canvasCtx.beginPath();

        const sliceWidth = width * 1.0 / bufferLength;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
            const v = dataArray[i] / 128.0;
            const y = v * height / 2;

            if (i === 0) {
                canvasCtx.moveTo(x, y);
            } else {
                canvasCtx.lineTo(x, y);
            }

            x += sliceWidth;
        }

        canvasCtx.lineTo(width, height / 2);
        canvasCtx.stroke();
    }

    drawWave();
}

// 8. CLIENT SPEECH TRANSCRIPTION & LIVE TELEMETRY
function setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        document.getElementById("transcription-status").textContent = "SPEECH REC UNSUPPORTED";
        document.getElementById("transcription-status").className = "font-mono text-red";
        return;
    }

    speechRecognitionObj = new SpeechRecognition();
    speechRecognitionObj.continuous = true;
    speechRecognitionObj.interimResults = true;
    speechRecognitionObj.lang = "en-US";

    speechRecognitionObj.onstart = () => {
        document.getElementById("transcription-status").textContent = "LISTENING...";
        document.getElementById("transcription-status").className = "font-mono text-green animate-pulse";
    };

    speechRecognitionObj.onend = () => {
        // Proactively restart speech recognition if we are still interviewing
        if (currentScreen === "interview-screen" && !isMicMuted) {
            try {
                speechRecognitionObj.start();
            } catch (e) {}
        } else {
            document.getElementById("transcription-status").textContent = "MIC MUTED / PAUSED";
            document.getElementById("transcription-status").className = "font-mono text-muted";
        }
    };

    speechRecognitionObj.onresult = (event) => {
        let interimTranscript = "";
        let finalTranscript = "";

        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                currentAnswerTranscript += event.results[i][0].transcript + " ";
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }

        const fullDisplay = currentAnswerTranscript + interimTranscript;
        
        // Render in live badge
        const transcriptBox = document.getElementById("live-transcript");
        if (fullDisplay.trim()) {
            transcriptBox.innerHTML = `<span>${fullDisplay}</span>`;
            
            // Calculate Live Words per Minute (WPM)
            calculateLivePacing(fullDisplay);
            
            // Scan for filler words
            scanForFillers(fullDisplay);
        } else {
            transcriptBox.innerHTML = `<span class="transcript-placeholder">Your spoken answer will appear here in real-time...</span>`;
        }
    };

    speechRecognitionObj.start();
}

function calculateLivePacing(text) {
    if (!questionStartTime) return;
    
    const words = text.trim().split(/\s+/).filter(w => w.length > 0);
    const wordCount = words.length;

    const elapsedSeconds = (Date.now() - questionStartTime) / 1000.0;
    const elapsedMinutes = elapsedSeconds / 60.0;
    
    const wpm = elapsedMinutes > 0 ? Math.round(wordCount / elapsedMinutes) : 0;

    // Display
    const wpmLabel = document.getElementById("pacing-wpm");
    const statusLabel = document.getElementById("pacing-status");

    wpmLabel.textContent = wpm;

    // Real-time pacing overlay alerts
    if (wordCount > 6) {
        if (wpm > 180) {
            showLiveHint("Speaking too fast!", "warning");
        } else if (wpm < 95) {
            showLiveHint("Speaking too slow", "warning");
        }
    }

    // WPM boundaries: Too Slow < 110 | Optimal 130–160 | Fast > 180
    if (wpm === 0) {
        statusLabel.textContent = "Silent";
        statusLabel.className = "hud-status-text font-mono text-muted";
    } else if (wpm < 110) {
        statusLabel.textContent = "Too Slow";
        statusLabel.className = "hud-status-text font-mono text-amber";
    } else if (wpm < 130) {
        statusLabel.textContent = "Slow";
        statusLabel.className = "hud-status-text font-mono text-cyan";
    } else if (wpm <= 160) {
        statusLabel.textContent = "Optimal";
        statusLabel.className = "hud-status-text font-mono text-green";
    } else if (wpm <= 180) {
        statusLabel.textContent = "Fast";
        statusLabel.className = "hud-status-text font-mono text-cyan";
    } else {
        statusLabel.textContent = "Too Fast";
        statusLabel.className = "hud-status-text font-mono text-red";
    }
}

function scanForFillers(text) {
    const fillerWords = {
        like: /\b(like)\b/gi,
        um: /\b(um)\b/gi,
        uh: /\b(uh)\b/gi,
        youknow: /\b(you know)\b/gi,
        yeah: /\b(yeah)\b/gi,
        basically: /\b(basically|so basically)\b/gi
    };

    let counts = { like: 0, um: 0, uh: 0, youknow: 0, yeah: 0, basically: 0 };
    
    for (let key in fillerWords) {
        const matches = text.match(fillerWords[key]);
        counts[key] = matches ? matches.length : 0;
        
        // Trigger alert if a new filler is spoken
        const diff = counts[key] - currentFillerCounts[key];
        if (diff > 0 && currentScreen === "interview-screen" && currentInterviewerState === "listening") {
            showLiveHint(`Filler used: "${key}"`, "warning");
        }

        // Update badge
        const badge = document.getElementById(`filler-${key}`);
        if (badge) {
            const numLabel = badge.querySelector(".badge-num");
            numLabel.textContent = counts[key];

            // Glow badge active if fillers are detected
            if (counts[key] > 0) {
                badge.classList.add("active");
            } else {
                badge.classList.remove("active");
            }
        }
    }

    currentFillerCounts = counts;
}

// 9. CLIENT PERIODIC COMPUTER VISION TELEMETRY
function startVisionTrackingLoop() {
    if (frameCaptureInterval) clearInterval(frameCaptureInterval);

    const video = document.getElementById("webcam-feed");
    
    // Canvas helper to capture image frame
    const canvas = document.createElement("canvas");
    canvas.width = 320;
    canvas.height = 240;
    const ctx = canvas.getContext("2d");

    frameCaptureInterval = setInterval(async () => {
        if (!localStream || isCamOff || video.paused || video.ended) {
            // If camera is disabled, simulate some coordinates
            updateVisionHUD(getSimulatedVisionData());
            return;
        }

        // Draw webcam current frame onto hidden canvas
        // Mirrors image back for facial coordinates alignment
        ctx.save();
        ctx.translate(canvas.width, 0);
        ctx.scale(-1, 1);
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        ctx.restore();

        const base64Data = canvas.toDataURL("image/jpeg", 0.6); // compressed JPG

        try {
            const response = await fetch("/api/process-frame", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ image_data: base64Data })
            });

            if (response.ok) {
                const telemetry = await response.json();
                updateVisionHUD(telemetry);
            }
        } catch (err) {
            console.error("Error processing webcam frame:", err);
            updateVisionHUD(getSimulatedVisionData());
        }
    }, 600); // Poll frames every 600ms
}

function updateVisionHUD(data) {
    // Record scores for question stats
    currentEyeContactScores.push(data.eye_contact_score);
    currentHeadScores.push(data.head_pose_score);

    // Update mini dashboard badges
    const eyeContactPct = document.getElementById("eye-contact-pct");
    const eyeContactStatus = document.getElementById("eye-contact-status");
    const eyeContactDesc = document.getElementById("eye-contact-desc");
    const eyeCircle = document.getElementById("eye-contact-circle");

    eyeContactPct.textContent = `${data.eye_contact_score}%`;
    eyeContactStatus.textContent = data.eye_contact_status;
    eyeContactDesc.textContent = data.gaze_details;

    // Real-time HUD visual/eye contact triggers
    if (data.eye_contact_score < 60 && currentScreen === "interview-screen" && currentInterviewerState === "listening") {
        showLiveHint("Maintain eye contact", "danger");
    }
    if (data.head_pose_score < 65 && currentScreen === "interview-screen" && currentInterviewerState === "listening") {
        showLiveHint("Posture alignment alert", "warning");
    }

    // Apply color class based on score
    if (data.eye_contact_score > 75) {
        eyeContactStatus.className = "hud-status-text font-mono text-green";
        eyeCircle.setAttribute("stroke", "var(--success-green)");
    } else if (data.eye_contact_score > 50) {
        eyeContactStatus.className = "hud-status-text font-mono text-cyan";
        eyeCircle.setAttribute("stroke", "var(--neon-cyan)");
    } else {
        eyeContactStatus.className = "hud-status-text font-mono text-red";
        eyeCircle.setAttribute("stroke", "var(--alert-red)");
    }

    // Radial dashboard circle animate
    const strokeDash = `${data.eye_contact_score}, 100`;
    eyeCircle.setAttribute("stroke-dasharray", strokeDash);

    // Update bounding overlays (draw boxes relative to face mesh vectors)
    const faceBox = document.getElementById("hud-face-box");
    const leftEye = document.getElementById("hud-left-eye");
    const rightEye = document.getElementById("hud-right-eye");

    // Distort bounding boxes slightly based on Pitch and Yaw to simulate 3D face mesh mesh wrapping
    const boxX = 220 + (data.yaw * 1.5);
    const boxY = 140 - (data.pitch * 1.2);
    faceBox.setAttribute("x", boxX);
    faceBox.setAttribute("y", boxY);

    leftEye.setAttribute("cx", boxX + 65 + (data.yaw * 0.2));
    leftEye.setAttribute("cy", boxY + 80 - (data.pitch * 0.2));

    rightEye.setAttribute("cx", boxX + 135 + (data.yaw * 0.2));
    rightEye.setAttribute("cy", boxY + 80 - (data.pitch * 0.2));
}

function getSimulatedVisionData() {
    // Basic browser-side simulated data if backend parser isn't responding
    const randomShift = (Math.random() - 0.5) * 4;
    return {
        eye_contact_score: Math.max(50, Math.min(100, Math.round(90 + randomShift))),
        head_pose_score: Math.round(94 + randomShift),
        eye_contact_status: "Steady",
        head_pose_status: "Centered",
        gaze_details: "Steady engagement",
        yaw: randomShift * 2,
        pitch: randomShift,
        roll: 0
    };
}

// 10. LOAD & PLAY QUESTION (AI SPEECH AND AVATAR WAVE)
async function loadConversationalQuestion(text) {
    // Reset transcription counters
    currentAnswerTranscript = "";
    currentFillerCounts = { like: 0, um: 0, uh: 0, youknow: 0, yeah: 0, basically: 0 };
    currentEyeContactScores = [];
    currentHeadScores = [];
    hasSpokenForVAD = false;
    lastSpeechTime = null;

    // Clear live displays
    document.getElementById("live-transcript").innerHTML = `<span class="transcript-placeholder">Your spoken answer will appear here in real-time...</span>`;
    document.getElementById("question-display").textContent = text;

    // Reset filler numbers on UI
    document.querySelectorAll(".filler-badge .badge-num").forEach(b => b.textContent = "0");
    document.querySelectorAll(".filler-badge").forEach(b => b.classList.remove("active"));

    // Set speaking state
    setInterviewerState("speaking");
    
    const nextBtn = document.getElementById("next-btn");
    const nextText = document.getElementById("next-btn-text");
    nextBtn.disabled = true;
    nextText.textContent = "Interviewer speaking...";

    // Play interviewer audio
    await speakInterviewerQuestion(text);

    // Re-enable mic for candidate
    if (localStream) {
        const audioTrack = localStream.getAudioTracks()[0];
        if (audioTrack) audioTrack.enabled = true;
    }
    
    // Play Turn Beep notifying the candidate it is their turn!
    playTurnBeep(true);

    // Re-enable primary action button for manual override
    nextBtn.disabled = false;
    nextText.textContent = "Done Speaking / Send";

    // Set starting timestamp for telemetry
    questionStartTime = Date.now();
    
    // Start Speech Recognition
    if (speechRecognitionObj) {
        try {
            speechRecognitionObj.start();
        } catch (e) {}
    }
}

async function speakInterviewerQuestion(text) {
    isInterviewerSpeaking = true;
    
    // Try to synthesize via ElevenLabs backend
    showLoadingSpeechIndicator(true);

    try {
        const response = await fetch("/api/synthesize-voice", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                text: text,
                persona: activePersona
            })
        });

        if (response.ok) {
            // Check if backend returned JSON fallback flag
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.includes("application/json")) {
                const fallbackData = await response.json();
                if (fallbackData.fallback) {
                    await playBrowserSpeechSynthesis(text);
                }
            } else {
                // ElevenLabs returned audio bytes stream
                const audioBlob = await response.blob();
                const audioUrl = URL.createObjectURL(audioBlob);
                await playAudioStream(audioUrl);
            }
        } else {
            await playBrowserSpeechSynthesis(text);
        }
    } catch (e) {
        console.error("Synthesizer error:", e);
        await playBrowserSpeechSynthesis(text);
    } finally {
        showLoadingSpeechIndicator(false);
        isInterviewerSpeaking = false;
    }
}

// Play binary voice stream with lip sync bars
function playAudioStream(url) {
    return new Promise((resolve) => {
        audioPlayer.src = url;
        audioPlayer.play();

        // Waveform visualization for speaking interviewer
        setupInterviewerAudioWave();

        audioPlayer.onended = () => {
            resolve();
        };

        audioPlayer.onerror = () => {
            resolve();
        };
    });
}

// Fallback: browser local speech synthesis
function playBrowserSpeechSynthesis(text) {
    return new Promise((resolve) => {
        if (!window.speechSynthesis) {
            resolve();
            return;
        }

        // Stop current speaking
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        
        // Pick optimal browser voice
        const voices = window.speechSynthesis.getVoices();
        
        // Set parameters based on persona guidelines
        if (activePersona === "alex") {
            // Direct, faster-paced, male profile
            utterance.rate = 1.15;
            utterance.pitch = 0.9;
            const maleVoice = voices.find(v => v.lang.startsWith("en") && v.name.toLowerCase().includes("male") || v.name.toLowerCase().includes("google uk english male"));
            if (maleVoice) utterance.voice = maleVoice;
        } else if (activePersona === "sarah") {
            // Warm, encouraging, female profile
            utterance.rate = 0.95;
            utterance.pitch = 1.05;
            const femaleVoice = voices.find(v => v.lang.startsWith("en") && (v.name.toLowerCase().includes("female") || v.name.toLowerCase().includes("rachel") || v.name.toLowerCase().includes("samantha") || v.name.toLowerCase().includes("google us english")));
            if (femaleVoice) utterance.voice = femaleVoice;
        } else if (activePersona === "marcus") {
            // Calm, deliberate, high-stakes authority male
            utterance.rate = 0.85;
            utterance.pitch = 0.75;
            const deepVoice = voices.find(v => v.lang.startsWith("en") && v.name.toLowerCase().includes("daniel") || v.name.toLowerCase().includes("premium male"));
            if (deepVoice) utterance.voice = deepVoice;
        }

        // Simulate frequency lipsync bar pulsing during browser reading
        let simulateSpeechInterval = setInterval(() => {
            if (window.speechSynthesis.speaking) {
                const pulse = Math.random() * 40 + 10;
                pulseLipsyncIndicator(pulse);
            } else {
                clearInterval(simulateSpeechInterval);
                pulseLipsyncIndicator(0);
            }
        }, 100);

        utterance.onend = () => {
            clearInterval(simulateSpeechInterval);
            pulseLipsyncIndicator(0);
            resolve();
        };

        utterance.onerror = () => {
            clearInterval(simulateSpeechInterval);
            pulseLipsyncIndicator(0);
            resolve();
        };

        window.speechSynthesis.speak(utterance);
    });
}

function showLoadingSpeechIndicator(show) {
    const avatarRing = document.getElementById("avatar-ring");
    if (show) {
        avatarRing.classList.add("animate-pulse");
    } else {
        avatarRing.classList.remove("animate-pulse");
    }
}

function pulseLipsyncIndicator(amplitude) {
    const lipSync = document.getElementById("lipsync-indicator");
    const avatarRing = document.getElementById("avatar-ring");
    
    // Scale bar horizontally
    lipSync.style.transform = `scaleX(${1 + amplitude / 20})`;
    
    // Add pulsing border glow based on amplitude
    avatarRing.style.boxShadow = `0 0 ${15 + amplitude * 0.4}px var(--neon-cyan-glow)`;
}

// Analyser drawing waves for interviewer speaking
function setupInterviewerAudioWave() {
    const canvas = document.getElementById("interviewer-audio-wave");
    if (!canvas) return;
    const canvasCtx = canvas.getContext("2d");

    if (!interviewerAudioContext) {
        interviewerAudioContext = new (window.AudioContext || window.webkitAudioContext)();
        interviewerAnalyser = interviewerAudioContext.createAnalyser();
        interviewerAnalyser.fftSize = 64;
        interviewerSource = interviewerAudioContext.createMediaElementSource(audioPlayer);
        interviewerSource.connect(interviewerAnalyser);
        interviewerAnalyser.connect(interviewerAudioContext.destination);
    }

    const bufferLength = interviewerAnalyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function drawInterviewerWave() {
        if (!isInterviewerSpeaking) {
            pulseLipsyncIndicator(0);
            return;
        }
        requestAnimationFrame(drawInterviewerWave);

        interviewerAnalyser.getByteFrequencyData(dataArray);

        const width = canvas.width = canvas.clientWidth;
        const height = canvas.height = canvas.clientHeight;

        canvasCtx.clearRect(0, 0, width, height);

        // Compute average amplitude for lip sync
        let totalAmp = 0;
        const barWidth = (width / bufferLength) * 1.5;
        let barHeight;
        let x = 0;

        canvasCtx.fillStyle = "rgba(0, 240, 255, 0.15)";
        canvasCtx.shadowBlur = 6;
        canvasCtx.shadowColor = "var(--neon-cyan-glow)";

        for (let i = 0; i < bufferLength; i++) {
            barHeight = dataArray[i] / 2;
            totalAmp += dataArray[i];

            // Render spectrum bars growing from center vertical axis
            canvasCtx.fillRect(x, height / 2 - barHeight / 2, barWidth - 2, barHeight);

            x += barWidth + 1;
        }

        const avgAmp = totalAmp / bufferLength;
        pulseLipsyncIndicator(avgAmp);
    }

    drawInterviewerWave();
}

// 11. INTERVIEW STEPS HANDLERS
async function handleAnswerCompleted() {
    // 1. Temporarily mute user mic and stop speech recognition
    if (localStream) {
        const audioTrack = localStream.getAudioTracks()[0];
        if (audioTrack) audioTrack.enabled = false;
    }
    if (speechRecognitionObj) {
        try {
            speechRecognitionObj.stop();
        } catch (e) {}
    }
    
    // Play Submit Beep
    playTurnBeep(false);

    // 2. Set AI state to "thinking" (yellow active status glow)
    setInterviewerState("thinking");
    const nextBtn = document.getElementById("next-btn");
    const nextText = document.getElementById("next-btn-text");
    nextBtn.disabled = true;
    nextText.textContent = "Processing response...";

    // 3. Capture metrics of answered question
    const elapsedSeconds = questionStartTime ? (Date.now() - questionStartTime) / 1000.0 : 60;
    const words = currentAnswerTranscript.trim().split(/\s+/).filter(w => w.length > 0);
    const wordCount = words.length;
    const wpm = elapsedSeconds > 0 ? Math.round(wordCount / (elapsedSeconds / 60.0)) : 140;

    const avgEyeContact = currentEyeContactScores.length > 0 
        ? Math.round(currentEyeContactScores.reduce((a, b) => a + b, 0) / currentEyeContactScores.length)
        : 90;

    // Record this turn in the candidate metrics list
    sessionQuestionsAnswered.push({
        question: lastQuestionAsked,
        focus: interviewQuestions[Math.min(currentStage - 1, 3)]?.focus || "communication",
        transcript: currentAnswerTranscript || "[No vocal answer recorded]",
        wpm: wpm,
        filler_count: Object.values(currentFillerCounts).reduce((a, b) => a + b, 0),
        eye_contact_score: avgEyeContact
    });

    // 4. Append transcript to conversation history
    const candidateAnswerText = currentAnswerTranscript || "[No vocal response]";
    conversationHistory.push({ role: "candidate", text: candidateAnswerText });

    // 5. Send to backend conversational-turn API
    try {
        const response = await fetch("/api/conversational-turn", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                candidate_email: candidateEmail,
                target_role: targetRole || "Software Engineer Intern",
                resume_text: resumeText || "[No resume uploaded. Generic Software Engineer profile]",
                job_description: jobDescription,
                history: conversationHistory,
                current_stage: currentStage,
                custom_questions: customQuestions
            })
        });

        if (response.ok) {
            const turnData = await response.json();
            
            // Advance stage
            currentStage = turnData.next_stage;
            
            // Acknowledge new interviewer reply
            const nextInterviewerText = turnData.response_text;
            lastQuestionAsked = nextInterviewerText;
            conversationHistory.push({ role: "interviewer", text: nextInterviewerText });

            if (turnData.is_final) {
                // If it is final, speak the wrap up question and then immediately generate report!
                setInterviewerState("speaking");
                nextText.textContent = "Concluding Interview...";
                document.getElementById("question-display").textContent = nextInterviewerText;
                await speakInterviewerQuestion(nextInterviewerText);
                finishAndEvaluate();
            } else {
                // Trigger the next question load
                loadConversationalQuestion(nextInterviewerText);
            }
        } else {
            alert("Error in conversational agent turn.");
            // Graceful fallback to advance stages manually
            currentStage = Math.min(currentStage + 1, 4);
            const mockQs = interviewQuestions[currentStage - 1];
            if (mockQs) {
                loadConversationalQuestion(mockQs.question);
            } else {
                finishAndEvaluate();
            }
        }
    } catch (err) {
        console.error("Conversational turn error:", err);
        finishAndEvaluate();
    }
}

// Trigger evaluation
async function finishAndEvaluate() {
    // If the candidate clicks "End & Evaluate" before completing the loop,
    // push the current active answer into the queue
    const words = currentAnswerTranscript.trim().split(/\s+/).filter(w => w.length > 0);
    if (words.length > 0 && sessionQuestionsAnswered.length < conversationHistory.length / 2) {
        const elapsedSeconds = questionStartTime ? (Date.now() - questionStartTime) / 1000.0 : 60;
        const avgEye = currentEyeContactScores.length > 0 
            ? Math.round(currentEyeContactScores.reduce((a, b) => a + b, 0) / currentEyeContactScores.length)
            : 90;
        
        sessionQuestionsAnswered.push({
            question: lastQuestionAsked,
            focus: interviewQuestions[Math.min(currentStage - 1, 3)]?.focus || "communication",
            transcript: currentAnswerTranscript || "[Interview terminated early by candidate]",
            wpm: elapsedSeconds > 0 ? Math.round(words.length / (elapsedSeconds / 60.0)) : 140,
            filler_count: Object.values(currentFillerCounts).reduce((a, b) => a + b, 0),
            eye_contact_score: avgEye
        });
    }

    stopMediaStreams();
    showLoading("EVALUATING YOUR INTERVIEW SESSION...");

    try {
        const response = await fetch("/api/evaluate-session", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                candidate_email: candidateEmail,
                target_role: targetRole || "Software Engineer Intern",
                questions_answered: sessionQuestionsAnswered
            })
        });

        const data = await response.json();
        hideLoading();

        if (response.ok) {
            renderScorecardReport(data);
            transitionScreen("report-screen");
        } else {
            alert("Failed to compute scorecard: " + data.detail);
        }
    } catch (err) {
        hideLoading();
        console.error("Evaluation error:", err);
        alert("An error occurred during response grading.");
    }
}

// 12. RENDER SCORECARD REPORT
let lastReportData = null; // Store reports globally to trigger webhook export later

function renderScorecardReport(report) {
    lastReportData = report;

    // Header values
    document.getElementById("report-role-label").textContent = targetRole || "Software Engineer";
    document.getElementById("report-email-label").textContent = candidateEmail;

    // Set Scores
    document.getElementById("report-overall-score").textContent = report.readiness_score;
    document.getElementById("report-jd-match").textContent = `${report.jd_match_percent}%`;

    // Radial animations
    const overallCircle = document.getElementById("overall-score-circle");
    const jdCircle = document.getElementById("jd-score-circle");

    // Circle dash calculations: radius 42 has circumference of 263.89
    const overallDash = (report.readiness_score / 100) * 263.89;
    const jdDash = (report.jd_match_percent / 100) * 263.89;

    overallCircle.setAttribute("stroke-dasharray", `${overallDash}, 263.89`);
    jdCircle.setAttribute("stroke-dasharray", `${jdDash}, 263.89`);

    // Render Strengths
    const strengthsContainer = document.getElementById("report-strengths");
    strengthsContainer.innerHTML = "";
    report.key_strengths.forEach(str => {
        const li = document.createElement("li");
        li.textContent = str;
        strengthsContainer.appendChild(li);
    });

    // Render Areas to Improve
    const redflagsContainer = document.getElementById("report-redflags");
    redflagsContainer.innerHTML = "";
    report.areas_to_improve.forEach(flag => {
        const li = document.createElement("li");
        li.textContent = flag;
        redflagsContainer.appendChild(li);
    });

    // STAR Progress bars
    document.getElementById("star-sit-val").textContent = `${report.rubric.situation_task_clarity}%`;
    document.getElementById("star-sit-bar").style.width = `${report.rubric.situation_task_clarity}%`;

    document.getElementById("star-act-val").textContent = `${report.rubric.action_specifics}%`;
    document.getElementById("star-act-bar").style.width = `${report.rubric.action_specifics}%`;

    document.getElementById("star-res-val").textContent = `${report.rubric.result_impact}%`;
    document.getElementById("star-res-bar").style.width = `${report.rubric.result_impact}%`;

    // Core Competencies progress bars
    const comps = report.competency_scores || { technical_articulation: 80, structured_delivery: 75, vocal_telemetry: 70, visual_presence: 90 };
    document.getElementById("comp-tech-val").textContent = `${comps.technical_articulation}%`;
    document.getElementById("comp-tech-bar").style.width = `${comps.technical_articulation}%`;

    document.getElementById("comp-struct-val").textContent = `${comps.structured_delivery}%`;
    document.getElementById("comp-struct-bar").style.width = `${comps.structured_delivery}%`;

    document.getElementById("comp-vocal-val").textContent = `${comps.vocal_telemetry}%`;
    document.getElementById("comp-vocal-bar").style.width = `${comps.vocal_telemetry}%`;

    document.getElementById("comp-visual-val").textContent = `${comps.visual_presence}%`;
    document.getElementById("comp-visual-bar").style.width = `${comps.visual_presence}%`;

    // Render Development Plan with checkboxes
    const devPlanContainer = document.getElementById("report-dev-plan");
    devPlanContainer.innerHTML = "";
    const devPlan = report.development_plan || [];
    devPlan.forEach((task, idx) => {
        const li = document.createElement("li");
        li.style.display = "flex";
        li.style.alignItems = "flex-start";
        li.style.gap = "8px";
        li.style.marginBottom = "8px";
        
        li.innerHTML = `
            <input type="checkbox" id="task-${idx}" style="accent-color: var(--success-green); margin-top: 4px; cursor: pointer;">
            <label for="task-${idx}" style="cursor: pointer; line-height: 1.4; color: var(--text-muted); font-size: 12px;">${task}</label>
        `;
        devPlanContainer.appendChild(li);
    });

    // Render Filler Diagnostics Critique Cards
    const fillerDiagContainer = document.getElementById("report-filler-diag-container");
    fillerDiagContainer.innerHTML = "";
    const diagnostics = report.filler_diagnostics || {};
    Object.entries(diagnostics).forEach(([word, advice]) => {
        const div = document.createElement("div");
        div.className = "response-box";
        div.style.margin = "0";
        div.style.padding = "12px";
        div.style.borderLeft = "3px solid var(--neon-cyan)";
        div.style.backgroundColor = "rgba(0, 240, 255, 0.03)";
        
        div.innerHTML = `
            <span class="box-title" style="color: var(--neon-cyan); text-transform: uppercase; font-size: 9px; letter-spacing: 0.05em; display: block; margin-bottom: 4px;">"${word}" Tic Advice</span>
            <p style="margin: 0; font-size: 11px; line-height: 1.4; color: var(--text-primary);">${advice}</p>
        `;
        fillerDiagContainer.appendChild(div);
    });

    // Expandable audit cards list (Questions response analysis)
    const auditContainer = document.getElementById("report-questions-list");
    auditContainer.innerHTML = "";

    report.questions.forEach((item, idx) => {
        const auditCard = document.createElement("div");
        auditCard.className = `audit-card ${idx === 0 ? "expanded" : ""}`;

        auditCard.innerHTML = `
            <div class="audit-header" onclick="toggleAuditCard(this)">
                <span class="audit-q-text font-mono">Q${idx+1}: ${item.question}</span>
                <div class="audit-meta-badges">
                    <span class="audit-score-badge">STAR: ${item.star_score}/100</span>
                    <i data-lucide="chevron-down" class="audit-arrow"></i>
                </div>
            </div>
            <div class="audit-body">
                <div class="response-split">
                    <div class="response-box">
                        <span class="box-title">Your Response</span>
                        <p class="box-content">${item.transcript}</p>
                        <div class="telemetry-bar-text font-mono" style="margin-top:10px; font-size:10px; color:var(--text-muted);">
                            PACE: ${item.wpm} WPM | FILLERS: ${item.fillers} | FOCUS: ${item.focus_score}%
                        </div>
                    </div>
                    <div class="response-box gold">
                        <span class="box-title"><i data-lucide="star" class="text-green" style="width:12px;height:12px;display:inline;"></i> Gold Standard STAR Response</span>
                        <p class="box-content">${item.gold_standard_response}</p>
                    </div>
                </div>
                <div class="audit-feedback">
                    <span class="box-title text-amber">Interviewer Feedback</span>
                    <p>${item.feedback}</p>
                </div>
            </div>
        `;

        auditContainer.appendChild(auditCard);
    });

    // Render JD Keywords Match Audit List
    const keywordsListContainer = document.getElementById("report-keywords-list");
    keywordsListContainer.innerHTML = "";
    const keywordsAnalysis = report.jd_keywords_analysis || [];
    keywordsAnalysis.forEach(item => {
        const div = document.createElement("div");
        div.className = "response-box";
        div.style.margin = "0";
        div.style.padding = "14px";
        
        const isMatched = item.status === "matched";
        const borderColor = isMatched ? "var(--success-green)" : "var(--error-red)";
        const labelClass = isMatched ? "success-green" : "error-red";
        const statusLabel = isMatched ? "SPOKEN" : "MISSING";
        
        div.style.borderLeft = `3px solid ${borderColor}`;
        div.style.backgroundColor = isMatched ? "rgba(0, 229, 153, 0.03)" : "rgba(255, 77, 77, 0.03)";
        
        div.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-weight: bold; font-size: 13px; color: var(--text-primary);">${item.keyword}</span>
                <span class="badge ${labelClass}" style="font-size: 9px; padding: 1px 6px;">${statusLabel}</span>
            </div>
            <p style="margin: 0; font-size: 11px; line-height: 1.4; color: var(--text-muted);">${item.context}</p>
        `;
        keywordsListContainer.appendChild(div);
    });

    // Make sure panel is collapsed initially
    document.getElementById("keywords-audit-panel").style.display = "none";

    lucide.createIcons();
    document.getElementById("webhook-status-msg").textContent = ""; // Clear webhook status
    
    const emailStatus = document.getElementById("email-status-msg");
    if (emailStatus) {
        if (report.smtp_configured) {
            emailStatus.textContent = `✓ Scorecard successfully emailed to ${candidateEmail}`;
            emailStatus.style.color = "var(--success-green)";
        } else {
            emailStatus.textContent = `⚠️ Email dispatch skipped: SMTP credentials not set on server. Setup SMTP_SERVER, SMTP_USERNAME, and SMTP_PASSWORD in terminal.`;
            emailStatus.style.color = "var(--alert-amber)";
        }
    }
}

// Toggle Collapsible Keywords Audit Panel
window.toggleKeywordsAudit = function() {
    const panel = document.getElementById("keywords-audit-panel");
    if (!panel) return;
    if (panel.style.display === "none") {
        panel.style.display = "block";
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
        panel.style.display = "none";
    }
};

// Collapsible helper for cards
window.toggleAuditCard = function(headerElement) {
    const card = headerElement.parentElement;
    card.classList.toggle("expanded");
};

// 13. DISPATCH WEBHOOK TO N8N WORKFLOW
async function dispatchWebhookToN8N() {
    if (!lastReportData) return;

    const statusMsg = document.getElementById("webhook-status-msg");
    const btn = document.getElementById("webhook-trigger-btn");

    statusMsg.textContent = "SENDING TO N8N...";
    statusMsg.className = "font-mono hud-sub-label text-cyan animate-pulse";
    btn.disabled = true;

    try {
        const response = await fetch("/api/evaluate-session?trigger_webhook=true", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                candidate_email: candidateEmail,
                target_role: targetRole || "Software Engineer Intern",
                questions_answered: sessionQuestionsAnswered
            })
        });

        const status = await response.json();
        
        btn.disabled = false;
        
        if (response.ok) {
            statusMsg.textContent = "SUCCESS // report_emailed";
            statusMsg.className = "font-mono hud-sub-label text-green";
        } else {
            statusMsg.textContent = "ERROR // dispatch_failed";
            statusMsg.className = "font-mono hud-sub-label text-red";
        }
    } catch (err) {
        btn.disabled = false;
        statusMsg.textContent = "DISPATCH FAILED";
        statusMsg.className = "font-mono hud-sub-label text-red";
        console.error("Webhook dispatch error:", err);
    }
}

// 14. MEDIA TOGGLES HELPERS
function toggleMicrophone() {
    if (!localStream) return;
    const audioTrack = localStream.getAudioTracks()[0];
    const micBtn = document.getElementById("toggle-mic");

    if (audioTrack.enabled) {
        audioTrack.enabled = false;
        isMicMuted = true;
        micBtn.classList.remove("active");
        micBtn.classList.add("muted");
        
        // Pause local speech recognition
        if (speechRecognitionObj) {
            try {
                speechRecognitionObj.stop();
            } catch (e) {}
        }
    } else {
        audioTrack.enabled = true;
        isMicMuted = false;
        micBtn.classList.add("active");
        micBtn.classList.remove("muted");
        
        // Resume local speech recognition
        if (speechRecognitionObj) {
            try {
                speechRecognitionObj.start();
            } catch (e) {}
        }
    }
}

function toggleCamera() {
    if (!localStream) return;
    const videoTrack = localStream.getVideoTracks()[0];
    const camBtn = document.getElementById("toggle-cam");

    if (videoTrack.enabled) {
        videoTrack.enabled = false;
        isCamOff = true;
        camBtn.classList.remove("active");
        camBtn.classList.add("muted");
    } else {
        videoTrack.enabled = true;
        isCamOff = false;
        camBtn.classList.add("active");
        camBtn.classList.remove("muted");
    }
}

// Loading overlay helpers
function showLoading(msg) {
    document.getElementById("loading-msg").textContent = msg;
    document.getElementById("loading-overlay").classList.add("active");
}

function hideLoading() {
    document.getElementById("loading-overlay").classList.remove("active");
}
