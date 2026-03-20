/**
 * Scanner de QR y Códigos de Barras para Mercado Envíos
 */

// Variables de estado
let html5QrCode = null;
let isScanning = false;
let isReturnscanMode = false;  // Modo escaneo de devoluciones
let lastScannedCode = null;
let lastScanTime = 0;
const DUPLICATE_THRESHOLD = 5000; // 5 segundos para evitar duplicados

// Contadores de sesión — arrancan con los valores actuales del día (desde la BD via Django)
const sessionCounters = {
    cambios: parseInt(document.getElementById('counter-cambios')?.textContent || '0', 10),
    particulares: parseInt(document.getElementById('counter-particulares')?.textContent || '0', 10)
};

function incrementCounter(tipo) {
    const t = (tipo || '').toUpperCase();
    if (t === 'CAMBIO') {
        sessionCounters.cambios++;
    } else if (t === 'PARTICULAR') {
        sessionCounters.particulares++;
    } else {
        return; // No es un tipo que necesitamos contar
    }
    // Actualizar DOM
    const elCambios = document.getElementById('counter-cambios');
    const elParticulares = document.getElementById('counter-particulares');
    const elTotal = document.getElementById('counter-total-mensajeria');
    if (elCambios) elCambios.textContent = sessionCounters.cambios;
    if (elParticulares) elParticulares.textContent = sessionCounters.particulares;
    if (elTotal) elTotal.textContent = sessionCounters.cambios + sessionCounters.particulares;
}

// Elementos DOM
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const scanStatus = document.getElementById('scan-status');
const resultContainer = document.getElementById('result-container');
const noResult = document.getElementById('no-result');
const apiDataEl = document.getElementById('api-data');
const userPicker = document.getElementById('user-picker');

// Web Audio API Context
let audioCtx = null;

function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
}

function playBeep(type) {
    initAudio();
    const osc = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();

    osc.connect(gainNode);
    gainNode.connect(audioCtx.destination);

    if (type === 'success') {
        // Sonido de VIGENTE: "Ding" agudo y placentero
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1000, audioCtx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(600, audioCtx.currentTime + 0.1);
        gainNode.gain.setValueAtTime(0.2, audioCtx.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.1);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.1);
    } else {
        // Sonido de CANCELADO/ERROR: "Buzzer" grave y largo
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(150, audioCtx.currentTime);
        osc.frequency.linearRampToValueAtTime(100, audioCtx.currentTime + 0.4);

        // Modulación de volumen para efecto "áspero"
        gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime);
        gainNode.gain.linearRampToValueAtTime(0.3, audioCtx.currentTime + 0.3);
        gainNode.gain.linearRampToValueAtTime(0.01, audioCtx.currentTime + 0.4);

        osc.start();
        osc.stop(audioCtx.currentTime + 0.4);
    }
}

// Elementos del Overlay
const overlay = document.getElementById('scan-overlay');
const overlayIcon = document.getElementById('overlay-icon');
const overlayText = document.getElementById('overlay-text');
const overlaySubtext = document.getElementById('overlay-subtext');

// Event Listeners
userPicker.addEventListener('change', () => {
    startBtn.disabled = !userPicker.value;
    const scanReturnBtn = document.getElementById('scanReturnBtn');
    if (scanReturnBtn) scanReturnBtn.disabled = !userPicker.value;
});

startBtn.addEventListener('click', () => {
    initAudio(); // Desbloquear audio con interacción del usuario
    startScanner();
});

stopBtn.addEventListener('click', stopScanner);

const scanReturnBtn = document.getElementById('scanReturnBtn');
if (scanReturnBtn) {
    console.log('✅ scanReturnBtn encontrado, agregando listener...');
    scanReturnBtn.addEventListener('click', () => {
        console.log('🔄 Botón "Escanear Regreso" presionado');
        initAudio(); // Desbloquear audio con interacción del usuario
        startReturnScanner();
    });
} else {
    console.warn('⚠️ scanReturnBtn NO encontrado en el DOM');
}

document.querySelectorAll('.history-item').forEach(item => {
    item.addEventListener('click', () => loadScanDetail(item.dataset.id));
});

// Funciones del Scanner
async function startScanner() {
    if (!userPicker.value) {
        showError('Por favor selecciona quién está escaneando');
        playBeep('error');
        return;
    }

    try {
        html5QrCode = new Html5Qrcode("reader");
        const config = {
            fps: 10,
            qrbox: { width: 250, height: 250 },
            formatsToSupport: [
                Html5QrcodeSupportedFormats.QR_CODE,
                Html5QrcodeSupportedFormats.CODE_128,
                Html5QrcodeSupportedFormats.CODE_39,
                Html5QrcodeSupportedFormats.EAN_13,
                Html5QrcodeSupportedFormats.EAN_8,
                Html5QrcodeSupportedFormats.UPC_A,
                Html5QrcodeSupportedFormats.CODABAR,
                Html5QrcodeSupportedFormats.ITF
            ]
        };

        await html5QrCode.start(
            { facingMode: "environment" },
            config,
            onScanSuccess,
            () => { }
        );

        isScanning = true;
        startBtn.disabled = true;
        stopBtn.disabled = false;
        userPicker.disabled = true;
        updateStatus('scanning', `🔍 Escaneando como ${userPicker.value}...`);

        // Limpiar estado
        hideOverlay();

    } catch (err) {
        console.error('Error:', err);
        showError('No se pudo acceder a la cámara. Verifica los permisos.');
    }
}

async function stopScanner() {
    if (html5QrCode && isScanning) {
        await html5QrCode.stop();
        html5QrCode.clear();
        isScanning = false;
        isReturnscanMode = false;
        startBtn.disabled = !userPicker.value;
        stopBtn.disabled = true;
        const scanReturnBtn = document.getElementById('scanReturnBtn');
        if (scanReturnBtn) scanReturnBtn.disabled = !userPicker.value;
        userPicker.disabled = false;
        updateStatus('', 'Scanner detenido');
    }
}

// Helper para determinar si está cancelado
function isCancelledScan(apiData) {
    if (!apiData) return true;

    if (apiData.is_logistics) {
        const status = apiData.status || 'NO VIGENTE';
        return status !== 'VIGENTE';
    } else {
        if (apiData.order?.status === 'cancelled') return true;
        if (apiData.shipment?.status === 'cancelled') return true;
        if (apiData.shipment?.substatus === 'cancelled') return true;
        return false;
    }
}

async function onScanSuccess(decodedText) {
    // Ignorar si estamos en modo de escaneo de devoluciones
    if (isReturnscanMode) return;

    // Prevención de duplicados inmediata
    const now = Date.now();
    if (decodedText === lastScannedCode && (now - lastScanTime < DUPLICATE_THRESHOLD)) {
        return; // Ignorar escaneo duplicado reciente
    }

    // Actualizar timestamp
    lastScannedCode = decodedText;
    lastScanTime = now;

    // Pausar scanner visualmente
    if (html5QrCode) await html5QrCode.pause();
    updateStatus('success', '⏳ Procesando...');

    try {
        const response = await fetch('/api/scan/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                qr_data: decodedText,
                scanner_user: userPicker.value
            })
        });

        const data = await response.json();

        if (data.success) {
            const apiData = data.api_data;

            // DETECTAR DUPLICADO PRIMERO
            if (data.duplicate === true || (apiData && apiData.is_duplicate === true)) {
                playBeep('error'); // Sonido de advertencia
                updateStatus('warning', '⚠️ YA ESCANEADO');

                // Mostrar overlay de duplicado con fecha/info del escaneo anterior
                // Normalizar previous_scan_date: puede venir en data o dentro de api_data
                const previousDate = data.previous_scan_date || (apiData && apiData.previous_scan_date) || 'Fecha desconocida';
                const overlayApiData = apiData || {};
                overlayApiData.previous_scan_date = previousDate;
                showOverlayDuplicate(overlayApiData, previousDate);
                addToHistory(data);
            } else {
                // No es duplicado - mostrar resultado normal
                // Determinar si es un éxito "VIGENTE", "CANCELADO" o "DEVOLUCION"
                const statusType = apiData.status_type; // Nuevo campo del backend (preferido)

                // Fallback para backward compatibility
                const isCancelled = isCancelledScan(apiData);

                if (statusType === 'CANCELADO' || (statusType === undefined && isCancelled)) {
                    playBeep('error');
                    updateStatus('error', '❌ SCAN CANCELADO');
                } else if (statusType === 'DEVOLUCION') {
                    playBeep('error'); // Usar sonido de alerta/error para devoluciones también
                    updateStatus('warning', '↩️ DEVOLUCIÓN');
                } else {
                    playBeep('success');
                    updateStatus('success', '✅ SCAN VIGENTE');
                }

                showOverlayResult(data.api_data);
                addToHistory(data);

                // Actualizar contadores de CAMBIO / PARTICULAR si aplica
                if (apiData && apiData.is_logistics && apiData.tipo) {
                    incrementCounter(apiData.tipo);
                }
            }

        } else {
            playBeep('error');
            showOverlayError(data.error);
            updateStatus('error', '❌ Error en escaneo');
        }
    } catch (error) {
        console.error('Error:', error);
        playBeep('error');
        showOverlayError('Error de red');
    }

    // Reanudar scanner después de un breve delay
    setTimeout(async () => {
        hideOverlay();
        if (html5QrCode && isScanning) {
            try { await html5QrCode.resume(); } catch (e) { }
        }
    }, 2000);
}

// Funciones de UI - Overlay
function showOverlayResult(apiData) {
    const overlay = document.getElementById('scan-overlay');
    if (!overlay) return;

    const overlayContent = document.getElementById('overlay-content');
    const overlayIcon = document.getElementById('overlay-icon');
    const overlayText = document.getElementById('overlay-text');
    const overlaySubtext = document.getElementById('overlay-subtext');

    let statusType = 'VIGENTE';
    let displayStatus = 'VIGENTE';

    // Usar status_type explicito del backend si existe
    if (apiData.status_type) {
        statusType = apiData.status_type;
        displayStatus = apiData.display_status || statusType;
    } else {
        // Fallback logic antigua
        const cancelled = isCancelledScan(apiData);
        if (apiData.is_logistics) {
            const status = apiData.status || 'NO VIGENTE';
            displayStatus = status;
            statusType = isCancelledScan(apiData) ? 'CANCELADO' : 'VIGENTE'; // Aproximado
        } else {
            statusType = cancelled ? 'CANCELADO' : 'VIGENTE';
            displayStatus = statusType;
        }
    }

    // Configurar UI según Status Type
    let color = '#22c55e'; // Green (VIGENTE)
    let icon = '✅';
    let subText = '';

    if (apiData.is_logistics) {
        subText = `${apiData.tipo} - ${apiData.customer_name}`;
        if (statusType === 'CANCELADO') {
            color = '#ef4444';
            icon = '❌';
        }
    } else {
        if (statusType === 'CANCELADO') {
            color = '#ef4444'; // Red
            icon = '❌';
        } else if (statusType === 'DEVOLUCION') {
            color = '#f97316'; // Orange-500
            icon = '↩️';
        }
    }

    overlayContent.style.borderColor = color;
    overlayIcon.textContent = icon;
    overlayText.textContent = displayStatus;
    overlayText.style.color = color;

    overlaySubtext.textContent = subText;
    overlaySubtext.style.color = '#4b5563';

    // Mostrar
    overlay.classList.remove('hidden');
    overlay.style.display = 'flex';
}

function showOverlayError(msg) {
    const overlay = document.getElementById('scan-overlay');
    if (!overlay) return;

    const overlayContent = document.getElementById('overlay-content');
    const overlayIcon = document.getElementById('overlay-icon');
    const overlayText = document.getElementById('overlay-text');
    const overlaySubtext = document.getElementById('overlay-subtext');

    overlayContent.style.borderColor = '#ef4444';
    overlayIcon.innerHTML = '⚠️';
    overlayText.textContent = 'ERROR';
    overlayText.style.color = '#ef4444';

    overlaySubtext.textContent = msg || 'Error desconocido';

    overlay.classList.remove('hidden');
    overlay.style.display = 'flex';
}

function showOverlayDuplicate(apiData, previousDate) {
    const overlay = document.getElementById('scan-overlay');
    if (!overlay) return;

    const overlayContent = document.getElementById('overlay-content');
    const overlayIcon = document.getElementById('overlay-icon');
    const overlayText = document.getElementById('overlay-text');
    const overlaySubtext = document.getElementById('overlay-subtext');

    overlayContent.style.borderColor = '#f59e0b'; // Amber
    overlayIcon.innerHTML = '⚠️';
    overlayText.textContent = 'YA ESCANEADO';
    overlayText.style.color = '#f59e0b';

    // Construir info adicional
    let infoText = `Escaneado: ${previousDate}`;

    // Agregar nombre si está disponible
    if (apiData.buyer_name || apiData.customer_name) {
        const name = apiData.buyer_name || apiData.customer_name;
        infoText += `\n👤 ${name}`;
    }

    // Agregar dirección si está disponible
    if (apiData.address) {
        infoText += `\n📍 ${apiData.address}`;
    }

    // Agregar tipo si es logística
    if (apiData.tipo) {
        infoText += `\n📦 ${apiData.tipo}`;
    }

    overlaySubtext.textContent = infoText;
    overlaySubtext.style.color = '#78350f';
    overlaySubtext.style.whiteSpace = 'pre-line'; // Para que respete los \n

    overlay.classList.remove('hidden');
    overlay.style.display = 'flex';
}

function hideOverlay() {
    const overlay = document.getElementById('scan-overlay');
    if (overlay) {
        overlay.classList.add('hidden');
        overlay.style.display = 'none';
    }
}

// Funciones Auxiliares
function addToHistory(data) {
    const historyList = document.getElementById('history-list');
    const noHistory = historyList.querySelector('.no-history');
    if (noHistory) noHistory.remove();

    const newItem = document.createElement('div');
    newItem.className = 'history-item';
    newItem.dataset.id = data.scan_id;

    const cancelled = isCancelledScan(data.api_data);
    const statusText = cancelled ? 'CANCELADO' : 'VIGENTE';

    // Clases según estado
    const badgeClass = cancelled ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800';

    // Texto adicional Logistica vs ML
    let displayStatus = statusText;
    if (data.api_data && data.api_data.is_logistics) {
        displayStatus = data.api_data.status || 'LOGISTICA';
    }

    newItem.innerHTML = `
        <div class="history-main" style="display:flex; justify-content:space-between; align-items:center; padding:10px; border-bottom:1px solid #eee;">
            <span class="shipment-id font-mono text-sm">${data.shipment_id || 'ID Desconocido'}</span>
            <span class="status-badge px-2 py-1 rounded text-xs font-bold ${badgeClass}">
                ${displayStatus}
            </span>
        </div>
        <div class="history-meta text-xs text-gray-500 px-2 pb-2">
            <span>Hace un momento</span>
        </div>
    `;

    historyList.insertBefore(newItem, historyList.firstChild);
    newItem.style.animation = 'highlight 1s ease';
}

function updateStatus(type, message) {
    scanStatus.className = 'scan-status ' + type;
    scanStatus.querySelector('.status-text').textContent = message;
}

function showError(message) {
    alert(message);
}

// Stub para loadScanDetail
async function loadScanDetail(scanId) {
    console.log("Cargar detalle scan:", scanId);
}

// ========== MODO ESCANEO DE DEVOLUCIONES (RETORNO) ==========
async function startReturnScanner() {
    console.log('📹 startReturnScanner() iniciando...');
    console.log(`  isScanning=${isScanning}, html5QrCode=${!!html5QrCode}`);

    try {
        // Si el scanner normal está activo, detenerlo primero
        if (isScanning && html5QrCode) {
            console.log('🛑 Deteniendo scanner anterior...');
            try {
                await html5QrCode.stop();
            } catch (e) {
                console.warn('Error deteniendo scanner anterior:', e);
            }
        }

        html5QrCode = new Html5Qrcode("reader");
        console.log('✅ Html5Qrcode inicializado');

        const config = {
            fps: 10,
            qrbox: { width: 250, height: 250 },
            formatsToSupport: [
                Html5QrcodeSupportedFormats.QR_CODE,
                Html5QrcodeSupportedFormats.CODE_128,
                Html5QrcodeSupportedFormats.CODE_39,
                Html5QrcodeSupportedFormats.EAN_13,
                Html5QrcodeSupportedFormats.EAN_8,
                Html5QrcodeSupportedFormats.UPC_A,
                Html5QrcodeSupportedFormats.CODABAR,
                Html5QrcodeSupportedFormats.ITF
            ]
        };

        console.log('📹 Iniciando cámara...');
        await html5QrCode.start(
            { facingMode: "environment" },
            config,
            onReturnScanSuccess,
            () => { }
        );

        console.log('✅ Cámara iniciada exitosamente');

        isScanning = true;
        isReturnscanMode = true;
        startBtn.disabled = true;
        stopBtn.disabled = false;
        const scanReturnBtn = document.getElementById('scanReturnBtn');
        if (scanReturnBtn) scanReturnBtn.disabled = true;
        userPicker.disabled = true;
        updateStatus('scanning', '🔄 Escaneando regreso/devolución...');
        hideOverlay();

    } catch (err) {
        console.error('❌ Error en startReturnScanner:', err);
        console.error(err.stack);
        showError('No se pudo acceder a la cámara. Verifica los permisos.');
    }
}

async function onReturnScanSuccess(decodedText) {
    // Prevención de duplicados inmediata (sin duplicate flag)
    const now = Date.now();
    if (decodedText === lastScannedCode && (now - lastScanTime < DUPLICATE_THRESHOLD)) {
        return; // Ignorar escaneo duplicado reciente
    }

    // Actualizar timestamp
    lastScannedCode = decodedText;
    lastScanTime = now;

    // Pausar scanner visualmente
    if (html5QrCode) await html5QrCode.pause();
    updateStatus('success', '⏳ Procesando devolución...');

    try {
        // Enviar al endpoint de marcar como entregado (sin crear Scan)
        const response = await fetch('/api/scan/mark_return_complete/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                shipment_id: decodedText.trim()
            })
        });

        const data = await response.json();

        if (data.success) {
            playBeep('success');
            updateStatus('success', '✅ REGRESO MARCADO');

            // Mostrar overlay de éxito
            const overlay = document.getElementById('scan-overlay');
            if (overlay) {
                const overlayContent = document.getElementById('overlay-content');
                const overlayIcon = document.getElementById('overlay-icon');
                const overlayText = document.getElementById('overlay-text');
                const overlaySubtext = document.getElementById('overlay-subtext');

                overlayContent.style.borderColor = '#10b981';  // Green
                overlayIcon.innerHTML = '✅';
                overlayText.textContent = 'ENTREGADO EN EMPRESA';
                overlayText.style.color = '#10b981';
                overlaySubtext.textContent = `Envío: ${decodedText.trim()}`;
                overlaySubtext.style.color = '#4b5563';

                overlay.classList.remove('hidden');
                overlay.style.display = 'flex';
            }
        } else {
            playBeep('error');
            updateStatus('error', '❌ No encontrado');

            // Mostrar overlay de error
            const overlay = document.getElementById('scan-overlay');
            if (overlay) {
                const overlayContent = document.getElementById('overlay-content');
                const overlayIcon = document.getElementById('overlay-icon');
                const overlayText = document.getElementById('overlay-text');
                const overlaySubtext = document.getElementById('overlay-subtext');

                overlayContent.style.borderColor = '#ef4444';  // Red
                overlayIcon.innerHTML = '⚠️';
                overlayText.textContent = 'NO ENCONTRADO';
                overlayText.style.color = '#ef4444';
                overlaySubtext.textContent = `${data.error || 'No se encontró en Pendientes de devolución'}`;
                overlaySubtext.style.color = '#78350f';

                overlay.classList.remove('hidden');
                overlay.style.display = 'flex';
            }
        }
    } catch (error) {
        console.error('Error:', error);
        playBeep('error');
        updateStatus('error', '❌ Error de red');
    }

    // Reanudar scanner después de un breve delay (mostrar overlay durante 2 segundos)
    setTimeout(async () => {
        hideOverlay();
        if (html5QrCode && isReturnscanMode) {
            try {
                await html5QrCode.resume();
            } catch (e) {
                console.warn('Error reanudando scanner:', e);
            }
        }
    }, 2000);
}
